import unittest

from v3.analytics.profit_contribution import build_profit_contribution


class TestProfitContribution(unittest.TestCase):
    def _item_by_sku(self, payload, sku):
        items = payload.get("items", []) if isinstance(payload, dict) else []
        for row in items:
            if isinstance(row, dict) and str(row.get("sku") or "") == sku:
                return row
        return {}

    def test_contract_groups_and_summary(self) -> None:
        payload = build_profit_contribution(
            {
                "sku_metrics": [
                    {"sku": "A", "revenue": 5000, "profit": 800},
                    {"sku": "B", "revenue": 3000, "profit": 150},
                    {"sku": "C", "revenue": 1000, "profit": 50},
                    {"sku": "D", "revenue": 700, "profit": -20},
                    {"sku": "E", "revenue": 400, "profit": None},
                ]
            }
        )

        self.assertIn(payload.get("status"), {"ok", "partial", "insufficient_data"})
        self.assertIsInstance(payload.get("warnings", []), list)
        self.assertIsInstance(payload.get("items", []), list)

        summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
        self.assertEqual(int(summary.get("sku_count", 0)), 5)
        self.assertEqual(int(summary.get("profit_sku_count", 0)), 3)
        self.assertEqual(int(summary.get("loss_sku_count", 0)), 1)
        self.assertEqual(float(summary.get("total_revenue", 0.0)), 10100.0)
        self.assertIn(summary.get("profit_concentration"), {"high", "medium", "low", "insufficient_data"})
        self.assertAlmostEqual(float(summary.get("top_20_profit_share", 0.0) or 0.0), 0.8, places=6)
        meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
        self.assertEqual(float(meta.get("total_revenue", 0.0)), 10100.0)

        a = self._item_by_sku(payload, "A")
        b = self._item_by_sku(payload, "B")
        d = self._item_by_sku(payload, "D")
        e = self._item_by_sku(payload, "E")

        self.assertEqual(a.get("profit_group"), "P1")
        self.assertEqual(b.get("profit_group"), "P2")
        self.assertEqual(d.get("profit_group"), "P4")
        self.assertEqual(e.get("status"), "insufficient_data")
        self.assertIn("profit_missing", e.get("warnings", []))

        # Backward compatibility for current report/facts layer.
        for key in ("p1", "p2", "p3", "p4", "top_profit_skus", "meta"):
            self.assertIn(key, payload)

    def test_non_positive_total_profit_marks_share_as_unavailable(self) -> None:
        payload = build_profit_contribution(
            {
                "sku_metrics": [
                    {"sku": "P", "profit": 10},
                    {"sku": "L", "profit": -20},
                ]
            }
        )
        item_p = self._item_by_sku(payload, "P")
        self.assertIsNone(item_p.get("profit_share"))
        self.assertIn("total_profit_non_positive", item_p.get("warnings", []))

    def test_missing_input_is_safe(self) -> None:
        payload = build_profit_contribution({})
        self.assertEqual(payload.get("status"), "insufficient_data")
        summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
        self.assertEqual(int(summary.get("sku_count", 0)), 0)

    def test_total_revenue_is_none_when_revenue_is_missing(self) -> None:
        payload = build_profit_contribution(
            {
                "sku_metrics": [
                    {"sku": "P", "profit": 10},
                    {"sku": "L", "profit": -2, "revenue": None},
                ]
            }
        )

        summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
        meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
        self.assertIsNone(summary.get("total_revenue"))
        self.assertIsNone(meta.get("total_revenue"))


if __name__ == "__main__":
    unittest.main()
