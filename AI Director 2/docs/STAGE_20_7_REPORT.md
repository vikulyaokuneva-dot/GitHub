# Stage 20.7 — Verification of current Wildberries API endpoints (diagnosis only)

**Изменений кода: НЕТ.** Только сопоставление: (1) код проекта, (2) официальные ответы WB API (сохранённые), (3) артефакты legacy-системы.

## 1. Sources

Доступ к официальным источникам:

- `https://dev.wildberries.ru/*` (включая все swagger/openapi JSON-пути) — **недоступен из этой среды**: HTTP 498, анти-бот challenge `wbaas` (`/__wbaas/challenges/antibot/...`). Проверены `/openapi/statistics-api`, `/openapi/analysis-api`, `/openapi/advertising-api`, `/swagger/*/swagger.json`, `/robots.txt` — все 498.
- Wayback Machine — снимков страниц документации WB нет (`archived_snapshots: {}`); CDX API отвечает 403.
- `web_search` — недоступен (ошибка аутентификации инструмента).

**Замена прямому чтению документации:** официальные ответы самого WB API, сохранённые в проекте (каждый содержит `detail`/`code`/`origin`/`requestId` — машиночитаемые официальные сообщения WB, включая ссылку на `https://dev.wildberries.ru/openapi/api-information`):

1. `.tmp/capture_multi_4297720/*.json` — захват 2026-09-07 (Stage 20.3), реальные ответы WB.
2. `cabinets/seller_001/artifacts/wb_api_core/2026-07-26/debug.json` — последний live-прогон legacy-системы с тем же токеном (2026-07-26), официальные тексты ошибок + статусы по каждому endpoint.
3. `cabinets/s/artifacts/wb_api_core/2026-07-11/debug.json` — предыдущий live-прогон (2026-07-11).
4. Код проекта: `wb_api_core/client.py`, `wb_api_core/loaders.py`, `packages/wb_core/contracts.py`, `packages/compat/wb_sales_funnel_transport.py`, `packages/wb_core/daily_ingestion.py`, `packages/wb_core/finance_ingestion.py`.

**Ограничение честности отчёта:** статусы `CURRENT_MATCH` ниже подтверждены фактическими ответами WB API (200/403/429 = endpoint существует; 404 = path не существует на данном host), а не чтением HTML-документации (она недоступна). Это более сильное доказательство актуальности, чем документация: живой API ответил.

## 2. КЛЮЧЕВОЕ ОТКРЫТИЕ: 404 ORDERS/SALES — ошибка диагностического скрипта Stage 20.3, а не endpoint'а

Фактические base URL из сохранённых файлов:

- Stage 20.3 (`orders.json`, `sales.json`): запрос шёл на `https://seller-analytics-api.wildberries.ru` → WB ответил `404 "path not found"` (`origin: ag-contentanalytics`).
- Фактический transport проекта (`wb_api_core/loaders.py:461-501`): `load_orders`/`load_sales` **не передают `base_url`** → `WBApiClient.request_json` использует default `statistics_base_url` = `https://statistics-api.wildberries.ru` (`client.py:61`).
- Live-прогон legacy 2026-07-26 (правильный host, statistics-api): `orders` → **429** `"Limited by global limiter, per seller df304a83-..."` (`origin: s2s-api`), `sales` → **429** (тот же global limiter).

**Вывод:** `/api/v1/supplier/orders` и `/api/v1/supplier/sales` **живые endpoint'ы на statistics-api** (429 = существует, ограничено лимитом; 404 был только потому, что диагностический скрипт Stage 20.3 послал их на analytics-host). Транспорт проекта использует правильный host.

## 3. Таблица сравнения

