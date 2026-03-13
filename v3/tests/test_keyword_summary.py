import unittest

from v3.analytics.keywords.engine import build_keyword_monitoring


class TestKeywordSummary(unittest.TestCase):
    def test_sku_and_global_summary(self) -> None:
        payload = build_keyword_monitoring(
            {
                "ads_rows": [
                    {"sku": "SKU1", "query": "q1", "impressions": 1000, "clicks": 100, "orders": 30, "add_to_cart": 80, "buyouts": 25, "ads_spend": 300},
                    {"sku": "SKU1", "query": "q2", "impressions": 300, "clicks": 30, "orders": 0, "add_to_cart": 1, "buyouts": 0, "ads_spend": 700},
                    {"sku": "SKU2", "query": "q3", "impressions": 150, "clicks": 20, "orders": 4, "add_to_cart": 15, "buyouts": 3, "ads_spend": 120},
                ]
            },
            run_date="2026-03-13",
        )

        self.assertIn(payload.get("status"), {"ok", "partial", "insufficient_data"})
        self.assertEqual(payload.get("date"), "2026-03-13")
        self.assertEqual(len(payload.get("items", [])), 3)
        self.assertEqual(len(payload.get("sku_items", [])), 2)

        summary = payload.get("summary", {})
        self.assertEqual(int(summary.get("sku_count_with_keywords", 0)), 2)
        self.assertEqual(int(summary.get("total_query_count", 0)), 3)
        self.assertGreaterEqual(int(summary.get("winner_query_count", 0)), 1)

    def test_empty_input_is_explicit(self) -> None:
        payload = build_keyword_monitoring({"ads_rows": []})
        self.assertEqual(payload.get("status"), "insufficient_data")
        warnings = payload.get("warnings", [])
        self.assertTrue(any(str(item.get("code") or "") == "keyword_monitoring_insufficient_data" for item in warnings if isinstance(item, dict)))


if __name__ == "__main__":
    unittest.main()
