from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from packages.finance.contracts import FinancialComponent, FinancialInputState
from packages.products.contracts import DirectPeriodCogsInput, ProductCostProfile
from packages.products.service import to_financial_component
from packages.wb_core.synthetic_scenario import synthetic_scope


def test_unit_cogs_is_an_explicit_effective_dated_product_input() -> None:
    profile = ProductCostProfile(
        scope=synthetic_scope(),
        nm_id="1001",
        state=FinancialInputState.PROVIDED,
        unit_cogs=Decimal("320.50"),
        packaging_per_unit=Decimal("12.00"),
        effective_from=date(2026, 8, 1),
        source="seller_cogs_workbook",
        source_record_id="cogs-row-1",
    )

    assert profile.unit_cogs == Decimal("320.50")
    assert profile.effective_from == date(2026, 8, 1)
    assert not hasattr(profile, "buyout_count")
    assert not hasattr(profile, "sale_id")


def test_missing_unit_cogs_does_not_become_zero() -> None:
    profile = ProductCostProfile(
        scope=synthetic_scope(),
        nm_id="1001",
        state=FinancialInputState.MISSING,
        source="seller_cogs_workbook",
        source_record_id="cogs-row-2",
    )

    assert profile.unit_cogs is None
    assert profile.packaging_per_unit is None


def test_direct_period_cogs_is_the_only_automatic_finance_adapter() -> None:
    source_input = DirectPeriodCogsInput(
        scope=synthetic_scope(),
        operational_date=date(2026, 8, 20),
        state=FinancialInputState.PROVIDED,
        amount=Decimal("-1234.56"),
        source="seller_general_ledger",
        source_record_id="ledger-2026-08-20",
        source_endpoint="seller_general_ledger",
    )

    component = to_financial_component(source_input)

    assert component.component == FinancialComponent.COGS
    assert component.amount == Decimal("-1234.56")
    assert component.state == FinancialInputState.PROVIDED


@pytest.mark.parametrize("amount", [Decimal("1"), Decimal("0.1")])
def test_direct_period_cogs_rejects_positive_amounts(amount: Decimal) -> None:
    with pytest.raises(ValueError, match="negative"):
        DirectPeriodCogsInput(
            scope=synthetic_scope(),
            operational_date=date(2026, 8, 20),
            state=FinancialInputState.PROVIDED,
            amount=amount,
            source="ledger",
            source_record_id="id",
            source_endpoint="ledger",
        )
