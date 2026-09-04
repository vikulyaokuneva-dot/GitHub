from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from packages.advertising.service import build_advertising_read_model
from packages.data.normalization import normalize_advertising_performance, normalize_finance_detail
from packages.finance.contracts import (
    FinancialComponent,
    FinancialComponentInput,
    FinancialFinality,
    FinancialFinalityInput,
    FinancialInputState,
    FinancialStatus,
)
from packages.finance.flow import calculate_integrated_financial_flow
from packages.products.contracts import DirectPeriodCogsInput
from packages.tax.contracts import SourcedTaxInput
from packages.wb_core.contracts import ADVERTISING_PERFORMANCE_ENDPOINT, FINANCE_DETAIL_ENDPOINT, RawObject
from packages.wb_core.synthetic_scenario import synthetic_scope

DAY = date(2026, 8, 20)


def _raw_finance() -> RawObject:
    return RawObject(
        object_id="f" * 64,
        scope=synthetic_scope(), endpoint=FINANCE_DETAIL_ENDPOINT, object_type=FINANCE_DETAIL_ENDPOINT.object_type,
        source="wildberries", retrieved_at=datetime(2026, 8, 24, 10, 30, tzinfo=UTC), operational_date=DAY,
        request_scope={"dateFrom": DAY.isoformat()}, schema_version=FINANCE_DETAIL_ENDPOINT.schema_version,
        payload={"data": [{"rrdId": "rrd-1", "rrDate": "2026-08-21", "saleDt": DAY.isoformat(), "nmId": 1001,
          "supplierArticle": "ART-1001", "supplierOperName": "Продажа", "docTypeName": "Продажа", "quantity": "2",
          "retailAmount": "1000.00", "retailPriceWithDiscRub": "600.00", "ppvzForPay": "700.00", "currency": "RUB"}]},
    )


def _advertising() -> object:
    raw = RawObject(
        object_id="e" * 64, scope=synthetic_scope(), endpoint=ADVERTISING_PERFORMANCE_ENDPOINT,
        object_type=ADVERTISING_PERFORMANCE_ENDPOINT.object_type, source="wildberries",
        retrieved_at=datetime(2026, 8, 24, 10, 30, tzinfo=UTC), operational_date=DAY,
        request_scope={"dateFrom": DAY.isoformat()}, schema_version=ADVERTISING_PERFORMANCE_ENDPOINT.schema_version,
        payload={"data": [{"advertId": 1, "nmId": 1001, "sum": "100.00"}, {"advertId": 1, "attributionScope": "period", "sum": "50.00"}]},
    )
    return build_advertising_read_model(normalize_advertising_performance(raw))


def _finality() -> tuple[FinancialFinalityInput, ...]:
    return (FinancialFinalityInput(source="wildberries", source_record_id="rrd-1", operational_date=DAY,
        financial_date=date(2026, 8, 21), finality=FinancialFinality.FINAL, evidence_code="statement_closed"),)


def test_integrated_financial_flow_calculates_complete_explicit_input_scenario() -> None:
    cogs = DirectPeriodCogsInput(scope=synthetic_scope(), operational_date=DAY, state=FinancialInputState.PROVIDED,
        amount=Decimal("-300.00"), source="ledger", source_record_id="cogs-1", source_endpoint="ledger")
    tax = SourcedTaxInput(scope=synthetic_scope(), operational_date=DAY, financial_date=date(2026, 8, 21),
        state=FinancialInputState.PROVIDED, amount=Decimal("-60.00"), source="tax_statement", source_record_id="tax-1", source_endpoint="tax")
    flow = calculate_integrated_financial_flow(finance_records=normalize_finance_detail(_raw_finance()), finality=_finality(),
        advertising=_advertising(), period_cogs=cogs, tax=tax)

    assert flow.financial_result is not None
    assert flow.financial_result.status == FinancialStatus.COMPLETE
    assert flow.financial_result.net_profit == Decimal("490.00")
    assert flow.financial_result.profit_margin == Decimal("49.00")
    assert flow.financial_input is not None
    assert {expense.nm_id for expense in flow.financial_input.advertising_expenses} == {"1001", None}


def test_unresolved_marketplace_component_is_excluded_and_makes_result_partial() -> None:
    unresolved = FinancialComponentInput(component=FinancialComponent.LOGISTICS, state=FinancialInputState.UNRESOLVED,
        amount=Decimal("17.00"), source="finance_detail", source_record_id="unresolved-logistics-1", source_endpoint="finance_detail", operational_date=DAY)
    flow = calculate_integrated_financial_flow(finance_records=normalize_finance_detail(_raw_finance()), finality=_finality(),
        unresolved_marketplace_components=(unresolved,))

    assert flow.financial_result is not None
    assert flow.financial_result.status == FinancialStatus.PARTIAL
    trace = next(item for item in flow.financial_result.component_traces if item.component == FinancialComponent.LOGISTICS)
    assert trace.included is False
    assert trace.amount == Decimal("17.00")
