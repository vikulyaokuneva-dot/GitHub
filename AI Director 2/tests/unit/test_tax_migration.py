from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from packages.finance.contracts import FinancialComponent, FinancialInputState
from packages.tax.contracts import SourcedTaxInput
from packages.tax.service import to_financial_component
from packages.wb_core.synthetic_scenario import synthetic_scope


def test_sourced_tax_becomes_a_signed_financial_component() -> None:
    source_input = SourcedTaxInput(
        scope=synthetic_scope(),
        operational_date=date(2026, 8, 20),
        financial_date=date(2026, 8, 21),
        state=FinancialInputState.PROVIDED,
        amount=Decimal("-60.00"),
        source="tax_statement",
        source_record_id="tax-2026-08-20",
        source_endpoint="seller_tax_statement",
    )

    component = to_financial_component(source_input)

    assert component.component == FinancialComponent.TAX
    assert component.amount == Decimal("-60.00")
    assert component.financial_date == date(2026, 8, 21)


def test_missing_tax_stays_missing_and_requires_diagnostic() -> None:
    source_input = SourcedTaxInput(
        scope=synthetic_scope(),
        operational_date=date(2026, 8, 20),
        state=FinancialInputState.MISSING,
        source="tax_statement",
        source_record_id="tax-missing",
        source_endpoint="seller_tax_statement",
        diagnostic="tax statement not supplied for the requested period",
    )

    assert to_financial_component(source_input).amount is None
    assert to_financial_component(source_input).state == FinancialInputState.MISSING


def test_tax_contract_rejects_default_rate_like_or_positive_values() -> None:
    with pytest.raises(ValueError, match="negative"):
        SourcedTaxInput(
            scope=synthetic_scope(),
            operational_date=date(2026, 8, 20),
            state=FinancialInputState.PROVIDED,
            amount=Decimal("60.00"),
            source="tax_rate_6_percent",
            source_record_id="forbidden",
            source_endpoint="configuration",
        )
