# Legacy Coverage At Stage 18.5

This is a cutover audit of target runtime ownership. It does not retire,
modify, or execute legacy modules.

| Legacy Module | Migrated | Adapter | Runtime Used | Status |
| --- | --- | --- | --- | --- |
| `wb_api_core/loaders.py` | partial: target raw contracts only | none | no | `BLOCKED`: production fetch/storage adapter not migrated |
| `wb_api_core/normalize.py` | partial: declared endpoint normalizers | none | no | `PARTIAL`: legacy aliases/artifact shapes are not a target raw contract |
| `wb_api_core/reconcile.py` | partial: target reconciliation | none | no | `PARTIAL`: legacy daily bundle reconciliation remains active legacy path |
| `v3/financial/snapshot_builder.py` | yes: finality/status boundary | none | no | `MIGRATED` |
| `v3/metrics/financial_kernel.py` | partial: constrained Decimal kernel | none | no | `BLOCKED`: Stage 9 marketplace deductions and legacy float parity remain open |
| `src/cogs.py` | yes: explicit Product Economics inputs | none | no | `MIGRATED` |
| `v3/metrics/ads_summary_assembler.py` | partial: scope-preserving advertising | none | no | `PARTIAL`: raw advertising acquisition replay absent |
| `v3/metrics/sales_funnel_assembler.py` | partial: canonical funnel retention | none | no | `PARTIAL`: full legacy funnel parity fixture absent |
| `v3/metrics/daily_kpi_assembler.py` | partial: operational read model | none | no | `PARTIAL`: legacy KPI compatibility projection remains unported |
| `v3/domain/event_model.py` | partial: date-separated target contracts | none | no | `PARTIAL` |
| `v3/core_report_bridge.py` | no | none | no | `NOT_MIGRATED`: filesystem bridge intentionally excluded from target |
| `report_v2/builders/report_payload_builder.py` | partial: pure target payload | none | no | `PARTIAL`: legacy inline calculations/artifact discovery not adopted |
| `report_v2/renderers/pdf_renderer_v2.py` | partial: deterministic target PDF renderer | none | no | `PARTIAL`: visual parity fixture absent |
| `report_v2/renderers/email_renderer_v2.py` | partial: deterministic target text/HTML | none | no | `PARTIAL`: presentation parity fixture absent |
| `v3/entry.py` | no | none | no | `NOT_MIGRATED`: orchestration/cutover route remains legacy |
| `audit/run_audit.py` | no | none | no | `UNRESOLVED`: offline WB/Ozon audit is outside current target domain |

## Runtime Dependency Audit

Static import scan of `AI Director 2/packages` found **zero executable imports**
of `v3`, `src`, `wb_api_core`, `report_v2`, or `audit`. The sole textual
reference is historical documentation in `LEGACY_MIGRATION_MAP.md`.

The target `packages.pipeline` and `packages.reports` have no direct
filesystem-read primitives (`Path`, `open`, `read_text`, `read_bytes`, `glob`,
`os`, or `subprocess`) and do not load a legacy artifact at runtime.

This proves target-source isolation for the inspected code. It does not prove
production cutover because an executable production acquisition adapter and a
replayable real-data fixture pack are still absent.
