import unittest

from v3.analytics.advertising_efficiency import build_advertising_efficiency


class TestAdvertisingEfficiency(unittest.TestCase):
    def _build_payload(self, *, metrics, ads_rows, daily_kpi, keyword_monitoring=None):
        return build_advertising_efficiency(
            metrics=metrics,
            ads_rows=ads_rows,
            keyword_monitoring=keyword_monitoring or {},
            daily_kpi=daily_kpi,
            seller_id="seller_test",
            run_date="2026-03-15",
            config={},
        )

    def test_romi_and_drr_calculation(self) -> None:
        payload = self._build_payload(
            metrics={
                "sku_metrics": [
                    {
                        "sku": "SKU1",
                        "orders": 20,
                        "buys": 10,
                        "revenue": 1000.0,
                        "cost_price": 400.0,
                    }
                ]
            },
            ads_rows=[
                {
                    "sku": "SKU1",
                    "ads_spend": 100.0,
                    "impressions": 1000,
                    "clicks": 120,
                    "orders": 10,
                    "query": "q-win",
                }
            ],
            daily_kpi={"orders_count_confirmed": True, "buyouts_count_confirmed": True},
        )

        summary = payload.get("summary", {})
        self.assertEqual(str(payload.get("analysis_mode")), "full")
        self.assertAlmostEqual(float(summary.get("portfolio_ad_spend", 0.0) or 0.0), 100.0, places=6)
        self.assertAlmostEqual(float(summary.get("portfolio_revenue_from_ads", 0.0) or 0.0), 500.0, places=6)
        self.assertAlmostEqual(float(summary.get("portfolio_profit_from_ads", 0.0) or 0.0), 200.0, places=6)
        self.assertAlmostEqual(float(summary.get("portfolio_ROMI", 0.0) or 0.0), 200.0, places=6)
        self.assertAlmostEqual(float(summary.get("portfolio_DRR", 0.0) or 0.0), 20.0, places=6)

    def test_order_vs_buyout_attribution_bridge(self) -> None:
        payload = self._build_payload(
            metrics={
                "sku_metrics": [
                    {
                        "sku": "SKU1",
                        "orders": 20,
                        "buys": 10,
                        "revenue": 1000.0,
                        "cost_price": 400.0,
                    }
                ]
            },
            ads_rows=[
                {
                    "sku": "SKU1",
                    "ads_spend": 80.0,
                    "impressions": 600,
                    "clicks": 60,
                    "orders": 8,
                    "query": "q-bridge",
                }
            ],
            daily_kpi={"orders_count_confirmed": True, "buyouts_count_confirmed": False},
        )

        sku_rows = payload.get("sku_performance", [])
        self.assertTrue(isinstance(sku_rows, list) and sku_rows)
        row = sku_rows[0]

        self.assertEqual(str(payload.get("analysis_mode")), "preview")
        self.assertAlmostEqual(float(row.get("order_to_buyout_rate", 0.0) or 0.0), 0.5, places=6)
        self.assertAlmostEqual(float(row.get("estimated_buyout_revenue_from_ads", 0.0) or 0.0), 200.0, places=6)

    def test_query_classification(self) -> None:
        payload = self._build_payload(
            metrics={
                "sku_metrics": [
                    {"sku": "SKU1", "orders": 20, "buys": 12, "revenue": 1200.0, "cost_price": 480.0},
                ]
            },
            ads_rows=[
                {"sku": "SKU1", "query": "winner", "ads_spend": 30.0, "impressions": 500, "clicks": 50, "orders": 6},
                {"sku": "SKU1", "query": "leak", "ads_spend": 700.0, "impressions": 1000, "clicks": 100, "orders": 0},
            ],
            daily_kpi={"orders_count_confirmed": True, "buyouts_count_confirmed": True},
        )

        rows = payload.get("query_performance", [])
        classes = {str(row.get("query")): str(row.get("classification")) for row in rows if isinstance(row, dict)}

        self.assertEqual(classes.get("winner"), "profitable")
        self.assertEqual(classes.get("leak"), "unprofitable")

    def test_graceful_degradation_when_ads_missing(self) -> None:
        payload = self._build_payload(
            metrics={"sku_metrics": [{"sku": "SKU1", "orders": 10, "buys": 5, "revenue": 500.0}]},
            ads_rows=[],
            daily_kpi={"orders_count_confirmed": True, "buyouts_count_confirmed": True},
        )

        self.assertEqual(str(payload.get("analysis_mode") or ""), "disabled")
        self.assertEqual(str(payload.get("status") or ""), "disabled")
        self.assertEqual(int(payload.get("query_profitability", {}).get("summary", {}).get("query_count", 0) or 0), 0)

    def test_signal_emission_logic(self) -> None:
        payload = self._build_payload(
            metrics={
                "sku_metrics": [
                    {"sku": "SKU1", "orders": 25, "buys": 15, "revenue": 2000.0, "cost_price": 900.0},
                ]
            },
            ads_rows=[
                {"sku": "SKU1", "query": "profit_q", "ads_spend": 40.0, "impressions": 700, "clicks": 70, "orders": 7},
                {"sku": "SKU1", "query": "leak_q", "ads_spend": 1500.0, "impressions": 900, "clicks": 90, "orders": 0},
            ],
            daily_kpi={"orders_count_confirmed": True, "buyouts_count_confirmed": True},
        )

        signal_types = {
            str(row.get("type") or "")
            for row in (payload.get("signals", []) if isinstance(payload.get("signals"), list) else [])
            if isinstance(row, dict)
        }
        self.assertIn("ads_profitable_query", signal_types)
        self.assertIn("ads_unprofitable_query", signal_types)
        self.assertIn("ads_budget_leak", signal_types)


if __name__ == "__main__":
    unittest.main()
