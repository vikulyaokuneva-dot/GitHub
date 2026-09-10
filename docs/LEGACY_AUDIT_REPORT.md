# Legacy Audit Report: WB Autopilot Migration

Audit date: 2026-08-24  
Scope: repository root legacy project plus `AI Director 2` target architecture.  
Method: static inspection of repository files, imports, entry points, tests, configuration, workflows, stored artifacts, and representative runtime contracts. No production code was changed, moved, renamed, or executed against external services.

## 1. Executive Summary

The repository already contains a working daily reporting chain:

```text
WB API -> wb_api_core raw bundle -> normalization -> reconciliation -> snapshot/debug
       -> v3 bridge/orchestration -> report_v2 payload -> PDF/HTML/text artifacts
```

It also contains a separate legacy `src` daily route and a file-based `audit` route. The new `AI Director 2` directory is intentionally only a platform shell: API health endpoints, worker shell, non-secret settings, a tenant-scoped raw-event contract, ADRs, and boundary tests. It is the target architecture, not an implementation replacement yet.

The recommended first migration slice is **read-only WB Core provenance plus snapshot compatibility**: create golden fixtures from one redacted closed period, implement the target `packages/wb_core` read adapter behind the existing `RawApiEvent` contract, and compare the produced normalized/snapshot read model with legacy. Finance, report rendering, AI, and all write automation remain outside that first slice.

Migration is not ready to move business calculations yet. There is meaningful regression coverage, especially around `report_v2`, finance reconciliation, data-quality states, and snapshot bridging. However, money in key legacy financial contracts is still represented as `float`, WB HTTP implementations are duplicated, the report builder reads neighboring artifacts from the filesystem, target tenant/persistence/credentials infrastructure is absent, and several direct legacy-to-legacy imports remain.

## 2. Repository Map

Static inventory found 780 relevant non-cache files and 345 Python source/test files in the inspected scope: 330 legacy Python files and 15 Python files in the target shell. The legacy roots contain 240 non-test Python files and 90 test files.

| Area | Observed role | Entry/use evidence | Migration position |
| --- | --- | --- | --- |
| `AI Director 2/` | Target modular-monolith shell | `apps/api/main.py`, `apps/worker/main.py`, target tests | Target; retain as architectural authority |
| `wb_api_core/` | Current API acquisition, raw-like bundle, normalization, reconciliation, snapshot/artifacts | `python -m wb_api_core.run_daily`; CI `daily.yml` | First adapter candidate |
| `v3/` | Active daily pipeline, metrics, finance, diagnostics, history, recommendations | `python -m v3.entry daily`; CI `daily.yml` | Transitional legacy core |
| `report_v2/` | Snapshot-to-report payload, PDF, HTML/text email files | `python -m report_v2.run_report_v2`; called by `v3/pipeline/daily_output_stage.py` | Preserve behavior behind reports adapter |
| `src/` | Older daily-report route, WB clients, LLM/email utilities, reusable helpers | deprecated CI `v2-daily-manual.yml`; imports from `v3` | Selective reuse only |
| `audit/` | Offline WB/Ozon spreadsheet audit and PDF | `python run.py --mode audit`; CI `audit.yml` | Separate manual-import product path |
| `shared/` | Small shared configuration/logistics helpers | imported by `shared/*`; no observed active `v3` caller | Target unclear |
| `cabinets/`, `runtime/`, `output/`, `history/` | Runtime state, reports, snapshots, fixtures-like artifacts | read/write from pipelines | Source material; must be redacted before fixtures |
| `.github/workflows/` | Scheduled/manual operational entry points | `daily.yml`, `audit.yml`, `v2-*` workflows | Preserve operational behavior until cutover |

## 3. Current Architecture

### Target architecture: `AI Director 2`

`AI Director 2/AGENTS.md` and ADRs establish the destination rules:

- WB API access only through `packages/wb_core`.
- Raw -> normalized -> derived -> AI is strict.
- Financial/business metrics are not calculated by AI.
- Tenant-owned data is tenant-scoped.
- Write actions require Automation Engine, Policy, Approval, and Audit.
- New domain packages cannot directly import `wb_api_core`, `v3`, `report_v2`, or `src`; `packages/compat` is the migration boundary.

Existing target code confirms that the platform is deliberately incomplete rather than silently coupled to legacy. `packages/wb_core/contracts.py` defines `TenantAccountScope`, `RawApiEvent`, UTC validation, payload hash, schema version, endpoint, and object URI. `apps/api/main.py` only serves health/readiness. `apps/worker/main.py` explicitly reports that no queue integration exists.

### Active legacy daily route

The scheduled workflow in `.github/workflows/daily.yml` runs:

```text
wb_api_core.run_daily
  -> validates snapshot
  -> v3.history.api_history_backfill
  -> v3.entry daily
  -> v3 input / metrics / AI / output stages
  -> report_v2 PDF is uploaded
```

`wb_api_core.run_daily` calculates the Moscow operational date, loads a WB bundle, normalizes and reconciles it, writes snapshot/debug/reconciled artifacts, stores price snapshots in SQLite, and may use prior successful snapshots as fallback. `v3` has a snapshot-first path: it reads the core snapshot through `v3/core_report_bridge.py`, then `v3/pipeline/daily_output_stage.py` invokes `report_v2.run_report_v2.build_report_v2_from_files` in report version `v2` mode.

### Other operational routes

