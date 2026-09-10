# PROJECT STATUS AUDIT — ИИ Директор ВБ

Дата аудита: **2026-09-04**
Режим: **только чтение**. Ни один файл продукта не изменён в рамках аудита.
Объект: `AI Director 2/` (целевой продукт) + соотношение с legacy (`v3/`, `src/`, `report_v2/`, `wb_api_core/`, `audit/`, `local_audit/`).

Источники плана:
`AI Director 2/docs/architecture/AI_DIRECTOR_2_IMPLEMENTATION_PLAN.md` (12 фаз, вехи C0–C6, карта модулей, карта метрик),
`AI Director 2/CODEX_BACKLOG.md` (EPIC 0–12, 116 задач),
`AI Director 2/WB_Autopilot_Architecture_Codex_v1.md`,
`AI Director 2/AGENTS.md`,
документы-расследования: `FINANCIAL_POLICY_GATES.md`, `STAGE_9_BLOCKER.md`, `STAGE_18_8_BLOCKER.md`, `STAGE_19_REPLAY_BLOCKER.md`, `reports/METRIC_PARITY_REPORT.md`.

---

## Резюме

```text
DONE:        12
PARTIAL:     25
IN PROGRESS:  0
TODO:        16
OBSOLETE:     6
BLOCKED:      4
VERIFY:       2
              ───
Всего оценено пунктов: 65
```

Разбивка по плоскостям оценки:

| Плоскость | DONE | PARTIAL | TODO | BLOCKED | OBSOLETE | VERIFY |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Фазы первоначального плана (12) | 3 | 7 | 0 | 2 | 0 | 0 |
| Вехи совместимости C0–C6 (7) | 2 | 1 | 3 | 1 | 0 | 0 |
| Пункты проверки пользователя (25) | 7 | 10 | 7 | 1 | 0 | 0 |
| EPIC 0–12 из CODEX_BACKLOG (13) | 0 | 7 | 6 | 0 | 0 | 0 |
| Устаревшие пункты плана (6) | — | — | — | — | 6 | — |
| Внеплановые непроверяемые (2) | — | — | — | — | — | 2 |

**Главный вывод одной фразой:** расчётное ядро и данные устроены честно и работают на реальных данных WB, но это пока **внутренний инструмент одного продавца без входа, без истории и без комиссий WB в прибыли**, а не продаваемый мультиарендный продукт.

### Фактический прогон проверок (2026-09-04)

```text
cd "AI Director 2"
$env:PYTHONPATH="D:\WB\Бот ИИ менеджер\GitHub"
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
  → 242 passed, 1 warning in 16.90s

"D:\Program Files\nodejs\node.exe" --check apps/web/static/app.js
  → exit 0

"D:\Program Files\nodejs\node.exe" tests/frontend/audit_screen_states.test.js
  → exit 0, 74 PASS / 0 FAIL
```

Что **не** проходит как «готово» из Definition of Done в `AGENTS.md`: `ruff` и `mypy` в целевом окружении не установлены и не запускаются (см. Е-7), линтер/тайп-чек часть гейта «before completing a task» формально не выполняется.

---

## Таблица 1. Фазы первоначального плана (`AI_DIRECTOR_2_IMPLEMENTATION_PLAN.md`, раздел «Implementation Phases»)

