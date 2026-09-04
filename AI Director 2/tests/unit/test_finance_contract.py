from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from packages.data.canonical import CanonicalCurrency
from packages.finance.contracts import (
    AdvertisingAttribution,
    AdvertisingExpenseInput,
    CogsAllocationInput,
    FinancialComponent,
    FinancialComponentInput,
    FinancialComponentStatus,
    FinancialComponentTrace,
    FinancialInput,
    FinancialInputState,
    FinancialFinality,
    FinancialFinalityInput,
    FinancialResult,
    FinancialStatus,
    MoneyRoundingPolicy,
    RevenueBasis,
    RevenueBasisInput,
    RebillLogisticsClassification,
    RebillLogisticsInput,
    UnitEconomicsResult,
)
from packages.wb_core.synthetic_scenario import synthetic_scope

OPERATIONAL_DATE = date(2026, 8, 20)
FINANCIAL_DATE = date(2026, 8, 24)


def _component(
    component: FinancialComponent,
    *,
    amount: Decimal | None = None,
    state: FinancialInputState = FinancialInputState.PROVIDED,
    source_record_id: str = "finance-row-001",
    financial_date: date | None = FINANCIAL_DATE,
) -> FinancialComponentInput:
    resolved_amount = amount
    if resolved_amount is None and state == FinancialInputState.PROVIDED:
        resolved_amount = Decimal("10.00") if component == FinancialComponent.REALIZED_REVENUE else Decimal("-10.00")
    return FinancialComponentInput(
        component=component,
        state=state,
        amount=resolved_amount,
        source="finance_detailed_api",
        source_record_id=source_record_id,
        source_endpoint="finance_detailed",
        operational_date=OPERATIONAL_DATE,
        financial_date=financial_date,
    )


def _input(
    *components: FinancialComponentInput,
    rebill_logistics: tuple[RebillLogisticsInput, ...] = (),
) -> FinancialInput:
    return FinancialInput(
        scope=synthetic_scope(),
        operational_date=OPERATIONAL_DATE,
        currency=CanonicalCurrency.RUB,
        reconciled_facts=(),
        components=components,
        rebill_logistics=rebill_logistics,
    )


def _trace(component: FinancialComponent, item: FinancialComponentInput) -> FinancialComponentTrace:
    return FinancialComponentTrace(
        component=component,
        status=FinancialComponentStatus.AVAILABLE,
        source_components=(item,),
        amount=item.amount,
    )


def test_financial_input_is_decimal_only_and_preserves_decimal_scale() -> None:
    commission = _component(FinancialComponent.MARKETPLACE_COMMISSION, amount=Decimal("-100.2500"))

    financial_input = _input(commission)

    assert financial_input.components[0].amount == Decimal("-100.2500")
    assert financial_input.components[0].amount.as_tuple().exponent == -4
    with pytest.raises(ValidationError, match="must not be float"):
        _component(FinancialComponent.LOGISTICS, amount=10.25)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "component",
    [
        FinancialComponent.MARKETPLACE_COMMISSION,
        FinancialComponent.LOGISTICS,
        FinancialComponent.REVERSE_LOGISTICS,
        FinancialComponent.ACQUIRING,
        FinancialComponent.STORAGE,
        FinancialComponent.PENALTIES,
        FinancialComponent.OTHER_MARKETPLACE_DEDUCTIONS,
        FinancialComponent.ADVERTISING,
        FinancialComponent.TAX,
        FinancialComponent.COGS,
        FinancialComponent.PACKAGING,
    ],
)
def test_expense_components_use_negative_signed_decimal_inputs(component: FinancialComponent) -> None:
    component_input = _component(component, amount=Decimal("-10.00"))

    assert component_input.amount == Decimal("-10.00")


def test_realized_revenue_uses_positive_signed_decimal_input() -> None:
    revenue = _component(FinancialComponent.REALIZED_REVENUE, amount=Decimal("100.00"))

    assert revenue.amount == Decimal("100.00")


def test_sign_contract_rejects_legacy_unsigned_expense_conventions() -> None:
    with pytest.raises(ValidationError, match="negative or zero"):
        _component(FinancialComponent.MARKETPLACE_COMMISSION, amount=Decimal("10.00"))
    with pytest.raises(ValidationError, match="positive or zero"):
        _component(FinancialComponent.REALIZED_REVENUE, amount=Decimal("-10.00"))