- `src/main.py` is still callable by `v2-daily-manual.yml`, whose own workflow text says it is deprecated.
- `run.py` dispatches file-based WB/Ozon audit modes.
- `audit/run_audit.py` reads spreadsheets, writes facts/actions/Markdown/PDF, and can send an email when explicitly requested.
- `v3` also exposes daily/weekly/audit CLI paths. The audit collector inside `v3` is marked as a stub, so the active offline route is `audit/run_audit.py`, not the `v3` audit skeleton.

## 4. Legacy Dependency Graph

The architectural graph is maintained in [LEGACY_DEPENDENCY_GRAPH.md](LEGACY_DEPENDENCY_GRAPH.md). The highest-centrality legacy modules are:

| Core | Why it is architectural | Observed dependents/callers |
| --- | --- | --- |
| `wb_api_core.client` + `loaders` | Sole active daily source for the core snapshot route; owns endpoint calls, retries, request budget and load semantics | `run_daily`, `history/api_history_backfill`, tests |
| `wb_api_core.normalize` + `reconcile` + `snapshot` | Convert raw API-specific responses to snapshot/report-compatible facts | `run_daily`, `report_v2` tests |
| `v3/entry.py` | Large compatibility/orchestration hub and dynamic namespace supplier | daily stages, CLI, tests |
| `v3/pipeline/daily_*` | Current daily stage order | `v3.entry`, `daily_pipeline_runner` |
| `v3/core_report_bridge.py` | Filesystem contract from core snapshot to v3/report consumers | daily input/output, report/email/artifact stages |
| `report_v2/builders/report_payload_builder.py` | Read-model assembler and secondary artifact reader | `run_report_v2`, v3 output stage, report tests |
| `report_v2/renderers/pdf_renderer_v2.py` | Production PDF finalization | `run_report_v2`, report tests |
| `v3/metrics/financial_kernel.py` | Account and SKU P&L calculation path | daily metrics, finance/parity tests |
| `v3/sources/wb_reports_loader.py` | Large spreadsheet ingestion/parser surface | v3 local-report paths, metric engine, tests |
| `audit/audit_facts_builder.py` + `audit/audit_report.py` | Offline audit facts and report generation | `audit/run_audit.py`, audit tests |

### Cycles, strong coupling, and hidden dependencies

- No static import cycle was proven by this audit. `UNKNOWN` remains for runtime cycles not exercised by static inspection.
- `v3/pipeline/daily_stage_support.py` imports `v3.entry` at runtime and copies its globals into stage module namespaces. This is a hidden dependency and makes stage behavior depend on `entry.py` symbols not declared in stage imports.
- `v3/entry.py` duplicates the daily-stage orchestration that is also expressed in `v3/pipeline/daily_pipeline_runner.py`. The CLI path uses the `entry.py` version.
- `v3` directly imports `report_v2`, `wb_api_core`, and selected `src` helpers. This is expected legacy coupling but forbidden in new packages.
- `report_v2` does not import `v3` production code, but its builder discovers neighboring JSON files from artifact directories. Its effective input is therefore broader than the `snapshot` argument.
- `src`, `audit`, and `v3` duplicate financial, PDF, client, and action/recommendation concepts. They must not be merged by filename alone.

## 5. WB API Inventory

All active API endpoints listed below are legacy-only until a typed `packages/wb_core` adapter exists. `wb_api_core.client.WBApiClient.request_json` uses `requests`, timeout, retry policy, Retry-After/rate-limit header parsing, bounded request count, and structured result dictionaries. It does not persist a target-style immutable raw event for every request.

| Legacy file/function | Endpoint / service | Purpose | Raw/provenance and normalization | Retry/rate limit/pagination | Migration note |
| --- | --- | --- | --- | --- | --- |
| `wb_api_core/loaders.py:load_cabinet_commerce` | `POST /api/analytics/v3/sales-funnel/products` | Daily cabinet commerce/funnel | rows in bundle; cache under artifacts; normalized by `normalize_bundle` | custom retry; cached response; request pagination semantics in loader | ADAPT; primary snapshot source |
| `load_orders` | `GET /api/v1/supplier/orders` | Operational orders | rows in bundle -> normalizer -> reconciliation | retry; no target raw store | ADAPT; event date semantics required |
| `load_sales` | `GET /api/v1/supplier/sales` | Operational sales/buyouts | rows in bundle -> normalizer -> reconciliation | retry; no target raw store | ADAPT; not final finance |
| `load_stocks` | `POST /api/analytics/v1/stocks-report/wb-warehouses` | WB warehouse stock | rows in bundle -> normalizer | offset pagination | ADAPT; snapshot date is distinct from sales day |
| `load_finance_final` | `POST /api/finance/v1/sales-reports/detailed` | Final/lagged finance details | rows -> finance normalization/reconciliation | retry; finance lag fallback wrapper | ADAPT; authoritative finance candidate |
| `load_finance_legacy` | `GET /api/v5/supplier/reportDetailByPeriod` | Legacy finance fallback | rows -> finance normalization/reconciliation | retry | DEPRECATE after parity; do not adopt as target core |
| `load_ads` | `GET /api/advert/v2/adverts`, `GET /adv/v3/fullstats` | Campaign and daily ad statistics | rows -> normalized ads | chunking adverts; retry | ADAPT; a separate v3 ads loader is only a placeholder |
| `load_search_report` | `POST /api/v2/search-report/table/groups`, `/details` | Search analytics | rows -> normalized/search report fields | group/detail traversal, retry | ADAPT; endpoint-specific pagination contract needed |
| `load_product_prices` | `POST /api/v2/list/goods/filter` | Product price state | raw price payload files + normalized rows | offset pagination | ADAPT; uses Decimal in pricing submodule |
| `load_fbs_order_prices` | `GET /api/v3/orders/new`, `/api/v3/orders` | FBS order price state/history | raw price payload files + normalized rows | current/history fallback | ADAPT; keep separate from finance |
| `v3/api/wb_client.py` + `v3/ingestion/*` | Duplicated statistics/analytics/advert clients/endpoints | Alternative v3 API ingestion | data transformed directly into v3 dictionaries | retries in duplicate client; varied pagination | DEPRECATE as clients; preserve normalization/parity tests |
| `src/wb_client.py`, `v3/wb_client.py` | Duplicated direct WB clients | Older report paths | direct row mapping | retry loops | DEPRECATE; no new callers |

