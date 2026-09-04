from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from packages.data.canonical import CanonicalCurrency, CanonicalSalesFunnelProduct, CanonicalSourceMetadata
from packages.data.normalization import normalize_sales_funnel_products
from packages.reconciliation.contracts import (
    CanonicalCohortMetricFact,
    CanonicalSalesConfirmationFact,
    ReconciliationDiagnosticCode,
    ReconciliationLagState,
    ReconciliationResult,
    ReconciliationRule,
    ReconciliationStatus,
)
from packages.reconciliation.service import reconcile_sales_funnel_products
from packages.wb_core.contracts import RawObjectType
from packages.wb_core.synthetic_scenario import synthetic_raw_object, synthetic_scope

OPERATIONAL_DATE = date(2026, 8, 20)
RETRIEVED_AT = datetime(2026, 8, 24, 10, 30, tzinfo=UTC)
CONFIRMATION_OBJECT_ID = "a" * 64
COHORT_OBJECT_ID = "b" * 64


def _sales_funnel_fact(
    *, quantity: int | None = 2, amount: Decimal | None = Decimal("1234.56")
) -> CanonicalSalesFunnelProduct:
    raw_object = synthetic_raw_object()
    payload = raw_object.model_copy(
        update={
            "payload": {
                "data": {
                    "products": [
                        {
                            "product": {"nmId": 1001, "vendorCode": "SYNTH-ART-1001"},
                            "statistic": {
                                "selected": {
                                    "orderCount": quantity,
                                    "orderSum": str(amount) if amount is not None else None,
                                    "currency": "RUB",
                                }
                            },
                        }
                    ]
                }
            }
        }
    )
    return normalize_sales_funnel_products(payload)[0]


def _source_metadata(*, object_id: str, source: str, index: int = 0) -> CanonicalSourceMetadata:
    return CanonicalSourceMetadata(
        source=source,
        scope=synthetic_scope(),
        source_object_id=object_id,
        endpoint_name=source,
        object_type=RawObjectType.SALES_FUNNEL_PRODUCTS,
        schema_version="synthetic-v1",
        retrieved_at=RETRIEVED_AT,
        source_record_index=index,
    )


def _confirmation(
    *,
    event_id: str | None = None,
    quantity: int | None = 2,
    amount: Decimal | None = Decimal("1234.56"),
    nm_id: str | None = "1001",
    seller_sku: str | None = "SYNTH-ART-1001",
) -> CanonicalSalesConfirmationFact:
    return CanonicalSalesConfirmationFact(
        source_metadata=_source_metadata(object_id=CONFIRMATION_OBJECT_ID, source="synthetic_sales_confirmation"),
        operational_date=OPERATIONAL_DATE,
        source_event_id=event_id,
        nm_id=nm_id,
        seller_sku=seller_sku,
        quantity=quantity,
        source_amount=amount,
        currency=CanonicalCurrency.RUB,
    )


def _cohort_fact(*, buyout_count: int = 1, buyout_sum: Decimal = Decimal("700.00")) -> CanonicalCohortMetricFact:
    return CanonicalCohortMetricFact(
        source_metadata=_source_metadata(object_id=COHORT_OBJECT_ID, source="synthetic_buyout_cohort"),
        operational_date=OPERATIONAL_DATE,
        nm_id="1001",
        seller_sku="SYNTH-ART-1001",
        buyout_count=buyout_count,
        buyout_sum=buyout_sum,
        currency=CanonicalCurrency.RUB,
    )


def _codes(result: ReconciliationResult) -> set[ReconciliationDiagnosticCode]:
    return {diagnostic.code for diagnostic in result.diagnostics}


def test_scenario_a_strong_identity_match_is_explainable_and_preserves_sources() -> None:
    sales_fact = _sales_funnel_fact()
    confirmation = _confirmation(event_id=f"{sales_fact.source_metadata.source_object_id}:0")

    result = reconcile_sales_funnel_products([sales_fact], [confirmation])[0]

    assert result.status == ReconciliationStatus.MATCHED
    assert result.identity.rule == ReconciliationRule.STRONG_SOURCE_RECORD_ID
    assert result.sales_funnel_facts == (sales_fact,)
    assert result.confirmation_facts == (confirmation,)
    assert ReconciliationDiagnosticCode.STRONG_IDENTITY_MATCH in _codes(result)
    assert result.lag_state == ReconciliationLagState.AWAITING_FINANCIAL_CONFIRMATION


def test_composite_identity_match_is_explicit_when_no_strong_identifier_exists() -> None:
    result = reconcile_sales_funnel_products([_sales_funnel_fact()], [_confirmation()])[0]

    assert result.status == ReconciliationStatus.MATCHED
    assert result.identity.rule == ReconciliationRule.COMPOSITE_OPERATIONAL_DATE_AND_PRODUCT
    assert result.identity.value == "2026-08-20:1001"
    assert ReconciliationDiagnosticCode.COMPOSITE_IDENTITY_MATCH in _codes(result)


