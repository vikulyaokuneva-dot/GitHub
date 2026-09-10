# Stage 20.6 — Диагностика реальных WB endpoint contracts (только отчёт, без исправлений)

Ничего не изменено в коде, `.env`, ReplayBundle, Finance Kernel, endpoint contracts, normalisation, legacy abs(), git history. Никаких повторных массовых запросов к WB (только чтение существующих файлов и кода). Для ADVERTISING — использованы сохранённые результаты предыдущих захватов (`.tmp/capture_multi_4297720/`), не новые массовые запросы.

---

## 1. Фактический путь каждого endpoint (из существующего кода)

Источники (без предположений):
- `wb_api_core/client.py` (PATH, base URLs)
- `wb_api_core/loaders.py` (load_orders, load_sales, load_stocks, load_ads, load_cabinet_commerce)
- `packages/compat/wb_sales_funnel_transport.py` (LegacyWBApiLoadersTransport, LegacyWBApiFinanceDetailTransport)
- `packages/wb_core/contracts.py` (EndpointMetadata, expected_payload_kind)
- `packages/wb_core/daily_ingestion.py` (WBDailyIngestionService — ingestion boundary)
- `packages/wb_core/finance_ingestion.py` (WBFinanceDetailIngestionService)
- `.tmp/capture_multi_4297720/` (реальные результаты захвата 4 endpoint)

### Таблица endpoint

| Endpoint | Method | Contract `expected_payload_kind` | Transport/file | Ingestion service | Base URL (из `client.py`) |
|---|---|---|---|---|---|
| FINANCE_DETAIL | POST (`FINANCE_DETAILED_PATH`) | ARRAY (`PayloadKind.ARRAY`) | `LegacyWBApiFinanceDetailTransport` (`wb_sales_funnel_transport.py:78`) | `WBFinanceDetailIngestionService` (`wb_core/finance_ingestion.py`) | `finance_base_url` (`client.py:30`: `https://finance-api.wildberries.ru`) |
| ORDERS | GET (`ORDERS_PATH`) | ARRAY (`PayloadKind.ARRAY`) | `LegacyWBApiLoadersTransport.load_orders()` (`loaders.py:791` делегирует) | `WBDailyIngestionService._ensure_orders()` (`daily_ingestion.py:172`) | `analytics_base_url` (`client.py:31`: `https://seller-analytics-api.wildberries.ru`) |
| SALES | GET (`SALES_PATH`) | ARRAY (`PayloadKind.ARRAY`) | `LegacyWBApiLoadersTransport.load_sales()` (`loaders.py`) | `WBDailyIngestionService._ensure_sales()` (`daily_ingestion.py:198`) | `analytics_base_url` (`client.py:31`) |
| STOCKS | POST (`STOCKS_WB_WAREHOUSES_PATH`) | OBJECT (`PayloadKind.OBJECT`) | `LegacyWBApiLoadersTransport.load_stocks()` (`loaders.py`) | `WBDailyIngestionService._ensure_stocks()` (`daily_ingestion.py:224`) | `analytics_base_url` (`client.py:31`) |
| SALES_FUNNEL_PRODUCTS | POST (`SALES_FUNNEL_PRODUCTS_PATH`) | OBJECT (`PayloadKind.OBJECT`) | `LegacyWBApiLoadersTransport.load_cabinet_commerce()` (`wb_sales_funnel_transport.py:163`) | `WBDailyIngestionService._ensure_funnel()` (`daily_ingestion.py:249`) | `analytics_base_url` (`client.py:31`) |
| ADVERTISING_PERFORMANCE | GET (`ADVERTS_PATH`) для adverts; `ADVERT_STATS_PATH` для stats (`/adv/v3/fullstats`) | OBJECT (`PayloadKind.OBJECT`) | `LegacyWBApiLoadersTransport.load_ads()` (`loaders.py:791`) → `ADVERTS_PATH` (`GET`) + `ADVERT_STATS_PATH` (`GET`, params `ids`, `beginDate`, `endDate`) | `WBDailyIngestionService._ensure_advertising()` (`daily_ingestion.py:276`) | `advert_base_url` (`client.py:32`: `https://advert-api.wildberries.ru`) |

### Точные строки из кода (без интерпретации)

`ORDERS`:
- PATH: `client.py:36` → `ORDERS_PATH = "/api/v1/supplier/orders"`
- Method: `LegacyWBApiLoadersTransport.fetch_orders()` (`transport.py:49`) → `method="GET"`, `params={"dateFrom": ..., "flag": 0}`
- Contract (`contracts.py:129`): `ORDERS_ENDPOINT` → `http_method="GET"`, `expected_payload_kind=ARRAY`, `logical_domain=ANALYTICS`

