import unittest

from v3.entry import _build_management_email_body
from v3.outputs.daily_email_stage import run_daily_email_stage


class TestEmailPartialDataWording(unittest.TestCase):
    def test_daily_email_summary_marks_partial_financials(self) -> None:
        payload = {
            "job": {},
            "daily_kpi": {
                "orders_count_confirmed": True,
                "buyouts_count_confirmed": True,
            },
            "data_quality": {
                "financial_finality_status": "partial",
                "sku_attribution_status": "ok",
                "report_reliability_level": "medium",
            },
            "report_guardrails": {
                "financial_finality_status": "partial",
                "sku_attribution_status": "ok",
                "report_reliability_level": "medium",
            },
            "key_insights": ["baseline commerce insight"],
            "totals": {},
        }

        out = run_daily_email_stage(payload)
        summary = out.get("job", {}).get("email_summary", {})
        insights = summary.get("key_insights", [])

        self.assertEqual(str(summary.get("financial_finality_status")), "partial")
        self.assertTrue(isinstance(insights, list) and insights)
        self.assertIn("provisional", str(insights[0]).lower())

    def test_parser_failure_is_not_rendered_as_business_insight(self) -> None:
        payload = {
            "job": {},
            "daily_kpi": {
                "orders_count_confirmed": True,
                "buyouts_count_confirmed": True,
            },
            "data_quality": {
                "financial_finality_status": "partial",
                "sku_attribution_status": "broken",
                "report_reliability_level": "low",
            },
            "report_guardrails": {
                "financial_finality_status": "partial",
                "sku_attribution_status": "broken",
                "report_reliability_level": "low",
            },
            "key_insights": [
                "53 unassigned rows detected in parser output.",
                "Territorial risk for top SKU is high.",
                "baseline insight",
            ],
            "totals": {},
        }

        out = run_daily_email_stage(payload)
        insights = out.get("job", {}).get("email_summary", {}).get("key_insights", [])
        joined = "\n".join(str(x).lower() for x in insights)

        self.assertIn("technical issue", joined)
        self.assertNotIn("53 unassigned rows", joined)
        self.assertNotIn("territorial risk", joined)

    def test_management_body_uses_provisional_wording(self) -> None:
        body = _build_management_email_body(
            seller_id="seller-1",
            run_date="2026-03-14",
            summary={
                "financial_finality_status": "partial",
                "financial_partial": True,
                "financial_revenue": 1000.0,
                "gross_profit": 250.0,
                "net_profit": 120.0,
                "margin_pct": 12.0,
                "profitability_pct": 20.0,
                "financial_completeness_pct": 33.33,
                "key_insights": [],
                "recommendations": [],
                "display": {},
            },
        )

        self.assertIn("Financial contour status: partial", body)
        self.assertIn("Financial KPI interpretation: provisional", body)
        self.assertNotIn("Financial KPI interpretation: final", body)


if __name__ == "__main__":
    unittest.main()
