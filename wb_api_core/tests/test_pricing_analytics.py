from __future__ import annotations

import sqlite3
from decimal import Decimal

from wb_api_core.loaders import load_fbs_order_prices, load_product_prices
from wb_api_core.normalize import normalize_bundle
from wb_api_core.pricing import (
    FBS_ORDER_SOURCE,
    PriceSnapshotStore,
    build_price_analytics,
    cents_to_money,
    discount_percent,
    normalize_fbs_order_prices,
    normalize_goods_prices,
)


def test_fbs_api_values_are_divided_by_100() -> None:
    rows = normalize_fbs_order_prices(
        [
            {
                "id": 11,
                "nmId": 101,
                "createdAt": "2026-07-24T08:00:00Z",
                "convertedPrice": 48_000,
                "convertedFinalPrice": 43_200,
            }
        ]
    )

    assert cents_to_money(48_000) == Decimal("480.00")
    assert rows[0]["buyer_price_before_wallet"] == "480.00"
    assert rows[0]["buyer_final_price"] == "432.00"


def test_platform_discount_52_percent_maps_1000_to_480() -> None:
    assert discount_percent(Decimal("1000"), Decimal("480")) == Decimal("52.00")


def test_wallet_discount_is_separate_from_platform_discount() -> None:
    rows = normalize_fbs_order_prices(
        [
            {
                "id": 12,
                "nmId": 102,
                "createdAt": "2026-07-24T08:00:00Z",
                "convertedPrice": 48_000,
                "convertedFinalPrice": 43_200,
            }
        ]
    )

    assert rows[0]["wallet_discount_percent"] == "10.00"
    assert "platform_discount_percent" not in rows[0]


def test_missing_price_stays_missing_instead_of_zero() -> None:
    rows = normalize_fbs_order_prices(
        [
            {
                "id": 13,
                "nmId": 103,
                "createdAt": "2026-07-24T08:00:00Z",
                "convertedPrice": None,
                "convertedFinalPrice": None,
            }
        ]
    )

    assert rows[0]["buyer_price_before_wallet"] is None
    assert rows[0]["buyer_final_price"] is None
    assert rows[0]["wallet_discount_percent"] is None
    assert rows[0]["data_quality_status"] == "missing_buyer_price"


def test_old_order_uses_only_snapshot_not_later_than_order(tmp_path) -> None:
    store = PriceSnapshotStore(tmp_path / "prices.sqlite3")
    prior = normalize_goods_prices(
        [
            {
                "nmID": 104,
                "discount": 0,
                "sizes": [{"sizeID": 1, "price": 1000, "discountedPrice": 1000}],
            }
        ],
        captured_at="2026-07-23T09:00:00Z",
    )
    later = normalize_goods_prices(
        [
            {
                "nmID": 104,
                "discount": 0,
                "sizes": [{"sizeID": 1, "price": 1200, "discountedPrice": 1200}],
            }
        ],
        captured_at="2026-07-25T09:00:00Z",
    )
    store.upsert_current_prices(seller_id="seller_1", rows=prior + later)
    order = normalize_fbs_order_prices(
        [
            {
                "id": 14,
                "nmId": 104,
                "createdAt": "2026-07-24T09:00:00Z",
                "convertedPrice": 48_000,
                "convertedFinalPrice": 48_000,
            }
        ]
    )
    store.upsert_fbs_orders(seller_id="seller_1", rows=order)

    order_row = next(row for row in store.rows(seller_id="seller_1") if row["source"] == FBS_ORDER_SOURCE)
    assert Decimal(str(order_row["seller_base_price"])) == Decimal("1000")
    assert Decimal(str(order_row["platform_discount_percent"])) == Decimal("52")


def test_order_before_first_snapshot_does_not_receive_current_price(tmp_path) -> None:
    store = PriceSnapshotStore(tmp_path / "prices.sqlite3")
    current = normalize_goods_prices(
        [
            {
                "nmID": 105,
                "discount": 0,
                "sizes": [{"sizeID": 1, "price": 1000, "discountedPrice": 1000}],
            }
        ],
        captured_at="2026-07-25T09:00:00Z",
    )
    store.upsert_current_prices(seller_id="seller_1", rows=current)
    order = normalize_fbs_order_prices(
        [
            {
                "id": 15,
                "nmId": 105,
                "createdAt": "2026-07-24T09:00:00Z",
                "convertedPrice": 48_000,
                "convertedFinalPrice": 48_000,
            }
        ]
    )
    store.upsert_fbs_orders(seller_id="seller_1", rows=order)

    order_row = next(row for row in store.rows(seller_id="seller_1") if row["source"] == FBS_ORDER_SOURCE)
    assert order_row["seller_base_price"] is None
    assert order_row["platform_discount_percent"] is None
    assert order_row["data_quality_status"] == "missing_historical_seller_snapshot"