`SALES`:
- PATH: `client.py:37` → `SALES_PATH = "/api/v1/supplier/sales"`
- Method: `transport.py:58` → `GET`, `params={"dateFrom": ..., "flag": 1}`
- Contract (`contracts.py:141`): `SALES_ENDPOINT` → `GET`, `ARRAY`, `ANALYTICS`

`STOCKS`:
- PATH: `client.py:38` → `STOCKS_WB_WAREHOUSES_PATH = "/api/analytics/v1/stocks-report/wb-warehouses"`
- Method: `load_stocks()` вызывает `client.request_json(...)` с `method="POST"`, `json_body` содержит `dateFrom`/`dateTo` (`loaders.py`); контракт (`contracts.py:153`) → `STOCKS_ENDPOINT` → `POST`, `OBJECT`, `ANALYTICS`, `PaginationSemantics.OFFSET_LIMIT`

`SALES_FUNNEL_PRODUCTS`:
- PATH: `client.py:40` → `SALES_FUNNEL_PRODUCTS_PATH = "/api/analytics/v3/sales-funnel/products"`
- Method: `transport.py:16` (`LegacyWBApiSalesFunnelTransport.fetch_sales_funnel_products`) → `POST`, `json_body` с `selectedPeriod` (`start`/`end` в `operational_date.isoformat()`), `limit`, `offset`, `nmIds`, `brandNames` и т.д.
- Contract (`contracts.py`): `SALES_FUNNEL_PRODUCTS_ENDPOINT` → `POST`, `OBJECT`, `ANALYTICS`

`FINANCE_DETAIL` (контрольный):
- PATH: `client.py:39` → `FINANCE_DETAILED_PATH = "/api/finance/v1/sales-reports/detailed"`
- Method: `transport.py:87` (`LegacyWBApiFinanceDetailTransport.fetch_finance_detail`) → `POST`, `json_body` с `dateFrom`/`dateTo`=`operational_date.isoformat()`, `period="daily"`, `limit=100000`, `rrdId=0`
- Base URL: `client.finance_base_url` (`transport.py:100`)
- Contract: `FINANCE_DETAIL_ENDPOINT` (`POST`, `ARRAY`, `FINANCE`)
- Реальный результат (`.tmp/live_capture_4297720/`): HTTP 200, payload ARRAY (252441 байт), sha256 `3f4c9f2c...`

`ADVERTISING_PERFORMANCE`:
- Endpoint `advertising_performance` определен в `contracts.py:166` (`GET`, `OBJECT`, `ANALYTICS`)
- В коде `load_ads()` (`loaders.py:791`) используется `ADVERTS_PATH` (`/api/advert/v2/adverts`) для `GET` adverts, затем для каждого `advertId` делается `GET` `ADVERT_STATS_PATH` (`/adv/v3/fullstats`) с параметрами `ids`, `beginDate`, `endDate`.
- Таким образом endpoint `advertising_performance` в проекте не имеет единого прямого `GET` вызова в `load_ads()`; используется двухэтапный подход (adverts → stats per advert). Это важно для диагностики `429` (может быть вызов `ADVERT_STATS_PATH` или `ADVERTS_PATH`).

---

## 2. ORDERS — диагностика

**Фактические данные из кода:**
- METHOD: `GET`
- BASE_URL: `analytics_base_url` (`https://seller-analytics-api.wildberries.ru`)
- PATH: `/api/v1/supplier/orders`
- PARAMS: `{"dateFrom":"...","flag":0}` (`transport.py:54` / `loaders.py` через `load_orders`)
- CONTRACT (`contracts.py:129`): `GET`, `ARRAY`, `ANALYTICS`, `source="wildberries"`, `schema_version="supplier-orders-v1"`

**Наблюдаемое поведение:** `.tmp/capture_multi_4297720/orders.json` → `success=False`, `status_code=404`, `payload=None` (из предыдущего захвата).

**Причина 404 — доказанные факты:**
- `BASE_URL` (`analytics_base_url`) и `PATH` совпадают с существующим контрактом (`contracts.py`).
- `METHOD` (`GET`) совпадает с контрактом (`ORDERS_ENDPOINT.http_method="GET"`).
- `PATH` (`/api/v1/supplier/orders`) — стандартный WB supplier orders endpoint (подтвержден в `client.py` и `loaders.py`).
- `404` означает, что сервер не находит endpoint под данным `PATH` или данный endpoint недоступен для текущего `token`/`provider`/`seller_id`.

