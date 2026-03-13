import unittest

from v3.analytics.sku_health import compute_sku_health


class TestSkuHealth(unittest.TestCase):
    def _item_by_sku(self, payload, sku):
        items = payload.get("items", []) if isinstance(payload, dict) else []
        for row in items:
            if isinstance(row, dict) and str(row.get("sku") or "") == sku:
                return row
        return {}

    def test_health_statuses_and_contract(self) -> None:
        payload = compute_sku_health(
            {"seller_id": "seller_001", "run_date": "2026-03-13"},
            {
                "sku_metrics": [
                    {
                        "sku": "STRONG",
                        "orders": 20,
                        "buyouts": 18,
                        "profit": 500,
                        "margin_pct": 35,
                        "ads_spend": 100,
                        "roi": 160,
                    },
                    {
                        "sku": "HEALTHY",
                        "orders": 6,
                        "buyouts": 4,
                        "profit": 120,
                        "margin_pct": 15,
                        "ads_spend": 20,
                        "roi": 90,
                    },
                    {
                        "sku": "UNSTABLE",
                        "orders": 2,
                        "buyouts": 1,
                        "profit": 50,
                        "margin_pct": 8,
                        "ads_spend": 0,
                    },
                    {
                        "sku": "RISK",
                        "orders": 0,
                        "buyouts": 0,
                        "profit": -40,
                        "margin_pct": -2,
                        "ads_spend": 100,
                    },
                ],
                "sales_funnel_diagnostics": {
                    "items": [
                        {"sku": "STRONG", "issue_type": "healthy_funnel"},
                        {"sku": "HEALTHY", "issue_type": "healthy_funnel"},
                        {"sku": "UNSTABLE", "issue_type": "card_problem"},
                        {"sku": "RISK", "issue_type": "traffic_problem"},
                    ]
                },
            },
        )

        strong = self._item_by_sku(payload, "STRONG")
        healthy = self._item_by_sku(payload, "HEALTHY")
        unstable = self._item_by_sku(payload, "UNSTABLE")
        risk = self._item_by_sku(payload, "RISK")

        self.assertEqual(strong.get("health_status"), "strong")
        self.assertEqual(healthy.get("health_status"), "healthy")
        self.assertEqual(unstable.get("health_status"), "unstable")
        self.assertEqual(risk.get("health_status"), "risk")

        self.assertIn(strong.get("status"), {"SCALE", "FIX", "WATCH", "LIQUIDATE"})
        self.assertIsInstance(strong.get("factors"), list)
        self.assertIsInstance(strong.get("warnings"), list)
        self.assertGreaterEqual(float(strong.get("health_score", -1)), 0.0)
        self.assertLessEqual(float(strong.get("health_score", 11)), 10.0)

        summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
        self.assertIn(summary.get("status"), {"ok", "partial", "insufficient_data"})
        self.assertIn("status_counts", summary)
        self.assertIn("average_health_score", summary)
        self.assertIn("top_risk_sku", summary)
        self.assertIn("top_strong_sku", summary)
        self.assertIn("insufficient_data_count", summary)

        self.assertIn("warnings", payload)
        self.assertIsInstance(payload.get("warnings"), list)

        # Backward compatible fields used by current recommendation layer.
        for key in ("SCALE", "FIX", "WATCH", "LIQUIDATE", "top_scale", "top_liquidate"):
            self.assertIn(key, summary)

    def test_fallback_uses_explicit_sku_rows(self) -> None:
        payload = compute_sku_health(
            {"seller_id": "seller_001", "run_date": "2026-03-13"},
            {},
            sku_rows=[{"sku": "SKU_FALLBACK", "orders": 5, "buyouts": 4, "profit": 100, "margin_pct": 20}],
        )
        item = self._item_by_sku(payload, "SKU_FALLBACK")
        self.assertTrue(bool(item))
        self.assertIn(item.get("health_status"), {"risk", "unstable", "healthy", "strong"})
        self.assertEqual(payload.get("summary", {}).get("sku_count"), 1)

    def test_missing_data_marks_insufficient(self) -> None:
        payload = compute_sku_health(
            {"seller_id": "seller_001", "run_date": "2026-03-13"},
            {"sku_metrics": [{"sku": "EMPTY"}]},
        )
        item = self._item_by_sku(payload, "EMPTY")
        self.assertEqual(item.get("scoring_status"), "insufficient_data")
        self.assertIn("insufficient_data", item.get("warnings", []))
        self.assertIn(payload.get("summary", {}).get("status"), {"partial", "insufficient_data"})
        self.assertGreaterEqual(int(payload.get("summary", {}).get("insufficient_data_count", 0) or 0), 1)
        self.assertIsInstance(payload.get("warnings", []), list)


if __name__ == "__main__":
    unittest.main()
