# Stage 20.8 — Capture available real WB endpoints into ReplayBundle

**Итог: новых payload'ов получить не удалось — все 4 попытки вернули честный 429 (global per-seller limiter WB). ReplayBundle расширен не был (не чем). Архитектура и код не изменялись. Финансовый аудит на существующем bundle прошёл как `partial` на реальных данных FINANCE_DETAIL.**

## A. Capture matrix

| Endpoint | Attempted | HTTP | Payload | Saved | Reason |
|---|---:|---:|---|---:|---|
| FINANCE_DETAIL | no (existing) | 200 existing | ARRAY | yes | существующий реальный capture; целостность проверена (§C) |
| SALES_FUNNEL_PRODUCTS | yes (1 attempt) | **429** | none | no | global per-seller rate limit (`seller-analytics-api`, штатный `load_cabinet_commerce`, `WB_CABINET_COMMERCE_MAX_ATTEMPTS=1` через env — код не менялся) |
| ORDERS | yes (1 attempt) | **429** | none | no | global per-seller rate limit (`statistics-api` — правильный host, штатный `load_orders`, 429 не ретраится) |
| SALES | yes (1 attempt) | **429** | none | no | global per-seller rate limit (`statistics-api`, штатный `load_sales`) |
| STOCKS | **no** | 403 known | — | no | `BLOCKED_BY_TOKEN_REQUIREMENTS` — «base token without secret is not allowed for this path» (Stage 20.7); запрос не выполнялся |
| ADVERTISING_PERFORMANCE | yes (1 attempt) | **429** | none | no | окно `X-RateLimit-Retry=3582` от 19:31:55Z истекло в 20:31:37Z; попытка выполнена в 21:17Z — снова 429 (глобальный лимит исчерпан); повтор не выполнялся |

- Всего HTTP-запросов к WB за этап: **4** (по одному на endpoint), `client.request_count()=4`, параллельных запросов нет, retry-циклов нет, retry policy не менялась, 429 не обходился.
- `RawCaptureWriter` не создал ни одного raw-файла (capture происходит только при 200): `.tmp/live_capture_multi_2026-09-07/` **не существует** — частичных артефактов нет.
- Сводка попыток: `.tmp/live_capture_multi_2026-09-07_summary.json` (success=false, status=429, rows=0 по всем 4).
- Токен не выводился (`TOKEN_VALUE_PRINTED: False`); `.env` не менялся.

## B. ReplayBundle contents (фактически)

```
.tmp/replay_fixtures/live-4297720-fd-2026-08-27/
  FINANCE_DETAIL   (raw/finance_detail.json)
```

Только один endpoint. SALES_FUNNEL_PRODUCTS/ORDERS/SALES/ADVERTISING в bundle не добавлены, потому что реальных ответов 200 получено не было. Фиктивных данных не создавалось; старые payload под новые даты не копировались.

## C. Integrity (проверено на существующем capture)

| Поле | Значение |
|---|---|
| endpoint | finance_detail |
| payload kind | ARRAY (json.loads → list) |
| sha256 | `3f4c9f2c82844a40c22baab69a114ee12bccbc7f54bf6e743a4d6de78778751c` |
| byte_length | 252441 |
| manifest sha match | True |
| manifest byte match | True |
| operational_date | 2026-08-27 |
| scope | tenant `8eeba4a7-3f9c-457e-90a9-fbd3b28a0318` / account `fed4abfa-bbda-4988-9202-e86d6fcc2b3c` |

## D. Scope (особое требование §10)

- Scope bundle **совпадает с авторитетной регистрацией** `seller_id=4297720` в `AI Director 2/runtime/wb_autopilot.sqlite3` (active=True) — это та БД, из которой веб-маршрут `/audit` берёт аккаунты. UUID не генерировались вручную, ничего не переписывалось.
- В `runtime/foundation/production_foundation.sqlite3` у `4297720` другая регистрация (`55f03958`/`2e398ead`) — зафиксировано как есть, задним числом scope не подменялся.

## E. Replay (offline)

```
WB_API_CALLS_DURING_REPLAY = 0
```
- `load_replay_bundle('live-4297720-fd-2026-08-27')` — успех; 1 raw object; sha256 payload == sha256 файла; ARRAY сохранён как ARRAY; endpoint policy валидация пройдена (`finance_detail: array`); scope авторитетный; сеть не использовалась.

## F. Audit на replay (существующий pipeline, без изменений)

```
data_origin      = replay_bundle
audit_status     = partial
finance_status   = partial
ingestion_status = replay_bundle_ingested
seller_id        = 4297720
raw_references   = 1 (finance_detail)
WB_API_CALLS_DURING_AUDIT = 0
```
- В отличие от Stage 20.5 (где тест использовал БД `production_foundation` с несовпадающим scope → `no_data`), при корректной привязке к `wb_autopilot.sqlite3` pipeline честно обработал реальный FINANCE_DETAIL и вернул **partial**: финансовое ядро посчитало то, что есть, и не превращало отсутствующие источники в ноль.
- Причина `partial`: отсутствуют orders/sales/stocks/funnel/advertising (нет данных), COGS/tax не заданы — штатное поведение kernel.

## G. Missing endpoints — реальные причины

| Endpoint | Причина |
|---|---|
| ORDERS | 429 global per-seller limiter (статистика хост правильный; endpoint жив — Stage 20.7) |
| SALES | 429 global per-seller limiter |
| STOCKS | BLOCKED_BY_TOKEN_REQUIREMENTS (403 «base token without secret is not allowed for this path»; запрос не выполнялся) |
| SALES_FUNNEL_PRODUCTS | 429 global per-seller limiter (endpoint жив: 200 в июльских прогонах) |
| ADVERTISING_PERFORMANCE | 429 (окно retry истекло, но глобальный лимит всё ещё исчерпан) |

## H. Важное ограничение на будущее (зафиксировано, не исправлялось)

Даже при успешном 200 **ORDERS/SALES не смогут попасть в ReplayBundle без изменения `packages/wb_core/endpoint_policy.py`**: их WB-ответ — ARRAY, а `ENDPOINT_ARRAY_POLICY` не содержит для них `"array"`, и replay loader отклонит такой payload (`_accept_payload_for_endpoint`). Изменение `endpoint_policy.py` на этом этапе запрещено — зафиксировано как задача следующего этапа. Для SALES_FUNNEL_PRODUCTS (OBJECT) и ADVERTISING (adverts-ответ — OBJECT) такого барьера нет; для ADVERTISING дополнительно требуется решить вопрос формы payload (raw adverts-ответ vs агрегированный `{"data": rows_raw}`, который персистит `daily_ingestion`) — зафиксировано без решений.

## I. Изменённые файлы

- Создан только этот отчёт: `docs/STAGE_20_8_REPORT.md`.
- Создан диагностический артефакт: `.tmp/live_capture_multi_2026-09-07_summary.json` (вне репозитория кода, в `.tmp/`).
- Код, контракты, endpoint_policy, replay.py, loaders, transports, ingestion, audit, Finance Kernel, normalization, frontend, `.env`, токен, retry policy, legacy `abs()`, ReplayBundle payload, git history — **не изменены**.
