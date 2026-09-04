from __future__ import annotations

import inspect
import sys
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from packages.data.canonical import CanonicalCurrency
from packages.data.normalization import normalize_sales_funnel_products
from packages.finance.contracts import (
    AdvertisingAttribution,
    AdvertisingExpenseInput,
    CogsAllocationInput,
    FinancialComponent,
    FinancialComponentInput,
    FinancialComponentStatus,
    FinancialComponentTrace,
    FinancialFinality,
    FinancialFinalityInput,
    FinancialInput,
    FinancialInputState,
    FinancialResult,
    FinancialStatus,
    RebillLogisticsClassification,
    RebillLogisticsInput,
    UnresolvedCogsEvent,
    UnresolvedCogsEventInput,
)
from packages.finance.kernel import calculate_financial_result
from packages.reconciliation.contracts import ReconciliationLagState
from packages.reconciliation.service import reconcile_sales_funnel_products
from packages.wb_core.synthetic_scenario import synthetic_raw_object, synthetic_scope

OPERATIONAL_DATE = date(2026, 8, 20)
FINANCIAL_DATE = date(2026, 8, 24)


def _component(
    component: FinancialComponent,
    amount: Decimal | None,
    *,
    state: FinancialInputState = FinancialInputState.PROVIDED,
    source_record_id: str | None = None,
) -> FinancialComponentInput:
    return FinancialComponentInput(
        component=component,
        state=state,
        amount=amount,
        source="finance_detailed_api",
        source_record_id=source_record_id or component.value,
        source_endpoint="finance_detailed",
        operational_date=OPERATIONAL_DATE,
        financial_date=FINANCIAL_DATE,
    )


def _finality(finality: FinancialFinality = FinancialFinality.FINAL) -> FinancialFinalityInput:
    return FinancialFinalityInput(
        source="finance_detailed_api",
        source_record_id="period-finality",
        operational_date=OPERATIONAL_DATE,
        financial_date=FINANCIAL_DATE,
        finality=finality,
        evidence_code="explicit_period_closure" if finality == FinancialFinality.FINAL else "closure_unknown",
    )


def _input(
    *components: FinancialComponentInput,
    cogs_allocations: tuple[CogsAllocationInput, ...] = (),
    advertising_expenses: tuple[AdvertisingExpenseInput, ...] = (),
    finality: tuple[FinancialFinalityInput, ...] | None = None,
    unresolved_cogs_events: tuple[UnresolvedCogsEventInput, ...] = (),
    rebill_logistics: tuple[RebillLogisticsInput, ...] = (),
) -> FinancialInput:
    return FinancialInput(
        scope=synthetic_scope(),
        operational_date=OPERATIONAL_DATE,
        currency=CanonicalCurrency.RUB,
        reconciled_facts=(),
        components=components,
        cogs_allocations=cogs_allocations,
        advertising_expenses=advertising_expenses,
        finality=(_finality(),) if finality is None else finality,
        unresolved_cogs_events=unresolved_cogs_events,
        rebill_logistics=rebill_logistics,
    )


def _base_components(*, tax: FinancialComponentInput | None = None) -> tuple[FinancialComponentInput, ...]:
    return (
        _component(FinancialComponent.REALIZED_REVENUE, Decimal("1000.00")),
        _component(FinancialComponent.MARKETPLACE_COMMISSION, Decimal("-100.00")),
        _component(FinancialComponent.LOGISTICS, Decimal("-50.00")),
        _component(FinancialComponent.ACQUIRING, Decimal("-10.00")),
        _component(FinancialComponent.COGS, Decimal("-400.00")),
        tax or _component(FinancialComponent.TAX, Decimal("-40.00")),
    )


def _trace(result: FinancialResult, component: FinancialComponent) -> FinancialComponentTrace:
    return next(item for item in result.component_traces if item.component == component)


def _unresolved_event(event: UnresolvedCogsEvent) -> UnresolvedCogsEventInput:
    return UnresolvedCogsEventInput(
        event=event,
        source="sales_events",
        source_record_id=f"event-{event.value}",
        source_endpoint="sales",
        operational_date=OPERATIONAL_DATE,
    )


def test_a_complete_sale_uses_signed_components_once() -> None:
    result = calculate_financial_result(_input(*_base_components()))

    assert result.status == FinancialStatus.COMPLETE
    assert result.net_profit == Decimal("400.00")
    assert result.profit_margin == Decimal("40.00")


def test_b_missing_tax_is_partial_and_not_zero() -> None:
    missing_tax = _component(FinancialComponent.TAX, None, state=FinancialInputState.MISSING)

    result = calculate_financial_result(_input(*_base_components(tax=missing_tax)))

    assert result.status == FinancialStatus.PARTIAL
    assert result.net_profit is None
    assert _trace(result, FinancialComponent.TAX).status == FinancialComponentStatus.MISSING
    assert _trace(result, FinancialComponent.TAX).amount is None