| Endpoint | Что использует проект (код) | Что отвечает живой WB API (сохранённые доказательства) | Метод | Host (проект) | Path | Request schema | Статус |
|---|---|---|---|---|---|---|---|
| FINANCE_DETAIL | `LegacyWBApiFinanceDetailTransport` → POST `finance_base_url` `/api/finance/v1/sales-reports/detailed`, body `dateFrom/dateTo/period/limit/rrdId` | **HTTP 200**, payload ARRAY, 252441 bytes (2026-08/09 capture) | POST | `finance-api.wildberries.ru` | `/api/finance/v1/sales-reports/detailed` | совпадает | **CURRENT_MATCH** |
| ORDERS | `load_orders` → GET **statistics** `/api/v1/supplier/orders?dateFrom&flag=0` | 2026-07-26 (statistics host): **429** «Limited by global limiter, per seller» → endpoint существует. 2026-09-07 (analytics host, диагностический скрипт): 404 «path not found» | GET | `statistics-api.wildberries.ru` | `/api/v1/supplier/orders` | query `dateFrom`,`flag` | **CURRENT_MATCH** (код проекта); основная причина 404 в Stage 20.3: **WRONG_BASE_URL диагностического скрипта**; текущий реальный блокер: **RATE_LIMIT** |
| SALES | `load_sales` → GET **statistics** `/api/v1/supplier/sales?dateFrom&flag=1` | 2026-07-26 (statistics host): **429** global limiter → существует; 2026-09-07 (analytics host, скрипт): 404 | GET | `statistics-api.wildberries.ru` | `/api/v1/supplier/sales` | query `dateFrom`,`flag` | **CURRENT_MATCH** (код); 404 = WRONG_BASE_URL скрипта; блокер = **RATE_LIMIT** |
| STOCKS | `load_stocks` → POST analytics `/api/analytics/v1/stocks-report/wb-warehouses`, body `nmIds/chrtIds/limit/offset` | 2026-07-26 (analytics host): **403** `"base token without secret is not allowed for this path"` (`origin: s2sauth-ca`); 2026-09-07 (analytics host): **403** `"token does not satisfy additional requirements"` (`origin: ag-contentanalytics`) — 403, а не 404 ⇒ path существует | POST | `seller-analytics-api.wildberries.ru` | `/api/analytics/v1/stocks-report/wb-warehouses` | JSON body (в Stage 20.3 скрипт послал неверный body `dateFrom/dateTo`, но 403 возникает до валидации body) | **ACCESS_RIGHTS** (endpoint актуален; токен без секретного ключа не допускается) |
| SALES_FUNNEL_PRODUCTS | `load_cabinet_commerce` / `LegacyWBApiSalesFunnelTransport` → POST analytics `/api/analytics/v3/sales-funnel/products`, body `selectedPeriod/nmIds/brandNames/subjectIds/tagIds/skipDeletedNm/limit/offset` | 2026-07-26 и 2026-07-11 (analytics host): **HTTP 200**, 24–25 rows (`cabinet_commerce`) — работает с этим токеном | POST | `seller-analytics-api.wildberries.ru` | `/api/analytics/v3/sales-funnel/products` | body совпадает с тем, что реально дал 200 в legacy | **CURRENT_MATCH** (live capture в Stage 20.3 не выполнялся; доказательство работоспособности — июльские прогоны) |
| ADVERTISING_PERFORMANCE | `load_ads` → GET advert `/api/advert/v2/adverts`, затем GET `/adv/v3/fullstats?ids&beginDate&endDate` | 2026-07-26 (advert host): **429** global limiter; 2026-09-07 (advert host): **429** `"rate limit exceeded, retry after the period specified in the X-RateLimit-Retry header"` (`origin: ag-advert`), `X-RateLimit-Remaining: 0`, `X-RateLimit-Retry: 3582` — endpoint существует (429, не 404) | GET | `advert-api.wildberries.ru` | `/api/advert/v2/adverts` + `/adv/v3/fullstats` | query `ids/beginDate/endDate` | **RATE_LIMIT** (endpoint актуален; лимит исчерпан: remaining=0, retry ≈ 1 час) |

## 4. Диагностика 404 ORDERS

