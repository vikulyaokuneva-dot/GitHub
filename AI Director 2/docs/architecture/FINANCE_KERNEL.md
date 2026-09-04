# Finance Kernel Contract

## Purpose And Scope

Stage 6 implements the constrained deterministic Finance Kernel Core:

```text
Reconciled facts -> FinancialInput -> Finance Kernel -> FinancialResult
```

The current implementation provides typed, immutable, Decimal-only contracts,
the pure `calculate_financial_result(FinancialInput)` calculator, and focused
contract/kernel tests. It does not implement a WB API client, raw loader,
normalizer, legacy adapter, report, database, filesystem, or network operation.

Finance Kernel Core is not yet a full WB Profit Engine.

## Stage 8 Finance Detail Revenue Migration

The finance-detail source is a distinct raw/canonical slice:

```text
RawObject(FINANCE_DETAIL) -> CanonicalFinanceDetailRecord
-> build_financial_input_from_finance_detail -> Finance Kernel
```

The source mapping preserves separate Decimal views from the same classified
finance-sale record:

| Raw source field | Canonical / Finance view | Stage 8 behavior |
| --- | --- | --- |
| `retailAmount` | `realized_gross`, `realized_revenue` | P&L revenue only for `financial_sale` records with a durable `rrdId` |
| `retailPriceWithDiscRub` | `buyer_discounted` | retained as a separate buyer-price view; it is not P&L revenue |
| `ppvzForPay` | `seller_payout` | retained as a separate settlement view; it is not P&L revenue |

`supplierOperName` and `docTypeName` are source-text classification evidence.
A return, unclassified, or otherwise non-sale record with a positive
`retailAmount` stays canonical but is excluded from authoritative realized
revenue. Missing `retailAmount` and missing durable `rrdId` are diagnostics,
not zero values. The detailed endpoint supplies no explicit finality signal,
so its Stage 8 inputs use `unknown` finality and Finance Kernel returns a
partial result until other required components and finality evidence exist.

The future kernel consumes only `FinancialInput`, not raw objects, endpoint
payloads, or legacy modules. It must be deterministic, auditable, and free of
global state.

## Input And Output Contracts

`FinancialInput` is a period-level input for one tenant/account, one
`operational_date`, one currency, reconciled facts, financial components, COGS
allocation inputs, advertising attribution, finality evidence, unresolved COGS
events, and a rounding policy.

`FinancialComponentInput` contains exactly one signed Decimal amount, an
availability state, and provenance: source, source record ID, source endpoint,
operational date, and optional financial date. It distinguishes:

| State | Amount |
| --- | --- |
| `provided` | Decimal, including explicit zero |
| `missing` | no amount |
| `not_applicable` | no amount |

`FinancialResult` is a period P&L result contract. It carries actual financial
dates, component traces, optional net profit and margin, diagnostics, and the
selected rounding policy. A non-complete result cannot claim net profit. A
`FinancialComponentTrace` preserves contributing component inputs instead of
silently replacing values.

The kernel sums authoritative signed inputs exactly once. A complete result
contains the aggregate net profit and percentage margin. A partial, lagged,
conflicting, or insufficient result keeps those authoritative totals
unavailable rather than presenting a knowingly incomplete number as profit.

## Metric Ownership And Revenue Views

