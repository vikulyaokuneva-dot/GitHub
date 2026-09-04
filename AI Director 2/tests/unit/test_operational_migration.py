from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from packages.data.canonical import CanonicalInputState
from packages.data.normalization import normalize_orders, normalize_sales, normalize_sales_funnel_products, normalize_stocks
from packages.operational.contracts import OperationalReadStatus
from packages.operational.service import build_operational_daily_read_model
from packages.wb_core.contracts import ORDERS_ENDPOINT, SALES_ENDPOINT, STOCKS_ENDPOINT, RawObject
from packages.wb_core.synthetic_scenario import SYNTHETIC_OBJECT_ID, synthetic_raw_object, synthetic_scope

OPERATIONAL_DATE = date(2026, 8, 20)
RETRIEVED_AT = datetime(2026, 8, 24, 10, 30, tzinfo=UTC)


def _raw_object(*, endpoint: object, object_id: str, rows: list[dict[str, object]]) -> RawObject:
    endpoint_metadata = endpoint
    return RawObject(
        object_id=object_id,
        scope=synthetic_scope(),
        endpoint=endpoint_metadata,
        object_type=endpoint_metadata.object_type,
        source="wildberries",
        retrieved_at=RETRIEVED_AT,
        operational_date=OPERATIONAL_DATE,
        request_scope={"dateFrom": OPERATIONAL_DATE.isoformat()},
        payload={"data": rows},
        schema_version=endpoint_metadata.schema_version,
    )


def _orders() -> tuple[object, ...]:
    return normalize_orders(
        _raw_object(
            endpoint=ORDERS_ENDPOINT,
            object_id="a" * 64,
            rows=[
                {
                    "srid": "order-1",
                    "nmId": 1001,
                    "supplierArticle": "ART-1001",
                    "quantity": "2",
                    "priceWithDisc": "1200.50",
                    "isCancel": False,
                    "date": "2026-08-20T09:15:00+03:00",
                }
            ],
        )
    )


def _sales() -> tuple[object, ...]:
    return normalize_sales(
        _raw_object(
            endpoint=SALES_ENDPOINT,
            object_id="b" * 64,
            rows=[
                {
                    "srid": "sale-1",
                    "nmId": 1001,
                    "supplierArticle": "ART-1001",
                    "quantity": "1",
                    "priceWithDisc": "600.25",
                    "date": "2026-08-20T12:00:00+03:00",
                }
            ],
        )
    )


def _stocks() -> tuple[object, ...]:
    return normalize_stocks(
        _raw_object(
            endpoint=STOCKS_ENDPOINT,
            object_id="c" * 64,
            rows=[
                {
                    "nmId": 1001,
                    "supplierArticle": "ART-1001",
                    "warehouseName": "Kolедино",
                    "quantity": "11",
                    "inWayToClient": "2",
                    "inWayFromClient": "3",
                }
            ],
        )
    )


def test_operational_normalizers_retain_typed_events_snapshots_and_provenance() -> None:
    order = _orders()[0]
    sale = _sales()[0]
    stock = _stocks()[0]

    assert order.source_event_id == "order-1"
    assert order.quantity == Decimal("2")
    assert order.amount == Decimal("1200.50")
    assert order.is_cancel is False
    assert order.source_event_date == OPERATIONAL_DATE
    assert sale.source_event_id == "sale-1"
    assert sale.amount == Decimal("600.25")
    assert stock.available_quantity == Decimal("11")
    assert stock.in_way_to_client_quantity == Decimal("2")
    assert stock.in_way_from_client_quantity == Decimal("3")
    assert order.source_metadata.retrieved_at == RETRIEVED_AT


def test_operational_read_model_has_one_owner_per_metric_and_keeps_cohorts_separate() -> None:
    funnel = normalize_sales_funnel_products(synthetic_raw_object())
    model = build_operational_daily_read_model(orders=_orders(), sales=_sales(), stock_snapshots=_stocks(), funnel_products=funnel)

    assert model.order_quantity.value == Decimal("2")
    assert model.sales_quantity.value == Decimal("1")
    assert model.available_stock_quantity.value == Decimal("11")
    assert model.funnel_order_count.value == Decimal("2")
    assert model.cohort_buyout_count.status == OperationalReadStatus.MISSING
    assert model.cohort_buyout_count.value is None
    assert model.cohort_buyout_sum.status == OperationalReadStatus.MISSING
    assert not hasattr(model.funnel_products[0], "order_id")
    assert not hasattr(model.funnel_products[0], "sale_id")


