# WB AUTOPILOT / ИИ Директор WB
## Полная архитектура платформы автоматизации и управления кабинетами Wildberries

Версия архитектуры: 1.0  
Дата: 22 августа 2026  
Назначение документа: основной технический blueprint для разработки проекта в Codex и GitHub.

---

# 0. Executive Summary

Проект строится не как "ещё один отчёт для WB", а как SaaS-платформа:

> Подключение кабинетов Wildberries → сбор и нормализация данных → единое хранилище → аналитика и расчёт экономики → обнаружение проблем → ИИ-анализ → рекомендации → автоматизация действий → уведомления → контроль результата.

Текущий проект "ИИ Директор ВБ" используется как существующий интеллектуально-аналитический фундамент.

Основные продуктовые контуры:

1. **WB Core** — единый слой интеграции с API Wildberries.
2. **Data Platform** — нормализация, хранение, история, snapshot'ы и качество данных.
3. **Finance & Unit Economics** — комиссии, логистика, реклама, себестоимость, налог, прибыль.
4. **Analytics** — продажи, воронка, товары, реклама, остатки, поиск, возвраты.
5. **AI Director** — объяснение причин, выводы, рекомендации, диалог.
6. **Automation Engine** — правила, события, действия, approval-политики.
7. **Notifications** — Telegram/email/web notifications и digest.
8. **Reporting** — HTML/PDF/Excel/CSV и отчёты для клиента.
9. **Multi-Tenant / Multi-Account** — клиенты, организации, кабинеты, пользователи и роли.
10. **Admin / Operations** — здоровье интеграций, лимиты, ошибки, задания, аудит.
11. **Developer / Agent Layer** — GitHub + Codex-friendly репозиторий, тесты, CI/CD, AGENTS.md, issue-driven development.

Главный принцип:

> Сначала создаём правильную платформу данных и доменную логику. ИИ и автоматизация только используют эти проверенные данные; они не должны напрямую придумывать финансовые цифры или обращаться к WB API хаотично.

---

# 1. Продуктовая концепция

## 1.1. Что получает клиент

После подключения WB API-ключей клиент получает:

- единый dashboard;
- продажи и заказы;
- прибыль и unit economics;
- расходы;
- рекламу;
- остатки;
- товары;
- поисковые показатели;
- возвраты и отмены;
- диагностику проблем;
- AI-рекомендации;
- уведомления;
- автоматические правила;
- отчёты;
- историю изменений.

Главная пользовательская ценность:

> "Не нужно постоянно сидеть в кабинете WB. Система сама собирает данные, объясняет происходящее и сообщает, что нужно сделать."

## 1.2. Принцип "не просто аналитика"

Каждое существенное отклонение проходит путь:

**Наблюдение → Проверка → Причина → Влияние на деньги → Рекомендация → Разрешённое действие → Контроль результата.**

Пример:

Падение заказов → проверка показов/переходов/конверсии/цены/рекламы/остатков → определение вероятной причины → оценка потери → действие → повторная проверка.

## 1.3. Три уровня автоматизации

### Level 1 — Observe
Система только наблюдает и сообщает.

### Level 2 — Recommend
Система предлагает действие, человек подтверждает.

### Level 3 — Autopilot
Для заранее разрешённых действий система выполняет их автоматически.

Нельзя сразу давать ИИ право на произвольные финансово значимые действия.

---

# 2. Архитектурные принципы

## 2.1. Главный принцип

**Одна метрика — один владелец.**

Например:

- финансовые начисления — Finance domain;
- продажи — Sales domain;
- воронка — Analytics/Funnel domain;
- остатки — Inventory domain;
- реклама — Ads domain;
- себестоимость — Product Economics domain.

Остальные модули получают данные через доменные сервисы/API, а не пересчитывают их самостоятельно.

## 2.2. Source of Truth

Разделяем:

### Raw source
Неизменяемые ответы WB API.

### Normalized facts
Приведённые к внутренней схеме данные.

### Derived metrics
Расчётные показатели.

### AI conclusions
Выводы ИИ, которые всегда имеют ссылки на факты/метрики, на которых основаны.

## 2.3. Никогда не использовать AI как калькулятор истины

ИИ не должен самостоятельно вычислять:

- комиссию;
- прибыль;
- ДРР;
- себестоимость;
- налог;
- логистику;
- количество заказов.

Он получает готовые структурированные цифры и объясняет их.

## 2.4. Все операции идемпотентны

Повторный запуск синхронизации, webhook, job или action не должен создавать дубль.

## 2.5. Время

Внутри системы:

- хранить timestamps в UTC;
- отдельно хранить business timezone организации;
- для WB учитывать документацию и даты, определённые конкретным endpoint;
- не смешивать event date, operational date, report date и accounting date.

В текущем проекте уже был найден класс ошибок, связанных с датами, поэтому это должно стать отдельным архитектурным правилом.

## 2.6. AI-friendly repository

Код должен быть устроен так, чтобы Codex мог быстро ориентироваться:

- маленькие модульные файлы;
- явные интерфейсы;
- типизация;
- тесты рядом с доменной логикой;
- AGENTS.md;
- ADR;
- отсутствие скрытой магии;
- понятные зависимости;
- запрет на дублирование бизнес-правил.

---

# 3. Рекомендуемый технологический стек

## 3.1. Backend

Python 3.12+.

Основной framework:

- FastAPI
- Pydantic v2
- SQLAlchemy 2.x
- Alembic

## 3.2. Database

PostgreSQL 16+.

Используется как основная транзакционная БД и хранилище агрегированных фактов для MVP.

Не использовать отдельную OLAP-БД до появления реальной потребности.

При росте объёма возможна миграция аналитических таблиц в ClickHouse/другой OLAP слой, но доменная модель не должна зависеть от этого.

## 3.3. Queue / background jobs

Для первой версии:

- RabbitMQ
- Celery

Альтернатива при упрощённом MVP: Redis Queue.

Предпочтение для масштабируемой версии: RabbitMQ + Celery, потому что нужно много асинхронных задач, retry, routing и отдельные очереди.

Очереди:

- `wb_sync`
- `analytics`
- `finance`
- `reports`
- `ai`
- `automation`
- `notifications`
- `maintenance`

## 3.4. Cache / short-lived state

Redis:

- rate-limit counters;
- locks;
- temporary job state;
- cache;
- idempotency keys;
- session-related short-lived data.

Не использовать Redis как единственный источник бизнес-данных.

## 3.5. Object Storage

S3-compatible:

- MinIO для local/dev;
- S3-compatible cloud/object storage для production.

Хранить:

- PDF;
- XLSX;
- CSV;
- raw WB payload archives;
- экспортированные отчёты;
- AI artifacts.

## 3.6. Frontend

Рекомендуемый стек:

- Next.js
- React
- TypeScript
- component library
- charts library

Frontend должен обращаться к backend API, а не к WB напрямую.

## 3.7. AI

AI Gateway/AI Service отделяет бизнес-логику от конкретного LLM-провайдера.

Поддержать:

- OpenAI;
- при необходимости другие модели;
- разные модели по стоимости/качеству;
- structured outputs;
- tool calling;
- embeddings при необходимости.

## 3.8. DevOps

- Docker
- Docker Compose для локальной разработки
- GitHub
- GitHub Actions
- staging
- production
- health checks
- structured logs
- error tracking
- metrics

Kubernetes на первом этапе не нужен.

---

# 4. Общая схема системы

```text
                        ┌──────────────────────┐
                        │     Web Frontend     │
                        │       Next.js        │
                        └──────────┬───────────┘
                                   │
                              REST / API
                                   │
                        ┌──────────▼───────────┐
                        │      API Backend     │
                        │       FastAPI        │
                        └──────────┬───────────┘
                                   │
           ┌───────────────────────┼────────────────────────┐
           │                       │                        │
     ┌─────▼─────┐          ┌──────▼──────┐         ┌──────▼──────┐
     │ Auth/Tenant│          │ Domain      │         │ AI Gateway  │
     │ & RBAC     │          │ Services    │         │ / Director  │
     └────────────┘          └──────┬──────┘         └─────────────┘
                                    │
                           ┌────────▼────────┐
                           │ Task / Orchestr.│
                           │ Celery + RabbitMQ│
                           └────────┬────────┘
                                    │
       ┌────────────────────────────┼───────────────────────────┐
       │                            │                           │
┌──────▼───────┐            ┌───────▼────────┐          ┌───────▼────────┐
│ WB API Core  │            │ Analytics /    │          │ Automation      │
│ Connectors   │            │ Finance        │          │ Engine          │
└──────┬───────┘            └───────┬────────┘          └───────┬────────┘
       │                            │                           │
       └────────────────────────────┼───────────────────────────┘
                                    │
                              ┌─────▼──────┐
                              │ PostgreSQL │
                              └─────┬──────┘
                                    │
                         ┌──────────▼──────────┐
                         │ Object Storage      │
                         │ PDF/CSV/Raw/Exports │
                         └─────────────────────┘
```

---

# 5. Репозиторий

Рекомендуемая структура:

```text
wb-autopilot/
│
├── apps/
│   ├── api/
│   │   └── main.py
│   ├── worker/
│   │   └── main.py
│   └── web/
│
├── packages/
│   ├── domain/
│   ├── wb_core/
│   ├── finance/
│   ├── analytics/
│   ├── inventory/
│   ├── advertising/
│   ├── products/
│   ├── reports/
│   ├── ai_director/
│   ├── automation/
│   ├── notifications/
│   ├── auth/
│   ├── tenants/
│   ├── auditing/
│   ├── storage/
│   └── common/
│
├── migrations/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   └── e2e/
│
├── docs/
│   ├── architecture/
│   ├── adr/
│   ├── api/
│   ├── domain/
│   ├── runbooks/
│   └── product/
│
├── scripts/
├── infra/
│   ├── docker/
│   ├── github/
│   └── deployment/
│
├── .github/
│   └── workflows/
│
├── AGENTS.md
├── AGENTS.local.md
├── CONTRIBUTING.md
├── SECURITY.md
├── pyproject.toml
├── docker-compose.yml
└── README.md
```

---

# 6. Tenant Model

Базовая иерархия:

```text
Platform
  └── Tenant
       ├── Organization
       │    ├── Users
       │    ├── Roles
       │    └── WB Accounts
       │         ├── Tokens
       │         ├── Products
       │         ├── Orders
       │         ├── Finance
       │         └── Automation rules
       └── Subscription
```

Минимальные сущности:

- Tenant
- User
- Organization
- Membership
- Role
- Permission
- MarketplaceAccount
- ApiCredential
- Subscription
- Plan
- Usage

Обязательное поле `tenant_id` на всех tenant-owned сущностях.

---

# 7. Authentication и RBAC

## 7.1. Пользователь

Поддержать:

- email/password;
- позже OAuth;
- password reset;
- email verification;
- 2FA на коммерческой стадии.

## 7.2. Роли

Минимум:

- owner
- admin
- manager
- analyst
- viewer

## 7.3. Permissions

Например:

```text
account.read
account.manage
finance.read
analytics.read
automation.read
automation.write
automation.execute
reports.read
reports.create
users.manage
billing.manage
```

Автоматическое выполнение должно требовать отдельного permission.

---

# 8. Хранение WB токенов

Токены — секреты.

Требования:

- никогда не логировать полный токен;
- шифровать at rest;
- маскировать в UI;
- отдельная сущность credentials;
- ротация;
- audit trail;
- минимальные права;
- хранить token category/type;
- проверять срок/валидность;
- не передавать токен в AI prompts.

