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


if __name__ == "__main__":
    unittest.main()
