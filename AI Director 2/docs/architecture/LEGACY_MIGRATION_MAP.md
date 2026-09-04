# Legacy Migration Map

## Scope

This map records the legacy production pipeline inspected for Stage 7. It is
an inventory, not a behavior change. Paths outside `AI Director 2/` are legacy
paths relative to the shared repository root.

The scheduled daily route is the current production reference:

```text
.github/workflows/daily.yml
  -> wb_api_core.run_daily
  -> v3.history.api_history_backfill
  -> v3.entry daily
  -> v3 pipeline input -> metrics -> AI -> output
  -> report_v2 PDF/payload/email artifacts -> SMTP
```

`v2-daily-manual.yml -> src.main` is marked deprecated but remains a runtime
consumer until a reviewed cutover. `audit.yml -> audit.run_audit` is an offline
spreadsheet route and is not part of the WB daily target pipeline.

## Production Entry Points

| Legacy file | Entry point | Responsibility | Inputs / outputs | Dependencies | Current owner | Target owner | Action |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `.github/workflows/daily.yml` | scheduled/manual `run` job | Production daily orchestration | WB credentials and seller/date -> core/v3/report artifacts | GitHub Actions, WB, SMTP | Legacy delivery workflow | Future deployment/orchestration | ADAPTER |
| `wb_api_core/run_daily.py` | `run_daily`, `main` | First daily acquisition, normalization, reconciliation, snapshot and artifacts | seller/date -> `snapshot.json`, `debug.json`, `reconciled_rows.json` | client, loaders, filesystem, SQLite price store | `wb_api_core` | `packages/wb_core`, `packages/data`, repositories | MIGRATE |
| `v3/entry.py` | `main`, `run_for_seller`, `run_daily_batch` | Daily/weekly/audit command dispatcher and seller loop | CLI/config/files -> pipeline/job/email dispatch | dynamic stage imports, paths, config, SMTP | `v3` | Application orchestration | REWRITE |
| `v3/pipeline/daily_pipeline_runner.py` | `run_daily_pipeline_for_seller` | Alternate daily stage runner | seller/date -> daily output | all daily stages | `v3` | Application orchestration | RETIRE |
| `.github/workflows/v2-daily-manual.yml` | `python -m src.main` | Deprecated manual daily route | environment/files -> PDF and email | direct WB client, LLM, PDF, SMTP | `src` | None after cutover | RETIRE |
| `src/main.py` | `main` | Previous monolithic daily report | environment and direct sources -> report/PDF/email | `src` clients, AI, renderer, SMTP | `src` | Split domain/output packages | RETIRE |
| `.github/workflows/audit.yml`, `audit/run_audit.py` | `run_audit_mode`, `main` | Offline WB/Ozon spreadsheet audit | XLSX/CSV -> facts, Markdown, PDF, optional email | audit parsers, filesystem, SMTP | `audit` | Product decision pending | UNRESOLVED |

## Acquisition And Raw Artifacts

| Legacy file | Class/function | Responsibility | Inputs / outputs | Dependencies | Current owner | Target owner | Action |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `wb_api_core/client.py` | `WBApiClient` | WB HTTP transport, endpoint calls and token use | requests -> raw endpoint responses | WB APIs, environment | `wb_api_core` | `packages/wb_core` | MIGRATE |
| `wb_api_core/loaders.py` | `load_bundle`, endpoint loaders | Fetches cabinet commerce, orders, sales, stocks, finance, ads, prices and search sources | API/cache -> raw bundle and debug | `WBApiClient`, cache filesystem | `wb_api_core` | `packages/wb_core` plus raw repository | MIGRATE |
| `wb_api_core/artifacts.py` | artifact/cache readers and writers | Writes snapshots/debug/reconciled rows; applies cache fallback | normalized/reconciled data -> seller files | filesystem | `wb_api_core` | repository/storage adapters | ADAPTER |
| `wb_api_core/pricing.py` | `PriceSnapshotStore`, price helpers | Product price history, FBS price evidence and analytics | API values -> SQLite/raw price payloads/analytics | SQLite, filesystem | `wb_api_core` | `packages/products`, storage | ADAPTER |
| `v3/api/wb_client.py`, `v3/wb_client.py`, `src/wb_client.py` | WB client classes/helpers | Parallel direct WB client implementations | API requests -> source payloads | WB APIs, environment | `v3` / `src` | `packages/wb_core` | RETIRE |
| `v3/ingestion/*.py` | API loader functions | Additional live endpoints for v3 pipeline | APIs -> row lists | `v3.api.WBApiClient` | `v3` | source-specific target adapters | ADAPTER |
| `v3/sources/wb_reports_loader.py` | `load_local_reports` | Reads local spreadsheet inputs | XLSX/CSV -> rows and diagnostics | filesystem, spreadsheet parsers | `v3` | import adapter; not daily WB transport | ADAPTER |