def test_scenario_b_unmatched_fact_is_retained_with_its_own_identity() -> None:
    sales_fact = _sales_funnel_fact()

    result = reconcile_sales_funnel_products([sales_fact])[0]

    assert result.status == ReconciliationStatus.UNMATCHED
    assert result.sales_funnel_facts == (sales_fact,)
    assert result.confirmation_facts == ()
    assert ReconciliationDiagnosticCode.SINGLE_SOURCE_FACT in _codes(result)


def test_scenario_c_conflict_preserves_both_values_and_emits_reason() -> None:
    sales_fact = _sales_funnel_fact(quantity=2, amount=Decimal("1234.56"))
    confirmation = _confirmation(
        event_id=f"{sales_fact.source_metadata.source_object_id}:0",
        quantity=3,
        amount=Decimal("1300.00"),
    )

    result = reconcile_sales_funnel_products([sales_fact], [confirmation])[0]

    assert result.status == ReconciliationStatus.CONFLICT
    assert result.sales_funnel_facts[0].quantity == 2
    assert result.confirmation_facts[0].quantity == 3
    assert result.sales_funnel_facts[0].source_amount == Decimal("1234.56")
    assert result.confirmation_facts[0].source_amount == Decimal("1300.00")
    assert ReconciliationDiagnosticCode.QUANTITY_CONFLICT in _codes(result)
    assert ReconciliationDiagnosticCode.AMOUNT_CONFLICT in _codes(result)


def test_missing_source_value_is_partial_not_silently_zeroed() -> None:
    sales_fact = _sales_funnel_fact(quantity=None)
    confirmation = _confirmation(event_id=f"{sales_fact.source_metadata.source_object_id}:0")

    result = reconcile_sales_funnel_products([sales_fact], [confirmation])[0]

    assert result.status == ReconciliationStatus.PARTIAL
    assert result.sales_funnel_facts[0].quantity is None
    assert ReconciliationDiagnosticCode.MISSING_QUANTITY in _codes(result)


def test_scenario_d_operational_fact_without_finance_is_lagged_not_conflict() -> None:
    result = reconcile_sales_funnel_products([_sales_funnel_fact()])[0]

    assert result.financial_dates == ()
    assert result.lag_state == ReconciliationLagState.AWAITING_FINANCIAL_CONFIRMATION
    assert result.status == ReconciliationStatus.UNMATCHED
    assert ReconciliationDiagnosticCode.FINANCIAL_CONFIRMATION_PENDING in _codes(result)
    assert result.retrieved_at_values == (RETRIEVED_AT,)
    assert result.operational_dates == (OPERATIONAL_DATE,)


def test_scenario_e_buyout_metrics_remain_cohort_metrics() -> None:
    sales_fact = _sales_funnel_fact()
    cohort_fact = _cohort_fact()

    result = reconcile_sales_funnel_products([sales_fact], cohort_metric_facts=[cohort_fact])[0]

    assert result.cohort_metric_facts == (cohort_fact,)
    assert result.cohort_metric_facts[0].metric_kind == "buyout_cohort"
    assert not hasattr(result.cohort_metric_facts[0], "order_id")
    assert ReconciliationDiagnosticCode.COHORT_METRIC_RETAINED in _codes(result)


def test_result_is_deterministic_across_input_ordering() -> None:
    first_sales_fact = _sales_funnel_fact()
    second_sales_fact = _sales_funnel_fact().model_copy(
        update={"source_metadata": _source_metadata(object_id="c" * 64, source="wildberries", index=1)}
    )
    first_confirmation = _confirmation(event_id=f"{first_sales_fact.source_metadata.source_object_id}:0")
    second_confirmation = _confirmation(event_id=f"{second_sales_fact.source_metadata.source_object_id}:1")

    forward = reconcile_sales_funnel_products(
        [first_sales_fact, second_sales_fact], [first_confirmation, second_confirmation]
    )
    reverse = reconcile_sales_funnel_products(
        [second_sales_fact, first_sales_fact], [second_confirmation, first_confirmation]
    )

    assert forward == reverse
    assert [result.reconciliation_id for result in forward] == [result.reconciliation_id for result in reverse]


def test_reconciliation_output_is_immutable_and_does_not_mutate_inputs() -> None:
    sales_fact = _sales_funnel_fact()
    confirmation = _confirmation(event_id=f"{sales_fact.source_metadata.source_object_id}:0")
    result = reconcile_sales_funnel_products([sales_fact], [confirmation])[0]

    with pytest.raises(Exception):
        result.status = ReconciliationStatus.CONFLICT
    with pytest.raises(Exception):
        sales_fact.quantity = 99
    assert result.status == ReconciliationStatus.MATCHED
    assert sales_fact.quantity == 2
    assert result.sales_funnel_facts[0] == sales_fact


def test_cross_tenant_inputs_are_rejected() -> None:
    sales_fact = _sales_funnel_fact()
    foreign_scope = synthetic_scope().model_copy(
        update={"account_id": "00000000-0000-0000-0000-000000000999"}
    )
    foreign_confirmation = _confirmation().model_copy(
        update={
            "source_metadata": _confirmation().source_metadata.model_copy(update={"scope": foreign_scope})
        }
    )

    with pytest.raises(ValueError, match="tenant/account"):
        reconcile_sales_funnel_products([sales_fact], [foreign_confirmation])
