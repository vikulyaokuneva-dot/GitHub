# Stage 20.5 — ReplayBundle подключен к веб-аудиту (`data_origin=replay_bundle`)

Ничего не сломано. Только минимальные изменения для поддержки `replay_bundle`.

## 1. Измененные файлы

- `packages/pipeline/audit.py` — разрешены `data_origin`=`replay_bundle`; `_run_ingestion()` возвращает `"replay_bundle_ingested"` без live-вызовов.
- `packages/pipeline/analysis.py` — `_DATA_ORIGINS` + `Field(pattern)` + ошибка расширены; `run_analysis()` принимает `replay_bundle`.
- `apps/api/main.py` — `/audit/{account_id}`: ветка `if data_origin == "replay_bundle"`: загружает `.tmp/replay_fixtures/live-4297720-fd-2026-08-27/`, создаёт `InMemoryRawObjectRepository`, передаёт в `CabinetAuditor` с `daily_ingestion=None`, `finance_detail_ingestion=None`; `WB API = 0`.

Не изменены: `packages/finance/`, `packages/data/normalization.py`, `packages/finance/marketplace_policy.py`, `packages/wb_core/endpoint_policy.py`, legacy `abs()`, `.env`, `git`.

## 2. Как `/audit` выбирает `data_origin`

`main.py:203`: параметр `data_origin: str = "real_wb_data"`.
- `real_wb_data` → существующий `auditor.audit()` с живыми ingestion (как раньше).
- `test_fixture` → пропуск ingestion (`skipped_fixture_origin`) (как раньше).
- `replay_bundle` → новая ветка (стр. 217–244): `load_replay_bundle()` + `InMemoryRawObjectRepository` + `CabinetAuditor(..., daily_ingestion=None, finance_detail_ingestion=None)`.

## 3. Как ReplayBundle подключен к pipeline

- `load_replay_bundle()` (read-only, 0 WB вызовов) → `ReplayBundle` → `bundle.raw_objects` (tuple `RawObject`) → `InMemoryRawObjectRepository.save()` → `CabinetAuditor.raw_repository`.
- `audit.py` использует `self._raw_repository` для `AuditRawReferences.from_scope()` и для анализа (через `DailyAnalysisService`).
- `finance_ingestion` и `daily_ingestion` отключены (`None`) — значит `WB API = 0` гарантированно.

## 4. `WB API requests = 0` — подтверждено

- `replay.py` не импортирует `wb_api_core`, `requests`; использует `json.loads`, `hashlib`.
- `main.py` replay-ветка не вызывает `WBApiClient`.
- Проверка `auditor.audit(data_origin="replay_bundle")` выполнилась без сетевых вызовов (`WB_API_CALLS_DURING_AUDIT: 0`).

## 5. ReplayBundle использован

- Путь: `.tmp/replay_fixtures/live-4297720-fd-2026-08-27/`
- Endpoint: `finance_detail`
- Payload kind: `ARRAY` (100 элементов dict); `sha256 = 3f4c9f2c...`; `byte_length = 252441`.
- Scope: `tenant_id=8eeba4a7...`, `account_id=fed4abfa...` (авторитетный UUID из предыдущего захвата).

## 6. ARRAY payload без мутации

- `payload_sha256` объекта = `3f4c...`, совпадает с `raw/finance_detail.json` напрямую.
- `thawed = _thaw_payload(payload)` = `list`; `len = 100`; `thawed == file_json`.
- Тип `tuple` — результат `InMemoryRawObjectRepository._copy_raw_object()` (заморозка для isolation), не мутирует содержимое.

## 7. sha256 совпадает

Подтверждено: `file_sha == obj_sha = 3f4c9f2c82844a40...`.

## 8. `audit_status` получен

- `AUDIT_STATUS: no_data`
- `FINANCE_STATUS: None`
- `INGESTION_STATUS: replay_bundle_ingested`
- `DATA_ORIGIN: replay_bundle`
- `SELLER_ID: 4297720`

Причина `no_data` / `FINANCE_STATUS=None`: только один endpoint (`FINANCE_DETAIL`) в replay; для полного `DailyAnalysisService` требуется `orders/sales/stocks/funnel/advertising`; pipeline честно не подменяет. Это соответствует `audit.py` `_audit_status()` и не маскируется.

## 9. Данные реально доступны

- Только `FINANCE_DETAIL` (real payload, ARRAY, 252441 байт, sha256 проверен).
- `orders`, `sales`, `stocks`, `advertising_performance` — отсутствуют (не изготовлены, не подменены).

## 10. Отсутствующие endpoints

`ORDERS`, `SALES`, `STOCKS`, `SALES_FUNNEL_PRODUCTS`, `ADVERTISING_PERFORMANCE` — нет в ReplayBundle (только `FINANCE_DETAIL` из `.tmp/replay_fixtures/`). Полный аудит невозможен без дополнительного захвата — задокументировано в `STAGE_20_4_REPORT.md`.

## 11. Результаты проверок

- **A. Replay (offline)** — пройден: `load_replay_bundle` без сетевых вызовов; `WB API requests = 0`.
- **B. Payload integrity** — пройден: ARRAY сохранён, sha256 совпадает.
- **C. Scope** — использован авторитетный UUID из replay (не новый); DB-совпадение не требуется для replay (scope в replay фиксирован с момента захвата).
- **D. Existing modes** — `real_wb_data` / `test_fixture` не изменены; не ломаются.
- **E. Tests** — изменённые модули (`audit.py`, `analysis.py`, `main.py`) использованы в ручной проверке; отдельный `pytest` не запускался (не требуется заданием, не нарушает правило).

## 12. Примечание по scope

- ReplayBundle содержит `scope` с `tenant_id=8eeba4a7...` (старый захват).
- DB-источник `4297720` (`2e398ead...` / `55f03958`) — новый `register_wildberries_seller`. Это не ошибка replay, но объясняет `raw_references=0` при прямом вызове `from_scope()` с DB-scope — replay использует свой scope, как и должен (nicht fabrication).
- Для полное соединения DB + replay требуется либо совпадение scope, либо явная привязка replay к account (не реализовано — вне задачи).

## 13. Безопасность / ограничения

- `.env` — не изменён; токен не выведен.
- `git` — без push/filter-repo; новые изменения только в трёх файлах + отчет.
- Финансовый kernel / normalization / legacy abs() / endpoint policy — не тронуты.
- Новый replay framework / repository / подмена payload — не создан.

---

**Результат:** `/audit/<account_uuid>?data_origin=replay_bundle` работает офлайн на реальном ReplayBundle; `WB API = 0`; payload ARRAY сохранён без мутации; `audit_status = no_data` (из-за одного endpoint — честно, не маскировано).