def test_sku_total_reconciles_with_fbs_orders(tmp_path) -> None:
    store = PriceSnapshotStore(tmp_path / "prices.sqlite3")
    prices = normalize_goods_prices(
        [
            {"nmID": 201, "discount": 0, "sizes": [{"sizeID": 1, "price": 1000, "discountedPrice": 1000}]},
            {"nmID": 202, "discount": 0, "sizes": [{"sizeID": 1, "price": 500, "discountedPrice": 500}]},
        ],
        captured_at="2026-07-23T08:00:00Z",
    )
    orders = normalize_fbs_order_prices(
        [
            {"id": 21, "nmId": 201, "createdAt": "2026-07-24T08:00:00Z", "convertedPrice": 48_000, "convertedFinalPrice": 48_000},
            {"id": 22, "nmId": 201, "createdAt": "2026-07-24T09:00:00Z", "convertedPrice": 48_000, "convertedFinalPrice": 48_000},
            {"id": 23, "nmId": 202, "createdAt": "2026-07-24T10:00:00Z", "convertedPrice": 40_000, "convertedFinalPrice": 40_000},
        ]
    )
    store.upsert_current_prices(seller_id="seller_1", rows=prices)
    store.upsert_fbs_orders(seller_id="seller_1", rows=orders)

    result = build_price_analytics(
        seller_id="seller_1",
        operational_date="2026-07-24",
        store_rows=store.rows(seller_id="seller_1"),
        finance_rows=[],
    )

    assert result["reconciliation"] == {
        "sku_buyer_final_total": "1360.00",
        "fbs_orders_buyer_final_total": "1360.00",
        "difference": "0.00",
        "fbs_orders_count": 3,
        "fbs_orders_with_price_count": 3,
        "fallback_buyouts_count": "0",
        "buyer_total_source": "fbs_converted_final_price",
        "status": "matched",
    }


def test_sales_funnel_fallback_uses_discounted_price_and_weighted_discount(tmp_path) -> None:
    store = PriceSnapshotStore(tmp_path / "prices.sqlite3")
    store.upsert_current_prices(
        seller_id="seller_1",
        rows=normalize_goods_prices(
            [
                {
                    "nmID": 1001020,
                    "discount": 20,
                    "sizes": [{"sizeID": 1, "price": 2500, "discountedPrice": 2000}],
                },
                {
                    "nmID": 1001009,
                    "discount": 20,
                    "sizes": [{"sizeID": 1, "price": 2500, "discountedPrice": 2000}],
                },
            ],
            captured_at="2026-07-26T08:30:00Z",
        ),
    )

    result = build_price_analytics(
        seller_id="seller_1",
        operational_date="2026-07-26",
        store_rows=store.rows(seller_id="seller_1"),
        finance_rows=[],
        funnel_rows=[
            {
                "nm_id": "1001020",
                "date": "2026-07-26",
                "buyouts": 1,
                "buyout_sum": "999.97",
                "buyout_count_confirmed": True,
                "buyout_sum_confirmed": True,
            },
            {
                "nm_id": "1001009",
                "date": "2026-07-26",
                "buyouts": 1,
                "buyout_sum": "900.00",
                "buyout_count_confirmed": True,
                "buyout_sum_confirmed": True,
            },
        ],
    )
    rows = {row["nm_id"]: row for row in result["sku_rows"]}

    assert rows["1001020"]["seller_price"] == "2000.00"
    assert rows["1001020"]["seller_base_price"] == "2500.00"
    assert rows["1001020"]["buyer_final_price"] == "999.97"
    assert rows["1001020"]["platform_discount_percent"] == "50.00"
    assert rows["1001009"]["buyer_final_price"] == "900.00"
    assert rows["1001009"]["platform_discount_percent"] == "55.00"
    assert rows["1001009"]["buyer_price_source"] == "sales_funnel_fallback"
    assert result["weighted_platform_discount_percent"] == "52.50"
    assert result["status"] == {
        "seller_price": "available",
        "fbs_price_data": "unavailable",
        "buyer_price": "fallback/available",
    }