Endpoint response formats are heterogeneous lists/dictionaries and are accessed with alias-based extractors. The target must store: endpoint/service name, request fingerprint, source API/schema version, request/responded UTC timestamps, HTTP status, raw payload hash, raw object URI, cursor/page, and tenant/account scope before any normalization. This is materially stricter than current debug artifacts.

## 6. Finance Inventory

Financial logic occurs in several independent families. It is not safe to consolidate them without a per-formula parity fixture.

| Component | Inputs and observed formula/semantics | Types/date state | Classification |
| --- | --- | --- | --- |
| `wb_api_core.normalize._normalize_finance_final` + `reconcile` | Maps finance detailed rows; selects target or lagged financial date; produces seller payout, commission, logistics, storage, penalties, deductions, acquiring, tax and realized metrics | Mostly `float`; date strings; `target_date` vs `actual_date` visible | ADAPT |
| `v3/ingestion/api_realization_loader.py` | New finance list/detail/period endpoint with legacy fallback; uses Decimal while parsing, serializes mapped values as floats | Decimal parse then float outputs; period dates | ADAPT |
| `v3/financial/finance_loader.py`, `finance_normalizer.py`, `snapshot_builder.py` | Unified-loader/snapshot experiment; field aliases, source/status/alignment/component completeness | `FinancialRow` fields are float; `FinancialSnapshot` has status/alignment | ADAPT; contract is valuable, money representation must change |
| `v3/metrics/financial_kernel.py` | Sale/return/logistics/storage/penalty classification; COGS matching; tax; account and SKU P&L | floats; tax `gross_revenue * tax_rate`; COGS from `src.cogs` fallback or file | MOVE to `packages/finance` after golden parity |
| `v3/metrics/financial_kpi_assembler.py`, `daily_kpi_resolver.py` | Selects sources and marks confirmation; separates daily operational counts/amounts from finance status | floats and explicit source policy | ADAPT; preserve policy and data-quality behavior |
| `src/metrics.py` / `audit/lib/metrics.py` | Older financial/funnel/ad calculations, with COGS helper | floats; offline/legacy inputs | ADAPT selectively; formula ownership requires comparison |
| `report_v2/builders/report_payload_builder.py` | Presentation-level profit/unit-economics recomputation from finance, COGS, ads and artifacts | uses Decimal in sections | ADAPT; move calculations out of rendering read model |
| `audit/audit_facts_builder.py` | File-based finance/COGS/logistics audit | floats; spreadsheet period semantics | TARGET_UNCLEAR; separate import workflow or reports domain |

Observed account-kernel formula is, in simplified form:

```text
tax = gross_revenue * configured_tax_rate
profit = gross_revenue - commission - logistics - storage - penalties - tax - cogs
margin = profit / gross_revenue when denominator is non-zero
```

This is a description, not an endorsement. `REQUIRES_VALIDATION`: commission signs, return allocation, rebill logistics, deductions/acquiring, tax basis, COGS coverage, and presentation-level recomputation must be reconciled against a closed WB period before any formula is moved. The existing ADR correctly keeps direct logistics and `rebillLogisticCost` separate.

## 7. Date/Time Inventory

| Source/module | Date field/logic | Time zone | Purpose | Risk |
| --- | --- | --- | --- | --- |
| `wb_api_core/run_daily.py` | requested run date -> operational date; current/future date shifts to prior local day | `TZ`, default `Europe/Moscow` | Daily API selection | Medium: fallback becomes `date.today()` if zone resolution fails |
| `wb_api_core/loaders.py` | finance target/date fallback; FBS price captured time | UTC capture; Moscow local start for FBS | load bounds and raw capture | Medium: endpoint-specific semantics not centralized |
| `wb_api_core/pricing.py` | ISO timestamp -> Moscow local date | UTC storage + `Europe/Moscow` derivation | Price analytics | Low/medium; one of the more explicit implementations |
| `v3/entry.py` | report timezone from env/config; operational period shifts current day | default `Europe/Moscow`, UTC timestamps | Daily orchestration | Medium: duplicated with core logic |
| `v3/history/api_history_backfill.py` | previous operational day | `Europe/Moscow`; `fetched_at` UTC | backfill | Medium: separate date policy implementation |
| `v3/financial/snapshot_builder.py` | target vs actual finance dates | date-only strings | alignment/lag | Medium: no timezone-bearing financial timestamps |
| `v3/pipeline/data_phase.py`, `report_phase.py`, `job_runner.py` | `datetime.utcnow().isoformat() + 'Z'` | UTC intended but naive object | artifact/job timestamps | High: violates target UTC-aware requirement |
| `src/main.py` | fallback report date | `Europe/Berlin` | old daily route | High: conflicts with WB Moscow-day target rule |
| `audit/run_audit.py`, `audit/audit_facts_builder.py` | report/audit date | `Europe/Moscow` | offline audit labels | Low/medium: event/source timezone comes from files |