| Metric or calculation | Owner | Required view or input | Current rule |
| --- | --- | --- | --- |
| buyer-facing sales analytics | operational analytics | `buyer_discounted` | never substitute financial payout or realization |
| realized revenue | Finance Kernel | `realized_gross` | requires a classified financial realization row |
| marketplace financial P&L | Finance Kernel | `realized_gross` | only for a classified finance-sale row sourced from `retailAmount`; unresolved inputs keep the result partial |
| seller payout reconciliation | Finance Kernel | `seller_payout` | settlement fields remain distinct from realized revenue |
| unit economics | Product Economics input | explicitly declared view | no default view is approved |
| marketplace commission | Finance Kernel | sourced component | never advertising spend |
| logistics and reverse logistics | Finance Kernel | separately classified source components | no rebill inference |
| acquiring | Finance Kernel | sourced component | `acquiringFee` candidate alias |
| storage, penalties, other deductions | Finance Kernel | sourced components | separate from logistics and advertising |
| advertising | Advertising domain; Finance consumes cost | attributed expense | no SKU allocation without direct evidence |
| tax | Finance Kernel | sourced amount or approved versioned policy | legacy 6% is prohibited as a default |
| COGS and packaging | Product Economics input | direct period cost or unit cost plus caller-authoritative realized quantity | no quantity is inferred from WB cohort metrics |

There is no universal `revenue` metric. `buyer_discounted`, `realized_gross`,
and `seller_payout` remain named views, even when they share a source row.
For a classified finance-sale row, `retailAmount` is the confirmed project
mapping for `realized_gross`: inspected rows preserve the same amount as
`gross_revenue` and `realized_sales_revenue`, while buyer price and seller
payout are separate views. An unclassified finance row with a positive
`retailAmount` is not revenue input.

`buyoutCount` and `buyoutSum` are cohort metrics. They cannot create financial
transactions, financial revenue, or financial COGS.

## Sign Convention

The target input convention is signed money:

| Component | Required sign |
| --- | --- |
| `realized_revenue` | positive or zero |
| `return_revenue_adjustment` | negative or zero |
| commission, logistics, reverse logistics, acquiring, storage, acceptance, penalties | negative or zero |
| other marketplace deductions, advertising, tax, COGS, packaging | negative or zero |

`packages/finance/marketplace_policy.py` is that source adapter for WB
marketplace charges: it maps one documented source field to one signed
component, keeps the raw value and provenance in the canonical record, and
returns an unresolved component instead of repairing a sign that contradicts
the documented convention. The kernel sums signed components once; it does not
apply `abs()` or subtract a negative component again, and it imports no sign
policy of its own.

## Decimal And Rounding Policy

Money is `Decimal` only. Floats are rejected by all financial contracts,
including unit economics. A source adapter must parse text directly to Decimal;
`Decimal(float_value)` is forbidden.

The current policy is `aggregate_then_half_up_to_cent`: retain source Decimal
precision during component collection and calculation, aggregate first, then
round a final presentational or settlement result to `0.01` with
`ROUND_HALF_UP`. No intermediate `round()` calls are authorized. Any
jurisdiction-specific exception requires approval before implementation.

## Marketplace Deductions And Rebill Protection

Commission, logistics, reverse logistics, acquiring, storage, penalties, and
other marketplace deductions have distinct component names. Advertising is
separate from commission; COGS and packaging are separate from marketplace
deductions. A source record may contribute each component once;
`FinancialInput` rejects duplicate `(component, source_record_id)` pairs.

`rebillLogisticCost` is an admissible deduction component, settled from the
source rather than from a guess: on all 20 real rows the VAT base is negative and
exactly `vw = -rebillLogisticCost / 1.22`, with `forPay` and `retailAmount` both
zero. WB books the operation as a reduction of the seller's revenue base, so the
kernel receives `rebill_logistics` as a signed negative component. The gate that
formerly held it out is documented in
`docs/architecture/REBILL_LOGISTICS_EVIDENCE.md`, including the falsification
criteria and the fallback: a source value that contradicts the non-negative
convention still arrives as `UNRESOLVED` with its original amount and keeps the
period partial.

`RebillLogisticsInput` is the separate Stage 6 diagnostic channel. It is not the
authoritative path for finance-detail rows, which arrive as components, and it
still reports itself as unresolved so a caller cannot mistake the diagnostic
input for a classified expense.

## Tax, COGS, Returns, And Advertising

