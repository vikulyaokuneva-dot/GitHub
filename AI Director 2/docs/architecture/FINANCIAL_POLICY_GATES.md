# Stage 5.3 Final Financial Evidence Investigation

## Scope

Stage 5.3 investigates what the repository artifacts can prove. It does not
implement a Finance Kernel, alter legacy code, modify the Golden Fixture or
parity harnesses, create a COGS allocation algorithm, or invent tax, return,
or advertising rules.

The statuses below describe readiness for a future kernel boundary:

- `READY`: the contract rule and the source mapping are sufficiently evidenced
  for the stated, narrow use.
- `OPTIONAL`: the component is representable without blocking the kernel core;
  a missing value keeps the result partial rather than becoming zero.
- `BLOCKED`: a required calculation or mapping lacks evidence and must not run.
- `UNRESOLVED`: the component can be retained as a diagnostic fact, but its
  economic classification or use is not proven.

`CONFIRMED` in this document means a restriction or representation is backed
by local evidence. It does not claim uninspected WB API semantics.

## Final Readiness Table

| Gate | Evidence | Decision | Kernel behavior | Status |
| --- | --- | --- | --- | --- |
| Classified financial sale revenue | 21 rows with `row_group=sale`; every row has `retailAmount = gross_revenue = realized_sales_revenue`; buyer price and payout differ | `retailAmount` maps to the internal `realized_gross` view only for a classified financial sale | emit `realized_revenue` with trace and actual financial date; keep buyer and payout views separate | `READY` |
| P&L revenue | Finance API Metric Passport names `retailAmount` gross revenue; classified financial sale evidence confirms the distinct amount relationship | P&L revenue view is `realized_gross`, not buyer price or payout | calculate no P&L from an unclassified row or an operational price fallback | `READY` |
| Marketplace deduction retention | finance rows have independent commission, delivery, storage, deduction, and acquiring fields | retain every supplied value separately with source provenance; the normalization layer stores the source sign untouched and never assigns meaning to it | missing remains missing and is not emitted as a component; a field the source declares as zero is emitted as a zero, which is a different fact | `READY` |
| Marketplace deduction sign policy | 40 real `sales-reports/detailed` rows with durable `rrdId`: every charge field is a non-negative magnitude and the row type comes from `sellerOperName`; the mixed signs previously cited came from the synthetic Golden Fixture, which only feeds legacy snapshot parity | `marketplace-sign-policy-v1` in `packages/finance/marketplace_policy.py`: canonical `−raw` for a documented magnitude, source value preserved as `UNRESOLVED` when the sign contradicts the convention | emit signed marketplace components with per-component provenance; a contradicting sign is never repaired and no `abs()` is permitted in the sign path | `READY` (2026-09-04, was `BLOCKED`) |
| Financial finality/status | no inspected artifact contains a WB closure field; row presence and legacy coverage are not finality | current source finality is `unknown` | results with financial facts but unknown finality remain `partial`; no final net profit | `READY` |
| `rebillLogisticCost` | 20 real rows named "Возмещение издержек …" with durable `rrdId`, non-negative amounts (76.92, 46.91), `retailAmount` and payout both zero, and a negative VAT base on every one of them: `vw = -rebillLogisticCost / 1.22` with matching negative `vwNds`, exact to the cent, zero counterexamples in 40 rows | the source books the operation as a reduction of the seller's revenue base, which is the accounting signature of a charge against the seller; a credit would carry a positive base like "Продажа" or no base like logistics and storage | admit as `rebill_logistics` with canonical `−raw` under `marketplace-sign-policy-v1`; a contradicting source sign still falls back to `UNRESOLVED` with the original amount preserved | `READY` (2026-09-04, was `UNRESOLVED`) — proof in `docs/architecture/REBILL_LOGISTICS_EVIDENCE.md` |
| Unit COGS source | WB finance rows contain no COGS; local Excel evidence exists with seven SKU unit costs, but no effective dates | COGS is an explicit Product Economics input, never WB-derived | accept only a sourced unit cost with an effective period; missing remains unavailable | `READY` |
| Unit COGS allocation | sale rows have `nmId` and quantity, but returns/cancellations lack event linkage and finality | no automatic unit-cost multiplication policy is approved | do not derive COGS from WB events until the event policy is approved | `BLOCKED` |
| Period COGS | `FinancialComponent.COGS` already accepts a signed, sourced period amount | direct period COGS is a separate input view | consume only a provided external period amount; do not derive it from orders or buyouts | `READY` |
| Returns and partial returns | return quantities appear on logistics rows, but have no financial event ID, sale link, or finality | return count is not a COGS reversal event | retain as operational/diagnostic evidence; no COGS reversal or net realized quantity | `BLOCKED` |
| Cancellations | orders contain `isCancel` and `srid`; finance rows contain no matching cancellation ID or shipment stage | cancellation stage and financial effect are unknown | do not create COGS or revenue adjustments from an operational cancellation | `BLOCKED` |
| Tax | inspected finance artifacts contain only zero or missing tax; no rate or base is evidenced | sourced and calculated tax remain distinct; 6% is not policy | represent tax as `missing`/unresolved and return `partial`; kernel core can operate without it | `OPTIONAL` |
| Advertising attribution | direct `nmId` evidence is separate from campaign, associated, period, and unknown costs | no invented SKU allocation | consume direct SKU cost only when direct evidence plus `nmId` exists | `OPTIONAL` |