def test_missing_zero_and_not_applicable_remain_distinct() -> None:
    zero_commission = _component(FinancialComponent.MARKETPLACE_COMMISSION, amount=Decimal("0"))
    missing_logistics = _component(
        FinancialComponent.LOGISTICS,
        amount=None,
        state=FinancialInputState.MISSING,
        source_record_id="finance-row-002",
    )
    not_applicable_acquiring = _component(
        FinancialComponent.ACQUIRING,
        amount=None,
        state=FinancialInputState.NOT_APPLICABLE,
        source_record_id="finance-row-003",
    )

    financial_input = _input(zero_commission, missing_logistics, not_applicable_acquiring)

    assert financial_input.components[0].amount == Decimal("0")
    assert financial_input.components[1].state == FinancialInputState.MISSING
    assert financial_input.components[2].state == FinancialInputState.NOT_APPLICABLE


def test_component_state_rejects_implicit_missing_zero_conversion() -> None:
    with pytest.raises(ValidationError, match="requires a Decimal"):
        FinancialComponentInput(
            component=FinancialComponent.TAX,
            state=FinancialInputState.PROVIDED,
            amount=None,
            source="finance_detailed_api",
            source_record_id="finance-row-missing",
            source_endpoint="finance_detailed",
            operational_date=OPERATIONAL_DATE,
            financial_date=FINANCIAL_DATE,
        )
    with pytest.raises(ValidationError, match="must not carry an amount"):
        _component(
            FinancialComponent.TAX,
            amount=Decimal("0"),
            state=FinancialInputState.MISSING,
        )


def test_cogs_packaging_and_marketplace_deductions_are_separate_components() -> None:
    financial_input = _input(
        _component(FinancialComponent.COGS, amount=Decimal("-25.00"), source_record_id="cogs-001"),
        _component(FinancialComponent.PACKAGING, amount=Decimal("-3.00"), source_record_id="pack-001"),
        _component(
            FinancialComponent.MARKETPLACE_COMMISSION,
            amount=Decimal("-11.00"),
            source_record_id="finance-001",
        ),
    )

    assert [component.component for component in financial_input.components] == [
        FinancialComponent.COGS,
        FinancialComponent.PACKAGING,
        FinancialComponent.MARKETPLACE_COMMISSION,
    ]


def test_cogs_allocation_keeps_unit_costs_separate_and_missing_is_not_zero() -> None:
    available = CogsAllocationInput(
        nm_id="1001",
        quantity=2,
        state=FinancialInputState.PROVIDED,
        unit_cogs=Decimal("20.5000"),
        packaging_per_unit=Decimal("3.00"),
        source="approved_cogs_catalog",
        source_record_id="cogs-catalog-1001",
        effective_date=OPERATIONAL_DATE,
    )
    missing = CogsAllocationInput(
        nm_id="1002",
        quantity=1,
        state=FinancialInputState.MISSING,
        source="approved_cogs_catalog",
        source_record_id="cogs-catalog-1002",
        effective_date=OPERATIONAL_DATE,
    )

    assert available.unit_cogs == Decimal("20.5000")
    assert available.packaging_per_unit == Decimal("3.00")
    assert missing.unit_cogs is None
    assert missing.packaging_per_unit is None


def test_double_count_protection_is_resolved_by_the_kernel() -> None:
    first = _component(FinancialComponent.LOGISTICS, source_record_id="finance-row-duplicate")
    second = _component(FinancialComponent.LOGISTICS, source_record_id="finance-row-duplicate")

    financial_input = _input(first, second)

    assert len(financial_input.components) == 2


def test_trace_preserves_component_provenance_without_a_calculation() -> None:
    revenue = _component(FinancialComponent.REALIZED_REVENUE, amount=Decimal("100.00"))
    trace = _trace(FinancialComponent.REALIZED_REVENUE, revenue)

    assert trace.amount == Decimal("100.00")
    assert trace.source_components[0].source == "finance_detailed_api"
    assert trace.source_components[0].financial_date == FINANCIAL_DATE


def test_financial_result_is_immutable_and_uses_the_central_rounding_policy() -> None:
    revenue = _component(FinancialComponent.REALIZED_REVENUE, amount=Decimal("100.00"))
    result = FinancialResult(
        scope=synthetic_scope(),
        operational_date=OPERATIONAL_DATE,
        financial_dates=(FINANCIAL_DATE,),
        currency=CanonicalCurrency.RUB,
        status=FinancialStatus.COMPLETE,
        rounding_policy=MoneyRoundingPolicy.AGGREGATE_THEN_HALF_UP_TO_CENT,
        component_traces=(_trace(FinancialComponent.REALIZED_REVENUE, revenue),),
        net_profit=Decimal("80.00"),
        profit_margin=Decimal("0.80"),
    )

    with pytest.raises(ValidationError):
        result.net_profit = Decimal("1.00")
    assert result.rounding_policy == MoneyRoundingPolicy.AGGREGATE_THEN_HALF_UP_TO_CENT
    assert result.net_profit == Decimal("80.00")