| № | Этап первоначального плана | Фактическое состояние | Статус | Доказательство | Что осталось |
| - | --- | --- | --- | --- | --- |
| 1 | Архитектура / контракты / границы | План, 2 ADR, `AGENTS.md`, статическая граница «нет legacy-импортов вне `compat`», золотая фикстура — всё на месте и зелёное | 🟢 DONE | `docs/architecture/adr/0001,0002`; `tests/unit/test_migration_boundaries.py` в зелёном прогоне 242 | Нечего; документ требует обновления (он описывает Stage 1, проект ушёл далеко вперёд) |
| 2 | Canonical domain models | `TenantAccountScope`, состояния полей `VALUE/MISSING/NOT_APPLICABLE/UNRESOLVED`, Decimal-валидаторы с отклонением float, UTC + бизнес-день `Europe/Moscow` | 🟢 DONE | `packages/wb_core/contracts.py:33`; `packages/data/canonical.py:148-158`; `packages/finance/contracts.py:19-42,107`; `tests/unit/test_finance_contract.py:91` (float отвергается) | Нет значения `not_applicable` в части оперативных метрик — проверено частично |
| 3 | Normalization layer | Сделано шире плана: 5 источников (funnel, orders, sales, stocks, finance detail) + advertising, идемпотентный повторный приём периода | 🟢 DONE | `packages/data/normalization.py` (624+ строк), `packages/wb_core/daily_ingestion.py:180-284`, `tests/unit/test_canonical_normalization.py` | Возвраты/отмены нормализуются только как флаг `is_cancel` (`normalization.py:59,624`), экономически не моделируются |
| 4 | Reconciliation layer | Реально подключён к бою, но сверяется **только один источник** — воронка | 🟡 PARTIAL | `packages/pipeline/service.py:329` `reconcile_sales_funnel_products(funnel)` → `:395,423 reconciled_facts=reconciled`; `packages/reconciliation/contracts.py:130-148` | Нет сверки orders↔sales↔finance↔stocks, нет матрицы fixture-кейсов из гейта фазы 4 |
| 5 | Finance Kernel | Ядро на Decimal, компонентный ledger, traces, статусная машина — готовы и покрыты. «Closed-period policy» из гейта не выполнена: WB не даёт признака закрытия, а рыночные компоненты не извлекаются | 🟡 PARTIAL | `packages/finance/kernel.py`, `contracts.py:19-33` (15 компонентов), `tests/unit/test_finance_kernel.py:96-98,257,319,332` | Подтверждение закрытия периода (сейчас — только ручное подтверждение продавца) и реальный parity закрытого периода |
| 6 | Sales / orders / buyouts | Приём и каноны orders/sales/stocks работают на реальных данных; оперативная read-model есть | 🟡 PARTIAL | `packages/operational/{contracts,service}.py`, `packages/wb_core/operational_ingestion.py`, `tests/unit/test_operational_migration.py` | Нет пакета `packages/sales` (обещан планом как владелец orders/sales/returns), нет домена возвратов, нет событийных репозиториев |
| 7 | Logistics / commission / fees | **Не сделано на уровне данных.** Адаптер из WB finance detail emits единственный компонент — `REALIZED_REVENUE`; поток принимает рыночные компоненты только как `UNRESOLVED` | 🟠 BLOCKED | `packages/finance/finance_detail_adapter.py:77-88` (единственный `components.append`); `packages/finance/flow.py:138-151`; `docs/architecture/STAGE_9_BLOCKER.md:9,19-25` | Снять блокер: redacted raw finance payload с durable `rrdId` + утверждённая field-level sign policy → затем извлечение 6–8 компонентов |
| 8 | Advertising | Расходы по SKU и period-level разделены, попадают в P&L, проверено на реальных данных (77.04 ₽) | 🟡 PARTIAL | `packages/advertising/{contracts,service}.py`, `packages/compat/wb_sales_funnel_transport.py:118-135`, `packages/pipeline/analysis.py:387-401` | Нет CTR/CPC/DRR/ACOS (ни одного совпадения в коде), нет статуса атрибуции как контракта, нет no-write тестов (писать нечем) |
| 9 | Analytics | Есть оперативная модель дня, product economics, агрегация аудита. Нет anomaly, сравнения периодов, поисковых метрик, dashboard read models | 🟡 PARTIAL | `packages/pipeline/analysis.py:472-502`; отсутствие `packages/analytics` (реестр пакетов: 15, см. Е-1) | Пакет `analytics` + владелец для производных отношений; сравнение периодов |
| 10 | Report payload | Версионированная чистая модель есть, собирается только из read-model, рендереры не пересчитывают | 🟡 PARTIAL | `packages/reports/contracts.py:38 schema_version="report-payload-v1"`, `packages/reports/service.py:18-65`, `tests/unit/test_report_payload_migration.py` | Гейт фазы — «semantic payload parity» с legacy — не выполнялся (`METRIC_PARITY_REPORT.md:96` = BLOCKED) |
| 11 | PDF / HTML output | Текст, HTML и PDF рендерятся, PDF отдаётся по HTTP и проверен живым запросом | 🟡 PARTIAL | `packages/reports/renderers.py:30,39,55`; `apps/api/main.py:228`; живая проверка 200 `application/pdf` | Нет доставки (SMTP/Telegram), нет renderer acceptance suite (гейт фазы), нет CSV/XLSX |
| 12 | Full parity / migration | Cutover официально **NO-GO**; legacy-маршрут до сих пор единственный боевой расписательный | 🟠 BLOCKED | `reports/METRIC_PARITY_REPORT.md:5,110-124`; `.github/workflows/daily.yml` (legacy) при отсутствии CI для AD2 | 20–30 redacted raw-бандлов, теневой прогон, решение о retirement |

## Таблица 2. Вехи совместимости C0–C6

| № | Этап первоначального плана | Фактическое состояние | Статус | Доказательство | Что осталось |
| - | --- | --- | --- | --- | --- |
| 13 | C0 `normalize→reconcile→snapshot` parity | Зелёный harness на синтетической фикстуре с manifest-хэшами, тесты на подделку хэша и дрейф | 🟢 DONE | `packages/compat/legacy_snapshot_parity.py:109,161,214`; `tests/unit/test_legacy_snapshot_parity.py:21-23` | Нечего (это и остаётся синтетическим базисом) |
| 14 | C1 raw provenance | `RawObject` с sha256, UTC loaded-at, версией API, tenant-scoped, неизменяемое хранилище, идемпотентность | 🟢 DONE | `packages/wb_core/{contracts,sqlite_repository}.py`, `tests/unit/test_raw_object_repository.py:155-159` | Retention/удаление сырых payload (политика не написана) |
| 15 | C2 canonical funnel parity | Воронка работает end-to-end на реальных данных, но **сравнения с legacy на одном raw-входе нет** | 🟡 PARTIAL | `packages/wb_core/contracts.py:105`; живые данные 2026-09-02; `METRIC_PARITY_REPORT.md:62` = UNRESOLVED | Парный raw-вход и таблица дельт |
| 16 | C3 finance ledger parity (закрытый период, Decimal) | Не выполнимо текущими средствами: нет raw-бандлов с durable `rrdId`, sign policy не утверждена | 🟠 BLOCKED | `METRIC_PARITY_REPORT.md:64-68,78-85`; `STAGE_9_BLOCKER.md:58-60` | См. фазу 7 + требование 1–4 из «Cutover Gate» |
| 17 | C4 report payload parity | Не начиналось | 🔴 TODO | `METRIC_PARITY_REPORT.md:96` (REPORT PAYLOAD = BLOCKED) | Сравнение `report_payload_v2.json` legacy с целевым payload |
| 18 | C5 renderer acceptance | Не начиналось; PDF проверяется только «файл создан / 200 OK / %PDF-» | 🔴 TODO | `tests/unit/test_report_output_migration.py` — текстовые проверки, не acceptance-набор | Критерии сравнения PDF (открытый вопрос плана №7) + набор эталонов |
| 19 | C6 production shadow run | Не начиналось | 🔴 TODO | нет ни одного shadow-сравнения в репозитории | Двухнедельный параллельный прогон legacy и AD2 на одном кабинете |