## Normalization, Reconciliation And Operational Facts

| Legacy file | Class/function | Responsibility | Inputs / outputs | Dependencies | Current owner | Target owner | Action |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `wb_api_core/normalize.py` | `normalize_bundle` and source normalizers | Maps raw bundle rows to legacy normalized rows | raw bundle -> normalized bundle | legacy field aliases and float parsing | `wb_api_core` | `packages/data` | MIGRATE |
| `wb_api_core/reconcile.py` | `reconcile_bundle` | Computes daily source blocks, date selection, totals and availability | raw/normalized rows -> reconciled blocks | legacy normalized shapes | `wb_api_core` | `packages/reconciliation`, domain packages | REWRITE |
| `wb_api_core/snapshot.py` | `build_snapshot` | Projects reconciled blocks into report snapshot schema | reconciled blocks -> snapshot dict | legacy report schema | `wb_api_core` | temporary compat projection | ADAPTER |
| `v3/normalization/*.py` | normalizers/models | v3 technical row normalization | source rows -> v3 models | v3 source conventions | `v3` | `packages/data` | ADAPTER |
| `v3/domain/event_model.py` | event/KPI builders | Separates report/operational/financial date and KPI views | pipeline rows -> event/KPI dicts | v3 shapes | `v3` | `packages/sales`, `packages/analytics` | REWRITE |
| `v3/metrics/sales_funnel_assembler.py` | funnel assembly | Builds sales-funnel metrics | funnel rows -> funnel metrics | legacy row fields | `v3` | `packages/analytics` | MIGRATE |
| `v3/metrics/sku_fact_table.py` | `build_sku_fact_table` | Joins operational and finance rows into SKU facts | orders/sales/stocks/finance -> SKU rows | mixed contours | `v3` | split Sales/Finance read models | REWRITE |
| `v3/metrics/daily_kpi_assembler.py`, `cabinet_funnel_builder.py` | KPI/funnel builders | Operational daily and funnel aggregates | source rows -> KPI dicts | v3 inputs | `v3` | `packages/analytics` | MIGRATE |
| `v3/metrics/sku_daily_dynamics_builder.py` | history comparison | Builds daily SKU deltas from artifacts | history files -> SKU dynamics | filesystem history | `v3` | analytics repository/read model | ADAPTER |

## Finance And Product Economics

| Legacy file | Class/function | Responsibility | Inputs / outputs | Dependencies | Current owner | Target owner | Action |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `wb_api_core/normalize.py` | `_normalize_finance_final` | Legacy finance-detail field/operation mapping | finance rows -> normalized finance rows | float parsing, aliases | `wb_api_core` | finance source adapter and canonical finance facts | MIGRATE |
| `wb_api_core/loaders.py` | `load_finance_final_with_lag` | Finance detailed fetch, fallback and lag selection | WB finance responses -> finance row bundle | HTTP, cache/fallback | `wb_api_core` | `packages/wb_core` adapter | ADAPTER |
| `v3/financial/finance_loader.py` | `FinanceLoader` | Loads finance report source for v3 | source rows -> `FinancialLoadResult` | v3 source layer | `v3` | finance ingestion adapter | ADAPTER |
| `v3/financial/finance_normalizer.py` | `FinanceNormalizer` | Maps finance aliases into `FinancialRow` | row dict -> float-based finance model | float parsing | `v3` | `packages/finance` input mapping | MIGRATE |
| `v3/financial/snapshot_builder.py` | `FinancialSnapshotBuilder` | Builds financial snapshot/status from v3 data | rows/kernel -> financial snapshot | float totals | `v3` | `packages/finance` result projection | REWRITE |
| `v3/metrics/financial_kernel.py` | `run_financial_kernel` | Legacy account/SKU financial aggregation | finance/cost rows -> float totals and SKU P&L | `src.cogs`, v3 models | `v3` | `packages/finance` | RETIRE |
| `v3/metrics/financial_kpi_assembler.py` | `assemble_financial_kpi` | Selects finance metrics for reports | totals/quality -> report finance KPI | alternate legacy sources | `v3` | finance read model/report projection | REWRITE |
| `src/cogs.py` | COGS loaders/helpers | Reads product cost input and legacy allocation support | files/config -> costs | filesystem | `src` | Product Economics boundary | ADAPTER |
| `v3/analytics/profit_contribution.py` | profit contribution | Derives SKU contribution analysis | financial/SKU rows -> analytics | legacy financial totals | `v3` | `packages/analytics` reading Finance results | REWRITE |