def test_contract_models_are_deterministic_value_objects() -> None:
    revenue = _component(FinancialComponent.REALIZED_REVENUE, amount=Decimal("100.00"))
    first = FinancialResult(
        scope=synthetic_scope(),
        operational_date=OPERATIONAL_DATE,
        financial_dates=(FINANCIAL_DATE,),
        currency=CanonicalCurrency.RUB,
        status=FinancialStatus.COMPLETE,
        rounding_policy=MoneyRoundingPolicy.AGGREGATE_THEN_HALF_UP_TO_CENT,
        component_traces=(_trace(FinancialComponent.REALIZED_REVENUE, revenue),),
        net_profit=Decimal("80.00"),
        profit_margin=Decimal("0.80"),
    )
    second = FinancialResult.model_validate(first.model_dump())

    assert first == second
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_partial_result_cannot_claim_net_profit() -> None:
    with pytest.raises(ValidationError, match="must not claim net_profit"):
        FinancialResult(
            scope=synthetic_scope(),
            operational_date=OPERATIONAL_DATE,
            financial_dates=(FINANCIAL_DATE,),
            currency=CanonicalCurrency.RUB,
            status=FinancialStatus.PARTIAL,
            rounding_policy=MoneyRoundingPolicy.AGGREGATE_THEN_HALF_UP_TO_CENT,
            component_traces=(),
            net_profit=Decimal("1.00"),
        )


def test_unresolved_tax_remains_missing_and_keeps_financial_result_partial() -> None:
    missing_tax = _component(
        FinancialComponent.TAX,
        amount=None,
        state=FinancialInputState.MISSING,
        source_record_id="tax-source-unavailable",
    )
    tax_trace = FinancialComponentTrace(
        component=FinancialComponent.TAX,
        status=FinancialComponentStatus.MISSING,
        source_components=(missing_tax,),
    )
    result = FinancialResult(
        scope=synthetic_scope(),
        operational_date=OPERATIONAL_DATE,
        financial_dates=(FINANCIAL_DATE,),
        currency=CanonicalCurrency.RUB,
        status=FinancialStatus.PARTIAL,
        rounding_policy=MoneyRoundingPolicy.AGGREGATE_THEN_HALF_UP_TO_CENT,
        component_traces=(tax_trace,),
    )

    assert missing_tax.amount is None
    assert tax_trace.amount is None
    assert result.status == FinancialStatus.PARTIAL
    assert result.net_profit is None


def test_financial_lag_is_not_reclassified_as_zero_or_complete() -> None:
    result = FinancialResult(
        scope=synthetic_scope(),
        operational_date=OPERATIONAL_DATE,
        financial_dates=(),
        currency=CanonicalCurrency.RUB,
        status=FinancialStatus.AWAITING_FINANCIAL_CONFIRMATION,
        rounding_policy=MoneyRoundingPolicy.AGGREGATE_THEN_HALF_UP_TO_CENT,
        component_traces=(),
    )

    assert result.status == FinancialStatus.AWAITING_FINANCIAL_CONFIRMATION
    assert result.financial_dates == ()
    assert result.net_profit is None


def test_unit_economics_is_separate_from_period_p_and_l() -> None:
    unit = UnitEconomicsResult(
        nm_id="1001",
        quantity=2,
        currency=CanonicalCurrency.RUB,
        revenue_per_unit=Decimal("50.00"),
        cogs_per_unit=Decimal("20.00"),
    )

    assert unit.revenue_per_unit == Decimal("50.00")
    assert unit.cogs_per_unit == Decimal("20.00")
    assert unit.profit_per_unit is None


def test_revenue_basis_retains_distinct_buyer_gross_and_payout_views() -> None:
    buyer_price = RevenueBasisInput(
        basis=RevenueBasis.BUYER_DISCOUNTED,
        amount=Decimal("900.00"),
        quantity=2,
        source="orders_api",
        source_record_id="order-001",
        source_field="priceWithDisc",
        operational_date=OPERATIONAL_DATE,
    )
    seller_payout = RevenueBasisInput(
        basis=RevenueBasis.SELLER_PAYOUT,
        amount=Decimal("700.00"),
        quantity=2,
        source="finance_detailed_api",
        source_record_id="finance-001",
        source_field="ppvzForPay",
        operational_date=OPERATIONAL_DATE,
        financial_date=FINANCIAL_DATE,
    )
    gross = RevenueBasisInput(
        basis=RevenueBasis.REALIZED_GROSS,
        amount=Decimal("1000.00"),
        quantity=2,
        source="finance_detailed_api",
        source_record_id="finance-001",
        source_field="retailAmount",
        operational_date=OPERATIONAL_DATE,
        financial_date=FINANCIAL_DATE,
    )

    assert buyer_price.amount == Decimal("900.00")
    assert gross.amount == Decimal("1000.00")
    assert seller_payout.amount == Decimal("700.00")
    assert len({buyer_price.basis, gross.basis, seller_payout.basis}) == 3