## Таблица 3. 25 пунктов, которые вы просили проверить особо

| № | Этап первоначального плана | Фактическое состояние | Статус | Доказательство | Что осталось |
| - | --- | --- | --- | --- | --- |
| 20 | WB API / `wb_core` | Контракты, реестр эндпоинтов, ingestion-сервисы — свои. **HTTP-транспорт, retry, rate-limit — легасовые**, вызываются через `compat`; в целевом `wb_core` нет ни одного совпадения `retry|rate_limit|timeout|429` | 🟡 PARTIAL | `packages/compat/wb_sales_funnel_transport.py:16,50,85,149-205` (импорты `wb_api_core.client/loaders`, retry прописан в compat:101,188-189); grep по `packages/wb_core` → 0 совпадений | Свой транспорт с timeout/retry/rate-limit/observability (правило 15 `AGENTS.md`) |
| 21 | raw → normalized → canonical → derived | Цепочка полная, с provenance на каждом уровне и разделением `missing/0/not_applicable` | 🟢 DONE | `packages/pipeline/service.py:329-423`; `tests/unit/test_end_to_end_pipeline.py`; живой аудит 2026-09-02 | Нечего как механизм; не хватает источников (см. №20, №7 фазы) |
| 22 | Finance Kernel | См. фазу 5: арифметика и честность статусов готовы, полнота состава — нет | 🟡 PARTIAL | `packages/finance/kernel.py:156-273`; `tests/unit/test_finance_kernel.py` | Компоненты из WB (фаза 7) |
| 23 | reconciliation | Подключён, но один источник | 🟡 PARTIAL | `packages/pipeline/service.py:329` | Кросс-источниковая сверка + fixture matrix |
| 24 | Golden Fixture / Parity Harness | C0+C1 закрыты, C2 частично, C3–C6 нет | 🟡 PARTIAL | строки 13–19 | Реальные redacted-бандлы |
| 25 | Financial policy gates | Документ есть, часть гейтов реализована кодом (revenue basis, finality, rebill, COGS source), ключевые — **BLOCKED/UNRESOLVED** | 🟠 BLOCKED | `FINANCIAL_POLICY_GATES.md:30` (sign policy = BLOCKED), `:34` (unit COGS allocation из WB-событий = BLOCKED); `kernel.py:115` guard | Решение по знакам; политика возвратов для COGS |
| 26 | COGS + Tax (проверка всей цепочки) | Цепочка подтверждена: UI → `PUT` → SQLite v3 → `FinancialSettings` → `_cogs_allocations`/`tax_input_from_rate` → kernel → traces → `net_profit` → UI | 🟢 DONE | `tests/integration/test_financial_settings_{repository,pipeline,api}.py` (33 теста), `tests/frontend/audit_screen_states.test.js` секция 6; живой прогон: COGS −550, налог −86.34, `net_profit=725.62` | Нет `DELETE`/истории изменений настроек; COGS не корректируется на возвраты (см. №25) |
| 27 | `component_traces` | Есть в контракте результата, несут source/amount/reason/included, попадают в payload и в API/фронтенд | 🟢 DONE | `packages/reports/service.py:46-47`; живой вывод трейсов 2026-09-02 | Трейсы есть только для тех компонентов, которые вообще извлекаются (4 из 15) |
| 28 | `net_profit` | Считается только при `COMPLETE`, никогда при `PARTIAL` — это правильно. Но **состав** = выручка − реклама − COGS − налог, без комиссий и логистики WB | 🟡 PARTIAL | `packages/finance/kernel.py` `_status`; живой кейс: `partial → net_profit=None`, после подтверждения дня → `725.62` | Пока фаза 7 не закрыта, цифра систематически завышена и не может подаваться клиенту как «прибыль» |
| 29 | Sales Funnel | `card_opens` = WB `openCount`, не показы рекламы; конверсии с защитой от отсутствующего знаменателя | 🟢 DONE | `packages/wb_core/contracts.py:79,105`; `packages/data/normalization.py`; `tests/unit/test_canonical_normalization.py` | Метрики конверсии как derived-владелец (фаза 9) |
| 30 | AI-анализ | **В целевом продукте отсутствует полностью.** Ни одного совпадения `openai|anthropic|llm|ai_director|recommendation` в `AI Director 2`. Блок «Что нужно сделать» на экране — детерминированные правила в JS | 🔴 TODO | grep по `AI Director 2` → 0; `apps/web/static/app.js` (правила); легаси-AI живёт в `src/openrouter_client.py:8-27` | `packages/ai_director` + `packages/recommendations` (evidence/confidence/lifecycle), AI не источник истины |
| 31 | report payload | Версионирован, чист, без пересчётов | 🟢 DONE | `packages/reports/contracts.py:38`; `service.py:27-28` (несовпадение scope/даты = ошибка) | Parity с legacy (C4) |
| 32 | PDF / HTML / email | PDF и HTML — есть и работают. Email — **только строки/HTML письма, отправки нет**: ни одного `smtp|telegram|send_mail` в AD2 | 🟡 PARTIAL | `renderers.py:30,39,55`; grep → 0; рабочая отправка есть только в legacy `src/mailer_yandex.py:94-99` | `packages/notifications` + провайдер + журнал доставок |
| 33 | frontend | Vanilla-экран одного дня аудита: 8 блоков + настройки COGS/налог/подтверждение дня, состояния ошибок, авто-перезапрос аудита после сохранения | 🟡 PARTIAL | `apps/web/static/{index.html,app.js,styles.css}`; 74 проверки регрессии экрана | Нет входа, истории, периода/диапазона, остатков, рекламы-кабинета, алертов; нет сборки/типов |
| 34 | backend API | 11 маршрутов: `/healthz`, `/readyz`, `/api/accounts`, `/analysis/{id}`, `/audit/{id}`, `/api/reports/{id}/{date}/report.pdf`, `financial-settings` GET + PUT tax/cogs/finality, статика на `/` | 🟡 PARTIAL | `apps/api/main.py:68-238` | Нет версионирования `/v1`, пагинации, идемпотентной записи, фоновых задач, ограничения частоты |
| 35 | SQLite / persistence | Миграционный механизм с версиями и `down`, WAL/FK, неизменяемый raw, 3 таблицы настроек, тест откатки | 🟢 DONE | `packages/persistence/sqlite.py` (v1–v3), `tests/integration/test_production_foundation.py::test_sqlite_migration_has_a_reversible_rollback`; живая БД: версии `[1,2,3]` | Бэкапы/restore, конкурентная запись из нескольких процессов, retention |
| 36 | авторизация | **Отсутствует.** Ни middleware, ни `Depends`, ни токена/сессии. `_settings_scope()` берёт `account_id` из URL и доверяет ему | 🔴 TODO | `apps/api/main.py:119-127` («Resolve the trusted server-side scope» — но источник доверия = сам вызывающий); grep `jwt|oauth|login|session` → 0 | Аутентификация + серверная привязка caller→tenant + авторизация на каждом эндпоинте |
| 37 | несколько продавцов / tenant isolation | Изоляция навязана в репозиториях (tenant в PK и в WHERE) и покрыта тестами. Но без аутентификации она не защищает от клиента; файловые пути отчётов — только по `account_id` | 🟡 PARTIAL | `packages/persistence/sqlite.py` (FK/PK по tenant+account), `tests/integration/test_financial_settings_repository.py` (tenant isolation), `tests/integration/test_daily_analysis.py:190-193` | Auth (№36) + RBAC/membership + тест «чужой tenant не может ни прочитать, ни записать» |
| 38 | подключение WB кабинета | Аккаунты создаются **только вызовом из кода/теста**: `register_wildberries_seller` не вызывается ни из API, ни из CLI. Токен берётся из переменных окружения процесса | 🔴 TODO | grep `register_wildberries_seller` → только `tests/` и `packages/accounts`; `wb_api_core/token_resolver.py:15-26`; `apps/cli/main.py` (команда только `audit`) | Онбординг-экран/эндпоинт + **per-account** креды (см. Е-2: `credential_ref` не потребляется) |
| 39 | хранение настроек | 3 таблицы, upsert, валидация до записи, человеческие ошибки 400, деньги как Decimal-текст | 🟢 DONE | `packages/settings/sqlite_repository.py`, `apps/api/financial_settings.py`, 25 тестов БД+API | Нет `DELETE`, нет журнала «кто и когда менял», нет прав |
| 40 | история аудитов | **Нет.** Ни таблицы, ни эндпоинта, ни экрана. Результат — только файлы в `runtime/reports/<account>/<date>/` | 🔴 TODO | grep `history|audit_log|list_reports` по `AI Director 2` → только `operational_dates` в reconciliation; `apps/api/main.py:230-231` (поиск файла по пути) | Таблица `audit_runs` + снимок ключевых метрик + список/график по периодам |
| 41 | production deployment | Инфраструктура объявлена, но не подключена: `docker-compose.yml` поднимает только Postgres/Redis/RabbitMQ (ни один из них кодом не читается), Dockerfile нет, CI для AD2 нет, пути к БД захардкожены относительно CWD | 🔴 TODO | `docker-compose.yml:1-39`; `.env.example` (DATABASE_URL/REDIS_URL/BROKER_URL — 0 потребителей в коде); `apps/api/main.py:244,258,275,279,283` `Path("runtime")`; grep по `.github/workflows` → 0 упоминаний AD2 | Dockerfile приложения, env-конфиг, миграции при старте, TLS/домен, запуск по расписанию, откат |
| 42 | безопасность / secrets | Хорошая часть: токены в виде имён env-переменных с отклонением секретоподобных значений, маскирование в raw/`_loader_debug`, тесты на утечку, граница импортов. Плохая: нет шифрования at rest (нечего шифровать, пока токен один на процесс), нет audit-журнала изменений, нет retention/удаления данных, боевой `.env` с `WB_API_TOKEN` лежит вне VCS, но в рабочих копиях | 🟡 PARTIAL | `packages/accounts/contracts.py:21-34`; `packages/wb_core/contracts.py:191`; `tests/unit/test_loader_debug_sanitization.py`, `test_raw_object_repository.py:155-159`; `STAGE_19_REPLAY_BLOCKER.md:42-44` (найдены `.env` с непустым токеном) | Секреты per-tenant + шифрование, журналирование изменений, политика хранения/удаления |
| 43 | monitoring / logging | **Нет.** Ни `logging`, ни `structlog`, ни `getLogger` в целевом коде — только `print()` в worker и CLI. Метрик, trace-id, алертов нет | 🔴 TODO | grep `^import logging|getLogger|structlog` по `AI Director 2` → 0 (кроме `.tmp_trace_probe.py`); `apps/worker/main.py:27` | Структурированные логи, correlation id, метрики длительности/статусов синка, error tracking |
| 44 | коммерческая часть / тарифы / оплата | **Нет.** Ни одного совпадения `billing|subscription|stripe|tariff|plan_id` в целевом коде | 🔴 TODO | grep по `AI Director 2/**/*.py` → 0; `CODEX_BACKLOG.md:21` (014 Subscription skeleton — `[ ]`), `:133` (106 Billing skeleton — `[ ]`) | Тарифы, лимиты, платёжный провайдер, self-service онбординг, удаление данных по запросу |