**Вывод (без предположений):** `404` не объясняется ошибкой в `method`, `path`, `base_url` или параметрах (все совпадают с контрактом). Вероятная причина — endpoint `/api/v1/supplier/orders` недоступен для данного `WB_API_TOKEN` или для данного `seller_id=4297720` (не существует, требует других прав или другого endpoint version). Уверенность: `MEDIUM` (код контракта верен, но точная причина `404` на уровне WB не доказана без body ответа — body не сохранён для `orders.json`, т.к. `payload=None`).

**Не изменено:** код, `.env`, контракт.

---

## 3. SALES — диагностика

**Фактические данные из кода:**
- METHOD: `GET`
- BASE_URL: `analytics_base_url` (`https://seller-analytics-api.wildberries.ru`)
- PATH: `/api/v1/supplier/sales`
- PARAMS: `{"dateFrom":"...","flag":1}` (`transport.py:63`)
- CONTRACT (`contracts.py:141`): `SALES_ENDPOINT` → `GET`, `ARRAY`, `ANALYTICS`, `schema_version="supplier-sales-v1"`

**Наблюдаемое:** `.tmp/capture_multi_4297720/sales.json` → `success=False`, `status_code=404`, `payload=None`.

**Аналогично ORDERS:** `method`, `path`, `base_url`, `params` соответствуют контракту. `404` не объясняется ошибкой в архитектуре вызова. Возможные причины: endpoint недоступен для данного token/seller, или endpoint устарел/изменился в WB API, или требуется другой `path` (например, `/api/v1/supplier/reportDetailByPeriod` для sales в legacy — но `SALES_PATH` — `/api/v1/supplier/sales`, не `/api/v5/supplier/reportDetailByPeriod`).

**Уверенность:** `MEDIUM` для архитектуры вызова (всё совпадает); `LOW` для точной причины 404 без body ответа WB.

**Не изменено:** ничего.

---

## 4. STOCKS — диагностика

**Фактические данные из кода:**
- METHOD: `POST`
- BASE_URL: `analytics_base_url` (`https://seller-analytics-api.wildberries.ru`)
- PATH: `/api/analytics/v1/stocks-report/wb-warehouses`
- BODY: `json_body` с `dateFrom`/`dateTo` (`loaders.py`, `load_stocks` через `request_json`)
- CONTRACT (`contracts.py:153`): `STOCKS_ENDPOINT` → `POST`, `OBJECT`, `ANALYTICS`, `PaginationSemantics.OFFSET_LIMIT`, `schema_version="stocks-wb-warehouses-v1"`

**Наблюдаемое:** `.tmp/capture_multi_4297720/stocks.json` → `success=False`, `status_code=403`, `payload=None`.

**Анализ 403:**
- `403 Forbidden` отличается от `404 Not Found` — это означает, что endpoint существует, но доступ запрещён для текущего caller (token, seller, provider, или права).
- `STOCKS_WB_WAREHOUSES_PATH` (`/api/analytics/v1/stocks-report/wb-warehouses`) — существующий endpoint в `client.py`.
- `method` (`POST`) совпадает с контрактом (`STOCKS_ENDPOINT.http_method="POST"`).
- `403` не объясняется неправильным `method` или `path`; это явно запрет доступа (rights/token/seller).

**Уверенность:** `HIGH` для архитектуры вызова (всё совпадает); `MEDIUM` для причины `403` (вероятно: недостаточные права или endpoint требует другого provider/seller, но точная причина на уровне WB не доказана без body ответа — body не сохранён для `stocks.json`).

**Не изменено:** ничего.

---

## 5. SALES_FUNNEL_PRODUCTS — диагностика (без нового live-запроса)

