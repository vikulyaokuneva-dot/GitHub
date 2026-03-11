# WB AI Agent v3 Layered Architecture (API-first)

## Target Layers

```
v3/
  raw/            # raw ingestion payloads (xlsx/api)
  normalization/  # canonical entities
  metrics/        # KPI and financial aggregation from normalized entities only
  decisions/      # decision engine from metrics/facts only
  history/        # snapshots/trends/memory integration (not for current KPI math)
```

## Current Logical Mapping (no full file move)

- `raw` layer:
  - `v3/raw/models.py` (new)
  - `v3/ingestion/*` (API loaders)
  - `v3/sources/wb_reports_loader.py` (local xlsx ingestion)

- `normalization` layer:
  - `v3/normalization/models.py` (new canonical models)
  - `v3/normalization/normalizers.py` (new transformations `raw -> normalized`)

- `metrics` layer:
  - `v3/metrics/engine.py` (new entry point `normalized -> metrics`)
  - legacy aggregator remains in `v3/sources/wb_reports_loader.py::build_metrics_from_reports`
    but is now called through metrics layer adapter.

- `decisions` layer:
  - `v3/decisions/runtime.py` (new wrapper)
  - existing logic in `v3/analysis/*`, `v3/analytics/*`

- `history/memory` layer:
  - `v3/history/*`
  - `v3/memory/*`
  - these modules consume final artifacts and do not calculate current day KPI directly.

## Minimal Refactor Applied

1. Daily run builds a `RawIngestionBundle`.
2. Raw bundle is transformed by `normalize_raw_bundle(...)`.
3. Metrics are built via `build_metrics_from_normalized(...)`.
4. Decisions are built via `build_decisions_layer(...)`.
5. History/memory flow remains unchanged.

This keeps compatibility with the current pipeline while enforcing:

`raw -> normalized -> metrics -> decisions -> history/memory`