## Таблица 4. EPIC из `CODEX_BACKLOG.md` (116 задач, все до сих пор с неотмеченным `[ ]`)

| № | Этап первоначального плана | Фактическое состояние | Статус | Доказательство | Что осталось |
| - | --- | --- | --- | --- | --- |
| 45 | EPIC 0 Repository & architecture | Скелет, ADR, AGENTS, FastAPI-приложение, health/readiness — есть. Celery/worker — shell. CI для AD2 — нет. ruff/mypy — не установлены | 🟡 PARTIAL | `apps/worker/main.py` (только health), отсутствие `.github/` в AD2 | 004 tooling, 007 worker, 008 CI, 009 конфиг из env |
| 46 | EPIC 1 Identity & tenancy | Есть `tenant_id`/`account_id` и tenant-scoped репозитории (015 — выполнено). User model, membership/RBAC, подписка, auth/session, audit log — отсутствуют | 🔴 TODO | `packages/accounts/contracts.py:37-61`; grep auth → 0 | 011–014, 016, 017 |
| 47 | EPIC 2 WB Core | Аккаунт-модель, реестр эндпоинтов, raw-хранилище, оркестрация дневного приёма — есть. Шифрование кредов, свой HTTP-клиент, retry-таксономия, rate-limit, sync job, watermark — нет | 🟡 PARTIAL | см. №20, №38, №42 | 019, 021–025, 027 |
| 48 | EPIC 3 Legacy migration | Инвентаризация, карта зависимостей, adapter-извлечение `wb_api_core`, извлечённый report-payload — есть. «Freeze legacy writes» и удаление мёртвых путей — нет | 🟡 PARTIAL | `docs/MIGRATION_INVENTORY.md`, `docs/architecture/LEGACY_MIGRATION_MAP.md`, `packages/compat/README.md` | 031, 033–034 (частично), 037–038 |
| 49 | EPIC 4 Core domains | Products/orders/advertising/finance/unit economics — работают. Returns, inventory-домен, price history, cost history UI — нет | 🟡 PARTIAL | `packages/{products,operational,advertising,finance}`; отсутствие `packages/{sales,inventory}` | 041–042, 046–047 |
| 50 | EPIC 5 Analytics | Funnel, product performance, data-quality status — есть. Search metrics, сравнение периодов, anomaly engine, dashboard read models — нет | 🟡 PARTIAL | `packages/pipeline/analysis.py`; grep `anomaly|period_comparison` → 0 | 049–054 |
| 51 | EPIC 6 Frontend | App shell, dashboard (1 день), finance-блок, products, настройки — есть. Auth screens, Connect WB account, inventory, alerts, recommendations как объект — нет | 🟡 PARTIAL | `apps/web/static/index.html`; `tests/unit/test_mvp_ui_static.py` | 057–058, 063–065 |
| 52 | EPIC 7 AI Director | Не начато в целевом продукте (066–076) | 🔴 TODO | №30 | Весь epic |
| 53 | EPIC 8 Reporting | Payload-модель и PDF — есть. CSV/XLSX, недельный, продуктовый, расписание — нет | 🟡 PARTIAL | `renderers.py`; отсутствие export-эндпоинтов | 079–084 |
| 54 | EPIC 9 Automation | Не начато; write-действий нет ни в одном слое (что соответствует правилу «автоматические изменения запрещены по умолчанию») | 🔴 TODO | grep write/automation → 0 в AD2 | 085–095 (не нужно для MVP, см. Г-5) |
| 55 | EPIC 10 Notifications | Не начато: есть только текст/HTML письма | 🔴 TODO | №32 | 096–100 |
| 56 | EPIC 11 Multi-account / Agency | Не начато, кроме существования нескольких записей аккаунтов в БД | 🔴 TODO | `packages/accounts/sqlite_repository.py:66-94` (list/get by tenant) | 101–107 |
| 57 | EPIC 12 Production | Не начато: monitoring, error tracking, backups, restore test, security/dependency scan, load tests, deployment, runbooks | 🔴 TODO | №41, №43 | 108–116 |

