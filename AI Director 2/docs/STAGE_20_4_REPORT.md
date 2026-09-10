# Stage 20.4 — Диагностика веб-аудита и ReplayBundle (только отчёт, без исправлений)

Ничего не исправлено и не рефакторено. Только исследование.

## 1. Фактический маршрут `/audit`

`apps/api/main.py` (стр. 202–226):
- `@app.get("/audit/{account_id}")` → `run_audit(account_id, date, data_origin="real_wb_data")`
- `data_origin` передаётся прямо в `auditor.audit(...)` (стр. 218–223)
- `auditor` создаётся в `_default_audit_service()` (стр. 282–300): `CabinetAuditor` с `SQLiteRawObjectRepository`, `DailyAnalysisService`, `WBDailyIngestionService` (legacy loader), `WBFinanceDetailIngestionService` (legacy transport)
- Нет никакой ветви для `replay`/`offline`; единственный ключ — `data_origin`, и единственное разрешённое значение в `CabinetAuditor.audit()` (audit.py стр. 189): `{"real_wb_data", "test_fixture"}`.

## 2. Поведение `data_origin`

- Поддерживается: `real_wb_data` (по умолчанию) и `test_fixture`.
- `real_wb_data` означает: `_run_ingestion()` вызывает `daily_ingestion.ingest()` и `finance_detail_ingestion.ingest()` → каждый из которых вызывает `LegacyWBApiLoadersTransport` / `LegacyWBApiFinanceDetailTransport` → живые запросы к WB API.
- `test_fixture` пропускает ingestion (`return "skipped_fixture_origin"` в audit.py стр. 244), но не подключает ReplayBundle; просто не делает запросы.
- **Отдельного режима replay/offline в архитектуре нет** — ReplayBundle остаётся вне `CabinetAuditor.audit()`.

## 3. ReplayBundle (текущая реализация)

- `packages/wb_core/replay.py`: `load_replay_bundle()` — только чтение, никаких `requests`, никаких `wb_api_core`.
- `ReplayBundle` содержит `metadata`, `manifest`, `raw_objects` (tuple `RawObject`).
- Реальный пакет: `.tmp/replay_fixtures/live-4297720-fd-2026-08-27/` — `raw/finance_detail.json` (ARRAY, sha256 `3f4c9f2c...`, 252441 байт), `manifest.json`, `metadata.json` со scope UUID (`8eeba4a7...` / `fed4...`).
- `InMemoryRawObjectRepository`: только тестовая реализация (audit.py использует `SQLiteRawObjectRepository` в production).
- **ReplayBundle не используется в `CabinetAuditor.audit()`**, не подключён к `main.py`; используется только в адаптере `final_audit_circle.py` и в ручных проверках.

## 4. FINANCE_DETAIL (реальные данные)

- Endpoint: `FINANCE_DETAIL_ENDPOINT` (`packages/wb_core/contracts.py` стр. 117–127), `expected_payload_kind=ARRAY`, `object_type=FINANCE_DETAIL`, schema `finance-detailed-v1`.
- ReplayBundle: `raw/finance_detail.json`, массив, sha256 проверен, byte_length 252441, не изменён с момента захвата (`live_capture_4297720`).
- `archive_path` предыдущего захвата: `.tmp/live_capture_4297720/live-capture-fd-4297720-2026-08-27/raw/0001_finance_detail.json` (original; переименован в replay в `finance_detail.json` для соответствия `ReplayPayloadManifestEntry.pattern`).
- `scope` — авторитетный UUID из `packages/accounts/service.py`, не выведен из `seller_id=4297720`.

## 5. Причина HTTP 500 (429 → 500)