- Endpoint **не удалён и не заменён**: на правильном host (`statistics-api`) WB отвечает 429 (существует, лимитируется), а не 404.
- 404 из Stage 20.3 = `path not found` от `ag-contentanalytics` — это корректный ответ analytics-хоста на чужой path. Причина — диагностический скрипт (не транспорт проекта).
- Точный актуальный endpoint (по факту живых ответов): `GET https://statistics-api.wildberries.ru/api/v1/supplier/orders?dateFrom=...&flag=0`.
- Категория: **B (неправильный host) — только в диагностическом скрипте Stage 20.3**; код проекта: **A/B/C/D — нет**; текущий operational-блокер: **F (rate limit)**.
- Уверенность: **HIGH** (два независимых live-доказательства: 404 на analytics + 429 на statistics).

## 5. Диагностика 404 SALES

- Аналогично ORDERS: `GET https://statistics-api.wildberries.ru/api/v1/supplier/sales?dateFrom=...&flag=1` — живой (429 global limiter 2026-07-26).
- 404 = WRONG_BASE_URL диагностического скрипта.
- Категория: **B** (скрипт) + **F** (фактический блокер). Уверенность: **HIGH**.

## 6. Диагностика 403 STOCKS

- Endpoint **актуален**: 403 (не 404) на analytics-host ⇒ path существует.
- Официальный текст WB (2026-07-26): `"base token without secret is not allowed for this path"` (`origin: s2sauth-ca`). Официальный текст WB (2026-09-07): `"token does not satisfy additional requirements"` (`origin: ag-contentanalytics`).
- Разделение (как требует задание):
  - endpoint актуален — **ДА** (доказано 403≠404);
  - доступ к endpoint разрешён — **НЕТ**: текущий `WB_API_TOKEN` выпущен без секретного ключа; WB требует для этого path токен с секретом.
- Категория: **E (API token не имеет необходимых прав)**. Уверенность: **HIGH** (прямой официальный текст ошибки WB).
- Токен и `.env` не проверялись и не менялись; вывод только из текста ответа WB.

## 7. Диагностика SALES_FUNNEL_PRODUCTS

- Проектный вызов (`POST /api/analytics/v3/sales-funnel/products`, analytics host, body `selectedPeriod{start,end}/nmIds/brandNames/subjectIds/tagIds/skipDeletedNm/limit/offset`) идентичен legacy-вызову, который получал **HTTP 200** 2026-07-11 и 2026-07-26 с этим же токеном.
- API version v3 — актуален (живые 200 в июле 2026).
- Формат дат `YYYY-MM-DD` в `selectedPeriod` — принимается (200).
- Live-запрос не выполнялся (не требуется: достаточно двух свежих 200-ответов).
- Категория: **нет проблемы**; статус **CURRENT_MATCH**. Уверенность: **HIGH**.
- Это единственный недостающий endpoint, который можно захватить ПРЯМО СЕЙЧАС без смены токена (с учётом global limiter — см. §11).

## 8. Диагностика ADVERTISING 429

- Оба endpoint'а живые: `GET /api/advert/v2/adverts` и `GET /adv/v3/fullstats` (advert host) — WB отвечает 429, а не 404.
- Официальный ответ WB (2026-09-07): `"rate limit exceeded, retry after the period specified in the X-RateLimit-Retry header"`, заголовки `X-RateLimit-Retry: 3582`, `X-RateLimit-Remaining: 0` (≈ 1 час до восстановления).
- Legacy (2026-07-26): тот же «global limiter, per seller» с `X-RateLimit-Retry: 10299` для statistics-host — WB применяет **глобальный per-seller лимит** между зонами API.
- Retry-механизм проекта: `load_ads` — `max_attempts=2`, retryable `(500,502,503,504)` — **429 не ретраится** (корректно: обход rate limit запрещён политикой проекта); `load_cabinet_commerce` — 429 ретраится с backoff до 6 попыток. Один аудит вызывает adverts 1 раз + stats по чанкам (не «несколько одинаковых запросов одного endpoint» — adverts вызывается один раз за ingest).
- Категория: **F (Rate limit)**. Уверенность: **HIGH**.

## 9. FINANCE_DETAIL контрольный