## Advertising, Analytics, AI And Recommendations

| Legacy file | Class/function | Responsibility | Inputs / outputs | Dependencies | Current owner | Target owner | Action |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `wb_api_core/loaders.py` | `load_ads` | Raw advertising source acquisition | WB ads responses -> raw rows | WB API | `wb_api_core` | `packages/wb_core` | MIGRATE |
| `v3/metrics/ads_summary_assembler.py` | `assemble_ads_summary` | Aggregates ad spend/performance summary | ad rows -> summary | float parsing | `v3` | `packages/advertising` | MIGRATE |
| `v3/analytics/advertising_efficiency/*` | engine and attribution helpers | Advertising efficiency and profitability | ads/finance/query rows -> analysis | legacy finance/ads shapes | `v3` | `packages/advertising`, `packages/analytics` | REWRITE |
| `src/ads_loader.py`, `src/ads_keyword_analyzer.py` | ad loaders/analysis | Older advertising flow | APIs/files -> ad metrics | direct clients/filesystem | `src` | `packages/advertising` | RETIRE |
| `v3/analytics/*` | funnel, SKU health, logistics, ABC, search and territory analytics | Derived analytical read models | domain rows/history -> analytics | legacy artifacts and mixed sources | `v3` | `packages/analytics` | MIGRATE |
| `v3/analysis/ai_director.py`, `src/analysis/ai_director.py` | AI analysis | Builds AI interpretation from facts | metrics/facts -> narrative/decisions | LLM client | `v3` / `src` | `packages/ai_director` | ADAPTER |
| `v3/decisions/*`, `src/decisions.py` | decision runtime | Recommendation generation and status | analytics -> decision data | v3/source models | `v3` / `src` | `packages/recommendations` | REWRITE |
| `src/action_orchestrator.py` | action suggestions | Suggestion orchestration | decisions -> candidate actions | legacy state | `src` | `packages/automation` | ADAPTER |
| `v3/memory/*`, `v3/history/*` | outcome/history storage | Persists history and decision outcomes | job/facts -> JSON/JSONL/history | filesystem | `v3` | persistence/audit model | ADAPTER |

## Reports, PDF, Email And Diagnostics

