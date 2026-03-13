import unittest

from v3.analysis.decision_engine import build_decisions


class TestDecisionEngineProfitSignals(unittest.TestCase):
    def _flatten(self, decisions_payload):
        summary = decisions_payload.get("summary", {}) if isinstance(decisions_payload, dict) else {}
        rows = []
        for key in ("scale", "fix", "watch", "liquidate"):
            bucket = summary.get(key, [])
            if isinstance(bucket, list):
                rows.extend([x for x in bucket if isinstance(x, dict)])
        return rows

    def test_profit_contribution_signals_are_exposed(self) -> None:
        metrics = {
            "sku_metrics": [
                {"sku": "SKU_P1", "profit": 100, "margin_pct": 30},
                {"sku": "SKU_P4", "profit": -40, "margin_pct": -5},
            ],
            "profit_contribution": {
                "summary": {"profit_concentration": "high", "top_20_profit_share": 0.9},
                "items": [
                    {"sku": "SKU_P1", "profit_group": "P1", "profit_share": 0.9},
                    {"sku": "SKU_P4", "profit_group": "P4", "profit_share": -0.1},
                ],
            },
        }
        payload = build_decisions(metrics, [], {"items": []}, {}, {})

        rows = self._flatten(payload)
        by_sku = {str(row.get("sku") or ""): row for row in rows}

        self.assertEqual(by_sku.get("SKU_P1", {}).get("profit_group"), "P1")
        self.assertEqual(by_sku.get("SKU_P4", {}).get("profit_group"), "P4")
        self.assertEqual(
            by_sku.get("SKU_P1", {}).get("profit_signal_ru"),
            "Этот SKU является драйвером прибыли.",
        )
        self.assertEqual(
            by_sku.get("SKU_P4", {}).get("profit_signal_ru"),
            "Этот SKU приносит убыток и требует внимания.",
        )
        self.assertEqual(
            payload.get("profit_concentration_signal_ru"),
            "Бизнес сильно зависит от небольшого числа SKU.",
        )


if __name__ == "__main__":
    unittest.main()