---

## А. Что уже реально готово (подтверждено кодом и зелёными тестами)

1. **Честное расчётное ядро.** Decimal-only, отказ на float, явные состояния `provided/missing/not_applicable/unresolved`, статус `complete/partial/conflict/insufficient_data`, запрет молча превращать отсутствие в ноль. 242 теста pytest.
2. **Неизменяемый raw-слой с provenance.** `RawObject` + SQLite-репозиторий, sha256, UTC loaded-at, версия API, tenant-scoped, идемпотентный повторный приём периода, маскирование секретов (тесты на подделку и на утечку).
3. **Реальный путь «WB → канон → P&L → отчёт» на настоящих данных кабинета.** Подтверждено живым прогоном: продажи, реализованная выручка 1439 ₽, реклама 77.04 ₽, PDF 200 `application/pdf`.
4. **Воронка с корректной семантикой `openCount`** и защитой от расчёта при отсутствующем знаменателе.
5. **Пользовательские финансовые параметры (COGS + налог + подтверждение дня)** — полная цепочка UI→API→БД→вход→ядро→traces→UI, 33 бэкенд-теста + 32 фронтенд-проверки, отработанные на копии боевой БД.
6. **`component_traces` как носитель provenance** каждой строки P&L, включая причину невключения в расчёт.
7. **Версионированный report payload** и три рендерера (text/HTML/PDF) без пересчёта метрик.
8. **Миграционный механизм SQLite** с обратимыми `up/down` и тестом откатки; живая БД имеет версии `[1,2,3]`.
9. **Архитектурная защита границ** — тест, запрещающий legacy-импорты вне `compat`.
10. **Тонкий CLI** однодневного аудита, печатающий статусы и пути артефактов.

