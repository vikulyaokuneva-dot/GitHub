import unittest

from v3.analysis.decision_engine import build_decisions


class TestDecisionEngineKeywordSignals(unittest.TestCase):
    def _flatten(self, payload):
        summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
        rows = []
        for key in ("scale", "fix", "watch", "liquidate"):
            bucket = summary.get(key, [])
            if isinstance(bucket, list):
                rows.extend([x for x in bucket if isinstance(x, dict)])
        return rows

    def test_keyword_signals_are_exposed(self) -> None:
        metrics = {
            "sku_metrics": [
                {"sku": "SKU1", "profit": 100, "margin_pct": 25},
                {"sku": "SKU2", "profit": 50, "margin_pct": 15},
            ],
            "keyword_monitoring": {
                "summary": {
                    "winner_query_count": 2,
                    "growth_query_count": 1,
                    "low_relevance_query_count": 4,
                    "no_orders_query_count": 3,
                    "costly_query_count": 1,
                },
                "sku_items": [
                    {
                        "sku": "SKU1",
                        "query_count": 3,
                        "winner_queries_count": 2,
                        "growth_queries_count": 1,
                        "weak_queries_count": 0,
                        "costly_queries_count": 0,
                        "keyword_health_status": "strong",
                    },
                    {
                        "sku": "SKU2",
                        "query_count": 4,
                        "winner_queries_count": 0,
                        "growth_queries_count": 0,
                        "weak_queries_count": 3,
                        "costly_queries_count": 1,
                        "keyword_health_status": "risk",
                    },
                ],
            },
        }

        payload = build_decisions(metrics, [], {"items": []}, {}, {})
        rows = self._flatten(payload)
        by_sku = {str(row.get("sku") or ""): row for row in rows}

        self.assertEqual(by_sku.get("SKU1", {}).get("keyword_health_status"), "strong")
        self.assertEqual(by_sku.get("SKU2", {}).get("keyword_health_status"), "risk")
        self.assertGreaterEqual(len(by_sku.get("SKU2", {}).get("keyword_signals_ru", [])), 1)
        self.assertEqual(
            payload.get("keyword_global_signal_ru"),
            "Часть запросов дает показы, но не дает коммерческого результата.",
        )


if __name__ == "__main__":
    unittest.main()
