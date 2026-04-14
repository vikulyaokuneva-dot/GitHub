import unittest

from v3.daily_kpi_resolver import resolve_daily_kpi
from v3.domain.event_model import STATUS_NOT_CONFIRMED, build_daily_status_matrix
from v3.domain.source_policy import SOURCE_UNKNOWN, resolve_source_policy


class TestFinancialContourSemantics(unittest.TestCase):
    def test_sales_api_does_not_confirm_financial_source(self) -> None:
        policy = resolve_source_policy(
            source_mode="wb_api",
            daily_kpi={
                "data_source_orders_count": "orders_api",
                "data_source_buyouts_count": "sales_api",
                "data_source_orders_amount": "unknown",
                "data_source_buyouts_amount": "sales_api",
            },
            financial_kpi={"revenue": 458.42, "is_partial": True},
            supplier_goods_daily={"found": False},
            api_debug={
                "sales_rows": 1,
                "realization_rows": 0,
                "financial_rows": 0,
                "local_financial_fallback_used": False,
                "endpoints": [
                    {"endpoint": "sales", "success": True, "rows_loaded": 1},
                ],
            },
            input_debug={"discovered": {"sales": [], "ads": [], "stocks": [], "unknown": []}},
            ads_loaded_from_file=False,
            ads_rows_count=0,
        )
        self.assertEqual(str(policy.get("sources", {}).get("revenue") or ""), SOURCE_UNKNOWN)

    def test_financial_status_is_not_confirmed_when_contour_unavailable(self) -> None:
        status = build_daily_status_matrix(
            order_kpi={
                "orders_count_confirmed": True,
                "orders_amount_confirmed": False,
                "source_count": "orders_api",
                "source_amount": "unknown",
            },
            buyout_kpi={
                "buyouts_count_confirmed": True,
                "buyouts_amount_confirmed": True,
                "source_count": "sales_api",
                "source_amount": "sales_api",
            },
            financial_kpi={
                "confirmed": False,
                "is_partial": True,
                "revenue": None,
                "financial_finality_status": "unavailable",
            },
            ads_summary={},
            data_quality={},
        )
        self.assertEqual(str(status.get("financials") or ""), STATUS_NOT_CONFIRMED)

    def test_orders_metrics_do_not_use_sales_entity(self) -> None:
        daily_kpi = resolve_daily_kpi(
            totals={},
            supplier_goods_daily={},
            api_orders_rows=[{"order_id": 1}, {"order_id": 2}, {"order_id": 3}],
            api_sales_rows=[{"sale_id": 1, "price": 500.0}, {"sale_id": 2, "price": 700.0}],
            api_realization_rows=[],
            source_mode="wb_api",
        )
        self.assertEqual(int(daily_kpi.get("daily_orders_count", 0) or 0), 3)
        self.assertEqual(str(daily_kpi.get("data_source_orders_count") or ""), "orders_api")
        self.assertEqual(str(daily_kpi.get("data_source_orders_amount") or ""), "unknown")
        self.assertFalse(bool(daily_kpi.get("orders_amount_confirmed", False)))
        self.assertAlmostEqual(float(daily_kpi.get("daily_orders_amount", 0.0) or 0.0), 0.0, places=2)
        trace = daily_kpi.get("trace_daily_orders_amount", {})
        rejected = trace.get("rejected_candidates", []) if isinstance(trace, dict) else []
        self.assertTrue(any(str(row.get("reason") or "") == "entity_mismatch" for row in rejected if isinstance(row, dict)))

    def test_buyouts_metrics_do_not_use_orders_entity(self) -> None:
        daily_kpi = resolve_daily_kpi(
            totals={},
            supplier_goods_daily={},
            api_orders_rows=[{"order_id": 1, "price": 1000.0}, {"order_id": 2, "price": 500.0}],
            api_sales_rows=[],
            api_realization_rows=[],
            source_mode="wb_api",
        )
        self.assertEqual(str(daily_kpi.get("data_source_buyouts_count") or ""), "unknown")
        self.assertEqual(str(daily_kpi.get("data_source_buyouts_amount") or ""), "unknown")
        self.assertFalse(bool(daily_kpi.get("buyouts_count_confirmed", False)))
        self.assertFalse(bool(daily_kpi.get("buyouts_amount_confirmed", False)))
        trace = daily_kpi.get("trace_daily_buyouts_count", {})
        rejected = trace.get("rejected_candidates", []) if isinstance(trace, dict) else []
        self.assertTrue(any(str(row.get("reason") or "") == "entity_mismatch" for row in rejected if isinstance(row, dict)))

    def test_metrics_totals_hints_are_not_confirmed_in_wb_api(self) -> None:
        daily_kpi = resolve_daily_kpi(
            totals={"sales_activity_qty": 12, "orders": 12, "buys": 11},
            supplier_goods_daily={},
            api_orders_rows=[],
            api_sales_rows=[],
            api_realization_rows=[],
            source_mode="wb_api",
        )
        self.assertEqual(str(daily_kpi.get("data_source_orders_count") or ""), "unknown")
        self.assertEqual(str(daily_kpi.get("data_source_buyouts_count") or ""), "unknown")
        self.assertFalse(bool(daily_kpi.get("orders_count_confirmed", False)))
        self.assertFalse(bool(daily_kpi.get("buyouts_count_confirmed", False)))
        self.assertTrue(bool(daily_kpi.get("quantity_fallback_blocked", False)))
        self.assertIn("totals_hint_debug_only", str(daily_kpi.get("orders_count_unknown_reason") or ""))
        self.assertIn("totals_hint_debug_only", str(daily_kpi.get("buyouts_count_unknown_reason") or ""))

    def test_wb_api_blocks_supplier_goods_as_confirmed_source(self) -> None:
        daily_kpi = resolve_daily_kpi(
            totals={},
            supplier_goods_daily={
                "found": True,
                "source_file": "supplier.xlsx",
                "orders_count": 999,
                "orders_amount": 99999.0,
                "buyouts_count": 888,
                "buyouts_amount": 88888.0,
                "orders_count_confirmed": True,
                "buyouts_count_confirmed": True,
                "amounts_confirmed": True,
            },
            api_orders_rows=[{"order_id": 1, "price": 100.0}, {"order_id": 2, "price": 200.0}],
            api_sales_rows=[{"sale_id": 1, "price": 150.0}],
            api_realization_rows=[],
            source_mode="wb_api",
        )
        self.assertEqual(str(daily_kpi.get("data_source_orders_count") or ""), "orders_api")
        self.assertEqual(str(daily_kpi.get("data_source_orders_amount") or ""), "orders_api")
        self.assertEqual(str(daily_kpi.get("data_source_buyouts_count") or ""), "sales_api")
        self.assertEqual(str(daily_kpi.get("data_source_buyouts_amount") or ""), "sales_api")
        self.assertTrue(bool(daily_kpi.get("supplier_goods_ignored_in_wb_api", False)))


if __name__ == "__main__":
    unittest.main()

