# STAGE 20.22 — seller Sergey: реальный путь данных сквозняком (WB → raw → normalize → ядро → DB → API → frontend)

Миссия: `AI Director 2 — автономно довести seller Sergey до реальных данных WB.md`.
Кабинет: `seller_Sergey` (`account_id 62b0754c-d359-4072-b432-239bcc0856f9`,
`tenant_id 52693933-f8e1-4821-bf06-84a226ee7a6d`, credential_reference `WB_API_TOKEN`).
Дата выполнения: 2026-09-10 (бизнес-день Europe/Moscow; D-1 = 2026-09-09).

---

## A. Исходная проблема

Аудит кабинета `seller_Sergey` не проходил сквозняком: `/audit` падал или
возвращал пустые дни, frontend не показывал подтверждённые данные WB.
Первый сбой на реальном пути воспроизводился стабильно, но его корень был не
в одном месте — ниже три независимых дефекта кода плюс два внешних ограничения
WB.

## B. Первопричина

1. **Fail-fast ingestion.** `WBDailyIngestionService.ingest()` выполнял 5
   источников последовательно и при первой же ошибке (например, гарантированный
   403 по stocks для текущего типа токена) прерывал **весь** аудит. Один
   недоступный источник уничтожал день целиком.
2. **Маскировка сбоя как «нет данных».** Legacy-лоадер при HTTP 403/429 возвращает
   `{"payload": {"data": []}, "debug": {"success": false, ...}}`; ingestion
   сохранял такой «пустой» payload как валидный RawObject. Сбой превращался в
   «0 данных», а идемпотентность (`_existing` по OperationalDate) блокировала
   повторную загрузку — день запирался навсегда. В БД накопилось **20 таких
   замаскированных raw**.
3. **Окно lastChangeDate вместо дня события.** statistics-api
   `/api/v1/supplier/orders|sales` возвращает окно `lastChangeDate >= dateFrom`
   (сырой raw за 09-02 содержал 34 строки с датами 08-22…09-10). Нормализатор
   приписывал **все** строки окна дню загрузки — метрики дня завышались строками
   чужих дней.
4. **Двойной ingestion на один `/audit`.** `CabinetAuditor._run_ingestion()`
   и `DailyAnalysisService.run_analysis()` каждый вызывали ingestion — при
   лимитере WB каждый сбойный источник запрашивался дважды за операцию.

Внешние ограничения (не баги кода): stocks
`/api/analytics/v1/stocks-report/wb-warehouses` → постоянный 403 «token does not
satisfy additional requirements» (`origin: ag-contentanalytics`) — токену кабинета
не назначена категория «Аналитика»; и глобальный per-seller лимитер WB
(`X-RateLimit-Retry: 3582/4267`), срывающий live-загрузку после серии запросов.

## C. Доказательства

- Инвентарь raw `seller_Sergey` после очистки (SQLite
  `runtime/wb_autopilot.sqlite3`, таблица `raw_object_payload_bytes`, sha256/байты):
  **26 raw** на 08-27…09-09; напр. `2026-09-02 orders=7912fdd0ac89(28247B),
  finance_detail=a4960a873781(45789B), sales_funnel_products=43f3a66cb971(37451B),
  advertising_performance=72b6a30cb1d0(188B), sales=391a103c8978(1748B)`;
  `2026-09-09 finance_detail=664f3102fee8(102107B), orders=8d66ef924e41(1730B),
  sales_funnel_products=124e1fd90983(54087B), advertising_performance=822ce9727ead(189B)`.
- Ответ API `/audit/62b0754c…?date=2026-09-02&data_origin=real_wb_data`:
  `audit_status=complete`, `finance_status=complete`,
  `ingestion_status=ingested:daily+finance_detail+degraded` (degraded — только
  stocks-403), `source_event_id` продаж — реальные `srid` WB
  (`ebC.i0e6e9caaee1646474e3f3a2e4cb56d7.0.0`), `retrieved_at=2026-09-03T15:18:25Z`.