def test_fbs_price_has_priority_over_sales_funnel_fallback(tmp_path) -> None:
    store = PriceSnapshotStore(tmp_path / "prices.sqlite3")
    store.upsert_current_prices(
        seller_id="seller_1",
        rows=normalize_goods_prices(
            [
                {
                    "nmID": 1001020,
                    "discount": 0,
                    "sizes": [{"sizeID": 1, "price": 2000, "discountedPrice": 2000}],
                }
            ],
            captured_at="2026-07-25T08:00:00Z",
        ),
    )
    store.upsert_fbs_orders(
        seller_id="seller_1",
        rows=normalize_fbs_order_prices(
            [
                {
                    "id": 991,
                    "nmId": 1001020,
                    "createdAt": "2026-07-26T08:00:00Z",
                    "convertedPrice": 100_000,
                    "convertedFinalPrice": 95_000,
                }
            ]
        ),
    )

    result = build_price_analytics(
        seller_id="seller_1",
        operational_date="2026-07-26",
        store_rows=store.rows(seller_id="seller_1"),
        finance_rows=[],
        funnel_rows=[
            {
                "nm_id": "1001020",
                "date": "2026-07-26",
                "buyouts": 1,
                "buyout_sum": "999.97",
                "buyout_count_confirmed": True,
                "buyout_sum_confirmed": True,
            }
        ],
    )

    row = result["sku_rows"][0]
    assert row["buyer_price_before_wallet"] == "1000.00"
    assert row["buyer_final_price"] == "950.00"
    assert row["buyer_price_source"] == "fbs_converted_price"
    assert result["status"]["fbs_price_data"] == "available"


def test_confirmed_sales_rows_supply_fallback_when_fbs_pair_is_incomplete(tmp_path) -> None:
    store = PriceSnapshotStore(tmp_path / "prices.sqlite3")
    store.upsert_current_prices(
        seller_id="seller_1",
        rows=normalize_goods_prices(
            [
                {
                    "nmID": 1001020,
                    "discount": 20,
                    "sizes": [{"sizeID": 1, "price": 2500, "discountedPrice": 2000}],
                }
            ],
            captured_at="2026-07-26T08:30:00Z",
        ),
    )
    store.upsert_fbs_orders(
        seller_id="seller_1",
        rows=normalize_fbs_order_prices(
            [
                {
                    "id": 991,
                    "nmId": 1001020,
                    "createdAt": "2026-07-26T08:00:00Z",
                    "convertedPrice": 55_600,
                    "convertedFinalPrice": None,
                }
            ]
        ),
    )
    normalized = normalize_bundle(
        {
            "sales": {
                "rows_raw": [
                    {
                        "date": "2026-07-26T09:00:00+03:00",
                        "nmId": 1001020,
                        "srid": "sale-1",
                        "priceWithDisc": 999.97,
                    }
                ]
            }
        }
    )

    result = build_price_analytics(
        seller_id="seller_1",
        operational_date="2026-07-26",
        store_rows=store.rows(seller_id="seller_1"),
        finance_rows=[],
        sales_rows=normalized["sales_rows"],
    )

    row = result["sku_rows"][0]
    assert normalized["sales_rows"][0]["amount_confirmed"] is True
    assert row["buyer_price_before_wallet"] == "999.97"
    assert row["buyer_final_price"] == "999.97"
    assert row["buyer_price_source"] == "sales_funnel_fallback"
    assert result["status"]["fbs_price_data"] == "unavailable"
    assert result["status"]["buyer_price"] == "fallback/available"


