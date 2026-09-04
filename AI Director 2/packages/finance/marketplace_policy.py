"""Explicit, versioned sign policy for WB marketplace charges.

The normalization layer stores every source money field with the sign WB sent.
This module is the single place that decides what that value means for the
Finance Kernel, so no other layer ever has to guess.

Design rules, all of them testable:

* the canonical ledger stores expenses as negative or zero amounts;
* the WB detailed finance report reports each charge as a non-negative
  magnitude on a row whose operation name says what was charged;
* a documented-positive magnitude therefore becomes a negative component by
  one uniform, declared rule;
* a value that contradicts the documented convention is never repaired: it
  becomes an unresolved component that keeps its original amount and states
  why, so the period stays partial instead of silently acquiring a flipped
  sign;
* ``abs()`` has no role here. Using it would erase exactly the contradiction
  this policy exists to surface.

Evidence base (recorded in ``docs/METRICS_PASSPORT.md`` and
``docs/architecture/REBILL_LOGISTICS_EVIDENCE.md``):

* 40 real ``/api/finance/v1/sales-reports/detailed`` rows with durable ``rrdId``
  across two reports: every charge field is non-negative, and charges appear on
  rows typed by ``sellerOperName`` ("Логистика", "Хранение", "Обработка товара",
  "Возмещение издержек ...") rather than as signed values on a sale row.
* ``rebillLogisticCost`` direction is settled by the source's own VAT columns:
  on all 20 real rebill rows ``vw = -rebillLogisticCost / 1.22`` and ``vwNds``
  is the matching negative VAT, exact to the cent, with no counterexample in the
  dataset. WB books the operation as a reduction of the seller's revenue base,
  which is the accounting signature of a charge against the seller.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from packages.data.canonical import CanonicalFinanceDetailRecord, CanonicalSourceMoney
from packages.finance.contracts import (
    FinancialComponent,
    FinancialComponentInput,
    FinancialInputState,
)

POLICY_VERSION = "marketplace-sign-policy-v1"


class MarketplaceEvidence(StrEnum):
    """How strongly a source field is evidenced for the authoritative P&L."""

    CONFIRMED = "confirmed"
    UNRESOLVED = "unresolved"


class MarketplaceSignPolicy(BaseModel):
    """Declared meaning of one WB charge field and its canonical treatment."""

    model_config = ConfigDict(frozen=True)

    source_field: str = Field(min_length=1, max_length=100)
    component: FinancialComponent
    participates_in_pnl: bool
    evidence: MarketplaceEvidence
    expected_raw_sign: str = Field(min_length=1, max_length=60)
    canonical_sign: str = Field(min_length=1, max_length=60)
    reason: str = Field(min_length=1, max_length=400)


NEGATIVE_CANONICAL = "negative or zero"
NON_NEGATIVE_RAW = "non-negative magnitude"

MARKETPLACE_SIGN_POLICIES: Mapping[str, MarketplaceSignPolicy] = {
    policy.source_field: policy
    for policy in (
        MarketplaceSignPolicy(
            source_field="ppvzSalesCommission",
            component=FinancialComponent.MARKETPLACE_COMMISSION,
            participates_in_pnl=True,
            evidence=MarketplaceEvidence.CONFIRMED,
            expected_raw_sign=NON_NEGATIVE_RAW,
            canonical_sign=NEGATIVE_CANONICAL,
            reason="WB commission charge for a realized sale",
        ),
        MarketplaceSignPolicy(
            source_field="deliveryService",
            component=FinancialComponent.LOGISTICS,
            participates_in_pnl=True,
            evidence=MarketplaceEvidence.CONFIRMED,
            expected_raw_sign=NON_NEGATIVE_RAW,
            canonical_sign=NEGATIVE_CANONICAL,
            reason="WB delivery and logistics charge",
        ),
        MarketplaceSignPolicy(
            source_field="deliveryRub",
            component=FinancialComponent.LOGISTICS,
            participates_in_pnl=True,
            evidence=MarketplaceEvidence.CONFIRMED,
            expected_raw_sign=NON_NEGATIVE_RAW,
            canonical_sign=NEGATIVE_CANONICAL,
            reason="legacy-shaped WB delivery charge field kept as an admitted alias",
        ),
        MarketplaceSignPolicy(
            source_field="paidStorage",
            component=FinancialComponent.STORAGE,
            participates_in_pnl=True,
            evidence=MarketplaceEvidence.CONFIRMED,
            expected_raw_sign=NON_NEGATIVE_RAW,
            canonical_sign=NEGATIVE_CANONICAL,
            reason="WB paid storage charge",
        ),
        MarketplaceSignPolicy(
            source_field="storageFee",
            component=FinancialComponent.STORAGE,
            participates_in_pnl=True,
            evidence=MarketplaceEvidence.CONFIRMED,
            expected_raw_sign=NON_NEGATIVE_RAW,
            canonical_sign=NEGATIVE_CANONICAL,
            reason="legacy-shaped WB storage charge field kept as an admitted alias",
        ),
        MarketplaceSignPolicy(
            source_field="paidAcceptance",
            component=FinancialComponent.ACCEPTANCE,
            participates_in_pnl=True,
            evidence=MarketplaceEvidence.CONFIRMED,
            expected_raw_sign=NON_NEGATIVE_RAW,
            canonical_sign=NEGATIVE_CANONICAL,
            reason="WB paid acceptance charge reported on 'Обработка товара' rows",
        ),
        MarketplaceSignPolicy(
            source_field="acquiringFee",
            component=FinancialComponent.ACQUIRING,
            participates_in_pnl=True,
            evidence=MarketplaceEvidence.CONFIRMED,
            expected_raw_sign=NON_NEGATIVE_RAW,
            canonical_sign=NEGATIVE_CANONICAL,
            reason="WB acquiring fee for a realized sale",
        ),
        MarketplaceSignPolicy(
            source_field="penalty",
            component=FinancialComponent.PENALTIES,
            participates_in_pnl=True,
            evidence=MarketplaceEvidence.CONFIRMED,
            expected_raw_sign=NON_NEGATIVE_RAW,
            canonical_sign=NEGATIVE_CANONICAL,
            reason="WB penalty charge",
        ),
        MarketplaceSignPolicy(
            source_field="penaltyAmount",
            component=FinancialComponent.PENALTIES,
            participates_in_pnl=True,
            evidence=MarketplaceEvidence.CONFIRMED,
            expected_raw_sign=NON_NEGATIVE_RAW,
            canonical_sign=NEGATIVE_CANONICAL,
            reason="legacy-shaped WB penalty field kept as an admitted alias",
        ),
        MarketplaceSignPolicy(
            source_field="deduction",
            component=FinancialComponent.OTHER_MARKETPLACE_DEDUCTIONS,
            participates_in_pnl=True,
            evidence=MarketplaceEvidence.CONFIRMED,
            expected_raw_sign=NON_NEGATIVE_RAW,
            canonical_sign=NEGATIVE_CANONICAL,
            reason="WB other marketplace deduction charge",
        ),
        MarketplaceSignPolicy(
            source_field="rebillLogisticCost",
            component=FinancialComponent.REBILL_LOGISTICS,
            participates_in_pnl=True,
            evidence=MarketplaceEvidence.CONFIRMED,
            expected_raw_sign=NON_NEGATIVE_RAW,
            canonical_sign=NEGATIVE_CANONICAL,
            reason=(
                "WB re-bills actual transport, relocation and handling costs to the seller; the source "
                "books the operation as a negative revenue item, since vw = -rebillLogisticCost/1.22 and "
                "vwNds carries the matching negative VAT on all 20 real rows"
            ),
        ),
    )
}

UNRESOLVED_REVERSAL_REASON = (
    "source sent a negative value, and a credit or reversal treatment has no approved policy"
)


def marketplace_component_input(
    charge: CanonicalSourceMoney,
    record: CanonicalFinanceDetailRecord,
) -> FinancialComponentInput | None:
    """Turn one source charge into one kernel component, or return ``None`` when unmapped.

    The returned amount is either a documented sign inversion of a
    non-negative magnitude, or the untouched source amount carried by an
    unresolved component. Nothing here ever estimates, defaults or repairs a
    value.
    """

    policy = MARKETPLACE_SIGN_POLICIES.get(charge.source_field)
    if policy is None:
        return None
    amount = charge.value
    if amount is None:  # pragma: no cover - the normalizer never stores a valueless charge
        return None

    common = {
        "component": policy.component,
        "source": record.source_metadata.source,
        "source_record_id": record.source_record_id,
        "source_endpoint": record.source_metadata.endpoint_name,
        "operational_date": record.operational_date,
        "financial_date": record.financial_date,
    }
    if policy.evidence is MarketplaceEvidence.UNRESOLVED:
        if amount == 0:
            # A zero charge has no direction to get wrong and cannot move the
            # total, so it does not hold the period partial. Only a material
            # amount of an unproven component is retained as unresolved.
            return None
        return FinancialComponentInput(state=FinancialInputState.UNRESOLVED, amount=amount, **common)
    if amount > 0:
        return FinancialComponentInput(state=FinancialInputState.PROVIDED, amount=-amount, **common)
    if amount == 0:
        return FinancialComponentInput(state=FinancialInputState.PROVIDED, amount=Decimal("0"), **common)
    return FinancialComponentInput(
        state=FinancialInputState.UNRESOLVED,
        amount=amount,
        **common,
    )


def unresolved_reason(component: FinancialComponent, amount: Decimal) -> str:
    """Human-readable reason for a component that could not be admitted."""

    if amount < 0:
        return f"{component.value}: {UNRESOLVED_REVERSAL_REASON}"
    policy = next((item for item in MARKETPLACE_SIGN_POLICIES.values() if item.component is component), None)
    return f"{component.value}: {policy.reason if policy else 'no approved sign policy'}"