def test_absent_tax_is_also_missing_not_implicit_zero() -> None:
    components = tuple(item for item in _base_components() if item.component != FinancialComponent.TAX)

    result = calculate_financial_result(_input(*components))

    assert result.status == FinancialStatus.PARTIAL
    assert _trace(result, FinancialComponent.TAX).status == FinancialComponentStatus.MISSING
    assert _trace(result, FinancialComponent.TAX).amount is None


def test_c_unresolved_rebill_is_excluded_with_amount_and_provenance() -> None:
    rebill = RebillLogisticsInput(
        amount=Decimal("-35.00"),
        classification=RebillLogisticsClassification.LOGISTICS,
        source="finance_detailed_api",
        source_record_id="rebill-001",
        operational_date=OPERATIONAL_DATE,
        financial_date=FINANCIAL_DATE,
    )

    result = calculate_financial_result(_input(*_base_components(), rebill_logistics=(rebill,)))
    trace = _trace(result, FinancialComponent.REBILL_LOGISTICS)

    assert result.status == FinancialStatus.PARTIAL
    assert trace.amount == Decimal("-35.00")
    assert trace.included is False
    assert trace.source_rebill_logistics == (rebill,)
    assert any("excluded from authoritative P&L" in item for item in result.diagnostics)


def test_d_sourced_tax_is_included() -> None:
    result = calculate_financial_result(_input(*_base_components()))

    trace = _trace(result, FinancialComponent.TAX)
    assert trace.amount == Decimal("-40.00")
    assert trace.included is True


def test_e_direct_advertising_retains_sku_attribution() -> None:
    expense = AdvertisingExpenseInput(
        amount=Decimal("-25.00"),
        attribution=AdvertisingAttribution.DIRECT,
        period_start=OPERATIONAL_DATE,
        period_end=OPERATIONAL_DATE,
        source="ads_report",
        source_record_id="ads-direct-001",
        nm_id="1001",
    )

    result = calculate_financial_result(_input(*_base_components(), advertising_expenses=(expense,)))
    trace = _trace(result, FinancialComponent.ADVERTISING)

    assert result.net_profit == Decimal("375.00")
    assert trace.source_advertising_expenses[0].nm_id == "1001"


def test_f_period_advertising_is_not_allocated_to_sku() -> None:
    expense = AdvertisingExpenseInput(
        amount=Decimal("-100.00"),
        attribution=AdvertisingAttribution.PERIOD_LEVEL,
        period_start=OPERATIONAL_DATE,
        period_end=OPERATIONAL_DATE,
        source="ads_report",
        source_record_id="ads-period-001",
    )

    result = calculate_financial_result(_input(*_base_components(), advertising_expenses=(expense,)))
    trace = _trace(result, FinancialComponent.ADVERTISING)

    assert result.net_profit == Decimal("300.00")
    assert trace.source_advertising_expenses[0].nm_id is None
    assert "without automatic SKU allocation" in trace.reason


def test_g_explicit_unit_cogs_uses_authoritative_quantity() -> None:
    allocation = CogsAllocationInput(
        nm_id="1001",
        quantity=3,
        state=FinancialInputState.PROVIDED,
        unit_cogs=Decimal("120.25"),
        source="approved_cogs_catalog",
        source_record_id="cogs-unit-001",
        effective_date=OPERATIONAL_DATE,
    )
    components = tuple(item for item in _base_components() if item.component != FinancialComponent.COGS)

    result = calculate_financial_result(_input(*components, cogs_allocations=(allocation,)))

    assert _trace(result, FinancialComponent.COGS).amount == Decimal("-360.75")
    assert result.net_profit == Decimal("439.25")


def test_h_direct_period_cogs_is_used_without_sku_allocation() -> None:
    result = calculate_financial_result(_input(*_base_components()))

    trace = _trace(result, FinancialComponent.COGS)
    assert trace.amount == Decimal("-400.00")
    assert trace.source_cogs_allocations == ()


@pytest.mark.parametrize(
    "event",
    [UnresolvedCogsEvent.RETURN, UnresolvedCogsEvent.CANCELLATION, UnresolvedCogsEvent.PARTIAL_RETURN],
)
def test_i_j_k_event_does_not_trigger_automatic_cogs_treatment(event: UnresolvedCogsEvent) -> None:
    components = tuple(item for item in _base_components() if item.component != FinancialComponent.COGS)

    result = calculate_financial_result(
        _input(*components, unresolved_cogs_events=(_unresolved_event(event),))
    )
    trace = _trace(result, FinancialComponent.COGS)

    assert result.status == FinancialStatus.PARTIAL
    assert result.net_profit is None
    assert trace.status == FinancialComponentStatus.UNRESOLVED
    assert trace.amount is None
    assert "no automatic reversal or allocation" in trace.reason