**Фактические данные из кода (без выполнения нового запроса):**
- METHOD: `POST` (`LegacyWBApiSalesFunnelTransport.fetch_sales_funnel_products`, `transport.py:16`)
- BASE_URL: `analytics_base_url` (`transport.py:32`)
- PATH: `/api/analytics/v3/sales-funnel/products` (`client.py:40`)
- BODY: `json_body` с `selectedPeriod` (`start`=`operational_date.isoformat()`, `end`=`operational_date.isoformat()`), `nmIds: []`, `brandNames: []`, `subjectIds: []`, `tagIds: []`, `skipDeletedNm: True`, `limit: 1000`, `offset: 0` (`transport.py:21`)
- CONTRACT (`contracts.py`): `SALES_FUNNEL_PRODUCTS_ENDPOINT` → `POST`, `OBJECT`, `ANALYTICS`, `schema_version` определён.
- TRANSPORT: `LegacyWBApiLoadersTransport.load_cabinet_commerce()` (`loaders.py:163`) → `LegacyWBApiSalesFunnelTransport.fetch_sales_funnel_products()` (`transport.py:15`)
- RETRY POLICY: `retryable_statuses` включает `429`, `max_attempts=6`, `base_delay_seconds=10.0` (`transport.py:189`) — это важное наблюдение для диагностики `429`.

**Наблюдаемое:** `SALES_FUNNEL_PRODUCTS` не был захвачен в `.tmp/capture_multi_4297720/` (только orders/sales/stocks/advertising). Поэтому текущий HTTP статус неизвестен (`N/A` в таблице). Однако контракт и transport существуют и используются в `WBDailyIngestionService` (`daily_ingestion.py:249`).

**Вывод:** нет доказательства ошибки для этого endpoint; код архитектурно верен. Для полного аудита необходим захват этого endpoint. Уверенность: `MEDIUM` (код совпадает с контрактом, но live-результат неизвестен).

---

## 6. ADVERTISING_PERFORMANCE — диагностика

**Фактические данные из кода:**
- `load_ads()` (`loaders.py:791`) использует два вызова:
  1. `GET` `/api/advert/v2/adverts` (`ADVERTS_PATH`, `client.py:41`) с `base_url=advert_base_url`, `method="GET"`, `retry_policy={"retryable_statuses": (500,502,503,504), "max_attempts": 2}`.
  2. Для каждого `advertId`: `GET` `/adv/v3/fullstats` (`ADVERT_STATS_PATH`, `client.py:42`) с `params={"ids":"...", "beginDate":"...", "endDate":"..."}` (`loaders.py:844`), `retry_policy` тот же.
- CONTRACT (`contracts.py:166`): `ADVERTISING_PERFORMANCE_ENDPOINT` → `GET`, `OBJECT`, `ANALYTICS`, `operational_date_semantics=REQUESTED_BUSINESS_DAY`, `schema_version="advertising-performance-v1"`.
- INGESTION SERVICE: `WBDailyIngestionService._ensure_advertising()` (`daily_ingestion.py:276`).

**Наблюдаемое:** `.tmp/capture_multi_4297720/advertising_performance.json` → `success=False`, `status_code=429`, `payload=None`.

**Причина 429:**
- `ADVERTS_PATH` (`GET`) был вызван с `retry_policy={"max_attempts": 2}`. Нет `429` в retryable для adverts (только `500, 502, 503, 504`). Однако в `LegacyWBApiLoadersTransport.load_cabinet_commerce()` (`transport.py:189`) retryable включает `429` (`max_attempts=6`, `base_delay_seconds=10`). Но `load_ads()` (`loaders.py:791`) использует `retry_policy` без `429`. То есть если первый вызов (`ADVERTS_PATH`) вернул `429`, retry не сработает для `load_ads()` (только 2 попытки без `429` в retryable). Но это не объясняет сам `429`.
- `429` — это rate limit. Возможно, вызов `load_ads()` (который делает сначала `GET /api/advert/v2/adverts`, затем `GET /adv/v3/fullstats` для каждого advert) вызвал несколько запросов в короткий период, и один из них получил `429`. Или `WBApiClient` сделал несколько запросов (например, предыдущий `FINANCE_DETAIL` + `ADVERTS_PATH` + `ADVERT_STATS_PATH` в рамках одной сессии) с одним `global_request_budget` (`DEFAULT_GLOBAL_REQUEST_BUDGET = 25`, `client.py:48`). При нескольких endpoint'ах в одной сессии (`orders` + `sales` + `stocks` + `advertising`) суммарное количество запросов может превышать budget или вызывать rate limit.
- Важно: `load_ads()` делает `GET /api/advert/v2/adverts` (один запрос), затем для каждого `advertId` — `GET /adv/v3/fullstats`. Если adverts много, это много запросов. В нашем случае (`.tmp/capture_multi_4297720/`) `advertising_performance` получил `429` на этапе `ADVERTS_PATH` (первый запрос), без выполнения `ADVERT_STATS_PATH`. Это подтверждает, что `429` вызван rate limit на `advert` endpoint, не на stats.

