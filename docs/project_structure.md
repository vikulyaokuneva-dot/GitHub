# Project Structure

- `v2` remains the ingestion layer and is not modified by this structure.
- `modules/` contains analytics and reporting logic that reads and writes JSON only.
- `pipeline/` orchestrates execution order: ingest -> finance -> assortment -> reporting.
- `runtime/cabinets/<seller>/` is the runtime data root for seller-scoped data.