| Legacy file | Class/function | Responsibility | Inputs / outputs | Dependencies | Current owner | Target owner | Action |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `v3/core_report_bridge.py` | snapshot bridge functions | Reads core snapshot/debug artifacts into v3 | seller filesystem -> bridge payload | filesystem artifact contract | `v3` | `packages/compat` | ADAPTER |
| `v3/pipeline/daily_input_stage.py` | `run_daily_input_stage` | Combines files/API/core snapshot and input diagnostics | files/APIs -> pipeline context | dynamic `sync_from_entry`, filesystem | `v3` | application input orchestration | REWRITE |
| `v3/pipeline/daily_metrics_stage.py` | `run_daily_metrics_stage` | Runs financial and operational legacy metrics | pipeline context -> metrics context | finance, analytics, dynamic globals | `v3` | orchestration over target domains | REWRITE |
| `v3/pipeline/daily_ai_stage.py` | `run_daily_ai_stage` | Builds facts and invokes decision layer | metrics -> AI context | v3 AI/decisions | `v3` | application orchestration | ADAPTER |
| `v3/pipeline/daily_output_stage.py` | `run_daily_output_stage` | Selects report generation and artifact/history stages | context -> report/PDF/email files/job | `report_v2`, bridge, filesystem | `v3` | application output orchestration | REWRITE |
| `report_v2/builders/report_payload_builder.py` | `build_report_payload_v2` | Builds report read payload and discovers secondary artifacts | snapshot/debug/artifacts -> payload dict | filesystem, legacy shapes | `report_v2` | `packages/reports` | REWRITE |
| `report_v2/run_report_v2.py` | `build_report_v2_from_files` | File-oriented payload/PDF/email artifact runner | snapshot/debug paths -> output files | filesystem, builder, renderer | `report_v2` | report delivery adapter | ADAPTER |
| `report_v2/renderers/pdf_renderer_v2.py` | `write_report_pdf_v2` | Renders PDF from report payload | payload -> PDF | ReportLab/filesystem | `report_v2` | `packages/reports` renderer | MIGRATE |
| `report_v2/renderers/email_renderer_v2.py` | HTML/text renderers | Renders email representations | payload -> HTML/text files | filesystem | `report_v2` | `packages/reports` / notifications | MIGRATE |
| `v3/outputs/daily_report_stage.py` | `run_daily_report_stage` | Legacy report content projection | metrics context -> report payload fields | dynamic globals | `v3` | report payload projection | RETIRE |
| `v3/outputs/daily_email_stage.py` | `run_daily_email_stage` | Legacy email wording/partial-state presentation | context -> email fields | dynamic globals | `v3` | notifications presentation | ADAPTER |
| `v3/outputs/daily_artifacts_stage.py`, `daily_history_stage.py` | artifact/history stages | Writes job, facts, warning and history artifacts | context -> seller files | filesystem | `v3` | repository/output adapters | ADAPTER |
| `v3/outputs/email_sender_orchestrator.py`, `src/mailer_yandex.py` | email orchestration/SMTP transport | Sends report email with failure normalization | PDF/body/env -> SMTP result | SMTP, environment | `v3` / `src` | `packages/notifications` | ADAPTER |
| `src/pdf_report.py` | older PDF renderer | Renders deprecated report format | facts -> PDF | ReportLab/filesystem | `src` | None after v2 retirement | RETIRE |

## Mapping Rules And Stage Order

- A target domain package never imports a legacy module. Transitional reads are
  explicit `packages.compat` adapters only.
- `MIGRATE` means transfer confirmed semantics with fixture parity; it does not
  authorize copy/paste or a new formula.
- `REWRITE` means the legacy unit mixes owners, relies on dynamic globals, or
  combines domain calculation with I/O. Its public behavior must be decomposed
  before migration.
- `ADAPTER` means preserve the legacy boundary temporarily while the target
  consumes a typed contract or repository interface.
- `RETIRE` means no target reimplementation is planned; removal requires a
  caller audit and reviewed cutover.
- `UNRESOLVED` requires a product or architecture decision before migration.

Stage 8 is implemented: `FINANCE_DETAIL` raw objects normalize into
`CanonicalFinanceDetailRecord`; its adapter creates `realized_revenue` only
from a classified finance sale's `retailAmount`. The buyer discounted and
seller payout views are retained separately in `FinancialInput.revenue_views`.
The adapter rejects unclassified rows, returns, missing `retailAmount`, and
records with no durable `rrdId` as authoritative revenue inputs.

Revenue consumers remain inventory items for later migration: the legacy
financial KPI/report projection must be rewritten in Stage 16, while legacy
kernel and snapshot builders are scheduled for retirement/rewrite after
component parity. No target domain package imports those consumers.

## Stage 10 Operational Migration

Stage 10 migrates operational facts independently of the blocked marketplace
deduction work in Stage 9. `orders`, `sales`, and warehouse `stocks` now have
minimal raw-object contracts, structural canonical records, deterministic
normalizers, and an operational daily read model in `packages/operational`.
All retain the raw-object identifier, UTC retrieval timestamp, tenant/account
scope, source-record index, and requested operational date.