def test_sales_fallback_does_not_use_later_seller_snapshot_for_discount(tmp_path) -> None:
    store = PriceSnapshotStore(tmp_path / "prices.sqlite3")
    store.upsert_current_prices(
        seller_id="seller_1",
        rows=normalize_goods_prices(
            [
                {
                    "nmID": 1001020,
                    "discount": 51,
                    "sizes": [{"sizeID": 1, "price": 2000, "discountedPrice": 980}],
                }
            ],
            captured_at="2026-07-27T08:30:00Z",
        ),
    )

    result = build_price_analytics(
        seller_id="seller_1",
        operational_date="2026-07-26",
        store_rows=store.rows(seller_id="seller_1"),
        finance_rows=[],
        sales_rows=[
            {
                "nm_id": "1001020",
                "date": "2026-07-26",
                "quantity": 1,
                "amount": "999.97",
                "quantity_confirmed": True,
                "amount_confirmed": True,
            }
        ],
    )

    row = result["sku_rows"][0]
    assert row["seller_price"] == "980.00"
    assert row["seller_snapshot_date"] is None
    assert row["buyer_final_price"] == "999.97"
    assert row["platform_discount_percent"] is None
    assert result["weighted_platform_discount_percent"] is None


def test_missing_previous_discounted_price_snapshot_keeps_change_missing(tmp_path) -> None:
    store = PriceSnapshotStore(tmp_path / "prices.sqlite3")
    store.upsert_current_prices(
        seller_id="seller_1",
        rows=normalize_goods_prices(
            [
                {
                    "nmID": 1001020,
                    "discount": 20,
                    "sizes": [{"sizeID": 1, "price": 2500, "discountedPrice": 2000}],
                }
            ],
            captured_at="2026-07-27T00:30:00Z",
        ),
    )

    result = build_price_analytics(
        seller_id="seller_1",
        operational_date="2026-07-26",
        store_rows=store.rows(seller_id="seller_1"),
        finance_rows=[],
    )

    assert result["sku_rows"][0]["seller_price_change_day"] is None


def test_reconciliation_without_order_prices_is_unavailable_not_zero(tmp_path) -> None:
    store = PriceSnapshotStore(tmp_path / "prices.sqlite3")
    store.upsert_fbs_orders(
        seller_id="seller_1",
        rows=normalize_fbs_order_prices(
            [
                {
                    "id": 26,
                    "nmId": 205,
                    "createdAt": "2026-07-24T08:00:00Z",
                    "convertedPrice": None,
                    "convertedFinalPrice": None,
                }
            ]
        ),
    )

    result = build_price_analytics(
        seller_id="seller_1",
        operational_date="2026-07-24",
        store_rows=store.rows(seller_id="seller_1"),
        finance_rows=[],
    )

    assert result["reconciliation"]["status"] == "unavailable"
    assert result["reconciliation"]["sku_buyer_final_total"] is None
    assert result["reconciliation"]["fbs_orders_buyer_final_total"] is None


def test_closed_sale_discount_reconciles_with_finance_component(tmp_path) -> None:
    store = PriceSnapshotStore(tmp_path / "prices.sqlite3")
    store.upsert_current_prices(
        seller_id="seller_1",
        rows=normalize_goods_prices(
            [
                {
                    "nmID": 203,
                    "discount": 0,
                    "sizes": [{"sizeID": 1, "price": 1000, "discountedPrice": 1000}],
                }
            ],
            captured_at="2026-07-23T08:00:00Z",
        ),
    )
    store.upsert_fbs_orders(
        seller_id="seller_1",
        rows=normalize_fbs_order_prices(
            [
                {
                    "id": 24,
                    "nmId": 203,
                    "createdAt": "2026-07-24T08:00:00Z",
                    "convertedPrice": 48_000,
                    "convertedFinalPrice": 48_000,
                }
            ]
        ),
    )

    result = build_price_analytics(
        seller_id="seller_1",
        operational_date="2026-07-24",
        store_rows=store.rows(seller_id="seller_1"),
        finance_rows=[
            {
                "nm_id": "203",
                "row_group": "sale",
                "platform_discount_percent_finance": "52.00",
            }
        ],
    )

    assert result["sku_rows"][0]["finance_discount_reference_percent"] == "52.00"
    assert result["sku_rows"][0]["finance_discount_reference_type"] == "platform_discount_percent"
    assert result["sku_rows"][0]["finance_discount_reconciliation"] == "matched"


