import unittest

from v3.daily_kpi_resolver import resolve_daily_kpi


class TestDailyKpiResolverRewrite(unittest.TestCase):
    def test_wb_api_orders_count_uses_only_orders_api(self) -> None:
        daily_kpi = resolve_daily_kpi(
            totals={},
            supplier_goods_daily={},
            api_orders_rows=[{"order_id": "o1"}, {"order_id": "o2"}, {"order_id": "o3"}],
            api_sales_rows=[{"sale_id": "s1"}, {"sale_id": "s2"}],
            api_realization_rows=[],
            source_mode="wb_api",
        )
        self.assertEqual(int(daily_kpi.get("daily_orders_count", 0) or 0), 3)
        self.assertEqual(str(daily_kpi.get("data_source_orders_count") or ""), "orders_api")
        self.assertTrue(bool(daily_kpi.get("orders_count_confirmed", False)))

    def test_wb_api_orders_amount_does_not_use_sales_api(self) -> None:
        daily_kpi = resolve_daily_kpi(
            totals={},
            supplier_goods_daily={},
            api_orders_rows=[{"order_id": "o1"}, {"order_id": "o2"}],
            api_sales_rows=[{"sale_id": "s1", "price": 1200.0}],
            api_realization_rows=[],
            source_mode="wb_api",
        )
        self.assertEqual(str(daily_kpi.get("data_source_orders_amount") or ""), "unknown")
        self.assertFalse(bool(daily_kpi.get("orders_amount_confirmed", False)))
        self.assertAlmostEqual(float(daily_kpi.get("daily_orders_amount", 0.0) or 0.0), 0.0, places=2)

    def test_wb_api_buyouts_count_uses_sales_or_realization(self) -> None:
        sales_only = resolve_daily_kpi(
            totals={},
            supplier_goods_daily={},
            api_orders_rows=[{"order_id": "o1"}],
            api_sales_rows=[{"sale_id": "s1"}, {"sale_id": "s2"}],
            api_realization_rows=[],
            source_mode="wb_api",
        )
        self.assertEqual(int(sales_only.get("daily_buyouts_count", 0) or 0), 2)
        self.assertEqual(str(sales_only.get("data_source_buyouts_count") or ""), "sales_api")

        realization_only = resolve_daily_kpi(
            totals={},
            supplier_goods_daily={},
            api_orders_rows=[{"order_id": "o1"}],
            api_sales_rows=[],
            api_realization_rows=[{"rrd": 1}, {"rrd": 2}, {"rrd": 3}],
            source_mode="wb_api",
        )
        self.assertEqual(int(realization_only.get("daily_buyouts_count", 0) or 0), 3)
        self.assertEqual(str(realization_only.get("data_source_buyouts_count") or ""), "realization_api")

    def test_wb_api_supplier_goods_is_blocked(self) -> None:
        daily_kpi = resolve_daily_kpi(
            totals={},
            supplier_goods_daily={
                "found": True,
                "orders_count": 100,
                "buyouts_count": 80,
                "orders_amount": 12345.0,
                "buyouts_amount": 10000.0,
                "orders_count_confirmed": True,
                "buyouts_count_confirmed": True,
                "amounts_confirmed": True,
            },
            api_orders_rows=[{"order_id": "o1", "price": 100.0}],
            api_sales_rows=[{"sale_id": "s1", "price": 80.0}],
            api_realization_rows=[],
            source_mode="wb_api",
        )
        self.assertNotEqual(str(daily_kpi.get("data_source_orders_count") or ""), "supplier_goods")
        self.assertNotEqual(str(daily_kpi.get("data_source_buyouts_count") or ""), "supplier_goods")
        self.assertTrue(bool(daily_kpi.get("supplier_goods_ignored_in_wb_api", False)))

    def test_wb_api_totals_hint_is_debug_only(self) -> None:
        daily_kpi = resolve_daily_kpi(
            totals={
                "sales_activity_qty": 17,
                "orders": 17,
                "buys": 9,
                "orders_amount": 9999.0,
                "buyouts_amount": 7777.0,
            },
            supplier_goods_daily={},
            api_orders_rows=[],
            api_sales_rows=[],
            api_realization_rows=[],
            source_mode="wb_api",
        )
        self.assertEqual(str(daily_kpi.get("data_source_orders_count") or ""), "unknown")
        self.assertEqual(str(daily_kpi.get("data_source_buyouts_count") or ""), "unknown")
        self.assertEqual(str(daily_kpi.get("data_source_orders_amount") or ""), "unknown")
        self.assertEqual(str(daily_kpi.get("data_source_buyouts_amount") or ""), "unknown")
        self.assertFalse(bool(daily_kpi.get("orders_count_confirmed", False)))
        self.assertFalse(bool(daily_kpi.get("buyouts_count_confirmed", False)))

    def test_trace_contains_rejected_candidates(self) -> None:
        daily_kpi = resolve_daily_kpi(
            totals={"sales_activity_qty": 5},
            supplier_goods_daily={
                "found": True,
                "orders_count": 12,
                "orders_count_confirmed": True,
                "orders_amount": 999.0,
                "amounts_confirmed": True,
            },
            api_orders_rows=[],
            api_sales_rows=[{"sale_id": "s1", "price": 500.0}],
            api_realization_rows=[],
            source_mode="wb_api",
        )
        trace = daily_kpi.get("trace_daily_orders_count", {})
        rejected = trace.get("rejected_candidates", []) if isinstance(trace, dict) else []
        reasons = {str(row.get("reason") or "") for row in rejected if isinstance(row, dict)}
        self.assertIn("entity_mismatch", reasons)
        self.assertIn("blocked_by_source_policy", reasons)
        self.assertIn("totals_hint_debug_only", reasons)

    def test_parity_fixture_matches_expected_day(self) -> None:
        daily_kpi = resolve_daily_kpi(
            totals={},
            supplier_goods_daily={},
            api_orders_rows=[
                {"order_id": "o1", "totalPrice": 1000.0},
                {"order_id": "o2", "totalPrice": 1200.0},
                {"order_id": "o3", "totalPrice": 1199.91},
            ],
            api_sales_rows=[
                {"sale_id": "s1", "priceWithDisc": 800.0},
                {"sale_id": "s2", "priceWithDisc": 900.0},
                {"sale_id": "s3", "priceWithDisc": 880.0},
            ],
            api_realization_rows=[],
            source_mode="wb_api",
        )
        self.assertEqual(int(daily_kpi.get("daily_orders_count", 0) or 0), 3)
        self.assertAlmostEqual(float(daily_kpi.get("daily_orders_amount", 0.0) or 0.0), 3399.91, places=2)
        self.assertEqual(int(daily_kpi.get("daily_buyouts_count", 0) or 0), 3)
        self.assertAlmostEqual(float(daily_kpi.get("daily_buyouts_amount", 0.0) or 0.0), 2580.0, places=2)
        self.assertEqual(str(daily_kpi.get("data_source_orders_count") or ""), "orders_api")
        self.assertEqual(str(daily_kpi.get("data_source_orders_amount") or ""), "orders_api")
        self.assertEqual(str(daily_kpi.get("data_source_buyouts_count") or ""), "sales_api")
        self.assertEqual(str(daily_kpi.get("data_source_buyouts_amount") or ""), "sales_api")

    def test_uses_operational_date_for_api_rows_filtering(self) -> None:
        daily_kpi = resolve_daily_kpi(
            totals={},
            supplier_goods_daily={},
            api_orders_rows=[
                {"order_id": "o-prev", "date": "2026-04-13T10:00:00", "totalPrice": 777.0},
                {"order_id": "o1", "date": "2026-04-14T10:00:00", "totalPrice": 1000.0},
                {"order_id": "o2", "date": "2026-04-14T11:00:00", "totalPrice": 1200.0},
                {"order_id": "o3", "date": "2026-04-14T12:00:00", "totalPrice": 1199.91},
            ],
            api_sales_rows=[
                {"sale_id": "s-prev", "date": "2026-04-13T10:00:00", "priceWithDisc": 111.0},
                {"sale_id": "s1", "date": "2026-04-14T10:00:00", "priceWithDisc": 800.0},
                {"sale_id": "s2", "date": "2026-04-14T11:00:00", "priceWithDisc": 900.0},
                {"sale_id": "s3", "date": "2026-04-14T12:00:00", "priceWithDisc": 880.0},
            ],
            api_realization_rows=[],
            source_mode="wb_api",
            event_date_model={"report_date": "2026-04-15", "operational_date": "2026-04-14"},
        )
        self.assertEqual(int(daily_kpi.get("daily_orders_count", 0) or 0), 3)
        self.assertAlmostEqual(float(daily_kpi.get("daily_orders_amount", 0.0) or 0.0), 3399.91, places=2)
        self.assertEqual(int(daily_kpi.get("daily_buyouts_count", 0) or 0), 3)
        self.assertAlmostEqual(float(daily_kpi.get("daily_buyouts_amount", 0.0) or 0.0), 2580.0, places=2)


if __name__ == "__main__":
    unittest.main()