No legacy date behavior was corrected in this audit. The target should formalize endpoint-specific `event_at`, `operational_date`, `report_date`, `financial_date`, and `business_timezone` rather than infer one meaning from a string field.

## 8. Report Pipeline

### Active `report_v2` pipeline

```text
WB API
  -> wb_api_core.load_bundle
  -> wb_api_core.normalize_bundle
  -> wb_api_core.reconcile_bundle
  -> wb_api_core.build_snapshot + build_debug + write_artifacts
  -> v3/core_report_bridge (transitional filesystem contract)
  -> v3/pipeline/daily_output_stage in REPORT_VERSION=v2
  -> report_v2.run_report_v2.build_report_v2_from_files
  -> report_v2.builders.build_report_payload_v2
  -> report_v2.renderers.write_report_pdf_v2
  -> report_v2.renderers.write_email_files
  -> PDF/HTML/text/report_meta/job artifacts
```

| File/function | Role | Source of truth / transformation | Risk |
| --- | --- | --- | --- |
| `wb_api_core/run_daily.py:run_daily` | Core acquisition and snapshot writer | raw bundle, normalized bundle, reconcile result | combines network, cache, storage, price DB and orchestration |
| `wb_api_core/snapshot.py:build_snapshot` | Snapshot contract | reconciliation outputs | must become versioned target read model |
| `wb_api_core/artifacts.py:write_artifacts` | JSON persistence/debug/fallback cache | artifacts under seller path | filesystem instead of repository/object storage |
| `v3/core_report_bridge.py` | Validates/reshapes snapshot for old stages | `snapshot.json` and optional `debug.json` | transitional and calculation-adjacent |
| `v3/pipeline/daily_output_stage.py:_run_daily_output_stage_v2` | Calls report_v2 and registers outputs | core snapshot path + v3 context artifacts | v3 directly imports report package |
| `report_v2/run_report_v2.py:build_report_v2_from_files` | File CLI/writer | loads JSON files, invokes payload/PDF/email | suitable compatibility boundary |
| `report_v2/builders/report_payload_builder.py:build_report_payload_v2` | Report read model and sections | snapshot plus artifact-directory discovery/history | 5,500+ lines; recomputes selected finance/report values |
| `report_v2/renderers/pdf_renderer_v2.py:write_report_pdf_v2` | PDF renderer | payload only plus internal artifact lookups | 2,000+ lines; visual regression required |
| `report_v2/renderers/email_renderer_v2.py:write_email_files` | HTML/text delivery artifacts | payload | does not send SMTP itself |

`report_meta.json` records renderer/version/source metadata in the v3 output route. It is a useful compatibility artifact but not yet a versioned target report entity. Debug artifacts are operationally relevant: `snapshot.json`, `debug.json`, `reconciled_rows.json`, caches, `financial_debug.json`, `api_debug.json`, `warnings.json`, and source counts explain degraded runs. Treat them as evidence, not as a stable public API.

## 9. Golden Fixtures

Existing material is useful but is not yet a clean, redacted fixture suite.

| Candidate | Contents/period evidence | Suitable parity checks | Risk and action |
| --- | --- | --- | --- |
| `cabinets/seller_001/artifacts/wb_api_core/<date>/{snapshot,debug,reconciled_rows}.json` | Multiple 2026-04, 2026-06, 2026-07 daily core snapshots | API normalization, reconciliation, snapshot contract, degraded/lagged state | Likely seller/product/business data; redact and hash; retain provenance manifest |
| `output/report_v2_2026-07-26_fixed/` | payload, PDF, facts, reconciliation, warnings, API debug | report payload, PDF text/structure, finance/report finalization | May contain customer/business data; select only redacted canonical period |
| `cabinets/seller_001/artifacts/report_payload_v2.json`, `report_v2.pdf`, `email_v2.*` | Final daily delivery representation | read-model/PDF/email parity | likely customer content; sanitize |
| `runtime/cabinets/seller_001/raw/` | XLSX finance/funnel/stocks and facts | manual import parser and audit parity | sensitive seller/export data; do not commit unredacted |
| `local_audit/input/` and `audit/output/` | offline source files and generated audit | audit parser/report checks | client data; use synthesized/redacted derivatives |
| `cabinets/seller_001/v5/data/*` and debug bundles | raw/normalized/facts/metrics comparison artifacts | legacy v5 compatibility research | semantic ownership and runtime role `UNKNOWN` |
| Existing tests under `wb_api_core/tests`, `v3/tests`, `report_v2/tests`, `src/tests` | 90 legacy test modules | unit/contract behavior | tests are not a replacement for redacted end-to-end golden fixtures |

`MISSING_GOLDEN_FIXTURE`: no manifest-controlled fixture set was found that pairs a redacted raw WB response, canonical normalized facts, finance reconciliation result, expected report payload, and expected PDF/text checksums under one immutable scenario. This is the first blocking artifact for moving calculations.

## 10. KEEP Inventory

