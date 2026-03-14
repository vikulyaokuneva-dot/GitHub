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
            "\u0427\u0430\u0441\u0442\u044c \u0437\u0430\u043f\u0440\u043e\u0441\u043e\u0432 \u0434\u0430\u0435\u0442 \u043f\u043e\u043a\u0430\u0437\u044b, \u043d\u043e \u043d\u0435 \u0434\u0430\u0435\u0442 \u043a\u043e\u043c\u043c\u0435\u0440\u0447\u0435\u0441\u043a\u043e\u0433\u043e \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442\u0430.",
        )


if __name__ == "__main__":
    unittest.main()
