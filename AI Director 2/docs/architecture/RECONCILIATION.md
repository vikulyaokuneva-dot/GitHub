# Reconciliation Contract

## Purpose

Stage 4 adds a pure reconciliation boundary after canonical normalization:

```text
RawObject -> Normalizer -> Canonical facts -> ReconciliationResult
```

The initial slice relates `CanonicalSalesFunnelProduct` facts to a synthetic
operational confirmation source. It records whether independently sourced
facts appear to refer to the same product/day fact and whether their raw
canonical values agree. It never edits a canonical input.

## Source Landscape and Legacy Evidence

The frozen synthetic Golden Fixture documents these distinct legacy contours:

| Source | What it describes | Date / identifier evidence | Reconciliation caution |
| --- | --- | --- | --- |
| Sales funnel / cabinet commerce | cohort counts | day; `nmId`, `vendorCode` | never an individual order or sale |
| Orders API | operational order events | order date, `srid`, `nmId` | separate from a financially closed realization |
| Sales API | operational sale/buyout events | event date, `saleID`, `nmId` | operational source, not a finance ledger |
| Finance detailed API | accrual rows | `saleDt`, `nmId`, article, warehouse | can lag; Finance owns it later |

The existing Golden Fixture shows an operational date of `2026-04-21` with
sales-funnel cohort values, a live order (`order-1`), a live sale (`sale-1`),
and a finance row. It also demonstrates that these values need not agree as
interchangeable facts. The fixture is reference evidence only; Stage 4 neither
imports legacy reconciliation nor copies a legacy snapshot shape.

`buyoutCount` and `buyoutSum` remain product/day cohort metrics. Stage 4 stores
them only as `CanonicalCohortMetricFact(metric_kind="buyout_cohort")`; it never
turns them into an order, sale, or financial transaction.

## Responsibilities

- Select a business identity through an explicit, deterministic matching rule.
- Retain all participating canonical facts, source metadata, and raw values.
- Return `matched`, `unmatched`, `partial`, or `conflict` without correcting a
  value from one source with a value from another.
- Emit structured diagnostics explaining the applied rule, missing values, and
  disagreements.
- Preserve operational dates, source retrieval timestamps, and a distinct
  financial-lag state.

## Non-Responsibilities

- No revenue, payout, profit, commission, tax, COGS, advertising, or other
  finance calculation.
- No reconciliation against a finance source in this stage.
- No source mutation, persistence, filesystem/network access, report/PDF
  access, legacy import, implicit deduplication, or global state.
- No use of `retrieved_at` as an event-date fallback.

## Identity Hierarchy

1. **Strong source-record identity**: a confirmation may explicitly reference
   `{sales_funnel_source_object_id}:{source_record_index}`. This is the only
   strong identity in the synthetic Stage 4 slice.
2. **Composite product/day identity**: `operational_date + nm_id`, falling back
   to `operational_date + seller_sku` only when `nm_id` is unavailable.

Composite matching is never silent. Its result has
`identity.rule = composite_operational_date_and_product` and an explicit
diagnostic. Facts must also share the same tenant/account scope. Mixed scopes
are rejected rather than matched.

## Matching and Conflict Policy

| Situation | Result status | Evidence |
| --- | --- | --- |
| Two operational sources match and compared values agree | `matched` | strong or composite identity diagnostic |
| Both source facts match but at least one compared value is absent | `partial` | missing-value diagnostic |
| Matched facts disagree in a compared field | `conflict` | field-specific diagnostic; both values remain intact |
| A source fact has no operational counterpart | `unmatched` | `single_source_fact` diagnostic |

`matched` does not mean financially settled and `conflict` does not choose a
winner. All money remains `Decimal`; there is no rounding, averaging, or value
substitution.

## Date and Lag Semantics

`operational_date` identifies the WB business-day cohort and is copied from
canonical input. `retrieved_at` stays UTC provenance. It is exposed in
`ReconciliationResult.retrieved_at_values`, but is not used to compute the
identity or event date.

Finance is deliberately absent from this slice. Therefore an operational fact
with no finance confirmation receives:

```text
lag_state = awaiting_financial_confirmation
financial_dates = ()
```

This is distinct from conflict. A later finance-specific canonical contract
may produce actual `financial_dates`, after which the reconciler can report
`financial_confirmation_present` without redefining operational facts.

## Result and Diagnostics

`ReconciliationResult` is frozen and contains a deterministic SHA-256
`reconciliation_id`, selected identity, original sales-funnel and confirmation
facts, optional cohort facts, status, diagnostics, operational dates,
financial dates, and lag state.

Diagnostics use typed codes such as:

- `strong_identity_match` / `composite_identity_match`
- `single_source_fact`
- `quantity_conflict`, `amount_conflict`, `currency_conflict`
- `missing_quantity`, `missing_amount`
- `financial_confirmation_pending`
- `cohort_metric_retained`

## Determinism and Immutability

Inputs are sorted by immutable source object ID and source-record index.
Results are sorted by their content-derived ID, so input ordering cannot alter
the output. The models are frozen Pydantic models; reconciliation holds the
original canonical values and never writes to them.

## Synthetic Scenarios

| Scenario | Contract test coverage |
| --- | --- |
| A: matched | strong identity and composite product/day matches |
| B: unmatched | an isolated source fact remains visible |
| C: conflict | same strong identity with distinct quantity and amount |
| D: lagged | operational fact has no financial fact; lag is not conflict |
| E: cohort | `buyoutCount` / `buyoutSum` remain `buyout_cohort` metrics |

Tests additionally cover missing values, deterministic ordering, result/source
immutability, and tenant/account isolation.

## Future Extension Pattern

Each source-family addition must be a separate task: define its canonical
model, source and date semantics, strong and composite matching eligibility,
conflict fields, lag/finality behavior, and fixtures. Financial source
matching belongs with the Stage 5 Finance Kernel Contract and must not be
implemented as a shortcut in this package.