| Component | Why keep | Evidence/use |
| --- | --- | --- |
| `AI Director 2/AGENTS.md`, ADR 0001/0002 | Explicit target boundaries and metric safety rules | target tests enforce no direct legacy imports |
| `AI Director 2/packages/wb_core/contracts.py` | Correct initial tenant/raw provenance boundary with UTC validation | unit tests cover UTC and scope |
| `AI Director 2/packages/common/{health,settings}.py` | Small non-secret shell infrastructure | API and worker shells import it |
| `v3/validation/{data_integrity,report_guardrails,sku_normalization}.py` | Data-quality policy and explicit suppression behavior are valuable | dedicated validation/report tests |
| `report_v2/contracts/report_payload_schema.py` | Typed report payload vocabulary | used by payload builder |
| `wb_api_core/token_resolver.py` | One resolved token lookup used by three legacy clients | imported by wb_api_core, v3 and src clients |
| `wb_api_core/pricing.py` Decimal helpers | Uses Decimal for price-specific money and handles UTC/Moscow conversion | price analytics tests |

## 11. ADAPT Inventory

| Component | Required adaptation | Dependencies/tests |
| --- | --- | --- |
| `wb_api_core/client.py` | Replace env-token singleton behavior with tenant credential resolver, typed request/result, per-account limiter, observability and raw event persistence | client rate-limit tests; endpoint snapshot tests |
| `wb_api_core/loaders.py` | Split endpoint adapters from cache/filesystem policy; declare cursor/page and source schemas | loader tests; redacted API fixtures |
| `wb_api_core/normalize.py`, `reconcile.py`, `snapshot.py` | Preserve semantics behind typed normalizers/read models; replace floats for money | snapshot/report parity |
| `wb_api_core/artifacts.py` | Replace seller filesystem cache with repository/object storage and idempotent records | fallback and replay parity |
| `wb_api_core/pricing.py:PriceSnapshotStore` | Move SQLite persistence to target data/storage package while preserving Decimal outputs | pricing analytics tests |
| `v3/core_report_bridge.py` | Replace paths/JSON reads with `packages/compat` repository adapter | core snapshot bridge tests |
| `v3/financial/*` | Make Decimal/typed contracts authoritative; preserve load fallback diagnostics | finance loader/normalizer/snapshot tests |
| `v3/metrics/daily_kpi_assembler.py`, `daily_kpi_resolver.py` | Preserve source policy and confirmed/unknown distinctions | daily KPI and contour tests |
| `v3/metrics/sales_funnel_assembler.py` | Separate operational/funnel sources and metric ownership | funnel tests |
| `v3/analytics/{sales_funnel,sku_health,profit_contribution,territorial_distribution,advertising_efficiency,keywords}` | Move one domain at a time after fixtures | focused analytics tests |
| `v3/history/*`, `v3/memory/*` | Replace filesystem JSON/JSONL with tenant-scoped persistence and immutable audit/outcome records | history/outcome tests |
| `v3/outputs/*` | Recast as report read-model/output compatibility adapters | output, guardrail, PDF tests |
| `report_v2/builders/report_payload_builder.py` | Separate business calculations and artifact reads from pure report read-model builder | report_v2 test suite |
| `report_v2/renderers/*` | Keep rendering behavior while making input one explicit payload | PDF/email tests |
| `src/mailer_yandex.py` | Make it a notification transport adapter with secret provider and audit outcome | mail tests; no direct domain use |
| `src/openrouter_client.py` | Replace with AI Gateway; prohibit raw credentials/raw WB payload exposure | no target direct use |
| `audit/audit_loader.py`, `audit/audit_facts_builder.py`, `audit/audit_report.py` | Treat as manual-import adapter; extract only proven shared parsing logic | audit tests and redacted spreadsheet fixtures |

## 12. MOVE Inventory

| From | To | Dependency changes | Transfer proof |
| --- | --- | --- | --- |
| `v3/metrics/financial_kernel.py` | `packages/finance` | remove `src.cogs` import; inject COGS repository | closed-period account/SKU finance parity |
| `v3/financial/{models,finance_loader,finance_normalizer,snapshot_builder}.py` | `packages/finance` | target Decimal money and WB Core interfaces | normalization, status/alignment and reconciliation tests |
| `v3/metrics/sales_funnel_assembler.py`, `v3/analytics/sales_funnel.py` | `packages/analytics` | consume canonical facts, not API clients | funnel golden + denominator absence tests |
| `v3/analytics/advertising_efficiency/*`, keywords | `packages/analytics` plus advertising domain | canonical ads/search facts | ads/search evidence and attribution parity |
| `v3/analysis/decision_engine.py`, `src/analysis/ai_director.py` | `packages/ai` or recommendations domain | consume derived facts/evidence only | structured recommendations with confidence/evidence |
| `v3/memory/{decision_logger,decision_outcomes}.py` | `packages/ai`/recommendations persistence | tenant scope and immutable audit history | outcome/idempotency tests |
| `report_v2/contracts` and pure renderer functions | `packages/reports` | reports only consume explicit report read model | payload/PDF/email parity |
| `src/mailer_yandex.py` | `packages/notifications` | send only an approved report notification job | transport contract tests |

## 13. DEPRECATE Inventory

| Component | Replacement/future component | Evidence |
| --- | --- | --- |
| `v3/api/wb_client.py` | target `packages/wb_core` client | duplicates endpoint/client surface |
| `v3/wb_client.py` | target `packages/wb_core` client | direct `requests` client, limited callers |
| `src/wb_client.py` | target `packages/wb_core` client | old direct client; `src` route only |
| `src/main.py` + `v2-daily-manual.yml` | v3 then target scheduled sync/report jobs | workflow labels it deprecated |
| `v3/ingestion/api_ads_loader.py` | target Ads adapter | explicitly returns `not_implemented` placeholder |
| `src/action_orchestrator.py` | `packages/automation` | only produces suggested actions; no Policy/Approval/Audit model |
| `v3/core_report_bridge.py` | `packages/compat` repository interface | ADR 0001 identifies it as transitional |
| `wb_api_core.load_finance_legacy` and v3 legacy finance fallback | Finance API adapter | known legacy endpoint fallback; retain until finance parity |

