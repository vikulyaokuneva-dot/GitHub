import unittest

from v3.analytics.keywords import safe_div
from v3.analytics.keywords.query_metrics import build_query_metrics


class TestKeywordMetrics(unittest.TestCase):
    def test_safe_div(self) -> None:
        self.assertEqual(safe_div(10, 2), 5.0)
        self.assertIsNone(safe_div(10, 0))
        self.assertIsNone(safe_div(None, 2))

    def test_query_metric_calculation(self) -> None:
        rows = [
            {
                "sku": "SKU1",
                "query": "кроссовки женские",
                "impressions": 1000,
                "clicks": 100,
                "add_to_cart": 50,
                "orders": 20,
                "buyouts": 15,
                "spend": 500.0,
            }
        ]
        payload = build_query_metrics(rows)
        self.assertEqual(len(payload), 1)
        item = payload[0]
        self.assertAlmostEqual(float(item.get("ctr") or 0.0), 0.1, places=6)
        self.assertAlmostEqual(float(item.get("cart_rate") or 0.0), 0.05, places=6)
        self.assertAlmostEqual(float(item.get("conversion") or 0.0), 0.02, places=6)
        self.assertAlmostEqual(float(item.get("click_to_order") or 0.0), 0.2, places=6)
        self.assertAlmostEqual(float(item.get("buyout_rate") or 0.0), 0.75, places=6)
        self.assertAlmostEqual(float(item.get("spend_per_order") or 0.0), 25.0, places=6)
        self.assertAlmostEqual(float(item.get("spend_per_buyout") or 0.0), 33.333333, places=4)


if __name__ == "__main__":
    unittest.main()
