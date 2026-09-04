from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from packages.finance.contracts import FinancialComponent, FinancialComponentInput, FinancialFinality, FinancialFinalityInput, FinancialInputState, FinancialStatus
from packages.pipeline.service import run_pipeline
from packages.products.contracts import DirectPeriodCogsInput
from packages.tax.contracts import SourcedTaxInput
from packages.wb_core.contracts import (
    ADVERTISING_PERFORMANCE_ENDPOINT,
    FINANCE_DETAIL_ENDPOINT,
    ORDERS_ENDPOINT,
    SALES_ENDPOINT,
    SALES_FUNNEL_PRODUCTS_ENDPOINT,
    STOCKS_ENDPOINT,
    InMemoryRawObjectRepository,
    RawObject,
)
from packages.wb_core.synthetic_scenario import synthetic_scope

DAY = date(2026, 8, 20)
RETRIEVED_AT = datetime(2026, 8, 24, 10, 30, tzinfo=UTC)


def _raw(*, endpoint: object, suffix: str, payload: dict[str, object]) -> RawObject:
    metadata = endpoint
    return RawObject(
        object_id=(suffix * 64)[:64], scope=synthetic_scope(), endpoint=metadata, object_type=metadata.object_type,
        source="wildberries", retrieved_at=RETRIEVED_AT, operational_date=DAY, request_scope={"dateFrom": DAY.isoformat()},
        payload=payload, schema_version=metadata.schema_version,
    )


def _base_raw_objects(*, include_finance: bool = True, include_ads: bool = True) -> tuple[RawObject, ...]:
    objects = [
        _raw(endpoint=ORDERS_ENDPOINT, suffix="1", payload={"data": [{"srid": "order-1", "nmId": 1001, "quantity": "2", "priceWithDisc": "100.00", "isCancel": False, "date": DAY.isoformat()}]}),
        _raw(endpoint=SALES_ENDPOINT, suffix="2", payload={"data": [{"srid": "sale-1", "nmId": 1001, "quantity": "1", "priceWithDisc": "50.00", "date": DAY.isoformat()}]}),
        _raw(endpoint=STOCKS_ENDPOINT, suffix="3", payload={"data": [{"nmId": 1001, "quantity": "10", "inWayToClient": "1", "inWayFromClient": "2"}]}),
        _raw(endpoint=SALES_FUNNEL_PRODUCTS_ENDPOINT, suffix="4", payload={"data": {"products": [{"product": {"nmId": 1001, "vendorCode": "ART-1001"}, "statistic": {"selected": {"openCount": 20, "cartCount": 4, "orderCount": 2, "buyoutCount": 1, "buyoutSum": "40.00", "currency": "RUB"}}}]}}),
    ]
    if include_finance:
        objects.append(_raw(endpoint=FINANCE_DETAIL_ENDPOINT, suffix="5", payload={"data": [{"rrdId": "rrd-1", "rrDate": "2026-08-21", "saleDt": DAY.isoformat(), "nmId": 1001, "supplierArticle": "ART-1001", "supplierOperName": "Продажа", "docTypeName": "Продажа", "quantity": "2", "retailAmount": "1000.00", "retailPriceWithDiscRub": "600.00", "ppvzForPay": "700.00", "currency": "RUB"}]}))
    if include_ads:
        objects.append(_raw(endpoint=ADVERTISING_PERFORMANCE_ENDPOINT, suffix="6", payload={"data": [{"advertId": 1, "nmId": 1001, "sum": "100.00"}, {"advertId": 1, "attributionScope": "period", "sum": "50.00"}]}))
    return tuple(objects)


def _finality(*, finality: FinancialFinality = FinancialFinality.FINAL) -> tuple[FinancialFinalityInput, ...]:
    return (FinancialFinalityInput(source="wildberries", source_record_id="rrd-1", operational_date=DAY, financial_date=date(2026, 8, 21), finality=finality, evidence_code="explicit_closed_statement"),)