Tax is either a sourced amount with documented source semantics or an output of
an approved, versioned tax policy. Those are distinct facts. The legacy
`gross_revenue * 0.06` calculation is not an approved rule and must not be
implemented by default. Current inspected artifacts contain only zero or
missing tax values, so they do not establish a rate, basis, or legal rounding.
Tax is optional at the kernel boundary: it is represented as `missing`, not
zero, and keeps a result `partial` until resolved.

`CogsAllocationInput` makes a declared unit cost, optional packaging cost,
effective date, source, and caller-authoritative realized quantity explicit.
Missing COGS is not zero. The kernel supports two mutually exclusive inputs:
a sourced signed period `COGS` component, or unit COGS multiplied by that
explicit quantity. Supplying both is a conflict. The kernel never derives the
quantity from `buyoutCount` or `buyoutSum`.

`UnresolvedCogsEventInput` retains return, cancellation, or partial-return
evidence. Without an explicit Product Economics treatment it makes COGS
unresolved and the result partial; it never creates a reversal, zero cost, or
allocation automatically.

Financial returns require classified finance rows. A return revenue adjustment
is negative; related reverse logistics is separate. COGS reversal is not
inferred from operational orders, sales, returns, or buyout cohort facts.

Advertising expense has evidence-bound granularity:

| Evidence | Finance input attribution | SKU cost allowed |
| --- | --- | --- |
| direct conversion with `nmId` | `direct` | yes |
| campaign total, period total, or associated conversion | `period_level` | no |
| insufficient evidence | `unknown` | no |

Campaign totals are period facts, not a license to proportionally allocate
advertising across SKU sales.

## Dates, Finality, Statuses, And Trace

Operational date and financial date remain independent. Financial dates in a
result are actual source dates, never inferred from `retrieved_at`.

Row presence is evidence of a financial fact, not source finality. In the
current source evidence, no WB closure signal is available, so finality is
`unknown`. `provisional` is reserved for a future explicit preliminary signal,
and `final` requires an approved explicit closure signal plus a financial date.
A completeness or attribution heuristic cannot supply that signal.

An operational result with no finance fact is
`awaiting_financial_confirmation`, not zero, complete, or conflict by itself.
Present but unknown/provisional financial facts can produce `partial`; only
approved finality and all other required inputs may permit `complete`.

Financial statuses are `complete`, `partial`,
`awaiting_financial_confirmation`, `conflict`, and `insufficient_data`. Status
is not a monetary value.

Status precedence is deterministic:

1. duplicate source keys or mutually exclusive inputs -> `conflict`;
2. operational reconciliation awaiting finance with no revenue ->
   `awaiting_financial_confirmation`;
3. no usable realized revenue -> `insufficient_data`;
4. missing/unresolved inputs or non-final evidence -> `partial`;
5. realized revenue, required inputs, and explicit finality -> `complete`.

Each result component has one `FinancialComponentTrace` referencing original
inputs and provenance. It records amount, status, included/excluded state, and
reason. The result therefore enumerates every formula component it uses:

```text
FinancialResult -> FinancialComponentTrace -> FinancialComponentInput -> source record
```

## Unresolved Blocking Gates

The former first gate — the `rebillLogisticCost` settlement direction — closed on
2026-09-04 from source evidence, not from a decision: the operation carries a
negative VAT base on all 20 real rows. See
`docs/architecture/REBILL_LOGISTICS_EVIDENCE.md`.

1. Return/cancellation linkage and reversal policy. Explicit caller-authoritative
   realized quantity is supported, but the kernel does not derive it.
2. WB financial closure signal and admissible lag window for `complete`
   results. A `complete` period today rests on the seller's own finality
   declaration; WB does not expose a closure field in the inspected payload.
3. A closed-period, redacted Decimal fixture with documented signed components
   for full calculation parity. Real open-period rows plus their signed
   components are now available; a period WB itself marks closed is not.

Tax is unresolved but optional: it must remain missing and make the result
partial, not prevent use of the constrained kernel boundary.