## Stage 9.0: Marketplace Sign Policy Matrix

### Policy Boundary

The canonical finance contract represents revenue as a positive `Decimal` and
marketplace deductions as negative `Decimal` values. This is a target economic
contract, not a rule to copy, negate, or apply `abs()` to a source value.

The only permitted transformation path is:

```text
source value and endpoint semantics
  -> identified economic event
  -> canonical component
  -> authoritative signed Decimal
```

`READY` would require evidence for every arrow in that path. The available
evidence establishes field retention and some legacy names, but it does not
establish a source-level signed economic event for any requested marketplace
component. Consequently, Stage 9.0 approves no new authoritative deduction
mapping. This is deliberate: `missing`, `unknown`, and `unresolved` remain
distinct from `Decimal("0")`.

| Field | Source endpoint | Example source signs | Legacy transformation | Economic meaning | Target component | Target sign | Evidence | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ppvzSalesCommission` (with legacy compensation aliases) | Finance detailed candidate: `POST /api/finance/v1/sales-reports/detailed`; aliases are also accepted from legacy-report-shaped rows | Golden raw detailed row: `+250.00`; retained normalized artifact contains both positive and negative `wb_commission` values | Composite of `ppvzSalesCommission`, `wbRewardBeforeAgent`, `pvzCompensation`, and payment-service compensation fields; summed directly, then subtracted in legacy profit | Project passport calls it WB commission, but the retained evidence does not prove whether every signed value is a charge, correction, or a net settlement adjustment | `marketplace_commission` only after source-event semantics are proven | No authoritative sign assigned | `docs/METRICS_PASSPORT.md` names the field and components; Golden row and normalized snapshot demonstrate incompatible retained sign representations; `v3/metrics/financial_kernel.py` folds several fields | `CONFLICT` |
| `deliveryService` / `deliveryRub` and aliases | Finance detailed candidate: `POST /api/finance/v1/sales-reports/detailed`; legacy aliases accept multiple endpoint shapes | Golden raw detailed row: `deliveryRub=-90.00`; retained normalized artifact has positive logistics values | Legacy selects the first truthy alias and applies `abs()` before aggregation for sales, returns, logistics, and fallback rows | Delivery/logistics label is present, but the evidence does not distinguish a charge from a correction and does not prove one sign convention across aliases/endpoints | `logistics` only after source-event semantics are proven | No authoritative sign assigned | Metric passport labels the aliases logistics; `wb_api_core/normalize.py` collapses many aliases; legacy `abs()` erases sign; retained artifact differs from Golden sign | `CONFLICT` |
| Reverse logistics | No separate source field or endpoint mapping retained | No source example: reverse logistics is only a derived legacy/report concept | No separate transformation; legacy folds logistics aliases and `rebillLogisticCost` into one magnitude | Not separable from ordinary logistics, return-related delivery, rebill, or corrections | none | No sign assigned | `docs/METRICS_PASSPORT.md` contains a legacy derived `return_reverse_logistics` formula, while the finance artifacts retain no distinct raw field or durable event link | `UNRESOLVED` |
| `acquiringFee` and aliases | Finance detailed candidate: `POST /api/finance/v1/sales-reports/detailed` | Golden raw detailed row: `-15.00`; retained normalized artifact has positive acquiring values | Normalizer retains the value, but the inspected legacy finance kernel has no independent acquiring aggregation/sign rule | Acquiring label identifies a candidate fee, but the source evidence does not prove whether a positive or negative value is a fee, refund, correction, or already-netted settlement item | `acquiring` only after source-event semantics are proven | No authoritative sign assigned | Golden raw fixture, retained normalized snapshot, `wb_api_core/normalize.py`, and metric-passport field map disagree on retained sign representation and supply no signed-event contract | `CONFLICT` |
| Acceptance | No mapped source field or endpoint projection found | No source example | No legacy transformation found | No independently evidenced acceptance economic event | none | No sign assigned | `FinancialComponent.ACCEPTANCE` exists as a target vocabulary value, but searches of normalizer, legacy kernel, metric passport, and artifacts found no accepted source mapping | `UNRESOLVED` |
| `deduction` / `deductions` (other marketplace deductions) | Finance detailed candidate: `POST /api/finance/v1/sales-reports/detailed` | Golden raw detailed row: `-10.00`; retained normalized artifact has positive deductions values | Retained separately by normalizer; no component-specific legacy sign transformation located | "Other deduction" is economically broad and can include corrections or different events; its name alone is insufficient to classify every value as an expense | `other_marketplace_deduction` only after event taxonomy is proven | No authoritative sign assigned | Metric passport labels `deduction` as other deductions; normalizer classifies by broad text markers including corrections/acquiring; artifacts show incompatible retained signs | `CONFLICT` |
| `rebillLogisticCost` | Finance detailed candidate and legacy finance-report-shaped artifacts | Retained artifacts: non-zero positive values, including `+68.61`; no retained raw payload or durable source ID | Legacy applies `abs()` and adds it to logistics | Could be reimbursement, rebill, logistics correction, marketplace compensation, or an already-represented adjustment | none; preserve `RebillLogisticsInput` diagnostic only | No sign assigned | Detailed investigation below: two endpoint variants, inconsistent operation metadata, absent durable identity, and no source-level economic classification | `UNRESOLVED` |

### Legacy `abs()` Assessment

| Field or legacy bucket | `abs()` classification | Decision |
| --- | --- | --- |
| Commission composite | `D` -- unknown | Legacy does not call `abs()` for the composite, but directly summing a blend of commission and compensation fields also cannot be promoted to a target sign policy. |
| Delivery/logistics aliases | `B` -- hides mixed source semantics | The same broad alias bucket covers sales, returns, logistics operations, and fallback rows. The Golden raw negative value and retained positive values demonstrate that the magnitude aggregation cannot establish one authoritative signed expense rule. |
| Reverse logistics | `B` -- hides mixed source semantics | There is no separate source field; legacy's magnitude bucket conceals whether a value is ordinary delivery, return delivery, correction, or rebill. |
| Acquiring | `D` -- unknown | No independent legacy aggregation/sign rule is present. The target cannot derive a rule from the fact that it was retained elsewhere. |
| Acceptance | `D` -- unknown | No source or legacy mapping exists. |
| Other deductions | `D` -- unknown | Legacy/project aggregation identifies only a broad `deduction` label, not a homogeneous event class with a sign contract. |
| `rebillLogisticCost` | `B` -- hides mixed source semantics | Legacy adds `abs(rebill)` to logistics, which discards a reimbursement/correction sign and collapses an unclassified field into a different component. |

### Stage 9 Disposition

No requested marketplace component is `READY`. They can all be retained as
canonical source facts and safely excluded from authoritative P&L, but a Stage
9 implementation that emits signed marketplace deductions would change the
base financial contract without evidence. Stage 9 therefore remains stopped at
the semantic blocker. A future unblock requires a redacted raw payload with a
stable record ID and source documentation or an approved versioned field-level
event/sign policy; it must not use a silent `abs()` fallback.

## Rebill Investigation

### Available Source Evidence

The artifacts retain normalized finance rows, not the original finance endpoint
payload. No inspected artifact contains `raw_payload`, `rrdId`, `srid`,
`saleID`, `saleId`, or `orderId` for the rebill records. `_raw_row_index` is a
position in one response and is diagnostic, not a durable source identity.

Two independent artifact sets contain non-zero values:

| Endpoint artifact | Rows | Sum | Operation evidence | Other observed facts |
| --- | ---: | ---: | --- | --- |
| Finance detailed, `2026-07-19` | 24 | `452.61` | operation/document: `Возмещение издержек по перевозке/по складским операциям с товаром`; group `reimbursement` | `logistics=0`, `seller_payout=0`, dates are `2026-07-19` |
| Legacy finance report, `2026-07-26` | 23 | `677.45` | operation and document are empty; group `other` | `logistics=0`, `seller_payout=0`; some rows have `nmId`, some only a barcode-like SKU |

The source endpoint differs between these sets, so equal-looking rows cannot be
deduplicated by amount, date, SKU, or raw index. In each individual snapshot,
the finance cache and daily snapshot are two materializations of the same
selected source rows and must not be counted as separate events.

### Detailed Example

```text
Source record
  artifact: cabinets/seller_001/artifacts/wb_api_core/2026-07-20/
            snapshot.json, finance_final_daily.rows[30]
  source endpoint: /api/finance/v1/sales-reports/detailed
  available identifiers: no durable transaction/order/sale ID; _raw_row_index=30
  dates: order_date=sale_date=report_date=2026-07-19
  raw-value visibility: original raw payload is not retained

