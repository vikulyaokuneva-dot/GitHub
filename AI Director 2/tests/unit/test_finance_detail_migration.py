from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from packages.data.canonical import CanonicalInputState, FinancialRecordClassification
from packages.data.normalization import NormalizationError, normalize_finance_detail
from packages.finance.contracts import FinancialComponent, FinancialStatus, RevenueBasis
from packages.finance.finance_detail_adapter import build_financial_input_from_finance_detail
from packages.finance.kernel import calculate_financial_result
from packages.wb_core.contracts import FINANCE_DETAIL_ENDPOINT, RawObject
from packages.wb_core.synthetic_scenario import synthetic_scope

OPERATIONAL_DATE = date(2026, 7, 14)
RETRIEVED_AT = datetime(2026, 7, 20, 10, 30, tzinfo=UTC)
OBJECT_ID = "a" * 64


def _raw_object(rows: list[dict[str, object]]) -> RawObject:
    return RawObject(
        object_id=OBJECT_ID,
        scope=synthetic_scope(),
        endpoint=FINANCE_DETAIL_ENDPOINT,
        object_type=FINANCE_DETAIL_ENDPOINT.object_type,
        source=FINANCE_DETAIL_ENDPOINT.source,
        retrieved_at=RETRIEVED_AT,
        operational_date=OPERATIONAL_DATE,
        request_scope={"dateFrom": OPERATIONAL_DATE.isoformat(), "dateTo": OPERATIONAL_DATE.isoformat()},
        payload={"data": rows},
        schema_version=FINANCE_DETAIL_ENDPOINT.schema_version,
    )


def test_finance_quantity_is_not_defaulted_when_absent() -> None:
    """The statistics one-row-one-item rule never leaks into finance_detail."""

    records = normalize_finance_detail(_raw_object([{"rrdId": "fin-1", "retailAmount": "100.00"}]))

    assert records[0].quantity_input.state == CanonicalInputState.MISSING
    assert records[0].quantity is None


def _sale(*, rrd_id: str = "100001") -> dict[str, object]:
    return {
        "rrdId": rrd_id,
        "rrDate": "2026-07-19",
        "saleDt": "2026-07-14",
        "nmId": 1001,
        "supplierArticle": "ART-1001",
        "supplierOperName": "Продажа",
        "docTypeName": "Продажа",
        "quantity": "2",
        "retailAmount": "902.00",
        "retailPriceWithDiscRub": "800.00",
        "ppvzForPay": "987.92",
        "currency": "RUB",
    }


def test_finance_detail_raw_contract_retains_an_immutable_array() -> None:
    raw_object = _raw_object([_sale()])

    assert isinstance(raw_object.payload, Mapping)
    assert isinstance(raw_object.payload["data"], tuple)
    assert isinstance(raw_object.payload["data"][0], Mapping)
    assert raw_object.payload["data"][0]["retailAmount"] == "902.00"


def test_legacy_finance_sale_fields_map_to_separate_decimal_views() -> None:
    record = normalize_finance_detail(_raw_object([_sale()]))[0]

    assert record.source_record_id == "100001"
    assert record.operational_date == OPERATIONAL_DATE
    assert record.financial_date == date(2026, 7, 19)
    assert record.sale_date == OPERATIONAL_DATE
    assert record.quantity == Decimal("2")
    assert record.retail_amount == Decimal("902.00")
    assert record.buyer_discounted_price == Decimal("800.00")
    assert record.seller_payout == Decimal("987.92")
    assert record.classification == FinancialRecordClassification.FINANCIAL_SALE
    assert not isinstance(record.retail_amount, float)


def test_retail_amount_becomes_realized_revenue_only_for_financial_sale() -> None:
    records = normalize_finance_detail(_raw_object([_sale()]))

    build = build_financial_input_from_finance_detail(records)

    assert build.financial_input is not None
    financial_input = build.financial_input
    assert financial_input.components[0].component == FinancialComponent.REALIZED_REVENUE
    assert financial_input.components[0].amount == Decimal("902.00")
    assert {view.basis for view in financial_input.revenue_views} == {
        RevenueBasis.BUYER_DISCOUNTED,
        RevenueBasis.REALIZED_GROSS,
        RevenueBasis.SELLER_PAYOUT,
    }
    buyer_view = next(view for view in financial_input.revenue_views if view.basis == RevenueBasis.BUYER_DISCOUNTED)
    payout_view = next(view for view in financial_input.revenue_views if view.basis == RevenueBasis.SELLER_PAYOUT)
    assert buyer_view.amount == Decimal("1600.00")
    assert payout_view.amount == Decimal("987.92")
    assert calculate_financial_result(financial_input).status == FinancialStatus.PARTIAL


def test_return_with_retail_amount_is_retained_but_not_revenue() -> None:
    returned = _sale(rrd_id="100002")
    returned["supplierOperName"] = "Возврат"
    returned["docTypeName"] = "Возврат"
    returned["retailAmount"] = "451.00"

    records = normalize_finance_detail(_raw_object([returned]))
    build = build_financial_input_from_finance_detail(records)

    assert records[0].classification == FinancialRecordClassification.RETURN
    assert build.financial_input is None
    assert "excluded from realized revenue" in build.diagnostics[0]


def test_unclassified_finance_row_with_positive_retail_amount_is_not_revenue() -> None:
    other = _sale(rrd_id="100003")
    other.pop("supplierOperName")
    other.pop("docTypeName")

    build = build_financial_input_from_finance_detail(normalize_finance_detail(_raw_object([other])))

    assert build.financial_input is None
    assert "excluded from realized revenue" in build.diagnostics[0]


def test_missing_retail_amount_is_not_converted_to_zero() -> None:
    sale = _sale()
    sale.pop("retailAmount")

    record = normalize_finance_detail(_raw_object([sale]))[0]
    build = build_financial_input_from_finance_detail((record,))

    assert record.retail_amount is None
    assert record.retail_amount_input.state == CanonicalInputState.MISSING
    assert build.financial_input is None
    assert "missing retailAmount" in build.diagnostics[0]


def test_missing_rrd_id_uses_diagnostic_identity_and_is_excluded_from_authoritative_revenue() -> None:
    sale = _sale()
    sale.pop("rrdId")

    record = normalize_finance_detail(_raw_object([sale]))[0]
    build = build_financial_input_from_finance_detail((record,))

    assert record.source_record_id == f"{OBJECT_ID}:0"
    assert record.source_record_id_input.state == CanonicalInputState.MISSING
    assert build.financial_input is None
    assert "lacks rrdId" in build.diagnostics[0]


@pytest.mark.parametrize("value", [True, "not-money"])
def test_finance_detail_rejects_malformed_retail_amount(value: object) -> None:
    sale = _sale()
    sale["retailAmount"] = value

    with pytest.raises(NormalizationError, match="retailAmount"):
        normalize_finance_detail(_raw_object([sale]))