## 14. DELETE_CANDIDATE Inventory

| Component | Evidence | Required proof before deletion |
| --- | --- | --- |
| `report_v2/payload.py`, `report_v2/payloads.py`, `report_v2/renderer.py`, `report_v2/renderers.py` compatibility fragments | Static search found no production callers beyond their own small compatibility chain; active route imports `builders/*` and `renderers/*` directly | add import-usage test, run full report regression, verify no package/public downstream import, then review manually |

No files are deleted by this audit. `DELETE_CANDIDATE` is a review status, not permission to remove code.

## 15. Legacy -> New Architecture Mapping

| Legacy component | Category | Target module | Confidence | Risk | Dependencies | Migration order |
| --- | --- | --- | --- | --- | --- |
| `wb_api_core.client/loaders` | ADAPT | `packages/wb_core` | High | High | WB endpoint semantics, credentials, rate limits | P0 |
| `wb_api_core.normalize/reconcile/snapshot` | ADAPT | `packages/wb_core`, `packages/data` | High | High | raw schemas, finance/date policies | P0-P1 |
| `wb_api_core.artifacts` | ADAPT | `packages/data`, `packages/storage` | High | High | replay/cache/idempotency | P0-P3 |
| `wb_api_core.pricing` | ADAPT | `packages/products`, `packages/data` | Medium | High | Decimal, SQLite price history | P1-P3 |
| `v3/core_report_bridge.py` | ADAPT | `packages/compat` | High | Medium | snapshot filesystem layout | P0-P2 |
| `v3/financial`, financial kernel | MOVE | `packages/finance` | High | Critical | finance source, COGS, tax, date alignment | P1 |
| `v3/daily_kpi_resolver.py` | ADAPT | `packages/analytics` | High | High | source policy and event semantics | P1 |
| `v3/metrics`, `v3/analytics` | ADAPT/MOVE | `packages/analytics` | Medium | High | one metric owner, domain facts | P1/P4 |
| `v3/validation` | KEEP/ADAPT | `packages/common` + domain policies | High | Medium | quality status contract | P0 |
| `v3/history` | ADAPT | `packages/data`, `packages/analytics` | Medium | Medium | historical snapshots | P3-P4 |
| `v3/memory` | MOVE | `packages/ai` / recommendations | Medium | High | tenant-scoped outcome persistence | P5 |
| `v3/analysis`, `src/analysis/ai_director.py` | MOVE | `packages/ai` | Medium | High | evidence schema; no finance calculation | P5 |
| `src/action_orchestrator.py` | DEPRECATE | `packages/automation` | High | Critical | Policy/Approval/Audit missing | P6 |
| `report_v2` | ADAPT/MOVE | `packages/reports` | High | High | snapshot/artifact read model, visual parity | P2 |
| `src/mailer_yandex.py` | MOVE | `packages/notifications` | High | Medium | secret provider, notification audit | P3/P6 |
| `audit/*` WB offline path | TARGET_UNCLEAR | `packages/data` + `packages/reports` | Medium | High | spreadsheet formats and offline finance semantics | after P2 |
| `audit/audit_ozon/*`, `local_audit_ozon/*` | TARGET_UNCLEAR | no WB Autopilot target decided | High | Medium | separate marketplace scope | HUMAN decision |
| `src/v3` duplicate clients | DEPRECATE | `packages/wb_core` | High | High | active callers and endpoint parity | P0-P1 |
| target `packages/auth`, `packages/tenancy` | N/A (no legacy owner) | target packages | High | Critical | auth/RBAC/persistence not implemented | P3 |

`TARGET_UNCLEAR`: the Ozon audit code is an active-looking isolated product path, but WB Autopilot architecture describes a Wildberries SaaS. It cannot be silently folded into WB domain packages.

## 16. Dependency Risks

1. Finance computations occur in `v3`, `src`, `audit`, and report composition; a naive extraction changes meaning.
2. `v3` stage modules borrow globals dynamically from `v3.entry`, obscuring declared dependencies and test surface.
3. `report_v2` reads filesystem siblings beyond the supplied snapshot; input closure is incomplete.
4. There are three direct WB clients plus `wb_api_core`; endpoint behavior can drift.
5. The scheduled workflow runs legacy writes into workspace paths and caches them as job state.
6. Existing artifacts include seller-scoped raw/debug/report material. They are evidence but not safe default fixtures.
7. Legacy code defaults many missing monetary values to `0.0`; target must preserve missing/zero/not-applicable distinctions.

## 17. Architecture Boundary Violations

These are findings against the **target** architecture or explicit migration goals. None was fixed in this audit.