Желательно:

```text
application secret encryption key
        ↓
encrypted credentials in PostgreSQL
```

На масштабировании:

- cloud KMS / Vault.

---

# 9. WB Core

Это главный фундамент.

## 9.1. Adapter architecture

```text
WBClient
 ├── ContentClient
 ├── AnalyticsClient
 ├── StatisticsClient
 ├── FinanceClient
 ├── AdvertisingClient
 ├── MarketplaceClient
 ├── FeedbacksClient
 ├── ReturnsClient
 ├── SuppliesClient
 ├── CommonClient
 └── UserManagementClient
```

Каждый клиент:

- типизирован;
- имеет timeout;
- retry policy;
- rate limit policy;
- structured errors;
- request id;
- metrics.

## 9.2. Не обращаться к requests/httpx из бизнес-логики

Запрещается:

```python
requests.get("https://...")
```

в доменных сервисах.

Только:

```python
wb.statistics.orders(...)
wb.finance.sales_report(...)
```

## 9.3. Rate limiting

Очень важно.

Ограничения WB различаются по endpoint/account.

Нужен:

```text
RateLimitPolicy(
    marketplace,
    account,
    service,
    endpoint,
    limit,
    interval
)
```

Очередь должна сама учитывать ограничения.

429 → backoff → retry.

Не пытаться лечить 429 бесконечными повторениями.

## 9.4. Data freshness

У каждого источника:

```text
source
last_success_at
last_attempt_at
last_watermark
data_lag
status
```

В UI показывать:

> Последнее обновление: 13:40  
> Финансы: 12:00  
> Реклама: 13:00

Не притворяться, что все данные real-time.

---

# 10. Ingestion Pipeline

Общий pipeline:

```text
Scheduler
   ↓
Sync Job
   ↓
Rate limiter
   ↓
WB API
   ↓
Raw response
   ↓
Validation
   ↓
Normalization
   ↓
Deduplication / idempotency
   ↓
Canonical facts
   ↓
Aggregations
   ↓
Quality checks
   ↓
AI/Analytics availability
```

## 10.1. Sync types

- initial sync;
- incremental sync;
- scheduled sync;
- manual sync;
- recovery sync;
- backfill.

## 10.2. Watermarks

Для каждого endpoint хранить:

- last cursor;
- last timestamp;
- last successful page;
- sync status.

При падении продолжать с последнего безопасного watermark.

---

# 11. Raw Data Layer

Raw payload нужно сохранять для:

- повторной обработки;
- расследования расхождений;
- аудита;
- обновления нормализатора без нового запроса к WB.

Структура:

```text
raw_api_events
- id
- tenant_id
- account_id
- source
- endpoint
- requested_at
- response_at
- http_status
- payload_object_uri
- payload_hash
- request_fingerprint
- schema_version
```

Raw payload лучше хранить в object storage, а metadata — в PostgreSQL.

---

# 12. Data Quality Layer

Каждый pipeline должен возвращать:

```text
status:
  OK
  PARTIAL
  STALE
  FAILED
```

Проверять:

- обязательные поля;
- типы;
- даты;
- дубли;
- отрицательные значения;
- неожиданные изменения схемы;
- расхождение агрегатов;
- lag.

## 12.1. Reconciliation

Для финансов:

```text
raw WB data
        ↓
normalized rows
        ↓
aggregated amount
        ↓
comparison with WB totals
```

Если разница выше порога:

> Finance reconciliation warning.

AI не должен строить вывод по неподтверждённым данным без пометки.

---

# 13. Domain: Products

Сущности:

- Product
- ProductVariant
- SKU/NmID
- Brand
- Subject
- Size
- ProductCost
- ProductPrice
- ProductStatus

Поддержать историю:

```text
cost_history
price_history
commission_history
```

## 13.1. Себестоимость

Не зашивать 100 ₽ или любое другое значение в код.

Модель:

```text
ProductCostProfile
- product_id
- unit_cost
- packaging_cost
- inbound_cost
- other_cost
- effective_from
- effective_to
- source
```

Это критично для реальной прибыли.

---

# 14. Domain: Sales

Сущности:

- Order
- OrderItem
- Sale
- Return
- Cancellation
- Buyout
- Delivery
- CustomerOrderEvent

Нужно различать:

- заказ;
- выкуп;
- продажу;
- возврат;
- отмену;
- финансовое начисление.

Нельзя считать их одним числом.

---

# 15. Domain: Analytics

## 15.1. Funnel

Хранить:

- views;
- clicks;
- card transitions;
- add_to_cart;
- orders;
- buyouts;
- cancellations;
- returns.

Расчёт:

```text
CTR
CR_to_cart
CR_to_order
buyout_rate
return_rate
```

Сохранять формулу каждой метрики.

## 15.2. Search

- query;
- frequency;
- position;
- orders;
- visibility;
- dynamics.

## 15.3. Product performance

Для каждого SKU:

```text
revenue
profit
orders
buyouts
conversion
ad_spend
ACOS/DRR
stock_days
return_rate
```

---

# 16. Domain: Finance

Это второй критический фундамент после WB Core.

## 16.1. Finance facts

Хранить детализацию начислений:

- sale amount;
- discount;
- WB commission;
- logistics;
- storage;
- paid services;
- penalties;
- advertising;
- acquiring;
- returns;
- other deductions;
- taxes.

## 16.2. Profit model

Минимальная формула:

```text
Net Revenue
- WB commissions
- logistics
- storage
- advertising
- acquiring
- penalties
- tax
- product COGS
- packaging
- other direct costs
= Contribution / Net Profit
```

Терминологию разделить:

- GMV;
- revenue;
- cash settlement;
- contribution margin;
- net profit.

## 16.3. Finance periods

Не смешивать:

- sale date;
- operational date;
- payout date;
- report date;
- accounting date.

---

# 17. Domain: Advertising

Сущности:

- Campaign
- CampaignItem
- CampaignSpend
- CampaignPerformance
- Bid/Placement settings where available
- Advertising Balance
- Change History

Показатели:

- spend;
- impressions;
- clicks;
- CTR;
- CPC;
- orders;
- revenue;
- DRR/ACOS;
- profit after ads.

## 17.1. Safe automation

Автоматически менять рекламу можно только:

- по правилам;
- в заданных пределах;
- с журналом;
- с rollback, если API позволяет;
- с лимитом изменений в сутки;
- с hard safety ceiling.

---

# 18. Domain: Inventory

Сущности:

- Stock;
- StockHistory;
- Warehouse;
- InTransit;
- Reserved;
- Available;
- Deficit;
- DaysOfCover.

Главный показатель:

```text
DaysOfCover =
available_stock / average_daily_sales
```

Но использовать сглаживание и minimum sample size.

При сезонности возможно:

- weighted moving average;
- separate forecast engine.

---

# 19. Domain: Unit Economics / Product Economics

Для каждого товара:

```text
Selling Price
- discount
- commission
- logistics
- ads
- tax
- COGS
- packaging
- other direct cost
= Profit per unit
```

Хранить:

- current unit economics;
- historical snapshots;
- scenario calculation.

## 19.1. Scenario engine

Позволить спрашивать:

> Что будет, если снизить цену на 10%?

или:

> Сколько останется при DRR 15%?

AI только вызывает scenario engine и объясняет результат.

---

# 20. AI Gateway

AI слой не должен знать внутренние детали каждого WB endpoint.

Архитектура:

```text
AI Director
    ↓
AI Gateway
    ↓
Tool Registry
    ├── get_sales
    ├── get_profit
    ├── get_product_economics
    ├── get_ad_metrics
    ├── get_stock_forecast
    ├── get_finance_reconciliation
    ├── compare_periods
    └── simulate_scenario
```

## 20.1. Tool calling

AI не получает гигантский raw dataset.

Он вызывает точные инструменты.

Например:

```text
get_product_profit(
    account_id,
    product_id,
    period
)
```

## 20.2. Structured answer

AI должен возвращать JSON-схему:

```json
{
  "summary": "...",
  "severity": "high",
  "facts": [],
  "cause": [],
  "financial_impact": {},
  "recommendations": [],
  "actions": [],
  "confidence": 0.87
}
```

Никаких свободных SQL/HTTP запросов из AI.

---

# 21. AI Director

## 21.1. Основные режимы

### Daily Brief
Что произошло за день.

### Executive Analysis
Что происходит с бизнесом.

### Product Analysis
Что происходит с конкретным SKU.

### Finance Analysis
Почему изменилась прибыль.

### Advertising Analysis
Где реклама теряет деньги.

### Inventory Analysis
Где грозит дефицит.

### Incident Analysis
Что пошло не так.

### Conversational
Ответ на вопросы пользователя.

---

# 22. AI Recommendations Engine

Рекомендация должна быть объектом:

```text
Recommendation
- id
- tenant_id
- account_id
- type
- severity
- facts
- expected_impact
- action
- confidence
- created_at
- expires_at
- status
```

Статусы:

- new;
- viewed;
- approved;
- rejected;
- executed;
- failed;
- expired.

---

# 23. Automation Engine

Это отдельный доменный модуль.

## 23.1. Event model

Пример:

```text
sales_drop
profit_drop
stock_low
stockout_risk
high_drr
low_conversion
price_gap
api_error
finance_mismatch
```

## 23.2. Rule

```text
WHEN event
IF conditions
THEN action
WITH safety limits
```

Пример:

```text
IF DRR > 20%
AND spend > 3000
AND orders < threshold
THEN recommend_reduce_ad_budget
```

## 23.3. Actions

Разделить:

### Read actions
Безопасны.

### Recommend actions
Требуют пользователя.

### Write actions
Меняют WB.

### Financial actions
Особо опасные.

Последняя категория по умолчанию только с подтверждением.

---

# 24. Approval Engine

Автоматизация не должна быть all-or-nothing.

Каждое действие классифицируется:

```text
LOW_RISK
MEDIUM_RISK
HIGH_RISK
FINANCIAL
```

Политика организации:

```text
LOW_RISK → auto
MEDIUM_RISK → approve
HIGH_RISK → explicit approval
FINANCIAL → never auto by default
```

Пользователь может ограничить:

- максимальную сумму;
- максимальный процент изменения;
- список кабинетов;
- список товаров;
- время выполнения;
- количество действий в сутки.

---

# 25. Automation Audit

Каждое действие:

```text
who/what initiated
rule_id
before_state
requested_change
API request id
result
after_state if available
timestamp
```

Необходимо иметь полный журнал.

---

# 26. Notifications

События:

- stockout risk;
- profit anomaly;
- API error;
- finance mismatch;
- campaign problem;
- automation executed;
- approval required;
- daily digest.

Каналы:

1. Telegram
2. Email
3. Web
4. позже — другие каналы.

Telegram особенно полезен для MVP.

---

# 27. Reporting Engine

Существующий модуль report_v2 должен быть переведён в reusable package.

Слои:

```text
report_data_builder
        ↓
report_payload
        ↓
template
        ↓
renderer
        ↓
PDF/HTML
```

Типы:

- daily report;
- weekly report;
- monthly report;
- product report;
- finance report;
- advertising report;
- audit report;
- client executive report.

---

# 28. Existing AI Director Migration

Текущий проект не переписывать "с нуля".

Сначала провести inventory:

```text
wb_api_core
report_v2
core_report_bridge
snapshot
normalization
finance
funnel
diagnostics
pdf renderer
```

Для каждого файла определить:

```text
KEEP
ADAPT
MOVE
DEPRECATE
DELETE
```

Правило:

> Работающий проверенный код сначала оборачивается тестами и интерфейсами, и только потом переносится.

Нельзя повторить старый сценарий большого необозримого рефакторинга.

---

# 29. Compatibility Layer

На переходном этапе:

```text
legacy current code
        ↓
Core Bridge
        ↓
new domain interfaces
```

После стабилизации bridge удаляется.

---

# 30. API Backend

Версионирование:

```text
/api/v1/
```

Основные группы:

```text
/auth
/tenants
/users
/organizations
/accounts
/products
/sales
/finance
/analytics
/inventory
/advertising
/ai
/recommendations
/automation
/reports
/notifications
/billing
/admin
/health
```

---

# 31. API Account endpoints

Пример:

```text
POST /api/v1/accounts
POST /api/v1/accounts/{id}/sync
GET  /api/v1/accounts/{id}/health
GET  /api/v1/accounts/{id}/freshness
GET  /api/v1/accounts/{id}/limits
```

---

# 32. Dashboard API

Не заставлять frontend делать десятки запросов.

Создать aggregated endpoints:

```text
GET /api/v1/dashboard/overview
GET /api/v1/dashboard/financial
GET /api/v1/dashboard/products
GET /api/v1/dashboard/alerts
GET /api/v1/dashboard/recommendations
```

Backend сам читает нужные domain read models.

---

# 33. Read Models

Для dashboard допустимы денормализованные таблицы:

```text
daily_account_metrics
daily_product_metrics
daily_finance_metrics
daily_ad_metrics
inventory_snapshots
```

Это повышает скорость интерфейса.

Доменная истина остаётся в canonical facts.

---

# 34. Scheduler

Задачи:

- hourly analytics refresh;
- finance sync;
- inventory sync;
- advertising sync;
- daily report;
- anomaly scan;
- stale data scan;
- token health;
- automation evaluation.

Scheduler не должен выполнять тяжёлую работу сам.

Он создаёт jobs в очереди.

---

# 35. Job System

Job model:

```text
job
- id
- tenant_id
- account_id
- type
- payload
- status
- attempts
- scheduled_at
- started_at
- finished_at
- error_code
- error_message
```

Статусы:

- queued
- running
- retrying
- success
- failed
- dead_letter
- cancelled

---

# 36. Error handling

Ошибки классифицировать:

```text
AUTH_ERROR
RATE_LIMIT
TIMEOUT
WB_TEMPORARY
WB_VALIDATION
SCHEMA_CHANGED
DATA_QUALITY
INTERNAL
AI_ERROR
AUTOMATION_DENIED
```

Retry только для retryable errors.

---

# 37. Observability

## Logs

JSON structured logs.

Fields:

```text
timestamp
service
tenant_id
account_id
job_id
request_id
trace_id
level
event
duration_ms
```

## Metrics

- requests;
- errors;
- 429 rate;
- API latency;
- sync freshness;
- jobs;
- queue lag;
- AI latency;
- AI cost;
- report generation time.

## Audit

Отдельный immutable audit log для security-sensitive операций.

---

# 38. Security

Минимум:

- HTTPS;
- secrets encryption;
- secure cookies/tokens;
- RBAC;
- tenant isolation;
- SQL parameterization;
- rate limiting;
- CSRF protection where applicable;
- SSRF protection;
- upload validation;
- webhook signature validation;
- dependency scanning;
- secret scanning;
- audit log;
- backup policy.

---

# 39. Tenant Isolation

На уровне приложения:

```text
every repository query
must include tenant scope
```

На уровне БД на зрелой стадии можно добавить PostgreSQL Row Level Security.

Запрещено передавать `tenant_id` от клиента как единственный источник доверия.

Tenant определяется из authenticated context.

---

# 40. Billing

Сущности:

- plan;
- subscription;
- invoice;
- usage;
- limits.

Можно тарифицировать:

- число WB кабинетов;
- число товаров;
- количество AI анализов;
- автоматизации;
- отчёты;
- пользователи.

---

# 41. Product Tiers

## START

- 1 кабинет;
- базовая аналитика;
- финансовый расчёт;
- отчёты;
- AI Director.

## PRO

- несколько кабинетов;
- расширенная аналитика;
- мониторинг;
- Telegram;
- рекомендации;
- сценарии.

## AUTOPILOT

- всё PRO;
- automation engine;
- approval policies;
- автоматические действия;
- расширенный аудит.

## AGENCY

- много клиентов;
- много кабинетов;
- роли;
- white-label позже;
- API;
- менеджерская панель.

---

# 42. Agency Mode

Это особенно перспективно для Kwork/агентств.

Организация может иметь:

```text
Agency
 ├── Client A
 │    ├── WB 1
 │    └── WB 2
 ├── Client B
 │    └── WB 3
 └── Client C
      └── WB 4
```

Менеджер видит только назначенных клиентов.

Можно продавать как инструмент:

> "один менеджер управляет десятками кабинетов".

---

# 43. White-label

Не делать в MVP.

Архитектурно предусмотреть:

- tenant branding;
- custom domain;
- logo;
- colors;
- custom email templates;
- PDF branding.

---

# 44. Browser Automation

Не использовать браузерную автоматизацию там, где существует нормальный официальный API.

Основной путь:

**WB API → integration layer.**

Browser automation допускается только как отдельный технический модуль для операций, которые официально не предоставлены API, после отдельной проверки:

- legal/ToS;
- security;
- stability;
- CAPTCHA/2FA;
- breakage risk.

Не смешивать browser automation с WB Core.

---

# 45. AI Cost Control

Каждый AI call записывать:

```text
model
prompt_version
input_tokens
output_tokens
cached_tokens
latency
estimated_cost
purpose
```

Не отправлять модели полный аккаунт каждый раз.

Использовать:

- tools;
- summaries;
- structured facts;
- cached context;
- short-lived analysis context;
- hierarchical analysis.

---

# 46. Prompt/Policy Versioning

Хранить:

```text
prompt_id
version
model
temperature/settings
tool_schema_version
created_at
```

AI вывод должен быть воспроизводим настолько, насколько это возможно.

---

# 47. AI Guardrails

Запретить AI:

- напрямую выполнять произвольный SQL;
- напрямую делать HTTP запросы к WB;
- самостоятельно получать секреты;
- менять настройки без policy check;
- считать важные финансовые показатели "в уме";
- скрывать отсутствие данных.

Обязать AI:

- указывать факты;
- указывать период;
- указывать качество данных;
- указывать confidence;
- указывать, когда данных недостаточно.

---

# 48. Anomaly Detection

Начинать не с ML.

MVP:

- z-score/percent change;
- moving average;
- thresholds;
- seasonal baseline where available;
- minimum sample size.

Примеры:

```text
sales drop > 25%
profit drop > 20%
DRR increase > 30%
CTR drop > 20%
stock days < 5
returns > baseline
```

Потом можно добавить ML/forecasting.

---

# 49. Forecasting

Отдельный сервис позже:

- demand forecast;
- stockout date;
- expected revenue;
- expected profit.

Не ставить forecasting в MVP ядро.

---

# 50. Search/Knowledge Layer

На первом этапе не нужен большой vector database.

Для AI достаточно:

- доменных tools;
- structured facts;
- recent snapshots;
- account/product context.

RAG добавляется, если появится база:

- инструкций;
- SOP;
- клиентских правил;
- карточек;
- документов.

---

# 51. GitHub Workflow for Codex

## Основная идея

Каждая задача = Issue.

Issue должна содержать:

```text
Goal
Context
Files/modules
Acceptance Criteria
Non-goals
Tests
Security impact
Migration impact
```

Это соответствует рекомендуемому подходу OpenAI: Codex лучше работает с хорошо ограниченными задачами и prompts, оформленными как GitHub Issue. Также OpenAI рекомендует постоянный `AGENTS.md` с контекстом проекта. 

## Branches

```text
main
develop
feature/*
fix/*
refactor/*
```

Для критичных изменений:

PR → review → merge.

---

# 52. AGENTS.md

Корень репозитория должен содержать:

```text
Project mission
Architecture rules
How to run
How to test
Database rules
Domain ownership
Forbidden patterns
Security rules
WB API rules
AI rules
Migration rules
Git workflow
Definition of Done
```

Дополнительные AGENTS.md можно размещать внутри отдельных packages.

---

# 53. ADR

Каждое серьёзное архитектурное решение:

```text
docs/adr/0001-modular-monolith.md
docs/adr/0002-postgresql.md
docs/adr/0003-rabbitmq.md
docs/adr/0004-wb-core-boundaries.md
...
```

---

# 54. Codex Task Strategy

Не давать Codex задачу:

> "Построй всю платформу."

Разбивать примерно так:

```text
Epic
 ↓
Feature
 ↓
Issue
 ↓
Implementation
 ↓
Tests
 ↓
PR
 ↓
Review
```

Оптимальный рабочий размер задачи:

- один доменный модуль;
- один use case;
- несколько связанных файлов;
- понятные acceptance criteria.

---

# 55. Codex Roles

Условно можно организовать несколько ролей:

## Architect Agent

Проектирует.

## Backend Agent

Пишет backend.

## Frontend Agent

Пишет UI.

## Data/Finance Agent

Пишет расчёты.

## QA Agent

Пишет тесты и ищет баги.

## Security Agent

Проверяет безопасность.

## Review Agent

Проверяет PR.

## Maintenance Agent

Проверяет технический долг.

Codex умеет работать в многoагентных сценариях и фоновых задачах; OpenAI также описывает orchestration-подход, где очередь задач становится control plane для coding agents. 

---

# 56. CI/CD

Каждый PR:

```text
lint
↓
type check
↓
unit tests
↓
integration tests
↓
contract tests
↓
security checks
↓
build
```

Для production:

```text
merge
↓
build image
↓
deploy staging
↓
smoke tests
↓
manual approval
↓
production
```

---

# 57. Testing Strategy

## Unit

Особенно:

- finance;
- dates;
- commissions;
- unit economics;
- forecasting;
- rules.

## Integration

- PostgreSQL;
- Redis;
- RabbitMQ;
- WB API clients.

## Contract tests

Фиксированные WB payload fixtures.

Очень важно для WB API.

## E2E

Сценарий:

```text
register
→ connect account
→ sync
→ dashboard
→ AI analysis
→ recommendation
→ approval
→ automation
→ audit
```

---

# 58. Golden Fixtures

Существующий проект уже имеет реальные debug artifacts.

Сделать безопасный обезличенный набор fixtures:

```text
tests/fixtures/wb/
tests/fixtures/finance/
tests/fixtures/funnel/
tests/fixtures/reports/
```

Зафиксировать known-good cases.

Это защитит от повторения предыдущих регрессий.

---

# 59. Migration Strategy from Current Project

## Phase A

Freeze legacy writes.

## Phase B

Extract interfaces.

## Phase C

Wrap existing logic with adapters.

## Phase D

Move tested functions into domain packages.

## Phase E

Add regression fixtures.

## Phase F

Remove legacy bridge.

## Phase G

Turn report_v2 into reusable reporting package.

---

# 60. MVP Roadmap

## Phase 0 — Architecture & Repo

Результат:

- repository;
- Docker;
- PostgreSQL;
- Redis;
- RabbitMQ;
- FastAPI;
- CI;
- AGENTS.md;
- ADR;
- base auth.

## Phase 1 — WB Core

- account;
- credentials;
- endpoint clients;
- rate limiting;
- retries;
- raw data;
- sync jobs;
- freshness.

