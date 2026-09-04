# Stage 18.5 Metric Parity Report

## Result

**Cutover validation is blocked.** This is a verification result, not a
request to change Stage 9, legacy code, the Golden Fixture, or target business
logic.

The repository contains 11 retained WB Core snapshot runs and 19 real local
WB report files. It does not contain the immutable raw payload bundle required
to replay those runs through the Stage 18 target pipeline. The retained
`reconciled_rows.json` files are already legacy-normalized values; finance rows
do not retain durable `rrdId`, and orders/sales/stocks/ads payloads are often
absent. Reinterpreting them as new raw endpoint payloads would be a new
adapter and an invented provenance contract, prohibited by this stage.

Ozon source code and test workbooks exist under `audit/` and `tmp_out/`, but
AI Director 2 currently has no Ozon RawObject endpoint or target pipeline
domain. Ozon parity is therefore out of scope for this WB target cutover and
is recorded as blocked rather than silently omitted.

## Evidence Set

| Group | Count | Coverage | Validation usability |
| --- | ---: | --- | --- |
| Retained WB Core snapshot/reconciled/debug sets | 11 | two seller identifiers, 2026-04-18 through 2026-07-26 | legacy baseline only; insufficient raw replay evidence |
| Finance-available snapshot runs | 7 | aligned and cached/lag-like repeated finance snapshots | baseline only; no finance raw payload with `rrdId` |
| Finance-unavailable snapshot runs | 3 | 2026-04-21, 2026-06-19, 2026-06-20 | supports missing/lag availability validation only |
| Explicit cancellation evidence | 1 retained operational set | orders for 2026-06-24 include `is_cancel=true` | normalized legacy evidence only |
| Local WB XLSX input reports | 19 | finance, funnel, stocks, ads, search, logistics, COGS | legacy audit input; not an AI Director 2 raw contract |
| Ozon XLSX workbooks | 5 | parser test artifacts | no target Ozon pipeline |

This is not the requested 20–30 replayable reports. The number and the raw
provenance requirement both prevent an authoritative Golden Regression Pack.

## Legacy Snapshot Baseline

| Seller | Operational date | Finance actual date | Legacy finance available | Gross revenue | Commission | Logistics | Acquiring | Deductions | Tax | Replay status |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `s` | 2026-07-11 | 2026-07-11 | yes | 688.00 | -48.36 | 534.78 | 27.52 | 0.00 | 0.00 | BLOCKED: no raw bundle |
| `seller_001` | 2026-04-18 | n/a | unknown legacy-v1 shape | n/a | n/a | n/a | n/a | n/a | n/a | BLOCKED: incompatible v1 artifact |
| `seller_001` | 2026-04-21 | n/a | no | n/a | n/a | n/a | n/a | n/a | n/a | BLOCKED: no raw bundle |
| `seller_001` | 2026-06-19 | n/a | no | n/a | n/a | n/a | n/a | n/a | n/a | BLOCKED: no raw bundle |
| `seller_001` | 2026-06-20 | n/a | no | n/a | n/a | n/a | n/a | n/a | n/a | BLOCKED: no raw bundle |
| `seller_001` | 2026-06-21 | 2026-06-21 | yes | 8,458.00 | -190.66 | n/a | 403.84 | 1,254.00 | 0.00 | BLOCKED: no raw finance payload |
| `seller_001` | 2026-06-24 | 2026-06-21 | yes | 8,458.00 | -190.66 | n/a | 403.84 | 1,254.00 | 0.00 | BLOCKED: repeated cached finance, no raw payload |
| `seller_001` | 2026-06-25 | 2026-06-25 | yes | 7,138.00 | 955.28 | n/a | 255.96 | 0.00 | 0.00 | BLOCKED: no raw finance payload |
| `seller_001` | 2026-06-26 | 2026-06-25 | yes | 7,138.00 | 955.28 | n/a | 255.96 | 0.00 | BLOCKED: repeated cached finance, no raw payload |
| `seller_001` | 2026-06-27 | 2026-06-25 | yes | 7,138.00 | 955.28 | n/a | 255.96 | 0.00 | BLOCKED: repeated cached finance, no raw payload |
| `seller_001` | 2026-07-26 | 2026-07-26 | yes | 0.00 | 59.48 | 85.80 | 36.24 | 893.00 | 0.00 | BLOCKED: no raw finance payload |

`n/a` means the legacy source did not provide a value in its snapshot, not
zero. The snapshots have been read only; no baseline files were edited.