## Б. Что частично готово — и чего конкретно не хватает

| Подсистема | Есть | Конкретно отсутствует |
| --- | --- | --- |
| WB-доступ | реестр эндпоинтов, ingestion-сервисы, 5 источников | свой HTTP-клиент, timeout/retry/rate-limit в целевом коде, per-account креды, observability |
| Reconciliation | контракт + сервис + подключение к потоку | сверка больше одного источника; матрица fixture-кейсов |
| Finance Kernel | арифметика, статусы, traces | извлечение 6–8 рыночных компонентов из WB; подтверждённая закрытость периода |
| P&L (`net_profit`) | считается только при `COMPLETE` | состав неполный → цифра завышена; нельзя показывать клиенту как прибыль |
| Advertising | расход по SKU/периоду в P&L | CTR/CPC/DRR/ACOS, статус атрибуции |
| Analytics | operational read model, product economics | пакет `analytics`, сравнение периодов, anomaly, поисковые метрики |
| Frontend | экран аудита + настройки + состояния | вход, история, диапазон дат, остатки, реклама, алерты |
| Backend API | 11 маршрутов, человеческие 400/404/503 | auth, `/v1`, пагинация, идемпотентная запись, rate-limit |
| Tenant isolation | tenant в PK/WHERE + тесты | серверная проверка, что вызывающий вообще имеет право на этот tenant |
| Secrets | маскирование, refs вместо значений, тесты | шифрование at rest, журнал изменений, retention/удаление |
| Настройки | 3 таблицы, upsert, валидация | `DELETE`, история изменений, права |

## В. Что ещё не сделано

### В-1. Критично для первого MVP (без этого нельзя отдавать даже знакомому продавцу)

1. **Аутентификация и авторизация** (№36) — сегодня любой, кто знает UUID аккаунта, читает и **перезаписывает** чужие себестоимости и налоговые ставки и запускает чужие аудиты.
2. **Онбординг кабинета WB** (№38) — нет ни экрана, ни эндпоинта, ни команды CLI для подключения; аккаунты создаются только из кода.
3. **Per-account токен** (Е-2) — `credential_ref` не потребляется; токен один на процесс, второй продавец физически не подключается.
4. **Комиссии и логистика WB в P&L** (фаза 7) — без них «прибыль» не является прибылью.
5. **История аудитов** (№40) — продукт «одна страница на сегодня» не удерживает ценность.
6. **Хотя бы один канал доставки** (№32, EPIC 10) — отчёт должен приходить сам, иначе это не «директор».

### В-2. Необходимо для первой продаваемой версии

7. Тарифы, лимиты, подписка и оплата (№44, EPIC 11).
8. Продакшн-развёртывание: Dockerfile, env-конфиг вместо `Path("runtime")`, миграции при старте, CI на AD2, TLS/домен (№41).
9. Monitoring/logging/error tracking (№43) и бэкапы + тест восстановления (EPIC 12).
10. AI-анализ и рекомендации с evidence/confidence (№30, EPIC 7) — без них нет обещанного «ИИ Директора».
11. Политика хранения и удаления данных продавца, выгрузка его данных по запросу (открытый вопрос плана №8).
12. Возвраты/отмены как экономические факты (EPIC 4/041) — сейчас только флаг `is_cancel`.
13. Acceptance-тесты PDF/HTML (C5) — сегодня «PDF готов» означает «файл открылся».

### В-3. Можно сделать после запуска

14. Сравнение периодов, anomaly engine, поисковые метрики (EPIC 5).
15. Agency-иерархия, назначения менеджеров (101–104).
16. CSV/XLSX-экспорт, недельные и продуктовые отчёты (079–083).
17. Automation Engine с approval/dry-run/rollback (EPIC 9).
18. Postgres вместо SQLite, очереди, горизонтальное масштабирование.
19. Второй маркетплейс (Ozon) — см. Г-4.

## Г. Что из первоначального плана больше НЕ НУЖНО

| № | Пункт плана | Почему больше не нужен |
| - | --- | --- |
| О-1 | ⚪ **EPIC 0/005: Postgres + Redis + RabbitMQ в `docker-compose.yml`** | Реальность: вся персистентность — SQLite с миграциями и тестом откатки; `WB_AUTOPILOT_DATABASE_URL/REDIS_URL/BROKER_URL` не читает ни одна строка кода. Инфраструктура на 3 сервиса для одного продавца — балласт. Нужен либо честный переход на Postgres как задача, либо признание SQLite базой MVP |
| О-2 | ⚪ **Celery/worker-контур (007, 024 sync job, 084 scheduled reports в текущем виде)** | План предполагал брокер и распределённые задачи. Фактически аудит — синхронный вызов на секунды; для MVP достаточно планировщика ОС/одного процесса. Возвращать имеет смысл только при асинхронном запуске по расписанию для многих аккаунтов |
| О-3 | ⚪ **`RawApiEvent` + `RawPayloadRepository` в первоначальной форме** | Заменено реализацией: `RawObject` + `SQLiteRawObjectRepository` с хэшами, scope и неизменяемостью. Продолжать искать «соответствие именам из плана» нечего |
| О-4 | ⚪ **Stage 19 replay-блокер и `ReplayContext` как отдельная ветка** (`STAGE_19_REPLAY_BLOCKER.md`) | Премисы документа отпали: появились `SQLiteAccountRegistrationRepository` с настоящими UUID и `SQLiteRawObjectRepository`, реальный аудит на боевом кабинете выполнен. Требуемое «authoritative tenant/account scope» уже существует. Документ надо архивировать, а не разблокировать |
| О-5 | ⚪ **Ozon-ветка (`audit/`, `local_audit_ozon/`, 5 XLSX)** | В целевом продукте нет ни Ozon RawObject, ни домена; `METRIC_PARITY_REPORT.md:17-20` сам выносит её за рамки. Это отдельный продукт, а не пункт этого плана |
| О-6 | ⚪ **Полное «retirement»-удаление legacy до парити** (038, Compatibility Strategy п.6) | Пока C3–C6 не закрыты, legacy — единственный рабочий боевой маршрут с расписанием. Удаление раньше времени лишит продавца отчётов. Правильный порядок: parity → shadow → только потом retirement |