## Phase 2 — Data Core

- normalization;
- products;
- sales;
- finance;
- advertising;
- inventory;
- snapshots.

## Phase 3 — Economics

- COGS;
- commissions;
- logistics;
- ads;
- tax;
- profit;
- unit economics.

## Phase 4 — Dashboard

- account overview;
- finance;
- products;
- advertising;
- stock;
- alerts.

## Phase 5 — AI Director

- tool registry;
- AI gateway;
- structured outputs;
- daily brief;
- product analysis;
- finance analysis;
- conversational mode.

## Phase 6 — Reports

- PDF;
- XLSX/CSV;
- scheduled reports;
- client reports.

## Phase 7 — Automation

- events;
- rules;
- recommendations;
- approvals;
- actions;
- audit.

## Phase 8 — Multi-account

- many cabinets;
- roles;
- agency mode;
- usage limits.

## Phase 9 — Production SaaS

- billing;
- monitoring;
- backups;
- security hardening;
- support tools.

---

# 61. Что не делать в MVP

Не делать одновременно:

- микросервисную архитектуру;
- Kubernetes;
- ML forecasting;
- vector DB;
- white-label;
- mobile apps;
- browser automation;
- десятки маркетплейсов;
- сложный CRM;
- собственную платежную систему.

Сначала доказать ценность на WB.

---

# 62. Масштабирование после MVP

Когда появится нагрузка:

```text
monolith
+
workers
```

→

```text
api
worker-sync
worker-ai
worker-reports
automation-worker
```

При необходимости:

```text
finance-service
analytics-service
ai-service
automation-service
```

Сначала разделять физически только те части, у которых:

- разная нагрузка;
- разные SLA;
- разные deployment cycles;
- разные команды;
- отдельная необходимость масштабирования.

---

# 63. Data Retention

Рекомендуемая политика:

### Raw API
3–12 месяцев в зависимости от тарифа.

### Canonical facts
дольше, например 2–3 года.

### Metrics
3–5 лет при коммерческой необходимости.

### Audit
долго, с отдельной политикой.

### AI logs
ограниченный период; чувствительные данные минимизировать.

---

# 64. Backup

PostgreSQL:

- daily full backup;
- WAL/PITR при production;
- проверка восстановления.

Object Storage:

- versioning;
- lifecycle policies.

Никогда не считать backup успешным без периодического restore test.

---

# 65. Multi-marketplace Future

Доменные интерфейсы можно сделать:

```text
MarketplaceAdapter
```

Реализация:

```text
WildberriesAdapter
OzonAdapter
YandexMarketAdapter
```

Но первый продукт — WB-only.

Не пытаться унифицировать все маркетплейсы на уровне каждой конкретной бизнес-метрики слишком рано.

---

# 66. Product API

После стабилизации можно предоставить внешнее API:

```text
GET /public/v1/accounts
GET /public/v1/products
GET /public/v1/finance
GET /public/v1/analytics
POST /public/v1/automation/rules
```

Это даст дополнительную B2B-модель.

---

# 67. Ключевые KPI самого продукта

Нужно измерять:

### Product KPI

- подключённые кабинеты;
- активные кабинеты;
- активные пользователи;
- DAU/WAU;
- количество AI запросов;
- количество рекомендаций;
- процент рекомендаций, признанных полезными;
- automation executions;
- retention;
- churn;
- MRR.

### Technical KPI

- sync success rate;
- data freshness;
- API error rate;
- 429 rate;
- job success;
- queue latency;
- AI cost per tenant;
- report generation time.

---

# 68. Главная бизнес-метрика

В продукте нужно постепенно прийти к:

> **Сколько денег система помогла клиенту сохранить/заработать.**

Например:

```text
AI detected ad waste: 8,300 ₽
AI prevented stockout: estimated 12,000 ₽ revenue
AI identified margin issue: 5,700 ₽
```

Это намного сильнее для продажи, чем:

> "У нас 27 графиков."

---

# 69. Что именно продавать

Основное позиционирование:

> **ИИ-управляющий кабинетом Wildberries**

Обещание:

> Система сама следит за продажами, прибылью, рекламой и остатками, объясняет проблемы и помогает выполнять действия.

Дополнительный B2B продукт:

> **Платформа автоматизации для агентств и менеджеров WB.**

Дополнительная услуга:

> **Индивидуальная автоматизация кабинета через Kwork/прямые продажи.**

Таким образом Kwork становится источником cashflow и customer discovery, а SaaS — масштабируемым продуктом.

---

# 70. Финальная архитектурная модель

```text
                        CUSTOMER
                           │
                           ▼
                    ┌──────────────┐
                    │ Web Dashboard│
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ FastAPI API  │
                    └──────┬───────┘
                           │
       ┌───────────────────┼───────────────────┐
       ▼                   ▼                   ▼
  Tenant/Auth          Domain Layer         AI Director
       │                   │                   │
       │          ┌────────┼────────┐          │
       │          ▼        ▼        ▼          ▼
       │       Sales     Finance   Ads      AI Gateway
       │       Stock     Funnel    Product      │
       │          │        │        │            │
       └──────────┴────────┴────────┴────────────┘
                           │
                           ▼
                     WB Core Layer
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
           WB API       Scheduler     Raw Data
              │            │            │
              └────────────┼────────────┘
                           ▼
                      Task Queue
                  RabbitMQ + Celery
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
      Sync Jobs        AI Jobs         Automation Jobs
          │                │                │
          └────────────────┼────────────────┘
                           ▼
                     PostgreSQL
                           │
                    Object Storage
                           │
                           ▼
                    Reports / Files


        ┌──────────────────────────────────────────┐
        │             AUTOMATION ENGINE            │
        │                                          │
        │ Event → Rule → Safety → Approval → Action│
        │                       │                  │
        │                       ▼                  │
        │                    WB API                │
        │                       │                  │
        │                       ▼                  │
        │                    Audit                 │
        └──────────────────────────────────────────┘
```