def test_rebill_requires_exactly_one_classified_logistics_component_per_source_record() -> None:
    rebill_as_logistics = RebillLogisticsInput(
        amount=Decimal("-35.00"),
        classification=RebillLogisticsClassification.LOGISTICS,
        source="finance_detailed_api",
        source_record_id="rebill-001",
        operational_date=OPERATIONAL_DATE,
        financial_date=FINANCIAL_DATE,
    )
    rebill_as_reverse_logistics = RebillLogisticsInput(
        amount=Decimal("-35.00"),
        classification=RebillLogisticsClassification.REVERSE_LOGISTICS,
        source="finance_detailed_api",
        source_record_id="rebill-001",
        operational_date=OPERATIONAL_DATE,
        financial_date=FINANCIAL_DATE,
    )

    assert rebill_as_logistics.classification != rebill_as_reverse_logistics.classification
    with pytest.raises(ValidationError, match="exactly one expense classification"):
        _input(rebill_logistics=(rebill_as_logistics, rebill_as_reverse_logistics))


def test_tax_is_a_sourced_negative_component_until_an_approved_policy_exists() -> None:
    sourced_tax = _component(FinancialComponent.TAX, amount=Decimal("-60.00"))

    assert sourced_tax.amount == Decimal("-60.00")
    assert sourced_tax.source == "finance_detailed_api"


@pytest.mark.parametrize(
    ("scenario", "quantity"),
    [
        ("normal_sale", 1),
        ("full_return", 1),
        ("cancellation", 1),
        ("partial_return", 2),
        ("non_buyout", 1),
    ],
)
def test_cogs_scenarios_remain_unavailable_without_an_approved_event_policy(scenario: str, quantity: int) -> None:
    allocation = CogsAllocationInput(
        nm_id="1001",
        quantity=quantity,
        state=FinancialInputState.MISSING,
        source="approved_cogs_catalog",
        source_record_id=f"cogs-{scenario}",
        effective_date=OPERATIONAL_DATE,
    )

    assert allocation.unit_cogs is None
    assert allocation.packaging_per_unit is None


def test_financial_finality_requires_explicit_evidence_and_date_for_final() -> None:
    unknown = FinancialFinalityInput(
        source="finance_detailed_api",
        source_record_id="finance-001",
        operational_date=OPERATIONAL_DATE,
        financial_date=FINANCIAL_DATE,
        finality=FinancialFinality.UNKNOWN,
        evidence_code="source_has_no_explicit_finality_signal",
    )

    assert unknown.finality == FinancialFinality.UNKNOWN
    with pytest.raises(ValidationError, match="requires financial_date"):
        FinancialFinalityInput(
            source="finance_detailed_api",
            source_record_id="finance-002",
            operational_date=OPERATIONAL_DATE,
            finality=FinancialFinality.FINAL,
            evidence_code="missing_date",
        )


def test_advertising_attribution_requires_evidence_for_sku_level_cost() -> None:
    direct = AdvertisingExpenseInput(
        amount=Decimal("-12.00"),
        attribution=AdvertisingAttribution.DIRECT,
        period_start=OPERATIONAL_DATE,
        period_end=OPERATIONAL_DATE,
        source="ads_report",
        source_record_id="campaign-row-001",
        campaign_id="42",
        nm_id="1001",
    )
    period_level = AdvertisingExpenseInput(
        amount=Decimal("-100.00"),
        attribution=AdvertisingAttribution.PERIOD_LEVEL,
        period_start=OPERATIONAL_DATE,
        period_end=OPERATIONAL_DATE,
        source="ads_report",
        source_record_id="campaign-total-001",
        campaign_id="42",
    )

    assert direct.nm_id == "1001"
    assert period_level.nm_id is None
    with pytest.raises(ValidationError, match="must not claim nm_id attribution"):
        AdvertisingExpenseInput(
            amount=Decimal("-12.00"),
            attribution=AdvertisingAttribution.PERIOD_LEVEL,
            period_start=OPERATIONAL_DATE,
            period_end=OPERATIONAL_DATE,
            source="ads_report",
            source_record_id="campaign-row-associated",
            campaign_id="42",
            nm_id="1001",
        )
    with pytest.raises(ValidationError, match="requires nm_id"):
        AdvertisingExpenseInput(
            amount=Decimal("-12.00"),
            attribution=AdvertisingAttribution.DIRECT,
            period_start=OPERATIONAL_DATE,
            period_end=OPERATIONAL_DATE,
            source="ads_report",
            source_record_id="campaign-row-002",
        )