Отдельно: **правило «не менять legacy» остаётся в силе**, но пункт плана «мигрировать `v3`/`src`/`report_v2` целиком» фактически свёлся к точечному переносу смыслов (финансовое ядро, payload, воронка, COGS/налог) — гнаться за 100 % копированием функциональности legacy не нужно.

## Д. Реальные блокеры (существующие, а не потенциальные)

| № | Блокер | В чём выражается | Что нужно, чтобы снять |
| - | --- | --- | --- |
| Д-1 | **Sign policy рыночных удержаний не утверждена** (`STAGE_9_BLOCKER.md`) | `ppvzSalesCommission`, `deliveryRub`, `acquiringFee`, `deduction`, `rebillLogisticCost` имеют конфликтующие знаки в источнике; legacy применяет `abs()`. Ни один компонент не может войти в P&L | Redacted raw finance payload с durable `rrdId` + поле-за-полем решение о знаке, зафиксированное в `METRICS_PASSPORT.md` и тестах. Это **решение человека**, не код |
| Д-2 | **WB не даёт признака закрытия финансового дня** | `finance_detail_adapter.py:131-140` жёстко проставляет `FinancialFinality.UNKNOWN` с evidence «finance_detail_has_no_explicit_finality_signal» → любой реальный день `partial`, `net_profit=None` | Частично снято сегодня: появилось ручное подтверждение продавца. Полноценно — нужна договорённость, когда день считается закрытым (например, по факту появления выплаты), и её кодификация |
| Д-3 | **Нет ни одного переиспользуемого боевого raw-бандла для parity** | `METRIC_PARITY_REPORT.md:9-15`: 11 snapshot-прогонов и 19 XLSX есть, immutable raw-бандлов с `rrdId` — нет; C3–C6 и фаза 12 стоят | Организованный capture 20–30 дней на реальном кабинете (с ретрайями по 429) + redaction review |
| Д-4 | **Отсутствие аутентификации блокирует любой внешний показ** | `apps/api/main.py:119-127` доверяет `account_id` из URL | Реализация №36. Это не блокер «снаружи», а собственный незакрытый контур — но он прямо запрещает выдачу продукта второму клиенту |
| Д-5 | **WB rate limit на живом токене** | Наблюдались HTTP 429 при пробах (задокументировано в `STAGE_19_REPLAY_BLOCKER.md:56-57`); в целевом коде нет rate-limit | Свой транспорт с backoff + окно capture. Влияет на планирование массового сбора данных, не на корректность расчёта |

## Е. Технический долг

| № | Долг | Факт |
| - | --- | --- |
| Е-1 | **16 обещанных модулей плана ≠ 15 фактических пакетов** | Есть: `accounts, advertising, common, compat, data, finance, operational, persistence, pipeline, products, reconciliation, reports, settings, tax, wb_core`. Нет: `tenancy, storage, sales, inventory, analytics, ai_director, recommendations, automation, notifications`. Часть из них (storage/tenancy) фактически закрыта другими пакетами — это расхождение надо задокументировать, а не «догонять» |
| Е-2 | **`credential_ref` — декоративное поле** | Хранится в `account_registrations.credential_reference`, но не читается ни одним резолвером; токен берётся из env процесса (`wb_api_core/token_resolver.py:15-26`). Создаёт ложное ощущение per-account кредов |
| Е-3 | **`AI Director 2/` целиком не в Git** | `git status --porcelain` → `?? "AI Director 2/"`; последний коммит `53c2f40` — про legacy. Весь целевой продукт (242 теста, 15 пакетов) существует только на этом диске |
| Е-4 | **Мусор в `runtime/` и в корне** | `runtime/finance/finance_*.sqlite3` (3 шт.), `runtime/orders/`, `runtime/operational/`, `runtime/foundation/`, `runtime/first_real_pnl/` — следы разовых проверок, а не продакшн-раскладка. В корне: `.tmp` (717 файлов), `tmp_out` (187), `cabinets` (339), `tmp_*`-каталоги, `artifacts/` |
| Е-5 | **Остался отладочный файл в целевом дереве** | `AI Director 2/.tmp_trace_probe.py` — пережиток прошлой проверки, должен быть удалён (в этом аудите не тронут) |
| Е-6 | **Документы отстают от кода и местами врут** | `README.md` до сих пор описывает «first vertical slice… does not connect to WB, persist data, use AI» и обещает PostgreSQL/Redis-пробы; `.env.example` задаёт несуществующие подключения; `STAGE_19_REPLAY_BLOCKER.md` описывает отсутствие production-репозитория, которое давно устранено; `CODEX_BACKLOG.md` — 116 неотмеченных чекбоксов при 242 зелёных тестах |
| Е-7 | **Линтер и типы не запускаются** | `ruff`/`mypy` не установлены в `.venv`, хотя `AGENTS.md` требует их перед завершением задачи; `pyproject.toml` их декларирует |
| Е-8 | **Дублирование «двух правд» в одном репозитории** | Боевой маршрут legacy (`daily.yml` → `v3.entry` → `report_v2`) и целевой (`packages/pipeline`) считают пересекающиеся смыслы разными кодами. Пока нет shadow-прогона, расхождение не обнаруживается ничем |
| Е-9 | **Параллельные «источники истины» для настроек** | Подтверждение закрытия дня живёт в таблице, а `finality` — в аргументе функции; приоритет разрешён (`analysis.py`), но правило нигде не зафиксировано в `METRICS_PASSPORT.md` |
| Е-10 | **Legacy-код в 465 + 147 + 36 + 43 файлах остаётся единственным источником HTTP** | Любое изменение semantics WB сначала ломает legacy, а не целевой код; граница `compat` это скрывает, но не лечит |

