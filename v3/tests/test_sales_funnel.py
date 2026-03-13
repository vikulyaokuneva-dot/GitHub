import unittest

from v3.analytics.sales_funnel import build_sales_funnel_metrics


class TestSalesFunnelEngine(unittest.TestCase):
    def _issue_by_sku(self, payload, sku):
        items = payload.get("items", []) if isinstance(payload, dict) else []
        for row in items:
            if isinstance(row, dict) and str(row.get("sku") or "") == sku:
                return str(row.get("issue_type") or "")
        return ""

    def test_classifies_required_issue_types(self):
        metrics = {
            "sku_metrics": [
                {
                    "sku": "A_HEALTHY",
                    "views": 1000,
                    "add_to_cart": 120,
                    "orders": 45,
                    "buyouts": 40,
                    "ads_spend": 100,
                },
                {
                    "sku": "B_TRAFFIC",
                    "views": 0,
                    "add_to_cart": 0,
                    "orders": 0,
                    "buyouts": 0,
                },
                {
                    "sku": "C_CARD",
                    "views": 1000,
                    "add_to_cart": 10,
                    "orders": 4,
                    "buyouts": 4,
                },
                {
                    "sku": "D_OFFER",
                    "views": 1000,
                    "add_to_cart": 100,
                    "orders": 10,
                    "buyouts": 10,
                },
                {
                    "sku": "E_BUYOUT",
                    "views": 1000,
                    "add_to_cart": 100,
                    "orders": 50,
                    "buyouts": 20,
                },
                {
                    "sku": "F_ADS",
                    "views": 200,
                    "add_to_cart": 20,
                    "orders": 0,
                    "buyouts": 0,
                    "ads_spend": 500,
                },
                {
                    "sku": "G_MISSING",
                    "views": None,
                    "add_to_cart": "",
                    "orders": None,
                    "buyouts": "-",
                    "ads_spend": None,
                },
            ]
        }

        payload = build_sales_funnel_metrics(metrics, run_date="2026-03-13")

        self.assertEqual(self._issue_by_sku(payload, "A_HEALTHY"), "healthy_funnel")
        self.assertEqual(self._issue_by_sku(payload, "B_TRAFFIC"), "traffic_problem")
        self.assertEqual(self._issue_by_sku(payload, "C_CARD"), "card_problem")
        self.assertEqual(self._issue_by_sku(payload, "D_OFFER"), "price_or_offer_problem")
        self.assertEqual(self._issue_by_sku(payload, "E_BUYOUT"), "buyout_problem")
        self.assertEqual(self._issue_by_sku(payload, "F_ADS"), "ads_efficiency_problem")
        self.assertEqual(self._issue_by_sku(payload, "G_MISSING"), "insufficient_data")

        summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
        issue_counts = summary.get("issue_counts", {}) if isinstance(summary, dict) else {}
        self.assertEqual(int(issue_counts.get("healthy_funnel", 0)), 1)
        self.assertEqual(int(issue_counts.get("traffic_problem", 0)), 1)
        self.assertEqual(int(issue_counts.get("card_problem", 0)), 1)
        self.assertEqual(int(issue_counts.get("price_or_offer_problem", 0)), 1)
        self.assertEqual(int(issue_counts.get("buyout_problem", 0)), 1)
        self.assertEqual(int(issue_counts.get("ads_efficiency_problem", 0)), 1)
        self.assertEqual(int(issue_counts.get("insufficient_data", 0)), 1)

    def test_missing_input_is_safe(self):
        payload = build_sales_funnel_metrics({"sku_metrics": [{"sku": "X"}]})
        self.assertIn(payload.get("status"), {"success", "partial_success", "failed"})
        self.assertEqual(self._issue_by_sku(payload, "X"), "insufficient_data")


if __name__ == "__main__":
    unittest.main()