- `POST https://finance-api.wildberries.ru/api/finance/v1/sales-reports/detailed` → HTTP 200, ответ — **JSON ARRAY** (252441 bytes, sha256 `3f4c9f2c...`), payload сохранён в ReplayBundle без мутации.
- Контроль подтверждает: метод/host/path/body проекта для finance корректны; контракт `PayloadKind.ARRAY` соответствует фактическому ответу WB.
- Статус: **CURRENT_MATCH**. Уверенность: **HIGH**.

## 10. Сохранённые результаты (использованы без повторных запросов)

- `.tmp/capture_multi_4297720/` (2026-09-07): orders 404 (analytics host), sales 404 (analytics host), stocks 403 (analytics host), advertising 429 (advert host) — полные официальные тексты ошибок извлечены выше.
- `cabinets/seller_001/artifacts/wb_api_core/2026-07-26/debug.json`: orders 429, sales 429, stocks 403, ads 429, cabinet_commerce 200, finance_final 200 (правильные hosts).
- Массовых повторных запросов не выполнялось; новых capture не создавалось; ReplayBundle не менялся.

## 11. Root-cause classification (главный вопрос)

Причина невозможности полного ReplayBundle — **комбинация трёх независимых факторов, ни один из них не «устаревший endpoint»**:

| Endpoint | Основная категория | Дополнительно |
|---|---|---|
| FINANCE_DETAIL | — (работает; ReplayBundle есть) | — |
| ORDERS | **F** (global per-seller rate limit на правильном host) | **B** — 404 Stage 20.3 был артефактом диагностического скрипта (analytics host), НЕ кода проекта |
| SALES | **F** (тот же global limiter) | **B** — то же: артефакт скрипта |
| STOCKS | **E** (токен без секретного ключа: официальный текст «base token without secret is not allowed for this path») | — |
| SALES_FUNNEL_PRODUCTS | **нет блокера** (CURRENT_MATCH; 200 в июле) | не захвачен только потому, что не входил в скрипт Stage 20.3 |
| ADVERTISING_PERFORMANCE | **F** (advert-zone лимит: remaining=0, retry≈3582 c; плюс глобальный per-seller лимит) | — |

Категории **A (устаревшие endpoint'ы), C (неправильный method), D (неправильный request schema)** — **не подтверждены ни для одного endpoint'а**: все проектные method/path/host соответствуют живым ответам WB (200/403/429 там, где endpoint существует).

## 12. Точные рекомендации для следующего этапа (НЕ выполнять сейчас)

- **ORDERS** → захватить через существующий транспорт проекта (`load_orders`, statistics host) в окне, когда global limiter свободен (`X-RateLimit-Retry` из последнего 429); НЕ использовать analytics host.
- **SALES** → аналогично ORDERS (`load_sales`, statistics host).
- **STOCKS** → оставить заблокированным до смены токена: требуется WB-токен с секретным ключом («base token without secret is not allowed»); решение на стороне пользователя (перевыпуск токена в кабинете WB). Код менять не нужно — host/path/method верны.
- **FUNNEL** → захватить через существующий `load_cabinet_commerce` (200 доказан); минимальный риск; учитывать global limiter.
- **ADVERTISING** → захватить после истечения `X-RateLimit-Retry` (≈1 час от последнего 429), одиночным запросом, без retry-обхода; либо оставить заблокированным.
- **ReplayBundle** → расширяем существующим механизмом (`RawCaptureWriter` → bundle) без изменения schema: funnel — реалистичен сразу; orders/sales/advertising — после окна лимита; stocks — только с токеном, имеющим секрет.

## 13. Соблюдение ограничений этапа

Код, контракты, `endpoint_policy.py`, `loaders.py`, transport, retry, ReplayBundle, Finance Kernel, normalization, audit, `.env`, токен, legacy, `abs()`, git history — **не изменены**. Live-запросов к WB API в этом этапе **не выполнялось** (только HTTP GET к публичному сайту документации, ответивший 498 анти-ботом, и к Wayback API). Отчёт создан: `docs/STAGE_20_7_REPORT.md`.
