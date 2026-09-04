# WB Autopilot

New production platform for Wildberries sellers. This directory is isolated from
the legacy project at the repository root. Legacy code is read only during the
migration and is imported only through future compatibility adapters.

## First vertical slice

This initial slice provides:

- project configuration and dependency boundaries;
- API liveness and readiness endpoints;
- a worker shell with no domain jobs yet;
- typed tenant and raw-event contracts;
- architectural decisions and regression boundaries for legacy migration.

It deliberately does not connect to WB, persist data, use AI, or execute
automation actions.

## Production foundation

The first production ingestion foundation now provides account registration,
stable internal tenant/account UUIDs, reversible SQLite migrations, durable
immutable raw storage, and one sales-funnel raw-to-canonical ingestion service.
Its security and ownership boundaries are documented in
`docs/architecture/PRODUCTION_FOUNDATION.md`.

## MVP Daily Analysis

`packages.pipeline.DailyAnalysisService` is the unified V2 daily use case. It
reads already durable, tenant-scoped raw objects and runs canonical
normalization, operational aggregation, finance, advertising, Product
Economics, sourced tax, P&L, and deterministic text/HTML/PDF reporting. It
does not make WB requests.

The minimal API entry point is:

```text
GET /analysis/{account_id}?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
```

The MVP accepts a single-day range only. The result declares `data_origin` as
`real_wb_data` or `test_fixture`; a missing Finance Detail result remains
unavailable rather than becoming zero profit. Endpoint-level live 429 results
therefore do not invalidate approved fixture E2E verification.

## Local commands

```powershell
cd 'AI Director 2'
..\\.venv\\Scripts\\python.exe -m pip install -e '.[dev]'
..\\.venv\\Scripts\\python.exe -m pytest
..\\.venv\\Scripts\\python.exe -m ruff check .
..\\.venv\\Scripts\\python.exe -m mypy
..\\.venv\\Scripts\\python.exe -m uvicorn apps.api.main:app --reload
```

`GET /healthz` reports that the API process is alive. `GET /readyz` is ready
only when its injected infrastructure probe confirms all required dependencies.
Actual PostgreSQL, Redis and RabbitMQ probes will be added with the persistence
and worker slices.
