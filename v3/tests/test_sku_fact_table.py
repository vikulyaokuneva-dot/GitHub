from __future__ import annotations

from v3.metrics import build_sku_fact_table


def _only_row(payload: dict) -> dict:
    rows = payload["sku_metrics"]
    assert len(rows) == 1
    return rows[0]


def test_sku_fact_table_creates_sku_from_orders_rows() -> None:
    payload = build_sku_fact_table(
        orders_rows=[
            {
                "nm_id": "1001",
                "seller_sku": "SKU-1001",
                "name": "Test item",
                "quantity": 2,
                "amount": 1760.0,
            }
        ]
    )

    row = _only_row(payload)

    assert row["sku"] == "SKU-1001"
    assert row["vendor_code"] == "SKU-1001"
    assert row["nm_id"] == "1001"
    assert row["name"] == "Test item"
    assert row["orders_qty"] == 2.0
    assert row["orders_revenue"] == 1760.0
    assert row["source_flags"]["orders"] is True
    assert payload["source_flags"]["orders"] is True


def test_sku_fact_table_enriches_sku_from_sales_rows_by_nm_id() -> None:
    payload = build_sku_fact_table(
        orders_rows=[{"nm_id": "1001", "seller_sku": "SKU-1001", "quantity": 2, "amount": 1760.0}],
        sales_rows=[{"nmId": "1001", "supplierArticle": "SKU-1001", "quantity": 1, "amount": 554.0}],
    )

    row = _only_row(payload)

    assert row["orders_qty"] == 2.0
    assert row["sales_qty"] == 1.0
    assert row["sales_revenue"] == 554.0
    assert row["source_flags"]["orders"] is True
    assert row["source_flags"]["sales"] is True


def test_sku_fact_table_enriches_sku_from_stocks_rows() -> None:
    payload = build_sku_fact_table(
        orders_rows=[{"nm_id": "1001", "seller_sku": "SKU-1001", "quantity": 2}],
        stocks_rows=[
            {
                "nmId": "1001",
                "supplierArticle": "SKU-1001",
                "quantityFull": 149,
                "lastChangeDate": "2026-04-30T01:02:03",
            }
        ],
    )

    row = _only_row(payload)

    assert row["stock_qty_live"] == 149.0
    assert row["stock_snapshot_date"] == "2026-04-30"
    assert row["stock_wb_qty"] is None
    assert row["stock_mp_qty"] is None
    assert row["source_flags"]["stocks"] is True


def test_sku_fact_table_enriches_sku_from_finance_rows() -> None:
    payload = build_sku_fact_table(
        orders_rows=[{"nm_id": "1001", "seller_sku": "SKU-1001"}],
        finance_rows=[
            {
                "nm_id": "1001",
                "seller_sku": "SKU-1001",
                "row_group": "sale",
                "realized_sales_qty": 1,
                "realized_sales_revenue": 554.0,
            }
        ],
    )

    row = _only_row(payload)

    assert row["realized_sales_qty"] == 1.0
    assert row["realized_revenue"] == 554.0
    assert row["revenue"] == 554.0
    assert row["source_flags"]["finance"] is True


def test_sku_fact_table_keeps_missing_fields_as_none_without_zero_fill() -> None:
    payload = build_sku_fact_table(orders_rows=[{"nm_id": "1001", "seller_sku": "SKU-1001"}])

    row = _only_row(payload)

    assert row["orders_qty"] is None
    assert row["orders_revenue"] is None
    assert row["sales_qty"] is None
    assert row["realized_sales_qty"] is None
    assert row["realized_revenue"] is None
    assert row["stock_qty_live"] is None
    assert row["stock_wb_qty"] is None
    assert row["stock_mp_qty"] is None
    assert row["stock_value"] is None
    assert "revenue" not in row


def test_sku_fact_table_preserves_explicit_zero_values() -> None:
    payload = build_sku_fact_table(orders_rows=[{"nm_id": "1001", "seller_sku": "SKU-1001", "quantity": 0, "amount": 0}])

    row = _only_row(payload)

    assert row["orders_qty"] == 0.0
    assert row["orders_revenue"] == 0.0
    assert row["revenue"] == 0.0


def test_sku_fact_table_merges_by_nm_id_even_when_vendor_code_differs() -> None:
    payload = build_sku_fact_table(
        orders_rows=[{"nm_id": "1001", "seller_sku": "OLD-SKU", "quantity": 2}],
        stocks_rows=[{"nmId": "1001", "supplierArticle": "NEW-SKU", "quantityFull": 5}],
    )

    row = _only_row(payload)

    assert row["nm_id"] == "1001"
    assert row["vendor_code"] == "OLD-SKU"
    assert row["orders_qty"] == 2.0
    assert row["stock_qty_live"] == 5.0


def test_sku_fact_table_fallback_merges_by_vendor_code_without_nm_id() -> None:
    payload = build_sku_fact_table(
        orders_rows=[{"supplierArticle": "SKU-FALLBACK", "quantity": 2, "amount": 300.0}],
        stocks_rows=[{"vendorCode": "SKU-FALLBACK", "quantityFull": 7}],
        supplier_goods_rows=[
            {
                "vendor_code": "SKU-FALLBACK",
                "stock_wb_qty": 465,
                "stock_mp_qty": 259,
                "stock_value": 1079217.0,
            }
        ],
    )

    row = _only_row(payload)

    assert row["sku"] == "SKU-FALLBACK"
    assert row["vendor_code"] == "SKU-FALLBACK"
    assert row["orders_qty"] == 2.0
    assert row["stock_qty_live"] == 7.0
    assert row["stock_wb_qty"] == 465.0
    assert row["stock_mp_qty"] == 259.0
    assert row["stock_total_qty"] == 724.0
    assert row["stock_value"] == 1079217.0
    assert row["source_flags"]["supplier_goods"] is True