---

# 71. Главные архитектурные решения

1. **Modular monolith first.**
2. **PostgreSQL first.**
3. **RabbitMQ + Celery for background work.**
4. **WB API Core is isolated and typed.**
5. **Raw → Normalized → Derived → AI is strict pipeline.**
6. **One metric — one owner.**
7. **Finance has reconciliation and date semantics.**
8. **AI cannot be source of truth.**
9. **All write actions go through Automation + Policy + Audit.**
10. **Tenant isolation from day one.**
11. **Codex gets small, testable GitHub Issues.**
12. **Existing AI Director is migrated, not blindly rewritten.**
13. **No microservices until load or organizational need proves them necessary.**
14. **No Kubernetes in MVP.**
15. **No direct browser automation where official WB API is available.**

---

# 72. First 25 GitHub Epics / Issues

1. Create repository skeleton.
2. Create architecture ADRs.
3. Setup FastAPI.
4. Setup PostgreSQL.
5. Setup Alembic.
6. Setup Redis.
7. Setup RabbitMQ.
8. Setup Celery workers.
9. Setup CI.
10. Create Auth/Tenant models.
11. Create WB Account model.
12. Create encrypted credentials storage.
13. Create WB Core interface.
14. Implement rate limiter.
15. Implement retry/error policy.
16. Implement raw response storage.
17. Implement sync orchestration.
18. Import current wb_api_core behind adapter.
19. Import finance normalization with regression tests.
20. Import funnel/sales normalization with regression tests.
21. Import report_v2 as reusable package.
22. Create Product/Sales domain.
23. Create Finance domain.
24. Create Dashboard read models.
25. Create AI Tool Registry.

После этих 25 задач можно начинать полноценный product vertical slice:

**подключить WB → собрать данные → показать деньги → задать вопрос ИИ → получить обоснованный ответ.**

---

# 73. Второй пакет задач

26. Inventory domain.
27. Advertising domain.
28. Unit economics.
29. Finance reconciliation.
30. Data freshness dashboard.
31. Product dashboard.
32. Finance dashboard.
33. Advertising dashboard.
34. Inventory dashboard.
35. Alerts.
36. AI Gateway.
37. AI Director daily brief.
38. AI product analysis.
39. AI finance analysis.
40. AI scenario engine.
41. Recommendations.
42. Notification service.
43. Telegram integration.
44. Report scheduling.
45. PDF reports.

---

# 74. Третий пакет задач

46. Event bus/domain events.
47. Automation rules.
48. Rule evaluator.
49. Approval engine.
50. Action registry.
51. Safe action policies.
52. Automation audit.
53. Dry-run mode.
54. Rollback policies where possible.
55. Multi-account dashboard.
56. Agency mode.
57. Usage metering.
58. Billing.
59. Admin operations panel.
60. Production monitoring.

---

# 75. Definition of Done

Issue считается завершённой только если:

- код написан;
- типы проходят;
- тесты написаны;
- тесты проходят;
- миграции проверены;
- логирование предусмотрено;
- security implications проверены;
- нет нарушения domain ownership;
- документация обновлена;
- backward compatibility проверена;
- acceptance criteria выполнены.

---

# 76. Definition of Done for Codex-generated changes

Дополнительно:

- Codex не изменял несвязанные модули;
- diff просмотрен;
- тесты реально запускались;
- не осталось TODO вместо реализации;
- нет новых hardcoded business values;
- нет прямых запросов WB из domain layer;
- нет секретов в коде/logs;
- нет новых дубликатов бизнес-логики;
- PR содержит краткое описание архитектурного решения.

---

# 77. Что должен сделать Codex в самом начале

Первые задачи Codex должны быть не "писать миллион строк", а:

1. Просканировать существующий проект.
2. Составить inventory файлов.
3. Составить dependency map.
4. Найти legacy/unused code.
5. Найти бизнес-логику, которая дублируется.
6. Зафиксировать текущий pipeline.
7. Составить миграционный план.
8. Добавить regression tests к проверенным участкам.
9. Только после этого начинать перенос.

Ключевой запрет:

> Не переписывать работающий pipeline целиком без тестов, snapshot'ов и возможности сравнить старый и новый результат.

---

# 78. Итог

Проект должен стать не "генератором отчёта" и не "ботом для WB", а:

> **операционной платформой управления бизнесом продавца Wildberries с AI Director и безопасным Autopilot.**

Фундамент:

**WB Core + Data Core + Finance**

Интеллект:

**AI Director + Recommendations**

Автоматизация:

**Events + Rules + Approval + Actions**

Интерфейс:

**Dashboard + Reports + Notifications**

Масштабирование:

**Multi-Tenant + Multi-Account + Agency**

Разработка:

**GitHub + Issues + Codex + CI/CD + AGENTS.md**

---

# 79. Официальные источники, использованные для архитектурной проверки

OpenAI Codex:
- https://openai.com/codex/
- https://openai.com/index/introducing-the-codex-app/
- https://openai.com/index/open-source-codex-orchestration-symphony/
- https://openai.com/index/harness-engineering/
- https://openai.com/index/running-codex-safely/
- https://openai.com/business/guides-and-resources/how-openai-uses-codex/

Wildberries API:
- https://dev.wildberries.ru/en/openapi/api-information
- https://dev.wildberries.ru/docs/openapi/analytics
- https://dev.wildberries.ru/openapi/financial-reports-and-accounting
- https://dev.wildberries.ru/en/openapi/reports
- https://dev.wildberries.ru/openapi/promotion

Примечание: лимиты и возможности отдельных WB endpoints необходимо периодически перепроверять по официальной документации перед реализацией конкретного адаптера, потому что они могут меняться.