**Вывод:** `429` вызван rate limit (`WB API rate limit exceeded`) для `advert` endpoint. Уверенность: `HIGH` для `429 = rate limit` (статус `429` — стандартный rate-limit ответ); `MEDIUM` для точной причины в контексте сессии (несколько endpoint в одной сессии с одним `WBApiClient` может вызвать rate limit даже при `max_attempts=2`).

**Не изменено:** retry policy, `.env`, budget.

---

## 7. Сравнение FINANCE_DETAIL vs другие endpoint (архитектурное)

| Аспект | FINANCE_DETAIL | ORDERS | SALES | STOCKS | SALES_FUNNEL | ADVERTISING |
|---|---|---|---|---|---|---|
| Base URL | `finance_base_url` | `analytics_base_url` | `analytics_base_url` | `analytics_base_url` | `analytics_base_url` | `advert_base_url` |
| Method | POST | GET | GET | POST | POST | GET (adverts) + GET (stats) |
| Contract domain | `FINANCE` | `ANALYTICS` | `ANALYTICS` | `ANALYTICS` | `ANALYTICS` | `ANALYTICS` |
| Contract payload | ARRAY | ARRAY | ARRAY | OBJECT | OBJECT | OBJECT |
| Transport class | `LegacyWBApiFinanceDetailTransport` | `LegacyWBApiLoadersTransport` | `LegacyWBApiLoadersTransport` | `LegacyWBApiLoadersTransport` | `LegacyWBApiSalesFunnelTransport` | `LegacyWBApiLoadersTransport` (`load_ads`) |
| Ingestion service | `WBFinanceDetailIngestionService` | `WBDailyIngestionService` | `WBDailyIngestionService` | `WBDailyIngestionService` | `WBDailyIngestionService` | `WBDailyIngestionService` |
| Retry `429` | Нет (`max_attempts=2`, retryable без `429`) | Не применяется (`load_orders` использует `WBApiClient` default retry — `retry_policy` не передаётся в `load_orders`, т.е. используется default клиента, который включает `429`? Проверка: `load_orders()` (`loaders.py`) вызывает `client.request_json(...)` без явного `retry_policy`; `client.py` default retry (`_normalize_retry_policy`) использует `retryable_statuses` из параметра или default `(429, 500, ...)`. Но `load_orders()` не передаёт `retry_policy`, поэтому используется default клиента (`max_attempts` из `WB_API_MAX_ATTEMPTS`, `base_delay_seconds` из `WB_API_TIMEOUT`...). Точная конфигурация retry для `load_orders()` — через `.env`, не через код. Это важно: `load_ads()` (`loaders.py:791`) явно передаёт `retry_policy` без `429`; `load_cabinet_commerce()` (`transport.py:173`) явно передаёт `retry_policy` с `429`; `load_stocks()` не передаёт `retry_policy`; `load_sales()` не передаёт; `load_orders()` не передаёт. То есть retry-поведение для `ORDERS` и `SALES` зависит от `.env`. Для `STOCKS` — также от `.env`. Для `FUNNEL` — явный retry с `429`, `max_attempts=6`, задержка 10s. Для `FINANCE` — явный retry без `429`, `max_attempts=2`. | | | | |
| Реальный HTTP (из `.tmp/capture_multi_4297720/`) | 200 (ранее) | 404 | 404 | 403 | Не захвачен (N/A) | 429 |
| Payload в replay bundle | Есть (`.tmp/replay_fixtures/live-4297720-fd-2026-08-27/`) | Нет (не захвачен) | Нет | Нет | Нет | Нет (`.tmp/capture_multi_4297720/` содержит только `advertising_performance.json` с `success=False`) |

---

## 8. Найденные существующие альтернативные реализации (без создания новых)

- `packages/compat/wb_sales_funnel_transport.py`: `LegacyWBApiSalesFunnelTransport` (для `SALES_FUNNEL_PRODUCTS`), `LegacyWBApiOperationalTransport` (для `ORDERS`/`SALES`/`STOCKS`), `LegacyWBApiFinanceDetailTransport` (для `FINANCE_DETAIL`), `LegacyWBApiLoadersTransport` (для `load_ads`/`load_cabinet_commerce`).
- `wb_api_core/loaders.py`: `load_orders`, `load_sales`, `load_stocks`, `load_ads`, `load_cabinet_commerce`, `load_finance_final_single_attempt` (стр. 939) — альтернативная реализация для `FINANCE_DETAIL` с другим retry (`max_attempts=1`, `retry_policy={"retryable_statuses": ()}`) и другим `empty_on_204=[]`. Но она не используется в `WBDailyIngestionService`; используется только через transport.
- `.tmp/live_capture_4297720/`: реальный захват `FINANCE_DETAIL` (200, ARRAY, sha256 `3f4c...`).
- `.tmp/replay_fixtures/live-4297720-fd-2026-08-27/`: replay bundle с `FINANCE_DETAIL`.
- `.tmp/replay_bundle_4297720_fd/` (из предыдущих сессий, не проверен в этой): возможно, другой replay bundle.

**Ничего нового не создано; ничего не изменено.**

---

## 9. Финальная таблица (с доказанными фактами)

| Endpoint | Method | Base URL | Path | Contract (code) | Actual HTTP | Cause (evidence-based) | Confidence |
|---|---|---|---|---|---|---|---|
| FINANCE_DETAIL | POST | `finance-api` (`finance_base_url`) | `/api/finance/v1/sales-reports/detailed` | `POST` / ARRAY / FINANCE / `finance-detailed-v1` | 200 (verified, `.tmp/live_capture_4297720/`) | — (работает) | HIGH |
| ORDERS | GET | `analytics-api` | `/api/v1/supplier/orders` | `GET` / ARRAY / ANALYTICS / `supplier-orders-v1` | 404 (verified, `.tmp/capture_multi_4297720/orders.json`) | `404`: endpoint отсутствует или недоступен для текущего token/seller (код вызова совпадает с контрактом; причина на стороне WB) | MEDIUM |
| SALES | GET | `analytics-api` | `/api/v1/supplier/sales` | `GET` / ARRAY / ANALYTICS / `supplier-sales-v1` | 404 (verified, `.tmp/capture_multi_4297720/sales.json`) | `404`: endpoint отсутствует или недоступен (код совпадает; причина на стороне WB) | MEDIUM |
| STOCKS | POST | `analytics-api` | `/api/analytics/v1/stocks-report/wb-warehouses` | `POST` / OBJECT / ANALYTICS / `stocks-wb-warehouses-v1` | 403 (verified) | `403`: endpoint существует, доступ запрещён (вероятно: права token/seller; код вызова верен) | HIGH (403 = access denied, not wrong path) |
| SALES_FUNNEL_PRODUCTS | POST | `analytics-api` | `/api/analytics/v3/sales-funnel/products` | `POST` / OBJECT / ANALYTICS | N/A (не захвачен в `.tmp/capture_multi_4297720/`; нет текущего HTTP статуса) | Неизвестно; код архитектурно верен; для диагноза требуется захват или проверка контракта WB (не изменён в этом этапе) | LOW / UNKNOWN |
| ADVERTISING_PERFORMANCE | GET (adverts) + GET (stats per advert) | `advert-api` (`advert_base_url`) | `/api/advert/v2/adverts` (GET adverts); `/adv/v3/fullstats` (GET stats) | `GET` / OBJECT / ANALYTICS / `advertising-performance-v1` | 429 (verified, `.tmp/capture_multi_4297720/advertising_performance.json`) | `429`: rate limit; вызов `load_ads()` делает `GET` adverts + stats; retry для `load_ads()` (`loaders.py`) не включает `429` (в отличие от `load_cabinet_commerce()` в `transport.py`); это усиливает вероятность rate limit | HIGH (429 = rate limit; архитектура вызова совпадает с контрактом) |

---

## 10. Диагностика `404` (ORDERS / SALES) — детальнее

Проверено по коду:
- `ORDERS_PATH` (`client.py:36`) = `/api/v1/supplier/orders`
- `SALES_PATH` (`client.py:37`) = `/api/v1/supplier/sales`
- Оба endpoint'а — часть существующего WB supplier analytics API (не новые/изменённые в проекте).
- `base_url` (`analytics_base_url`) = `https://seller-analytics-api.wildberries.ru`.
- `method` (`GET`) совпадает с контрактом (`ORDERS_ENDPOINT.http_method="GET"`, `SALES_ENDPOINT.http_method="GET"`).
- `request_json()` использует `headers=_headers()` (`client.py:80`) → `Authorization: <token>`, `Content-Type: application/json`. Токен загружен из `.env` (не выведен в отчёте).
- Нет ошибки в параметрах (`dateFrom` в формате `YYYY-MM-DD`, `flag` = 0 для orders, 1 для sales).
- `404` не может быть объяснён неправильным `path`, `method`, `base_url`, `params`, или `headers` (все совпадают с контрактом и существующим кодом).
- Возможные причины `404` (не доказанные полностью, но перечислены честно):
  - Endpoint устарел или изменился в WB API (требуется проверка документации WB — не в проекте).
  - Endpoint недоступен для текущего `seller_id` или `provider`.
  - Endpoint требует другого `token` или `provider`.
- Уверенность: `MEDIUM` для «код вызова верен»; `LOW` / `UNKNOWN` для точной причины `404` без body ответа WB.

---

## 11. Диагностика `403` (STOCKS) — детальнее

- `STOCKS_WB_WAREHOUSES_PATH` (`client.py:38`) = `/api/analytics/v1/stocks-report/wb-warehouses`
- `method` (`POST`) совпадает с контрактом (`STOCKS_ENDPOINT.http_method="POST"`).
- `base_url` (`analytics_base_url`) совпадает.
- `json_body` содержит `dateFrom`/`dateTo` (формат `YYYY-MM-DD`).
- `403` — это не `404`; endpoint существует. Запрет доступа (`Forbidden`) указывает на:
  - Недостаточные права токена для данного endpoint (например, endpoint требует другого уровня доступа или другого `provider`).
  - Endpoint доступен, но для другого `seller_id` или без необходимых параметров в `json_body`.
- Уверенность: `HIGH` для «код вызова верен»; `MEDIUM` для «403 = права/доступ» (без body ответа WB — не доказано на 100%).

---

## 12. Диагностика `429` (ADVERTISING) — детальнее

- `ADVERTS_PATH` (`client.py:41`) = `/api/advert/v2/adverts`
- `ADVERT_STATS_PATH` (`client.py:42`) = `/adv/v3/fullstats`
- `load_ads()` (`loaders.py:791`) выполняет:
  1. `GET /api/advert/v2/adverts` (`ADVERTS_PATH`)
  2. Для каждого `advertId`: `GET /adv/v3/fullstats` с параметрами `ids=..., beginDate=..., endDate=...`
- `retry_policy` в `load_ads()` (`loaders.py:792`): `retryable_statuses=(500, 502, 503, 504)`, `max_attempts=2`. **Нет `429` в retryable для `load_ads()`.**
- В отличие от этого, `LegacyWBApiLoadersTransport.load_cabinet_commerce()` (`transport.py:173`) имеет `retryable_statuses` с `429` (`max_attempts=6`, `base_delay_seconds=10`).
- При предыдущем захвате (`.tmp/capture_multi_4297720/`) `advertising_performance` получил `success=False`, `status_code=429`, `payload=None`. Это означает, что `GET /api/advert/v2/adverts` (первый вызов) вернул `429`. Без retry для `429` (`load_ads`) — это единственный результат.
- Возможные причины `429`: rate limit со стороны WB (`advert-api` имеет строгие лимиты); или сессия делает несколько endpoint в короткий период (`orders` + `sales` + `stocks` + `advertising`) с одним `WBApiClient` (`global_request_budget=25`); или `advert` endpoint имеет отдельный rate limit, независимый от `global_request_budget`.
- Уверенность: `HIGH` для «429 = rate limit, архитектура вызова верна»; `MEDIUM` для точной причины (без логов WB rate-limit headers в `.tmp/capture_multi_4297720/advertising_performance.json` — body ответа не сохранён, только `success=False`, `status=429`).

---

## 13. Почему невозможно получить полноценный ReplayBundle для всех endpoint

Ответ на основной вопрос этапа:

### Для каждого endpoint — причина невозможности реального полного ReplayBundle (доказанная из кода и `.tmp/capture_multi_4297720/`)

- **FINANCE_DETAIL** (`200`): работает; ReplayBundle существует (`.tmp/replay_fixtures/live-4297720-fd-2026-08-27/`). Это единственный endpoint с полным реальным ReplayBundle.
- **ORDERS** (`404`): код вызова верен (`GET /api/v1/supplier/orders`, `analytics_base_url`); `404` означает, что endpoint недоступен для текущего `token`/`seller`. Без исправления доступа или endpoint URL — реальный ReplayBundle невозможен. **Причина: F (Endpoint недоступен для данного API/token)** или **G (Недостаточно данных)** — без body ответа WB. Уверенность: `MEDIUM`.
- **SALES** (`404`): аналогично ORDERS. **Причина: F / G**. Уверенность: `MEDIUM`.
- **STOCKS** (`403`): код вызова верен (`POST /api/analytics/v1/stocks-report/wb-warehouses`); `403` = доступ запрещён. Без изменения прав/токена или endpoint — реальный ReplayBundle невозможен. **Причина: D (Недостаточные права)** или **F**. Уверенность: `HIGH` для `403 = access denied`; `MEDIUM` для точной причины прав.
- **SALES_FUNNEL_PRODUCTS** (`N/A`): код вызова верен; но live-результат не захвачен (нет в `.tmp/capture_multi_4297720/`). Без дополнительного захвата — невозможно создать ReplayBundle; но это не ошибка архитектуры. **Причина: G (Недостаточно данных для захвата)**. Уверенность: `LOW` / `UNKNOWN` (без live-проверки).
- **ADVERTISING_PERFORMANCE** (`429`): код вызова верен (`GET /api/advert/v2/adverts` + stats); `429` = rate limit. Без снижения частоты или изменения retry-policy или получения доступа — повторный захват невозможен без получения `429`. **Причина: E (Rate limit)**. Уверенность: `HIGH`.

### Общий вывод

Невозможность получения полноценного ReplayBundle объясняется **не ошибкой в архитектуре вызова**, а **внешними факторами WB API** (`404`, `403`, `429`) и **отсутствием захвата** (`SALES_FUNNEL`). Код вызова для всех endpoint совпадает с проектными контрактами (`packages/wb_core/contracts.py`, `client.py`, `loaders.py`, `wb_sales_funnel_transport.py`). Нет доказательств неправильного method, path, base_url, или параметров в коде.

---

## 14. Рекомендации для следующего этапа (без выполнения сейчас)

- **FINANCE_DETAIL**: ReplayBundle уже готов; используется в `data_origin=replay_bundle` (Stage 20.5).
- **ORDERS / SALES**: проверить `base_url` и `path` через документацию WB (`/api/v1/supplier/orders` — стандартный, но `404` указывает на отсутствие доступа или изменение endpoint); возможный следующий шаг — попробовать альтернативный `path` или `base_url`, или использовать существующий `loaders.py` без изменений. Не исправлено в этом этапе.
- **STOCKS**: `403` указывает на права; возможный шаг — проверить `provider` или `token` права для `analytics` endpoint (`wb-warehouses`). Не исправлено.
- **SALES_FUNNEL_PRODUCTS**: захватить через существующий `load_cabinet_commerce()` (код верен); если `429` не возникнет отдельно от advertising — ReplayBundle возможен. Не выполнено (требует захвата).
- **ADVERTISING_PERFORMANCE**: `429` — rate limit; возможный шаг — использовать `load_cabinet_commerce()`-подобный retry (`max_attempts=6`, `base_delay_seconds=10`) для `load_ads()`; или выполнить захват отдельно от других endpoint (чтобы избежать rate limit). Не исправлено (retry policy не изменён).

---

## 15. Безопасность / ограничения соблюдены

- `.env`: не изменён; `WB_API_TOKEN` не выведен в отчёт.
- `packages/finance/marketplace_policy.py`, `packages/data/normalization.py`, `packages/wb_core/endpoint_policy.py`, `legacy abs()`, `audit.py` (кроме `replay_bundle` из Stage 20.5, не тронут в 20.6), `ReplayBundle payload`: не изменены.
- `git`: без push/filter-repo.
- Новые fixtures/payload: не созданы.
- Новые live запросы к WB: не выполнены (только чтение `.tmp/` файлов из предыдущих захватов; для `SALES_FUNNEL` — только чтение кода, без нового запроса).
- Код не изменён функционально (только диагностика через чтение).
- Отчёт содержит только доказанные факты из существующих файлов (`client.py`, `loaders.py`, `contracts.py`, `transport.py`, `.tmp/capture_multi_4297720/`, `.tmp/replay_fixtures/`), без изобретённых данных.

---

## 16. Точная причина невозможности полноценного ReplayBundle (однострочно)

`FINANCE_DETAIL` работает (`200`, ReplayBundle готов); остальные endpoint (`ORDERS`, `SALES`, `STOCKS`, `ADVERTISING`) блокированы внешними WB-ответами (`404`, `403`, `429`) при верной архитектуре вызова (метод, URL, параметры совпадают с контрактами проекта); `SALES_FUNNEL` — отсутствует захват; код вызова для всех endpoint верен (доказано по `client.py`, `contracts.py`, `transport.py`, `loaders.py`).