- `runtime/reports/62b0754c…/2026-09-02/report.txt`:
  `realized_revenue=1439`, `net_profit=304.28`, `profit_margin=21.15`,
  `marketplace_commission=-325.57`, `acceptance=-10`, `acquiring=-57.56`,
  `advertising=-77.04`, `logistics=-75.4`, `rebill_logistics=-76.92`,
  `storage=-5.89`, `tax=-86.34`, `funnel_opens=211`, `funnel_carts=11`,
  `sales=2`, `orders: Нет данных` (в окне 09-02 не было строк с датой 09-02 —
  честное состояние «нет данных», не «0»), `available_stock: Нет данных` (403).
  Диагностики исключений политик (`cashbackAmount`, `kvw`, `spp`, `vw`, `vwNds` —
  «excluded, not zeroed») видны в API и отчёте.
- 429/403 зафиксированы как диагностики источника с `requestId` WB
  (`origin: ag-statistics`, `ag-contentanalytics`), а не как тишина.
- Очистка: удалено 20 замаскированных пустых raw (идентичный sha `8fe32e40…`),
  51→31 raw в runtime-БД на момент чистки (позднее добавлены backfill-дни).
- `GET /api/reports/62b0754c…/2026-09-02/report.pdf` → 200, 5049 байт,
  `application/pdf`; `GET /` (frontend `app.js`) → 200.

## D. Что исправлено (код)

| Файл | Изменение |
|---|---|
| `packages/wb_core/daily_ingestion.py` | `ingest()` возвращает `tuple[str, ...]` диагностик; каждый источник изолирован (`source_unavailable:<endpoint>: …`); сбойный ответ (`debug.success=false`) никогда не персистится — `RuntimeError` со статусом WB; `request_scope` orders приведён к фактическому `flag: 0` |
| `packages/pipeline/audit.py` | `_run_ingestion` возвращает `(status, diagnostics)`; частичный сбой → `ingested:…+degraded`; total outage (ни одного persisted raw за день) → `RuntimeError(“no WB source could be ingested …”)` → 503 в API; `_merge_diagnostics` (дедуп без потери порядка); `run_analysis(ingest_first=False)` — один ingestion на аудит |
| `packages/pipeline/analysis.py` | протокол `DailyIngestion.ingest -> tuple[str,...]`; диагностика ingestion включается в результат анализа; параметр `ingest_first` (регрессия двойного запроса WB); `retrieved_at: datetime | None` (соответствие протоколу) |
| `packages/data/normalization.py` | `_statistics_row_belongs_to_day`: строка windows принадлежит только своему дню события (`date`); отсутствие/неспарсенность даты → не приписывается никуда; сырое окно в raw не изменяется |
| `packages/compat/wb_sales_funnel_transport.py` | finance `204 empty` → `[]` (контракт array-endpoint вместо маски `{“data”: []}`) |
| `apps/api/main.py` | replay-ветка: `RuntimeError → 503 “transport/upstream error”` (единообразие с live-веткой 20.17) |
| `docs/METRICS_PASSPORT.md` | правило атрибуции окна STAGE 20.22 (прямое применение `WHERE date = target_date`) + указание тестов |
| тесты | 4 файла регрессий (см. §J) |

## E. Реальный путь данных (пройден без mock/fixture)

`WBApiClient` (statistics-api / finance-api / seller-analytics-api / advert-api,
токен `WB_API_TOKEN`) → `LegacyWBApiLoadersTransport` →
`WBDailyIngestionService`/`WBFinanceDetailIngestionService` →
`SQLiteRawObjectRepository` (`runtime/wb_autopilot.sqlite3`, неизменяемые raw +
sha256) → `run_stored_daily_pipeline` (только чтение persisted raw) → Finance
Kernel (Decimal, sign-policy, finality) → артефакты `runtime/reports/<id>/<date>/`
→ `GET /audit/{account_id}?data_origin=real_wb_data` → frontend `app.js`.

## F. Результат seller Sergey

- **2026-09-02**: полный сквозной цикл, `audit_status=complete`, реальные
  продажи/финанс/воронка/реклама (см. C). Orders — честное «Нет данных» для дня.
