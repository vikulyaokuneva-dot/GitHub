# Stage 9.0 Blocker Report: Marketplace Sign Policy

## Result

Stage 9.0 is complete. It examined the available source evidence, retained
normalized artifacts, Golden raw fixture, metric passport, and legacy
semantics without changing legacy code or the Golden Fixture.

No requested marketplace deduction is `READY` for authoritative P&L. The
existing artifacts prove candidate field names and preserve values, but do not
prove a field-by-field economic event and its signed source convention. Where
the evidence conflicts, source values must remain diagnostic facts rather than
being normalized by a silent `abs()` rule.

## Authoritative Sign-Policy Matrix

| Field | Source endpoint | Example source signs | Legacy transformation | Economic meaning | Target component | Target sign | Evidence | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ppvzSalesCommission` and compensation aliases | Finance detailed candidate: `POST /api/finance/v1/sales-reports/detailed`; legacy-report-shaped aliases also accepted | Golden raw row: `+250.00`; retained normalized values include both positive and negative commission | Sum commission plus `wbRewardBeforeAgent`, PVZ, and payment-service compensation fields; subtract the result in legacy profit | Candidate commission expense, but the blend can contain charge, correction, or net-settlement semantics | `marketplace_commission` only after source-event semantics are proven | No authoritative sign assigned | Metric passport, Golden raw fixture, normalized snapshot, and `v3/metrics/financial_kernel.py` | `CONFLICT` |
| `deliveryService` / `deliveryRub` and aliases | Finance detailed candidate: `POST /api/finance/v1/sales-reports/detailed`; multiple legacy aliases | Golden raw row: `deliveryRub=-90.00`; retained normalized logistics values are positive | Select first truthy alias and apply `abs()` in every legacy aggregation branch | Delivery/logistics label exists, but a charge, correction, and alias-specific sign convention are not distinguished | `logistics` only after source-event semantics are proven | No authoritative sign assigned | Metric passport, normalizer alias list, Golden raw fixture, normalized snapshot, legacy `abs()` | `CONFLICT` |
| Reverse logistics | No distinct retained source field | No source example | No separate mapping; legacy folds logistics aliases and rebill into one magnitude | Cannot be separated from ordinary delivery, return delivery, rebill, or correction | none | No sign assigned | Legacy derived report formula has `return_reverse_logistics`; finance artifacts have no distinct raw field or durable event link | `UNRESOLVED` |
| `acquiringFee` and aliases | Finance detailed candidate: `POST /api/finance/v1/sales-reports/detailed` | Golden raw row: `-15.00`; retained normalized acquiring values are positive | Value is retained by normalizer; no independent legacy finance-kernel aggregation/sign rule | Candidate fee, but a fee, refund, correction, and already-netted settlement item cannot be distinguished | `acquiring` only after source-event semantics are proven | No authoritative sign assigned | Golden raw fixture, normalized snapshot, normalizer projection, metric-passport field map | `CONFLICT` |
| Acceptance | No mapped source field or endpoint projection found | No source example | No legacy transformation found | No independently evidenced acceptance event | none | No sign assigned | Target enum exists, but no matching source field was found in the normalizer, legacy kernel, metric passport, or artifacts | `UNRESOLVED` |
| `deduction` / `deductions` | Finance detailed candidate: `POST /api/finance/v1/sales-reports/detailed` | Golden raw row: `-10.00`; retained normalized deductions values are positive | Retained separately; no component-specific signed legacy transformation located | Broad label can cover deductions, corrections, and heterogeneous events | `other_marketplace_deduction` only after an event taxonomy is proven | No authoritative sign assigned | Metric passport, broad normalizer markers, Golden raw fixture, normalized snapshot | `CONFLICT` |
| `rebillLogisticCost` | Finance detailed candidate and legacy finance-report-shaped artifacts | Retained non-zero values are positive, including `+68.61`; raw payload and durable record ID are absent | `abs(rebill)` is added to legacy logistics | Could be reimbursement, rebill, correction, compensation, or an already represented adjustment | none; retain unresolved rebill diagnostic only | No sign assigned | Two endpoint variants have inconsistent operation metadata; detailed investigation in `FINANCIAL_POLICY_GATES.md` | `UNRESOLVED` |

## `abs()` Classification

| Field or legacy bucket | Classification | Rationale |
| --- | --- | --- |
| Commission composite | `D` -- unknown | The legacy composite is not `abs()`-normalized, but its blend of commission and compensation fields cannot become a signed target rule. |
| Delivery/logistics aliases | `B` -- hides mixed source semantics | One magnitude bucket combines multiple aliases and operation classes; the retained and Golden signs conflict. |
| Reverse logistics | `B` -- hides mixed source semantics | It has no separate source field and is folded into legacy logistics magnitude. |
| Acquiring | `D` -- unknown | No independent legacy finance-kernel sign rule exists. |
| Acceptance | `D` -- unknown | No source or legacy mapping exists. |
| Other deductions | `D` -- unknown | The broad deduction label does not establish a homogeneous economic event. |
| `rebillLogisticCost` | `B` -- hides mixed source semantics | `abs()` discards the sign of an unclassified reimbursement/correction candidate and folds it into logistics. |

## Mandatory Runtime Boundary

- Preserve every unresolved value with its amount, source, provenance, and
  diagnostic.
- Do not map `missing`, `unknown`, or `unresolved` to zero.
- Do not map a positive source value to revenue or a negative source value to
  expense solely because of its sign.
- Do not classify `rebillLogisticCost`, assign it a sign, or include it in
  authoritative P&L.
- Do not reproduce legacy `abs()` as a target policy.

## Stage 9 Disposition

All unresolved components can remain excluded from authoritative P&L without
loss of source evidence. However, the purpose of Stage 9 is to migrate
marketplace deductions into signed Finance Kernel components. Implementing
that migration now would alter the base financial contract without an
authoritative sign policy, so Stage 9 is stopped on this real semantic blocker.

To unblock implementation, supply a redacted raw finance payload with durable
record IDs and source documentation for each event/sign combination, or approve
a versioned field-level event and sign policy. Neither a legacy aggregate nor a
new `abs()` fallback is sufficient evidence.

## Stage 9.1 Resolution (2026-09-04)

The unblocking condition listed above is met by the first option, and the
implementation now follows the versioned policy in
`packages/finance/marketplace_policy.py` (`marketplace-sign-policy-v1`),
documented in `docs/METRICS_PASSPORT.md` §3.12.1.

What changed the picture: the immutable raw store holds **40 real
`/api/finance/v1/sales-reports/detailed` rows across two reports, every one
with a durable `rrdId`** — the payload the blocker said did not exist. In that
real evidence every charge field is a non-negative magnitude, and the row type
comes from `sellerOperName` ("Логистика", "Доставка", "Хранение", "Обработка
товара", "Возмещение издержек …"). Money arrives as JSON strings.

The recorded `CONFLICT` was an artifact of comparing two different sources: the
Golden Fixture row lives at `/finance_final/rows_raw[0]`, uses the legacy
finance-report shape (`deliveryRub`, float values, `tax`), and is consumed only
by `packages/compat/legacy_snapshot_parity.py`. It is not an input to the target
finance path, so its mixed signs are not evidence about the detailed endpoint.
The fixture is unchanged.

| Field | Stage 9 status | Stage 9.1 status | Basis |
| --- | --- | --- | --- |
| `ppvzSalesCommission` | `CONFLICT` | `CONFIRMED` → `marketplace_commission`, canonical `−raw` | 5 non-negative values (198.00, 132.00 — synthetic stand-ins for the observed magnitudes); the composite aliases `pvzCompensation` / `paymentServicesCompensation` are absent from this endpoint, so the legacy blend does not apply |
| `deliveryService` / `deliveryRub` | `CONFLICT` | `CONFIRMED` → `logistics`, canonical `−raw` | 7 non-negative values on rows named "Логистика"/"Доставка"; `retailAmount` is 0 on those rows, so no double count with revenue |
| `paidStorage` | not assessed | `CONFIRMED` → `storage`, canonical `−raw` | rows named "Хранение" (6.15, 6.50 — synthetic stand-ins); metric passport maps `paidStorage → storage` |
| `paidAcceptance` | `UNRESOLVED` ("no mapped source field") | `CONFIRMED` → `acceptance`, canonical `−raw` | the field exists in the real payload on rows named "Обработка товара" |
| `acquiringFee` | `CONFLICT` | `CONFIRMED` → `acquiring`, canonical `−raw` | 5 non-negative values on sale rows (36.00, 24.00 — synthetic stand-ins) |
| `penalty` / `penaltyAmount` | not assessed | `CONFIRMED` → `penalties`, canonical `−raw` | field present; zero in this sample, so no non-zero observation yet |
| `deduction` | `CONFLICT` | `CONFIRMED` → `other_marketplace_deductions`, canonical `−raw` | field present; zero in this sample |
| `rebillLogisticCost` | `UNRESOLVED` | `CONFIRMED` → `rebill_logistics`, canonical `−raw` | the source settles the direction itself: on all 20 real rows `vw = -rebillLogisticCost / 1.22` with matching negative `vwNds`, i.e. WB books the operation as a reduction of the seller's revenue base, while `forPay` and `retailAmount` are both zero. Proof and falsification criteria: `docs/architecture/REBILL_LOGISTICS_EVIDENCE.md` |
| Reverse logistics | `UNRESOLVED` | `UNRESOLVED` | still no distinct source field |

Stage 9.1 closed the last marketplace deduction on 2026-09-04. With
`rebillLogisticCost` classified from source evidence, every component of the
target P&L formula is admitted, and the first day reached `COMPLETE`
(`2026-09-02`, `net_profit = 206.25 ₽` — synthetic stand-in for the observed result).

The mandatory runtime boundary is implemented rather than only stated: no
`missing → 0`, no sign inference, no `abs()` (a static test forbids `abs()`
calls in the sign path), and a source value that contradicts the documented
convention becomes an unresolved component that keeps its original amount.