def test_funnel_buyout_metrics_remain_cohort_metrics_and_are_not_operational_sales() -> None:
    raw_funnel = synthetic_raw_object().model_copy(
        update={
            "payload": {
                "data": {
                    "products": [
                        {
                            "product": {"nmId": 1001, "vendorCode": "SYNTH-ART-1001"},
                            "statistic": {
                                "selected": {
                                    "orderCount": 2,
                                    "buyoutCount": 1,
                                    "buyoutSum": "700.00",
                                }
                            },
                        }
                    ]
                }
            }
        }
    )
    model = build_operational_daily_read_model(funnel_products=normalize_sales_funnel_products(raw_funnel))

    assert model.funnel_order_count.value == Decimal("2")
    assert model.cohort_buyout_count.value == Decimal("1")
    assert model.cohort_buyout_sum.value == Decimal("700.00")
    assert model.sales == ()


def test_operational_missing_value_is_not_converted_to_zero() -> None:
    raw = _raw_object(
        endpoint=ORDERS_ENDPOINT,
        object_id="d" * 64,
        rows=[
            {
                "srid": "order-2",
                "nmId": 1001,
                "supplierArticle": "ART-1001",
                "quantity": None,
                "isCancel": False,
                "date": "2026-08-20",
            }
        ],
    )
    order = normalize_orders(raw)[0]
    model = build_operational_daily_read_model(orders=(order,))

    assert order.quantity_input.state == CanonicalInputState.NULL
    assert order.quantity is None
    assert model.order_quantity.status == OperationalReadStatus.MISSING
    assert model.order_quantity.value is None


def test_statistics_rows_without_quantity_field_normalize_to_one_item() -> None:
    """WB statistics /orders and /sales emit one item per row with no quantity field."""

    orders = normalize_orders(
        _raw_object(
            endpoint=ORDERS_ENDPOINT,
            object_id="e" * 64,
            rows=[
                {
                    "srid": "order-no-qty",
                    "nmId": 1001,
                    "supplierArticle": "ART-1001",
                    "priceWithDisc": 780,
                    "isCancel": False,
                    "date": "2026-08-20T09:15:00+03:00",
                }
            ],
        )
    )
    sales = normalize_sales(
        _raw_object(
            endpoint=SALES_ENDPOINT,
            object_id="f" * 64,
            rows=[
                {
                    "srid": "sale-no-qty",
                    "nmId": 1001,
                    "supplierArticle": "ART-1001",
                    "priceWithDisc": 605,
                    "date": "2026-08-20T19:15:30+03:00",
                }
            ],
        )
    )
    model = build_operational_daily_read_model(orders=orders, sales=sales)

    assert len(orders) == 1 and len(sales) == 1
    for event in (*orders, *sales):
        assert event.quantity == Decimal(1)
        assert event.quantity_input.state == CanonicalInputState.VALUE
        assert event.quantity_input.raw_path == "quantity"
    assert model.order_quantity.value == Decimal(1)
    assert model.order_quantity.status == OperationalReadStatus.COMPLETE
    assert model.sales_quantity.value == Decimal(1)
    assert model.sales_quantity.status == OperationalReadStatus.COMPLETE


def test_statistics_quantity_rule_is_not_applied_to_stocks() -> None:
    """Stocks rows without quantity must stay missing; no source-wide default."""

    stocks = normalize_stocks(
        _raw_object(
            endpoint=STOCKS_ENDPOINT,
            object_id="1" * 64,
            rows=[{"nmId": 1001, "supplierArticle": "ART-1001", "warehouseName": "Коледино"}],
        )
    )
    model = build_operational_daily_read_model(stock_snapshots=stocks)

    assert stocks[0].available_quantity_input.state == CanonicalInputState.MISSING
    assert stocks[0].available_quantity is None
    assert model.available_stock_quantity.status == OperationalReadStatus.MISSING


def test_operational_read_model_is_deterministic_and_rejects_mixed_days() -> None:
    first = build_operational_daily_read_model(orders=_orders(), sales=_sales())
    second = build_operational_daily_read_model(sales=reversed(_sales()), orders=reversed(_orders()))

    assert first == second
    foreign_day_sale = _sales()[0].model_copy(update={"operational_date": date(2026, 8, 21)})
    with pytest.raises(ValueError, match="operational_date"):
        build_operational_daily_read_model(orders=_orders(), sales=(foreign_day_sale,))