## Внеплановые пункты, которые нельзя подтвердить из репозитория

| № | Пункт | Статус | Почему |
| - | --- | --- | --- |
| V-1 | Фактическое состояние боевого расписания legacy (успешные/упавшие прогоны `daily.yml`, актуальность секретов) | ❓ VERIFY | Нужен доступ к GitHub Actions и к секретам репозитория; из рабочего дерева не проверяется |
| V-2 | Стабильность WB API на боевом токене сейчас (доля 429, задержки finance detail) | ❓ VERIFY | Требует серии живых запросов, а в рамках аудита сетевых вызовов не было |

---

# Что конкретно осталось сделать от текущего состояния до первой продаваемой версии ИИ Директор ВБ

Сегодня продукт — **честный внутренний расчётчик одного дня одного продавца**: данные из WB берутся и складываются корректно, ничего не выдумывается, отчёт собирается в PDF, а пользовательские себестоимость и налог проходят весь путь до прибыли. Продавать это нельзя по четырём причинам, и все они устранимы: **входа нет** (ни аутентификации, ни подключения кабинета), **истории нет**, **прибыль неполная** (комиссии и логистика WB в неё не входят), **доставки нет** (отчёт надо самому открыть).

Правильный порядок работ — сначала перестать быть «одним файлом на одном диске», затем закрыть вход и данные, затем сделать цифру настоящей, затем добавить ценность (AI, доставка), затем коммерцию и эксплуатацию.

### Следующие 10 задач (в этом порядке)

1. **Зафиксировать текущее состояние: коммит `AI Director 2/` в Git** (с проверкой, что в индекс не попадают `.env`, `runtime/`, `.tmp*`). Это не «задача разработки», а снятие риска полной потери продукта — сейчас он не отслеживается вообще. *(Ваше отложенное действие — делаю только по команде.)*
2. **Аутентификация + авторизация.** Серверная привязка вызывающего к `tenant_id`, проверка владения `account_id` на каждом эндпоинте (включая `PUT financial-settings` и `report.pdf`), закрытие публичного `/analysis`. Тесты: «чужой tenant получает 403 и ничего не читает».
3. **Онбординг кабинета WB + per-account креды.** Экран/эндпоинт регистрации, потребление `credential_ref` реальным резолвером, шифрование токена at rest, проверка токена read-only health-запросом к WB. Без этого второй продавец физически не подключается.
4. **История аудитов.** Таблица `audit_runs` (дата, статус, ключевые метрики, пути артефактов) + запись при каждом прогоне + `GET /api/accounts/{id}/audits` + экран истории с переходом к отчёту за любой день.
5. **Разблокировать и закрыть фазу 7: комиссии, логистика, хранение, эквайринг, удержания в P&L.** Шаг 5а — организованный capture 20–30 дней с durable `rrdId` и redaction review; шаг 5б — field-level sign policy в `METRICS_PASSPORT.md` + тесты; шаг 5в — извлечение компонентов в `finance_detail_adapter`. До закрытия — **не называть `net_profit` прибылью ни в UI, ни в PDF** (переименовать подачу в «маржа до удержаний площадки»).
6. **Финансовая закрытость дня как продукт-политика.** Зафиксировать правило (например: день = `final` при подтверждении продавца либо при появлении выплаты по этой дате), отразить в `finality_assessment`, в объяснении на экране и в PDF.
7. **Доставка отчётов: `packages/notifications` + расписание.** SMTP-провайдер (перенос semantics из `src/mailer_yandex.py` через интерфейс), журнал попыток доставки, ежедневный запуск аудита по планировщику, повтор с backoff на 429.
8. **AI-анализ поверх derived-фактов.** `packages/ai_director` (вызов LLM только по read-model, без доступа к кредом и без права считать деньги) + `packages/recommendations` (доказательство, уверенность, lifecycle) + экран рекомендаций. Это возвращает продукту его название.
9. **Продакшн-обвязка.** Dockerfile приложения, конфиг путей/БД/секретов из env вместо `Path("runtime")`, миграции при старте, CI-джоб на `AI Director 2` (pytest + ruff + mypy + node-тесты), structured logging с correlation id, error tracking, бэкап SQLite + тест восстановления, удаление `runtime`-мусора и `.tmp*`.
10. **Коммерческий контур.** Тарифы и лимиты (число кабинетов/глубина истории), подписка и платёж, self-service регистрация, выгрузка и удаление данных продавца по запросу, политика хранения raw-payload. После этого — 2–3 пилота на shadow-режиме рядом с legacy и только потом retirement.

**Минимально-достаточный набор до «можно отдать первому платному клиенту»: задачи 1–6.** Задачи 7–10 делают продукт продаваемым массово, но без 1–6 его нельзя отдать никому.