- **2026-09-09 (D-1, дефолт UI)**: `audit_status=partial`,
  `ingestion_status=ingested:daily+finance_detail+degraded`. 4 источника с
  реальными raw: `orders` (2 события), `sales_funnel_products` (opens 225,
  carts 25, orders 3), `advertising_performance` (−65.31), `finance_detail`
  (51 записи: realized_revenue 1737, logistics −1753.87, acquiring −69.48,
  storage −4.46, tax −104.22). `net_profit/profit_margin = Недоступно`:
  отрицательный `marketplace_commission` (−81.96) без утверждённой credit-
  политики исключён ядром из authoritative P&L (sign-policy, §3.12.1
  METRICS_PASSPORT) — ядро отказывается считать прибыль из неполного набора,
  а не рисует ложное число. `sales = Нет данных` (429 лимитера),
  `stocks = Нет данных` (403 категория токена).
- Прочие дни 09-03…09-08: orders полностью (backfill из сохранённого окна,
  0 запросов), sales 09-03/07/08, funnel 09-03/06/07/08, ads 09-02/03/06/07/08,
  finance 09-02/09. Догрузка sales-окна 09-03 подтвердила ровно 2 продажи
  (уже персистированы); для 09-05/06/09 продаж в окне не оказалось.
- Stocks: «Нет данных» + явная диагностика 403 — внешний блок (см. K).
- Frontend: корень `/` и PDF-роут отдают контент; UI (`runAudit` c
  `data_origin=real_wb_data`) отображает `audit_status`, `ingestion_status`,
  `diagnostics`, KPI из реальных raw и различает «Нет данных» /
  «Недоступно» / «Не определено» / число.

## G. Происхождение старых данных

Подтверждено предыдущими отчётами (STAGE 20.11 FINAL): данные, которые
проект показывал в начале, брались из **реального** legacy-пути
(`wb_api_core`/`report_v2`) по тому же токену продавца — не mock. AD2-цепочка
настарте теряла эти же данные из-за дефектов B1–B3, а не из-за отсутствия
доступа к WB.

## H. WB API

- `GET /api/v1/supplier/orders|sales` (statistics-api) — окно `lastChangeDate`,
  `flag=0`; атрибуция по дню события (B3).
- `POST /api/v2/finance-realization-detail-report` (finance-api) — отдельный
  лимитер; 204 → `[]`.
- `POST /content-analytics/v2/product-sold-out-stats` (seller-analytics-api) —
  воронка по SKU, работает.
- `GET /api/v3/advert/promotion/price/su` + performance (advert-api) — реклама.
- `GET /api/analytics/v1/stocks-report/wb-warehouses` — **403** для текущего
  токена (нужна категория «Аналитика»).
- Лимитер глобальный per-seller: `x_ratelimit_remaining=0`,
  `x_ratelimit_retry=4267s` зафиксированы в raw-ответе; повторных «штормовых»
  запросов не выполнялось (§10 миссии): серия 429 → стоп → плановая одна
  попытка после сброса.

## I. Проверки

- `pytest tests` (PYTHONPATH=корень репо): **327 passed** (baseline HEAD —
  313 passed; +14 новых тестов, 0 падений).
- `ruff check` тронутых файлов: ошибок новых нет; 13 оставшихся — все E501 на
  неизменяемых/существовавших в HEAD строках (проверено сравнением с baseline
  worktree HEAD).
- `mypy`: **150** ошибок против baseline **151** при 109 проверенных файлах
  (было 101) — ни одной новой, одна исправленная (согласование протокола
  `retrieved_at`).
- API: `GET /healthz` ok; `GET /api/accounts` отдаёт `seller_Sergey`;
  `/audit` 09-02 → 200 complete; 09-09 → 200 partial (4 реальных источника,
  diagnostics без двойных запросов, 12 s); PDF → 200; replay-ветка: без
  `replay_case` → 400 (хардкод живого кабинета удалён из кода).
- Секрет-скан diff: 0 токеноподобных строк; `4297720`/`Sergey` в `main.py`
  отсутствуют; runtime-артефакты и `.tmp` — в `.gitignore`.

## J. Регрессии