| ID | Finding | Evidence | Severity |
| --- | --- | --- | --- |
| AB-01 | Duplicate direct WB HTTP clients exist outside `wb_api_core` | `src/wb_client.py`, `v3/wb_client.py`, `v3/api/wb_client.py` use `requests` | High |
| AB-02 | Legacy finance contracts/calculations use `float` extensively | `v3/financial/models.py`, `financial_kernel.py`, normalization/metrics | Critical |
| AB-03 | Naive UTC construction remains | `v3/pipeline/data_phase.py`, `report_phase.py`, `job_runner.py` use `datetime.utcnow()` | High |
| AB-04 | Old route uses Berlin as report-date fallback | `src/main.py` | High |
| AB-05 | Dynamic import/global namespace coupling in daily stages | `v3/pipeline/daily_stage_support.py` | High |
| AB-06 | Domain/report flow accesses filesystem artifacts as an implicit data API | `v3/core_report_bridge.py`, `report_v2/report_payload_builder.py` | High |
| AB-07 | v3 imports legacy `src` helpers directly | financial kernel, AI alias, mailer, analytics aliases | High |
| AB-08 | Automation recommendation objects lack Policy/Approval/Audit lifecycle | `src/action_orchestrator.py` | Critical if ever executable |
| AB-09 | AI-era legacy client has direct external HTTP but no target gateway contract | `src/openrouter_client.py` | Medium |
| AB-10 | Target architecture shell has no tenant persistence, credentials, sync jobs, or raw storage yet | `AI Director 2/packages` and worker shell | Expected gap, Critical for migration gate |

No direct WB API, AI finance computation, or write-action implementation was found in `AI Director 2/apps` or `AI Director 2/packages`; the boundary test passes by design.

## 18. Security Findings

Secrets were not printed or copied into this report.

| ID | Finding | Evidence | Severity |
| --- | --- | --- | --- |
| SEC-01 | `wb_api_core/run_daily.py` and `v3/entry.py` log whether `WB_API_TOKEN` exists and its length | source lines in respective entry paths | Medium |
| SEC-02 | Legacy modules auto-load root `.env` at import time | `v3/__init__.py`, `wb_api_core/__init__.py` | Medium |
| SEC-03 | Git tracks 191 runtime/data/artifact paths, including raw/debug/report and seller configuration material | `git ls-files` inspection | High |
| SEC-04 | Artifact directories contain raw API payloads and customer/business data; access classification is absent | `cabinets/*`, `runtime/*`, `output/*`, `local_audit/*` | High |
| SEC-05 | Target raw-event object expects object storage and tenant scope, but legacy uses workspace paths and no tenant boundary | target contract versus legacy artifact paths | High |
| SEC-06 | Current `.gitignore` covers many generated paths, but tracked historical artifacts remain tracked | `git ls-files` versus ignore rules | High |

Pattern scans did not establish a committed plaintext credential value, so no `SECRET_FOUND_AT` record is asserted. This is not proof that no secret exists: binary documents, ignored `.env`, history, and external Git history were out of scope for value disclosure. Before creating golden fixtures, run a dedicated approved secret scan and remove/redact customer data from any fixture candidate.

## 19. Regression Strategy

| Component | Golden/parity test | Unit/contract/integration coverage needed |
| --- | --- | --- |
| WB Core | redacted endpoint response -> exact normalized facts/snapshot/provenance | typed HTTP errors, 429/backoff, pages/cursors, UTC, raw hash, idempotency |
| Finance | closed period raw finance -> exact component ledger/account/SKU totals | Decimal rounding, source fallback, component completeness, lag/alignment, COGS coverage |
| Daily KPI/funnel | same source bundle -> confirmed/unknown status and metric traces | denominator absent; no order/buyout cohort mixing; source priority |
| `report_v2` | snapshot + declared secondary artifacts -> payload JSON and PDF semantic/text checks | pure builder contract, visual/layout smoke, email HTML/text |
| Core bridge | snapshot/debug -> legacy bridge read model | missing/invalid/mismatched seller/date errors |
| History/memory | facts/decision event -> idempotent stored outcomes | tenant scope, duplicate run, audit immutability |
| Automation | recommendation -> no execution until approved policy path | policy denial, dry-run, approval, audit record, rollback where supported |
| Target packages | old fixture -> target result equals legacy result | no legacy imports outside compat; API/DB contract tests |

The required acceptance invariant is:

```text
legacy fixture result == target fixture result
```

Any intentional deviation needs a versioned migration decision, an updated metric passport, a fixture update, and reviewer approval. Do not compare live WB API calls during parity tests.

## 20. Migration Order

The requested P0-P6 order is valid with one refinement: **fixture/redaction work precedes every business-code movement**.

1. P0a: freeze and document active production route; build redacted fixture manifest and reproducible legacy replay.
2. P0b: target foundations: tenancy/auth boundaries, encrypted credential design, raw event/object storage, date/money/error contracts, test/CI shell.
3. P0c: WB Core read adapter for one endpoint/snapshot slice with per-account rate limits and idempotency.
4. P1: finance source normalization, closed-period reconciliation and Decimal kernel parity; then funnel/source-policy parity.
5. P2: report read model, `report_v2` adapter, PDF/email artifact parity.
6. P3: tenant/account persistence, credentials, sync jobs, watermarks, freshness, historical replay.
7. P4: analytics facts/KPIs/diagnostics one owner at a time.
8. P5: AI gateway and evidence-backed recommendations over derived facts only.
9. P6: policy-gated automation and audit. No WB write capability before this gate.

## 21. Recommended First 20 Implementation Tasks