The operational read model owns only its source metrics: order quantity comes
from orders, sales quantity from sales, available stock from warehouse stock
snapshots, and funnel counts from `sales_funnel_products`. `inWayToClient` and
`inWayFromClient` stay separate from available stock. Operational sales remain
operational facts, never financial realization or COGS evidence.

`buyoutCount` and `buyoutSum` are retained in the existing sales-funnel
canonical record solely as cohort metrics. They are never converted into an
order or sales event and remain separate from the operational sales owner.
Missing/null/empty values remain explicit canonical states; a missing metric
is represented as missing, never zero. The sales-funnel endpoint semantics are
not changed.

## Stage 11 Advertising Migration

Stage 11 adds `advertising_performance` raw/canonical normalization and the
`packages/advertising` read model. Each record is retained at exactly one
evidence-backed attribution scope: `direct_sku`, `campaign`, `period`,
`associated`, or `unknown`. Only `direct_sku` with `nmId` is exposed in the
SKU spend map. All other scopes remain at their original scope and cannot be
allocated to SKU by the target implementation. Missing spend remains missing,
not zero.

## Stage 12 Product Economics / COGS Migration

Stage 12 adds `packages/products` with two explicit input boundaries:
`ProductCostProfile` for effective-dated seller-provided unit COGS/packaging,
and `DirectPeriodCogsInput` for a signed external period COGS total. Neither
reads WB operational data. There is no return reversal, cancellation
allocation, partial-return allocation, or use of `buyoutCount`/`buyoutSum` as
a COGS event. Only direct-period COGS adapts to `FinancialComponent.COGS`.

## Stage 13 Tax Migration

Stage 13 adds `packages/tax`. `SourcedTaxInput` accepts only an explicitly
sourced signed tax amount and its provenance. Missing or unresolved tax must
carry a diagnostic and maps to a missing/unresolved Finance component without
an amount. No rate, revenue base, or legacy 6% fallback exists in the target
boundary.

## Stage 14 Financial Finality / Status

Stage 14 adds `packages.finance.status.assess_financial_finality`. It treats
legacy `available`, date alignment, and row-count notions as availability or
lag heuristics only, not finality evidence. A financial row without explicit
finality is `partial`; conflicting evidence is `conflict`; absent facts are
`insufficient_data`; an explicitly final source can be complete only when it
is not marked lagged. Financial lag is now carried into `FinancialInput` so
the Finance Kernel cannot emit a complete result for a lagged source.

## Stage 15 Integrated Financial Flow

`packages.finance.flow.calculate_integrated_financial_flow` composes canonical
Finance Detail revenue, reconciliation, explicit finality, advertising,
direct-period COGS, and sourced tax into one `FinancialInput` and
`FinancialResult`. Marketplace components are admitted only as explicit
`UNRESOLVED` diagnostics and stay excluded from authoritative P&L. Missing tax
and unresolved marketplace values therefore keep the result partial rather
than becoming zero.

## Stage 16 Report Payload

`packages.reports` introduces a typed immutable `ReportPayload`. It projects
already-calculated Operational, Financial, and Advertising domain results. The
payload has no filesystem input and owns no business calculation: every metric
names its existing domain owner. The legacy `report_v2` builder remains an
unmodified compatibility reference; its hidden artifact discovery and inline
calculations are not carried into the target report path.

## Stage 17 Output

`packages.reports.renderers` provides deterministic text, HTML, and PDF
renderers whose sole input is `ReportPayload`. They perform formatting only,
read no artifacts, and do not compute revenue, profit, margin, COGS, tax,
advertising, or finance status.

## Stage 18 End-to-End Target Pipeline

`packages.pipeline.run_pipeline` is the first composed target path:
`RawObjectRepository -> Canonical -> Reconciliation -> Operational -> Finance
-> Advertising -> Product Economics -> Tax -> Financial Status -> ReportPayload`.
It has synthetic coverage for a complete explicit-input flow, partial and
unresolved marketplace flow, financial-lag flow, no-finance operational flow,
missing tax, and both direct-SKU and period advertising. The pipeline imports
no legacy runtime module and has no hidden filesystem input. Stage 9 remains
blocked: it is represented only by excluded unresolved diagnostics.