def test_l_duplicate_source_record_is_conflict_not_silent_aggregation() -> None:
    first = _component(FinancialComponent.LOGISTICS, Decimal("-10.00"), source_record_id="duplicate")
    second = _component(FinancialComponent.LOGISTICS, Decimal("-10.00"), source_record_id="duplicate")

    result = calculate_financial_result(
        _input(_component(FinancialComponent.REALIZED_REVENUE, Decimal("100.00")), first, second)
    )

    assert result.status == FinancialStatus.CONFLICT
    assert result.net_profit is None
    assert any("duplicate source component" in item for item in result.diagnostics)


def test_m_unknown_finality_is_partial() -> None:
    result = calculate_financial_result(
        _input(*_base_components(), finality=(_finality(FinancialFinality.UNKNOWN),))
    )

    assert result.status == FinancialStatus.PARTIAL
    assert result.net_profit is None


def test_operational_fact_without_finance_is_awaiting_confirmation() -> None:
    canonical = normalize_sales_funnel_products(synthetic_raw_object())
    reconciliation = reconcile_sales_funnel_products(canonical)[0]
    financial_input = FinancialInput(
        scope=synthetic_scope(),
        operational_date=OPERATIONAL_DATE,
        currency=CanonicalCurrency.RUB,
        reconciled_facts=(reconciliation,),
        components=(),
    )

    result = calculate_financial_result(financial_input)

    assert reconciliation.lag_state == ReconciliationLagState.AWAITING_FINANCIAL_CONFIRMATION
    assert result.status == FinancialStatus.AWAITING_FINANCIAL_CONFIRMATION
    assert result.financial_dates == ()


def test_n_zero_revenue_has_no_margin() -> None:
    components = (
        _component(FinancialComponent.REALIZED_REVENUE, Decimal("0")),
        _component(FinancialComponent.COGS, Decimal("0")),
        _component(FinancialComponent.TAX, Decimal("0")),
    )

    result = calculate_financial_result(_input(*components))

    assert result.status == FinancialStatus.COMPLETE
    assert result.net_profit == Decimal("0.00")
    assert result.profit_margin is None


def test_o_money_contract_rejects_float_contamination() -> None:
    with pytest.raises(ValidationError, match="must not be float"):
        _component(FinancialComponent.REALIZED_REVENUE, 100.0)  # type: ignore[arg-type]


def test_p_rounding_aggregates_before_round_half_up() -> None:
    result = calculate_financial_result(
        _input(
            _component(FinancialComponent.REALIZED_REVENUE, Decimal("1.005")),
            _component(FinancialComponent.LOGISTICS, Decimal("-0.004")),
            _component(FinancialComponent.COGS, Decimal("0")),
            _component(FinancialComponent.TAX, Decimal("0")),
        )
    )

    assert result.net_profit == Decimal("1.00")


def test_q_negative_expenses_are_not_subtracted_twice() -> None:
    result = calculate_financial_result(
        _input(
            _component(FinancialComponent.REALIZED_REVENUE, Decimal("1000")),
            _component(FinancialComponent.MARKETPLACE_COMMISSION, Decimal("-200")),
            _component(FinancialComponent.LOGISTICS, Decimal("-100")),
            _component(FinancialComponent.COGS, Decimal("-50")),
            _component(FinancialComponent.TAX, Decimal("0")),
        )
    )

    assert result.net_profit == Decimal("650.00")


def test_direct_and_unit_cogs_conflict() -> None:
    allocation = CogsAllocationInput(
        nm_id="1001",
        quantity=1,
        state=FinancialInputState.PROVIDED,
        unit_cogs=Decimal("400"),
        source="approved_cogs_catalog",
        source_record_id="unit-cogs",
        effective_date=OPERATIONAL_DATE,
    )

    result = calculate_financial_result(_input(*_base_components(), cogs_allocations=(allocation,)))

    assert result.status == FinancialStatus.CONFLICT
    assert _trace(result, FinancialComponent.COGS).status == FinancialComponentStatus.CONFLICT


def test_same_input_is_deterministic_and_not_mutated() -> None:
    financial_input = _input(*_base_components())
    before = financial_input.model_dump(mode="json")

    first = calculate_financial_result(financial_input)
    second = calculate_financial_result(financial_input)

    assert first == second
    assert financial_input.model_dump(mode="json") == before


def test_kernel_has_no_forbidden_runtime_dependencies() -> None:
    module = sys.modules[calculate_financial_result.__module__]
    source = inspect.getsource(module)

    for forbidden in ("legacy", "v3", "report_v2", "core_report_bridge", "filesystem", "wb_api"):
        assert forbidden not in source.lower()