1. `SAFE_AUTONOMOUS`: Add a redacted golden-fixture manifest format and scenario directory policy.
2. `REVIEW_REQUIRED`: Select one closed seller period and approve data redaction rules.
3. `SAFE_AUTONOMOUS`: Add legacy replay command documentation for the selected fixture.
4. `SAFE_AUTONOMOUS`: Add contract test that snapshot/debug output has a declared schema version.
5. `SAFE_AUTONOMOUS`: Add target `Money`/`Decimal` and date-time contract tests, without moving formulas.
6. `SAFE_AUTONOMOUS`: Add target WB error taxonomy and rate-limit policy contracts.
7. `SAFE_AUTONOMOUS`: Add target raw-object repository interface and in-memory test implementation.
8. `REVIEW_REQUIRED`: Design tenant/account/credential persistence and encryption/key-management ADR.
9. `SAFE_AUTONOMOUS`: Implement read-only target adapter for sales-funnel snapshot fixture.
10. `SAFE_AUTONOMOUS`: Add parity test: legacy versus target normalized cabinet-commerce snapshot.
11. `SAFE_AUTONOMOUS`: Add endpoint registry metadata for the first core endpoint.
12. `SAFE_AUTONOMOUS`: Add per-account/per-endpoint limiter unit tests.
13. `SAFE_AUTONOMOUS`: Add idempotent ingestion request/fingerprint tests.
14. `REVIEW_REQUIRED`: Establish finance fixture sign conventions and expected component ledger with finance owner.
15. `SAFE_AUTONOMOUS`: Convert the selected finance fixture parser to typed Decimal test data.
16. `SAFE_AUTONOMOUS`: Add finance source/lag/completeness parity tests before migration.
17. `SAFE_AUTONOMOUS`: Introduce a `packages/compat` snapshot repository interface around `core_report_bridge` behavior.
18. `SAFE_AUTONOMOUS`: Add pure `report_v2` fixture tests declaring all secondary artifact inputs.
19. `REVIEW_REQUIRED`: Define report PDF comparison acceptance (semantic text, visual tolerances, known nondeterminism).
20. `HUMAN_ONLY`: Approve whether Ozon offline audit is a separate product, future marketplace adapter, or sunset candidate.

## 22. Open Questions

1. Which legacy route is production-authoritative when `daily.yml`, `v2-daily-manual.yml`, audit workflows, and historical v5 artifacts disagree?
2. Which finance definition is contractual for revenue, commission signs, rebill logistics, deductions/acquiring, tax, returns, and COGS?
3. Is Ozon audit in scope for WB Autopilot or explicitly a separate product?
4. Which stored seller artifacts may be retained for tests after legal/privacy review?
5. What is the authoritative WB credential category per endpoint and how will credential rotation work?
6. What output delivery is required in the target: stored report, email, Telegram, dashboard, or all?

## 23. Assumptions

- `AI Director 2` documents and ADRs are the target architecture authority.
- `.github/workflows/daily.yml` is the most relevant current scheduled daily route because it uses `wb_api_core` then `v3` and uploads `report_v2.pdf`.
- Static absence of a caller is not evidence of dead runtime use; it is recorded as such.
- Artifact directories may contain real seller information and must be treated as sensitive.
- No network calls, DB mutations, or email delivery were made during the audit.

## 24. Unknowns

- `UNKNOWN`: dynamic/global names supplied by `sync_from_entry` may create callers not visible in module imports.
- `UNKNOWN`: actual production schedule enablement and latest successful workflow run were not inspected remotely.
- `UNKNOWN`: all historical spreadsheet schemas and WB response-version variants.
- `UNKNOWN`: semantic equivalence among v3, src, audit, and historical v5 finance implementations.
- `UNKNOWN`: hidden consumers outside this repository or manual operator procedures.

## 25. Final Migration Readiness Assessment

Score: **43/100**. The score is an evidence-weighted readiness indicator, not a quality judgement of the existing reporting product.

| Dimension | Score | Evidence |
| --- | ---: | --- |
| Architecture clarity | 65 | clear target blueprint/ADRs and recognizable active daily route; legacy has duplicate routes and dynamic stage coupling |
| Test coverage | 60 | 90 legacy test modules plus focused report/finance/client tests; no unified target CI baseline yet |
| Fixture coverage | 30 | many artifacts exist but no redacted, manifest-controlled end-to-end goldens |
| Dependency clarity | 45 | major imports/entry points are identifiable; global injection and artifact discovery conceal dependencies |
| Finance safety | 35 | finance status/lag tests and Decimal islands exist; key models/kernels use float and multiple owners |
| API isolation | 40 | `wb_api_core` is a strong first core, but three duplicate direct clients remain and target adapter is absent |
| Migration safety | 30 | target boundaries exist but tenant persistence, raw storage, credentials, replay, and parity gates are not implemented |

The project is ready for **fixture-first adapter work**, not for broad extraction or production cutover. The hard gate is finance and report finalization parity on redacted immutable fixtures.

## Appendix A: Classification Counts

Counts are by significant migration unit, not every helper file. Small helpers inherit the disposition of their owning unit; tests are counted as verification assets rather than production migration units.

| Status | Count |
| --- | ---: |
| KEEP | 7 |
| ADAPT | 20 |
| MOVE | 8 |
| DEPRECATE | 8 |
| DELETE_CANDIDATE | 1 |
| UNKNOWN / TARGET_UNCLEAR | 2 |

## Appendix B: Codex / CI Delegation

| Class | Work that may be assigned |
| --- | --- |
| SAFE_AUTONOMOUS | fixture harnesses with synthetic/redacted data; unit/contract tests; target interfaces; docs; static import checks; pure report renderer tests; CI lint/type/test wiring |
| REVIEW_REQUIRED | finance formulas or expected values; fixture selection/redaction; schema migrations; report visual tolerance; migration of active operational route; any change to metric passport |
| HUMAN_ONLY | production credentials/tokens, credential rotation keys, production data approval, destructive data migration, WB write API enablement, billing, tenant access policy, final automation approval policy |