def _cogs() -> DirectPeriodCogsInput:
    return DirectPeriodCogsInput(scope=synthetic_scope(), operational_date=DAY, state=FinancialInputState.PROVIDED, amount=Decimal("-300.00"), source="ledger", source_record_id="cogs-1", source_endpoint="ledger")


def _tax(*, state: FinancialInputState = FinancialInputState.PROVIDED) -> SourcedTaxInput:
    return SourcedTaxInput(scope=synthetic_scope(), operational_date=DAY, financial_date=date(2026, 8, 21), state=state, amount=Decimal("-60.00") if state == FinancialInputState.PROVIDED else None, source="tax_statement", source_record_id="tax-1", source_endpoint="tax", diagnostic=None if state == FinancialInputState.PROVIDED else "tax statement unavailable")


def test_complete_pipeline_uses_only_raw_objects_and_domain_outputs() -> None:
    repository = InMemoryRawObjectRepository()
    result = run_pipeline(repository=repository, raw_objects=_base_raw_objects(), finality=_finality(), period_cogs=_cogs(), tax=_tax())

    assert len(repository.list(scope=synthetic_scope())) == 6
    assert result.operational.order_quantity.value == Decimal("2")
    assert result.financial_flow.financial_result is not None
    assert result.financial_flow.financial_result.status == FinancialStatus.COMPLETE
    assert result.financial_flow.financial_result.net_profit == Decimal("490.00")
    assert any(metric.key == "advertising_period" and metric.value == Decimal("50.00") for metric in result.report_payload.metrics)


def test_pipeline_preserves_partial_lag_unresolved_and_missing_states() -> None:
    unresolved = FinancialComponentInput(component=FinancialComponent.LOGISTICS, state=FinancialInputState.UNRESOLVED, amount=Decimal("25.00"), source="finance_detail", source_record_id="unresolved-logistics", source_endpoint="finance_detail", operational_date=DAY)
    result = run_pipeline(repository=InMemoryRawObjectRepository(), raw_objects=_base_raw_objects(), finality=_finality(), period_cogs=_cogs(), tax=_tax(state=FinancialInputState.MISSING), unresolved_marketplace_components=(unresolved,))

    assert result.financial_flow.financial_result is not None
    assert result.financial_flow.financial_result.status == FinancialStatus.PARTIAL
    assert result.financial_flow.financial_result.net_profit is None
    logistics = next(trace for trace in result.financial_flow.financial_result.component_traces if trace.component == FinancialComponent.LOGISTICS)
    assert logistics.included is False
    tax = next(trace for trace in result.financial_flow.financial_result.component_traces if trace.component == FinancialComponent.TAX)
    assert tax.amount is None


def test_pipeline_handles_financial_lag_and_absent_finance_without_operational_finance_mix() -> None:
    lagged_finality = (FinancialFinalityInput(source="wildberries", source_record_id="rrd-1", operational_date=DAY, financial_date=date(2026, 8, 19), finality=FinancialFinality.FINAL, evidence_code="historical_statement"),)
    lagged = run_pipeline(repository=InMemoryRawObjectRepository(), raw_objects=_base_raw_objects(include_ads=False), finality=lagged_finality, period_cogs=_cogs(), tax=_tax(), financial_lag=True)
    absent = run_pipeline(repository=InMemoryRawObjectRepository(), raw_objects=_base_raw_objects(include_finance=False, include_ads=False))

    assert lagged.financial_flow.finality_assessment is not None
    assert lagged.financial_flow.finality_assessment.status == FinancialStatus.PARTIAL
    assert lagged.financial_flow.financial_result is not None
    assert lagged.financial_flow.financial_result.status == FinancialStatus.PARTIAL
    assert absent.financial_flow.financial_input is None
    assert absent.financial_flow.financial_result is None
    assert any(metric.key == "sales" and metric.value == Decimal("1") for metric in absent.report_payload.metrics)
