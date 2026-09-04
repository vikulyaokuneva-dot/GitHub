"""Adapt sourced tax amounts and seller rate settings to the Finance input boundary."""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

from packages.finance.contracts import FinancialComponent, FinancialComponentInput, FinancialInputState

from .contracts import SourcedTaxInput, TaxRateBasis, TaxRateSetting

_CENT: Final = Decimal("0.01")
_HUNDRED: Final = Decimal("100")


def to_financial_component(input_value: SourcedTaxInput) -> FinancialComponentInput:
    """Create a tax component without calculating or defaulting any tax amount."""

    return FinancialComponentInput(
        component=FinancialComponent.TAX,
        state=input_value.state,
        amount=input_value.amount,
        source=input_value.source,
        source_record_id=input_value.source_record_id,
        source_endpoint=input_value.source_endpoint,
        operational_date=input_value.operational_date,
        financial_date=input_value.financial_date,
    )


def tax_input_from_rate(
    setting: TaxRateSetting,
    *,
    operational_date: date,
    realized_revenue: Decimal | None,
) -> SourcedTaxInput:
    """Declare one sourced tax amount from a seller rate, or an explicit missing tax.

    The rate is applied only to the base the setting itself declares.  When that
    base is unavailable the result is ``MISSING`` with a diagnostic: an absent
    base is never read as zero revenue, and the Finance Kernel keeps refusing to
    invent a tax.  The P&L summation itself stays inside the kernel.
    """

    if setting.basis != TaxRateBasis.REALIZED_REVENUE:
        raise ValueError("only the realized_revenue tax basis is supported")
    if isinstance(realized_revenue, float):
        raise ValueError("tax base must not be float")

    source_record_id = f"tax-rate:{setting.scope.account_id}:{operational_date.isoformat()}"
    if realized_revenue is None:
        return SourcedTaxInput(
            scope=setting.scope,
            operational_date=operational_date,
            state=FinancialInputState.MISSING,
            source=setting.source,
            source_record_id=source_record_id,
            source_endpoint="financial_settings",
            diagnostic="tax rate is set but the declared tax base is unavailable for the period",
        )
    amount = -(realized_revenue * setting.rate_percent / _HUNDRED).quantize(_CENT, rounding=ROUND_HALF_UP)
    return SourcedTaxInput(
        scope=setting.scope,
        operational_date=operational_date,
        state=FinancialInputState.PROVIDED,
        amount=amount,
        source=setting.source,
        source_record_id=source_record_id,
        source_endpoint="financial_settings",
    )
