import unittest

from v3.analytics.keywords.query_classifier import classify_query_item


class TestKeywordClassifier(unittest.TestCase):
    def test_required_query_statuses(self) -> None:
        winner = classify_query_item({"impressions": 1000, "clicks": 120, "orders": 30, "conversion": 0.03, "click_to_order": 0.25})
        growth = classify_query_item({"impressions": 150, "clicks": 20, "orders": 4, "conversion": 0.0267, "click_to_order": 0.2})
        low_conversion = classify_query_item({"impressions": 1200, "clicks": 80, "orders": 3, "conversion": 0.0025, "click_to_order": 0.0375})
        low_relevance = classify_query_item({"impressions": 900, "clicks": 80, "orders": 1, "conversion": 0.0011, "click_to_order": 0.0125})
        traffic_only = classify_query_item({"impressions": 500, "clicks": 12, "orders": 0, "cart_rate": 0.0})
        no_orders = classify_query_item({"impressions": 150, "clicks": 20, "orders": 0, "cart_rate": 0.05})
        costly = classify_query_item({"impressions": 500, "clicks": 30, "orders": 0, "spend": 1500.0, "spend_per_order": None})
        insufficient = classify_query_item({"impressions": None, "clicks": None, "orders": None, "spend": None})

        self.assertEqual(winner, "winner")
        self.assertEqual(growth, "growth_opportunity")
        self.assertEqual(low_conversion, "low_conversion")
        self.assertEqual(low_relevance, "low_relevance")
        self.assertEqual(traffic_only, "traffic_only")
        self.assertEqual(no_orders, "no_orders")
        self.assertEqual(costly, "costly")
        self.assertEqual(insufficient, "insufficient_data")


if __name__ == "__main__":
    unittest.main()