- `LegacyWBApiFinanceDetailTransport.fetch_finance_detail()` (wb_sales_funnel_transport.py стр. 84–109) при `response.get("success") == False` поднимает `RuntimeError("finance_detail WB request failed with status 429")`.
- `CabinetAuditor.audit()` (audit.py) не ловит `RuntimeError`; только `(LookupError, ValueError)` в `main.py` стр. 224.
- Поэтому внешняя ошибка `429` становится необработанным исключением → FastAPI возвращает `500`.
- Это **текущая ожидаемая ошибка**; механизм `graceful` (PARTIAL/no_data) в `_audit_status()` существует, но не достигается, так как исключение прерывает поток до формирования результата.

## 6. Может ли ReplayBundle использоваться в веб-аудите без нарушения архитектуры?

- Архитектурно — **да**, но требуется новое соединение, не нарушающее существующие границы:
- Вариант C (`data_origin=replay` / offline режим) — минимальное нарушение: `audit.py` уже знает `test_fixture`; нужно либо расширить `data_origin` на `replay_bundle`, либо подменить `raw_repository` в `main.py` на `InMemoryRawObjectRepository`, загруженный из `load_replay_bundle`, при сохранении `daily_ingestion`/`finance_detail_ingestion` в режиме пропуска (как для `test_fixture`).
- Вариант B (ReplayBundle напрямую в `CabinetAuditor.audit()`) — требует изменения `_run_ingestion()` или передачи `raw_repository` с уже загруженными объектами; не нарушает kernel/finance/normalization.
- **Вариант A (всегда live)** — текущее состояние, объясняет проблему.
- **Рекомендуемый следующий шаг** (не реализовано здесь): либо добавить `data_origin="replay_bundle"` с загрузкой из `.tmp/replay_fixtures/live-4297720-fd-2026-08-27`, либо изменить `_default_audit_service()` в `main.py`, чтобы при `data_origin="replay_bundle"` использовать replay-репозиторий вместо живых транспортов.

## 7. Файлы, которые потребуется изменить на следующем этапе (если исправление утвердят)

- `apps/api/main.py` (`_default_audit_service()` или `run_audit()` — передача replay-флага; возможно, новый `replay_raw_repo`)
- `packages/pipeline/audit.py` (`_run_ingestion()` — пропуск live только при replay-режиме; или передача `raw_repository` с уже загруженными `RawObject`)
- `packages/wb_core/replay.py` (не изменять — только читать; уже исправлен endpoint-specific guard)
- `packages/compat/wb_sales_funnel_transport.py` (не трогать — legacy transport; только пропускать при replay-режиме)
- Возможно: новый `docs/` или `tests/` для replay-аудита (не обязателен для первого шага).

## 8. Что НЕ изменено (подтверждено)

- `packages/finance/`, `packages/data/normalization.py`, `packages/finance/marketplace_policy.py`, `packages/finance/kernel.py` — не тронуты.
- `packages/wb_core/endpoint_policy.py` — только чтение.
- `legacy abs()` — не изменён; `test_marketplace_sign_policy.py` не изменён в этом этапе.
- `.env` — не изменён, токен не выведен.
- `.git` — без push/filter-repo; репозиторий `GitHub-clean` не затронут.
- ReplayBundle payload (`raw/finance_detail.json`) — не изменён, sha256 совпадает.
- Не выполнены новые live WB запросы (кроме диагностических чтений уже существующих файлов).

## 9. Точный ответ на вопрос повышения

> Почему веб-интерфейс не использует уже существующий реальный ReplayBundle и вместо этого снова обращается к WB API?

Потому что `main.py` создаёт `CabinetAuditor` с `WBDailyIngestionService` / `WBFinanceDetailIngestionService`, каждый из которых содержит `WBApiClient`; `data_origin` по умолчанию `real_wb_data`; отсутствует механизм подмены `raw_repository` на `InMemoryRawObjectRepository`, загруженный из `ReplayBundle`; `ReplayBundle` сейчас используется только в тестовых/офлайн-адаптерах (`final_audit_circle.py`), не подключён к `run_audit`.

---

**Статус:** диагностика завершена; исправление не выполнено (как требовано); следующий шаг определяется пользователем (вариант C — replay-режим — минимально нарушает архитектуру); `docs/STAGE_20_4_REPORT.md` создан.