## Metric Diff

| Metric | Legacy | V2 | Delta | Status |
| --- | --- | --- | --- | --- |
| Operational order quantity | retained for selected legacy runs | not replayed from raw payload | n/a | `BLOCKED` |
| Operational sales quantity | retained for selected legacy runs | not replayed from raw payload | n/a | `BLOCKED` |
| Available stock | retained for selected legacy runs | not replayed from raw payload | n/a | `BLOCKED` |
| Funnel opens/carts/orders | raw funnel payload cached for some days only | partial source evidence only | n/a | `UNRESOLVED` |
| Cohort `buyoutCount` / `buyoutSum` | retained as cohort metrics | no full multi-source replay | n/a | `UNRESOLVED` |
| Realized gross revenue | legacy aggregate present in 7 snapshots | no durable raw finance replay | n/a | `BLOCKED` |
| Marketplace commission | legacy aggregate has mixed signs | Stage 9 policy blocked | n/a | `BLOCKED` |
| Logistics/reverse logistics | legacy aggregate or absent | Stage 9 policy blocked | n/a | `BLOCKED` |
| Acquiring | legacy aggregate has mixed signs | Stage 9 policy blocked | n/a | `BLOCKED` |
| Other marketplace deductions | legacy aggregate has mixed signs | Stage 9 policy blocked | n/a | `BLOCKED` |
| Advertising | selected legacy normalized rows exist | no retained raw advertising payload | n/a | `BLOCKED` |
| Tax | zero or absent in inspected legacy snapshots | sourced tax not supplied | n/a | `UNRESOLVED` |
| COGS | no approved period input paired with replay source | direct COGS not supplied | n/a | `UNRESOLVED` |
| Profit | legacy snapshot does not provide a comparable authoritative total | target intentionally partial for blocked inputs | n/a | `BLOCKED` |
| Margin | legacy snapshot does not provide a comparable authoritative total | target intentionally partial for blocked inputs | n/a | `BLOCKED` |

No row is marked `IDENTICAL` or `ACCEPTED DIFFERENCE`: a Decimal delta would
misrepresent unexecuted replay as a comparison.

## Money Diff

No cent-level `Decimal` comparison was executed. The target accepts immutable
raw endpoint payloads and preserves monetary values as `Decimal`; retained
legacy finance records are a float-based normalized projection. They cannot be
treated as raw Finance Detail because the source record ID, exact endpoint
shape, and field-level provenance are missing. Stage 9 also prohibits a
commission/logistics/acquiring/deductions sign conversion for comparison.

## Pipeline Diff

| Pipeline stage | Retained real artifact | Target replay snapshot | Status |
| --- | --- | --- | --- |
| RAW | cached raw funnel payload only for selected dates | not produced | `BLOCKED` |
| CANONICAL | legacy normalized/reconciled projections | not produced | `BLOCKED` |
| RECONCILIATION | `reconciled_rows.json` | not produced | `BLOCKED` |
| FINANCE INPUT | no durable raw finance identity | not produced | `BLOCKED` |
| FINANCIAL RESULT | legacy aggregate/snapshot only | not produced | `BLOCKED` |
| REPORT PAYLOAD | legacy `report_payload_v2.json` exists for selected runs | not produced | `BLOCKED` |
| PDF | legacy PDFs exist for selected runs | not produced | `BLOCKED` |

The Stage 18 target pipeline was verified only on its synthetic fixtures. It
must not be pointed at a legacy normalized artifact under a claim of raw
parity. Consequently, no new snapshot directory was created in this stage.

## Performance

No legacy-versus-target timing, memory, or transformation-count comparison was
run. A comparable measurement requires executing both pipelines over the same
immutable raw bundle. That bundle is absent. Measuring a legacy artifact read
against target synthetic execution would not be a cutover performance result.

## Cutover Gate

**Decision: NO-GO.** Required evidence to rerun Stage 18.5:

1. 20–30 redacted immutable WB raw bundles covering the requested scenarios.
2. Every endpoint payload, API/schema version, request date scope, UTC
   retrieval time, tenant/account scope, and payload hash.
3. Durable Finance Detail record identifiers, including representative positive
   and negative marketplace component values.
4. Paired approved direct COGS and sourced tax evidence where profit/margin
   parity is expected.
5. A separate product decision and target contract before Ozon parity.

Until then, Stage 9 remains blocked and this report is the complete cutover
validation result.
