# v4 Clean Rebuild Skeleton

v4 is a new clean contour and not an extension of legacy runtime paths.

## Data Flow

`source -> normalize -> metrics -> facts -> decisions -> report`

## Folder Intent

- `entry/`: thin CLI wrappers only.
- `core/`: contracts, domain rules, static config models.
- `ingestion/`: source adapters (API/files) and raw bundle assembly.
- `normalization/`: raw to canonical records.
- `metrics/`: KPI computation only.
- `decisions/`: recommendation/priority layer only.
- `pipeline/`: mode-specific stage orchestration.
- `outputs/`: facts mapping, renderers, email/artifact builders.
- `diagnostics/`: source/data-quality/warnings models.
- `audit/`: isolated audit-file mode components.
- `validation/`: report-level guardrails.
- `tests/`: v4-only test packages.

## Hard Boundaries

- Ingestion does not compute metrics.
- Metrics do not render reports.
- Outputs do not recalculate KPI.
- `None` cannot be converted to `0` before render policy.
- `daily_api_mode` and `audit_file_mode` remain separated.

## Stage 1 Scope

This skeleton intentionally contains placeholders only.
Business logic wiring is deferred to next stages.