- `tests/unit/test_daily_ingestion_resilience.py` — частичный/полный сбой
  источников; сбой не персистится; успешные источники не ретелятся.
- `tests/integration/test_cabinet_audit_degraded_sources.py` — degraded-аудит,
  total-outage → RuntimeError; **каждый loader вызывается ровно 1 раз за
  аудит** (защита от двойного ingestion).
- `tests/unit/test_statistics_window_day_attribution.py` — атрибуция окна по
  дню события; структурно битая строка по-прежнему роняет strict-builder.
- `tests/unit/test_stage_20_17_runtime_error.py` — заглушка-аудитор:
  RuntimeError→503+`transport/upstream error`, LookupError/ValueError→400.

## K. Ограничения

1. Stocks: 403 по категории токена — лечится только назначением кабинету
   токена «Аналитика» на стороне WB. В системе отражено как «Нет данных» +
   явная диагностика (не 0, не сбой цикла).
2. Глобальный per-seller лимитер WB сорвал live-догрузку 09-03…09-09. После
   сброса окна (X-RateLimit-Retry истёк) была выполнена **одна** аккуратная
   серия из 8 запросов (§10 миссии): sales-окно (200 OK), finance 09-09
   (51 запись), ads/funnel 09-09, finance 09-03/06 (снова 429 → немедленный
   стоп, без шторма). Остались не закрытыми: `finance_detail` 09-03…08,
   `sales` 09-05/06/09 (в догруженном окне продаж за эти даты строк нет,
   но полный ответ по дням не персистирован). Это внешние live-ограничения,
   а не ошибки цепочки: при освобождении лимитера идемпотентный
   `audit(2026-09-09)` дозагрузит недостающие raw автоматически.
3. Строки окна с датами ≤ 08-22 намеренно не backfill-ятся: для них окно
   09-02 не является полным доказательством (lastChange-история обрезана).
4. `net_profit` за 09-09 = «Недоступно» из-за отсутствия approved credit-
   политики для отрицательного `marketplace_commission` (см. F). Это
   управленческое решение по §3.12.1 METRICS_PASSPORT, а не ошибка ядра;
   для получения authoritative P&L требуется утвердить политику кредит-
   записей (следующий stage).
5. Live-запросы выполнялись только production-путём
   (`wb_core`/`compat`-транспорт); никаких параллельных загрузчиков не
   создавалось (§9 миссии).

## L. Git

- `git push` не выполнялся; `.env` не изменялся; новых зависимостей нет.
- Изменения: 9 tracked-файлов (+337/−69 на момент составления отчёта) и новые
  тестовые файлы. Единственный файл вне `AI Director 2/` —
  `docs/METRICS_PASSPORT.md` (корень репо): того требует корневой AGENTS.md
  («изменение формулы метрики — только с обновлением METRICS_PASSPORT.md и
  тестов»), отдельной копии паспорта в AD2 нет.
- Не коммитятся (в реальном виде вне Git, как и раньше): отчёты STAGE с
  цифрами продавца, `packages/wb_core/adapters/` (одноразовые диагностические
  скрипты c живыми идентификаторами), runtime-БД и артефакты, `.tmp*`.
- Ветку replay в `apps/api/main.py` санитизирована: `replay_case` передаётся
  параметром, идентификатор реального кабинета из кода удалён.
- Временные .tmp-скрипты диагностики/дозагрузки удалены после завершения
  работы (доказательства — в этом отчёте). Worktree `.tmp/baseline-head` удалён.

---

### Ответ миссии §12/§18: какая первая ошибка на реальном пути?

Первая **живая** ошибка на пути seller Sergey — `403 Forbidden` на stocks
(`ag-contentanalytics`, токену не назначена категория «Аналитика»); она была
безопасной по данным, но из-за дефекта №1 (fail-fast) убивала весь аудит, а
дефект №2 превращал такие сбои в фальшивые «пустые» raw, запиравшие дни.
Первая **существенная** для денег ошибка — дефект №3 (окно lastChangeDate
завышало день событиями чужих дней). Все три исправлены с регрессиями;
остаток ограничений — внешний (см. K).
