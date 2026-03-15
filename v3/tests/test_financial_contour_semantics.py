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
                "data_source_orders_amount": "sales_api",
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
            order_kpi={"orders_count_confirmed": True, "orders_amount_confirmed": True, "source_count": "orders_api", "source_amount": "sales_api"},
            buyout_kpi={"buyouts_count_confirmed": True, "buyouts_amount_confirmed": True, "source_count": "sales_api", "source_amount": "sales_api"},
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

    def test_commerce_kpi_keeps_sales_api_buyout_confirmation(self) -> None:
        daily_kpi = resolve_daily_kpi(
            totals={},
            supplier_goods_daily={},
            api_orders_rows=[{"order_id": 1}, {"order_id": 2}, {"order_id": 3}, {"order_id": 4}],
            api_sales_rows=[{"price": 458.42}],
            api_realization_rows=[],
        )
        self.assertEqual(int(daily_kpi.get("daily_orders_count", 0) or 0), 4)
        self.assertEqual(int(daily_kpi.get("daily_buyouts_count", 0) or 0), 1)
        self.assertTrue(bool(daily_kpi.get("buyouts_amount_confirmed", False)))
        self.assertAlmostEqual(float(daily_kpi.get("daily_buyouts_amount", 0.0) or 0.0), 458.42, places=2)


if __name__ == "__main__":
    unittest.main()
