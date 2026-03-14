import unittest

from v3.validation.report_guardrails import apply_report_guardrails


class TestReportGuardrails(unittest.TestCase):
    def test_partial_financials_keep_commerce_but_disable_profit_confidence(self) -> None:
        payload = {
            "data_quality": {
                "sku_attribution_status": "ok",
                "financial_finality_status": "partial",
            },
            "financial_kpi": {"financial_finality_status": "partial", "is_partial": True},
            "daily_kpi": {
                "orders_count_confirmed": True,
                "buyouts_count_confirmed": True,
            },
            "cabinet_funnel": {"funnel": {}},
            "ads_rows_count": 0,
            "ads_source_file": "",
        }

        out = apply_report_guardrails(payload)
        guard = out.get("report_guardrails", {})

        self.assertTrue(bool(guard.get("commerce_commentary_enabled")))
        self.assertFalse(bool(guard.get("profitability_commentary_enabled")))
        self.assertFalse(bool(guard.get("ads_analysis_enabled")))
        self.assertFalse(bool(guard.get("views_analysis_enabled")))
        notices = guard.get("notices", [])
        self.assertTrue(any("provisional" in str(line).lower() for line in notices))

    def test_broken_sku_attribution_suppresses_sku_level_engines(self) -> None:
        payload = {
            "data_quality": {
                "sku_attribution_status": "broken",
                "financial_finality_status": "partial",
            },
            "financial_kpi": {"financial_finality_status": "partial", "is_partial": True},
            "daily_kpi": {
                "orders_count_confirmed": True,
                "buyouts_count_confirmed": True,
            },
            "territorial_distribution": {"status": "ok", "summary": {"sku_total": 10}},
            "profit_contribution": {"status": "ok", "summary": {"sku_count": 10}},
            "key_insights": [
                "53 unassigned rows found.",
                "Territorial risk detected on top SKU.",
                "Some neutral insight.",
            ],
        }

        out = apply_report_guardrails(payload)

        self.assertEqual(str(out.get("territorial_distribution", {}).get("status")), "suppressed_due_to_data_quality")
        self.assertEqual(str(out.get("profit_contribution", {}).get("status")), "suppressed_due_to_data_quality")
        self.assertFalse(bool(out.get("data_quality", {}).get("territorial_analysis_enabled")))
        self.assertFalse(bool(out.get("data_quality", {}).get("profit_contribution_enabled")))

        insights = out.get("key_insights", [])
        self.assertTrue(isinstance(insights, list) and insights)
        self.assertIn("technical issue", str(insights[0]).lower())
        joined = "\n".join(str(x).lower() for x in insights)
        self.assertNotIn("unassigned", joined)
        self.assertNotIn("territorial risk", joined)


if __name__ == "__main__":
    unittest.main()