def test_spp_finance_field_is_marked_as_component_not_whole_platform_discount(tmp_path) -> None:
    store = PriceSnapshotStore(tmp_path / "prices.sqlite3")
    store.upsert_current_prices(
        seller_id="seller_1",
        rows=normalize_goods_prices(
            [{"nmID": 204, "discount": 0, "sizes": [{"sizeID": 1, "price": 1000, "discountedPrice": 1000}]}],
            captured_at="2026-07-23T08:00:00Z",
        ),
    )
    store.upsert_fbs_orders(
        seller_id="seller_1",
        rows=normalize_fbs_order_prices(
            [{"id": 25, "nmId": 204, "createdAt": "2026-07-24T08:00:00Z", "convertedPrice": 48_000, "convertedFinalPrice": 48_000}]
        ),
    )

    result = build_price_analytics(
        seller_id="seller_1",
        operational_date="2026-07-24",
        store_rows=store.rows(seller_id="seller_1"),
        finance_rows=[{"nm_id": "204", "row_group": "sale", "spp_component_percent_finance": "52.00"}],
    )

    assert result["sku_rows"][0]["finance_discount_reference_type"] == "spp_component_ppvz_spp_prc"


def test_finance_normalization_does_not_rename_ppvz_spp_as_all_platform_discounts() -> None:
    normalized = normalize_bundle(
        {
            "finance_final": {
                "rows_raw": [
                    {
                        "rrDate": "2026-07-24",
                        "nmId": 204,
                        "docTypeName": "Продажа",
                        "quantity": 1,
                        "retailAmount": 480,
                        "ppvz_spp_prc": 52,
                    }
                ]
            }
        }
    )
    row = normalized["finance_final_rows"][0]

    assert row["spp_component_percent_finance"] == 52.0
    assert row["platform_discount_percent_finance"] is None


def test_migration_has_working_rollback(tmp_path) -> None:
    store = PriceSnapshotStore(tmp_path / "prices.sqlite3")
    store.migrate()
    with sqlite3.connect(store.path) as connection:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='product_price_snapshot'"
        ).fetchone()

    store.rollback()
    with sqlite3.connect(store.path) as connection:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='product_price_snapshot'"
        ).fetchone() is None


def test_goods_prices_loader_uses_v2_filter_and_pagination() -> None:
    class Client:
        prices_base_url = "https://discounts-prices-api.wildberries.ru"

        def __init__(self) -> None:
            self.calls = []

        def request_json(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "success": True,
                "payload": {"data": {"listGoods": [{"nmID": 301, "sizes": []}]}},
                "status_code": 200,
                "attempts": 1,
            }

    client = Client()
    result = load_product_prices(client, "2026-07-25T08:00:00+00:00")

    assert result["rows_raw"][0]["nmID"] == 301
    assert client.calls[0]["path"] == "/api/v2/list/goods/filter"
    assert client.calls[0]["params"] == {"limit": 1000, "offset": 0}
    assert client.calls[0]["base_url"] == client.prices_base_url


def test_fbs_loader_combines_new_and_period_orders_without_duplicates() -> None:
    class Client:
        marketplace_base_url = "https://marketplace-api.wildberries.ru"

        def __init__(self) -> None:
            self.calls = []

        def request_json(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs["path"].endswith("/new"):
                return {
                    "success": True,
                    "payload": {
                        "orders": [
                            {
                                "id": 401,
                                "nmId": 501,
                                "createdAt": "2026-07-24T08:00:00Z",
                                "convertedPrice": 48_000,
                                "convertedFinalPrice": 48_000,
                            }
                        ]
                    },
                    "status_code": 200,
                    "attempts": 1,
                }
            return {
                "success": True,
                "payload": {
                    "next": 402,
                    "orders": [
                        {
                            "id": 401,
                            "nmId": 501,
                            "createdAt": "2026-07-24T08:00:00Z",
                            "convertedPrice": 48_000,
                            "convertedFinalPrice": 48_000,
                        },
                        {
                            "id": 402,
                            "nmId": 502,
                            "createdAt": "2026-07-24T09:00:00Z",
                            "convertedPrice": 40_000,
                            "convertedFinalPrice": 40_000,
                        },
                    ],
                },
                "status_code": 200,
                "attempts": 1,
            }

    client = Client()
    result = load_fbs_order_prices(
        client,
        "2026-07-25T08:00:00+00:00",
        "2026-07-24",
    )

    assert {row["id"] for row in result["rows_raw"]} == {401, 402}
    assert client.calls[0]["path"] == "/api/v3/orders/new"
    assert client.calls[1]["path"] == "/api/v3/orders"
    assert client.calls[1]["params"]["limit"] == 1000
    assert client.calls[1]["params"]["next"] == 0
    assert client.calls[1]["params"]["dateFrom"] < client.calls[1]["params"]["dateTo"]
