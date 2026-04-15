import unittest

from v3.metrics.sales_funnel_assembler import assemble_sales_funnel


class TestSalesFunnelAssembler(unittest.TestCase):
    def test_unknown_sources_do_not_emit_fake_zero_conversions(self) -> None:
        payload = assemble_sales_funnel(
            run_date="2026-03-04",
            metrics={
                "totals": {"views": 1000, "orders": 0, "buys": 0},
                "data_sources": {"orders_count": "unknown", "buyouts_count": "unknown", "ads_spend": "unknown"},
                "daily_kpi": {},
                "commerce_kpi": {},
                "financial_kpi": {},
            },
            ads_diagnostics={},
        )

        funnel = payload.get("funnel", {}) if isinstance(payload, dict) else {}
        self.assertIsNone(funnel.get("view_to_order_conversion"))
        self.assertIsNone(funnel.get("order_to_buyout_conversion_pct"))

    def test_known_sources_enable_conversion_when_confirmed_counts_missing(self) -> None:
        payload = assemble_sales_funnel(
            run_date="2026-03-04",
            metrics={
                "totals": {"views": 1000, "orders": 50, "buys": 20},
                "data_sources": {"orders_count": "api.orders", "buyouts_count": "api.sales", "ads_spend": "unknown"},
                "daily_kpi": {},
                "commerce_kpi": {},
                "financial_kpi": {},
            },
            ads_diagnostics={},
        )

        funnel = payload.get("funnel", {}) if isinstance(payload, dict) else {}
        self.assertEqual(funnel.get("view_to_order_conversion"), 5.0)
        self.assertEqual(funnel.get("order_to_buyout_conversion_pct"), 40.0)


    def test_over_100_order_to_buyout_is_marked_with_note(self) -> None:
        payload = assemble_sales_funnel(
            run_date="2026-03-04",
            metrics={
                "totals": {"views": 1000, "orders": 6, "buys": 7},
                "data_sources": {"orders_count": "api.orders", "buyouts_count": "api.sales", "ads_spend": "unknown"},
                "daily_kpi": {},
                "commerce_kpi": {},
                "financial_kpi": {},
            },
            ads_diagnostics={},
        )

        funnel = payload.get("funnel", {}) if isinstance(payload, dict) else {}
        status = payload.get("status", {}) if isinstance(payload, dict) else {}
        self.assertTrue(bool(funnel.get("order_to_buyout_over_100", False)))
        self.assertTrue(bool(str(funnel.get("order_to_buyout_note") or "").strip()))
        self.assertEqual(str(status.get("buyout_stage") or ""), "partial")

    def test_upper_missing_with_lower_present_marks_partial_and_keeps_nulls(self) -> None:
        payload = assemble_sales_funnel(
            run_date="2026-04-14",
            metrics={
                "totals": {"orders": 3, "buys": 3},
                "data_sources": {
                    "orders_count": "api.orders",
                    "buyouts_count": "api.sales",
                    "views": "api.traffic",
                    "add_to_cart": "api.traffic",
                    "ads_spend": "unknown",
                },
                "data_quality": {
                    "funnel_upper_available": False,
                    "funnel_upper_unavailable_from_api": True,
                    "funnel_contract_source": "api_contract",
                },
                "daily_kpi": {},
                "commerce_kpi": {},
                "financial_kpi": {},
            },
            ads_diagnostics={},
        )

        funnel = payload.get("funnel", {}) if isinstance(payload, dict) else {}
        funnel_status = payload.get("funnel_status", {}) if isinstance(payload, dict) else {}
        self.assertIsNone(funnel.get("views"))
        self.assertIsNone(funnel.get("impressions"))
        self.assertIsNone(funnel.get("clicks"))
        self.assertIsNone(funnel.get("add_to_cart"))
        self.assertEqual(funnel.get("orders"), 3)
        self.assertEqual(funnel.get("buyouts"), 3)
        self.assertEqual(str(funnel_status.get("overall") or ""), "partial")
        self.assertEqual(funnel.get("order_to_buyout_conversion_pct"), 100.0)
        self.assertIsNone(funnel.get("view_to_order_conversion"))

    def test_upper_confirmed_zero_is_not_missing(self) -> None:
        payload = assemble_sales_funnel(
            run_date="2026-04-14",
            metrics={
                "totals": {
                    "orders": 2,
                    "buys": 1,
                    "add_to_cart": 0,
                    "ads_impressions": 0,
                    "ads_clicks": 0,
                },
                "data_sources": {
                    "orders_count": "api.orders",
                    "buyouts_count": "api.sales",
                    "views": "api.traffic",
                    "add_to_cart": "api.traffic",
                    "ads_spend": "unknown",
                },
                "data_quality": {
                    "funnel_upper_available": True,
                    "funnel_upper_unavailable_from_api": False,
                    "funnel_contract_source": "api_contract",
                },
                "daily_kpi": {},
                "commerce_kpi": {},
                "financial_kpi": {},
            },
            ads_diagnostics={"selected_totals": {"ads_impressions": 0, "ads_clicks": 0}},
        )

        funnel = payload.get("funnel", {}) if isinstance(payload, dict) else {}
        self.assertEqual(funnel.get("views"), 0)
        self.assertEqual(funnel.get("impressions"), 0)
        self.assertEqual(funnel.get("clicks"), 0)
        self.assertEqual(funnel.get("add_to_cart"), 0)
        self.assertEqual(str(funnel.get("views_status") or ""), "confirmed_zero")
        self.assertEqual(str(funnel.get("impressions_status") or ""), "confirmed_zero")
        self.assertEqual(str(funnel.get("clicks_status") or ""), "confirmed_zero")
        self.assertEqual(str(funnel.get("add_to_cart_status") or ""), "confirmed_zero")

    def test_full_funnel_computes_all_supported_conversions(self) -> None:
        payload = assemble_sales_funnel(
            run_date="2026-04-14",
            metrics={
                "totals": {
                    "views": 1000,
                    "add_to_cart": 100,
                    "orders": 20,
                    "buys": 10,
                    "ads_impressions": 900,
                    "ads_clicks": 180,
                },
                "data_sources": {
                    "orders_count": "api.orders",
                    "buyouts_count": "api.sales",
                    "views": "api.traffic",
                    "add_to_cart": "api.traffic",
                    "ads_spend": "unknown",
                },
                "data_quality": {
                    "funnel_upper_available": True,
                    "funnel_upper_unavailable_from_api": False,
                    "funnel_contract_source": "api_contract",
                },
                "daily_kpi": {},
                "commerce_kpi": {},
                "financial_kpi": {},
            },
            ads_diagnostics={},
        )

        funnel = payload.get("funnel", {}) if isinstance(payload, dict) else {}
        funnel_status = payload.get("funnel_status", {}) if isinstance(payload, dict) else {}
        self.assertEqual(str(funnel_status.get("overall") or ""), "full")
        self.assertEqual(funnel.get("view_to_order_conversion"), 2.0)
        self.assertEqual(funnel.get("cart_to_order"), 20.0)
        self.assertEqual(funnel.get("order_to_buyout_conversion_pct"), 50.0)
        self.assertEqual(funnel.get("ctr"), 20.0)

    def test_no_funnel_data_produces_missing_overall_and_no_fake_conversions(self) -> None:
        payload = assemble_sales_funnel(
            run_date="2026-04-14",
            metrics={
                "totals": {},
                "data_sources": {
                    "orders_count": "unknown",
                    "buyouts_count": "unknown",
                    "views": "unknown",
                    "add_to_cart": "unknown",
                    "ads_spend": "unknown",
                },
                "daily_kpi": {},
                "commerce_kpi": {},
                "financial_kpi": {},
            },
            ads_diagnostics={},
        )

        funnel = payload.get("funnel", {}) if isinstance(payload, dict) else {}
        funnel_status = payload.get("funnel_status", {}) if isinstance(payload, dict) else {}
        self.assertEqual(str(funnel_status.get("overall") or ""), "missing")
        self.assertIsNone(funnel.get("view_to_order_conversion"))
        self.assertIsNone(funnel.get("cart_to_order"))
        self.assertIsNone(funnel.get("order_to_buyout_conversion_pct"))
        self.assertIsNone(funnel.get("ctr"))


if __name__ == "__main__":
    unittest.main()