Available normalized source fields
  operation/document: "Возмещение издержек по перевозке/по складским
                      операциям с товаром"
  nmId/seller SKU: absent
  quantity: 2
  rebill_logistic_cost: +68.61
  logistics/logistics_amount/seller_payout: 0 / 0 / 0

Canonical representation
  row_group=reimbursement
  has_financial_effect=true
  include_logistics=true (legacy aggregation flag only)

Reconciliation
  rebill_logistic_cost contributes to a separate daily aggregate of 452.61;
  it is not a sale revenue or payout value.

Proposed financial component
  none; diagnostic=unresolved_rebill_excluded
```

The reimbursement label establishes only that the normalizer recognized a
reimbursement-like text. It does not establish whether positive
`rebillLogisticCost` is a refund, rebill, logistics correction, marketplace
compensation, other adjustment, or a value already represented elsewhere. The
legacy `abs()` logistics aggregation destroys the source sign and cannot supply
that missing economic meaning.

**Decision:** `rebill_classification = unresolved`. Finance Kernel must not
automatically include this field in `logistics`, `reverse_logistics`, revenue,
or payout. It must preserve a diagnostic trace and keep an authoritative P&L
partial when the unresolved value is material. This is the safe behavior that
prevents both invented expense semantics and double count.

To close the gate, retain a redacted raw finance payload with a stable source
record ID and WB documentation for the field's sign and economic meaning.

## Retail Amount, Realized Gross, And P&L Revenue

The project Metric Passport defines Finance API `retailAmount` as gross revenue
and `ppvzForPay` as seller payout. This is supported by the classified finance
sale rows, not by a generic alias alone. Across the inspected classified sale
rows, all 21 records satisfy:

```text
retailAmount = gross_revenue = realized_sales_revenue
retailAmount != buyer discounted amount
seller_payout != retailAmount
```

In 9 records payout is greater than `retailAmount`; in 12 it is lower. It is
therefore a separate settlement view, not a subtraction-derived alias for
revenue.

**Concrete finance-sale example** from the detailed finance artifact:

| Field | Value |
| --- | ---: |
| quantity | `1` |
| operation/document | `Продажа` / `Продажа` |
| order date / financial date | `2026-07-14` / `2026-07-19` |
| `retailPriceWithDisc` / buyer discounted amount | `800.00` |
| `retailAmount` | `451.00` |
| `gross_revenue` / `realized_sales_revenue` | `451.00` / `451.00` |
| `ppvzForPay` / seller payout | `493.96` |
| commission / acquiring | `-50.00` / `18.04` |

The buyer price is the customer-facing discounted-price view. `retailAmount`
is the finance-sale gross view carried consistently into both realized fields.
`ppvzForPay` is the independently reported settlement value. The component
fields do not form a reliable per-row payout equation in the artifacts, so the
kernel must retain all views rather than derive one from another.

Two records from the legacy report endpoint also contain a positive
`retailAmount`, but blank operation labels and no `realized_sales_revenue`.
They are not evidence for P&L revenue because they cannot be classified as a
financial sale.

**Decision:** `realized_gross` is confirmed as the target P&L revenue view
only when the record is a classified Finance API sale and the amount is sourced
from `retailAmount`. It is not a fallback for operational `priceWithDisc`,
`totalPrice`, or seller payout. This closes the source mapping for the kernel
core while retaining the explicit source-field provenance for later external
WB API documentation review.

## COGS Evidence And Model

WB finance artifacts contain no COGS field. COGS must enter Finance as explicit
Product Economics data. Existing project evidence supports a local seller
input: audit artifacts describe a parsed workbook
`local_audit/input/cogs/Себестоимость товара.xlsx` with columns `Артикул WB`
and `Себестоимость`, seven loaded SKU values, and partial coverage. The runtime
`cogs.json` for `seller_001` currently contains no SKU costs. The architecture
also specifies `ProductCostProfile` with unit cost, packaging, effective dates,
and source.

The workbook proves an input source exists; it does not prove a cost effective
date, accounting method, or WB-derived economic event. Its absence or partial
coverage must remain unavailable, never zero.

### Two Explicit COGS Views

| View | Input | Status | Safe behavior |
| --- | --- | --- | --- |
| Unit Economics COGS | declared unit COGS, packaging cost, product identity, effective period, and an approved realized quantity policy | model `READY`, allocation `BLOCKED` | retain the unit cost as input; do not multiply it by WB quantity automatically yet |
| Period P&L COGS | external signed `FinancialComponent.COGS` amount with period scope and provenance | `READY` | consume the supplied amount directly; do not derive it from orders, buyouts, or WB finance rows |

This deliberately keeps unit economics and period P&L as separate financial
views. Neither one is inferred from `buyoutCount`, `buyoutSum`, or an
unattributed SKU report.

## Sales, Returns, Cancellations, And Partial Returns

| Scenario | Evidence available | Quantity available | Event identity available | Financial finality available | Decision |
| --- | --- | --- | --- | --- | --- |
| sale | classified Finance API sale rows | yes (`quantity`) | no durable finance transaction ID retained | no | revenue mapping is ready; COGS allocation remains blocked |
| return | `returns_qty` appears on finance logistics rows | yes as an aggregate row count | no link to original sale/order | no | do not reverse COGS or revenue automatically |
| cancellation before shipment | operational Orders API contains `isCancel=true`, cancellation date, and `srid` | yes | yes in Orders API | no financial effect/finality link | do not create P&L or COGS component |
| cancellation after shipment or delivery | no explicit shipment/delivery stage plus cancellation evidence | no | no | no | unresolved; do not infer stage |
| partial return | sale and return quantities exist in different unlinked rows | no reliable remaining realized quantity | no | no | do not calculate net COGS or reversal |
| non-buyout | only cohort-style buyout data is available | aggregate only | no event link | no | do not use as a sale/return substitute |

The available return rows are labeled logistics, hold zero sales revenue and
payout, and carry no retained transaction identity. Their quantity establishes
that a return-related count was reported, but not a source-of-truth event for
COGS reversal. Operational cancellation records similarly do not expose the
post-shipment or post-delivery state. These are intentional limitations, not
zero values.

## Tax And Advertising

Inspected finance rows contain only zero or missing tax. The Finance contract
already distinguishes `provided`, `missing`, and `not_applicable` states, and
`FinancialResult(status=partial)` cannot claim net profit. Therefore tax is an
optional unresolved component, not a core-blocking calculation gate. A future
versioned tax policy or documented sourced tax amount may close it; the legacy
6% calculation remains prohibited as default policy.

Advertising is likewise optional for the core: direct SKU cost needs direct
evidence and `nmId`; campaign, associated, period, and unknown costs remain
period-level or unknown and receive no invented SKU allocation.

## Safe Fallback Behavior

| Condition | Required behavior |
| --- | --- |
| unclassified finance row with positive `retailAmount` | retain as source fact/diagnostic; exclude from `realized_revenue` |
| no financial sale row for an operational day | `awaiting_financial_confirmation`; do not substitute operational buyer price |
| unresolved rebill | exclude from authoritative P&L; retain source trace/diagnostic; no double count across snapshot/cache representations |
| missing or unresolved tax | `FinancialComponentInput(state=missing, amount=None)` and `FinancialResult(status=partial)`; never `0` |
| missing COGS source or incomplete coverage | COGS is unavailable; period result stays partial; do not use zero or a hard-coded fallback |
| return, cancellation, partial return, or non-buyout without linked final event | no automated COGS reversal, no net realized quantity, and no P&L adjustment |
| period-level/associated/unknown advertising | retain outside SKU P&L; do not allocate proportionally to sales |

## Finance Kernel Readiness

The boundary is **READY for a constrained core**, but a complete profit
calculator is **BLOCKED** until its required inputs are supplied or the result
is deliberately returned as `partial`.

The constrained core may accept:

- classified finance-sale `realized_gross` revenue;
- independently sourced marketplace deductions;
- explicit external period COGS input;
- optional tax and advertising inputs;
- financial dates, provenance, and `unknown` finality.

It must not automatically calculate:

- rebill economics;
- unit COGS allocation or reversal;
- return/cancellation/partial-return effects;
- tax from a rate;
- SKU advertising allocation without direct evidence;
- a `complete` final result without an explicit closure signal.

## Source Trace

- `cabinets/seller_001/artifacts/wb_api_core/2026-07-20/` and
  `tmp_out/wb_report_79_fixed/.../2026-07-20/`: classified detailed finance
  sale and reimbursement evidence.
- `cabinets/seller_001/artifacts/wb_api_core/2026-07-26/`: second finance
  endpoint variant with unlabeled positive rebill rows.
- `wb_api_core/normalize.py` and `wb_api_core/reconcile.py`: exact retained
  field projection and daily aggregation behavior.
- `docs/METRICS_PASSPORT.md`: existing project semantics for `retailAmount`,
  seller payout, and local COGS.
- `local_audit/output/facts_audit_2026-07-17.json` and
  `cabinets/seller_001/artifacts/facts_audit_2026-06-19.json`: parsed local
  COGS workbook evidence and partial coverage.
- `AI Director 2/WB_Autopilot_Architecture_Codex_v1.md`: Product Economics
  ownership and `ProductCostProfile` specification.
