import os
import tempfile
import unittest

from v3.outputs.daily_report_stage import run_daily_report_stage


class TestReportMetaFields(unittest.TestCase):
    def test_report_meta_contains_email_and_dates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            payload = {
                "out_dir": tmp_dir,
                "seller_id": "seller_001",
                "run_date": "2026-03-15",
                "job": {
                    "email_summary": {
                        "key_insights": ["insight"],
                        "recommendations": ["recommendation"],
                    }
                },
                "event_date_model": {"operational_date": "2026-03-14"},
                "data_quality": {"financial_finality_status": "partial", "report_reliability_level": "low"},
                "report_guardrails": {"notices": ["Financial KPI are provisional."]},
            }
            try:
                out = run_daily_report_stage(payload)
            except FileNotFoundError:
                self.skipTest("TTF font for PDF is not available in this environment")
                return

            report_meta = out.get("report_meta", {}) if isinstance(out, dict) else {}
            self.assertEqual(str(report_meta.get("seller_id") or ""), "seller_001")
            self.assertEqual(str(report_meta.get("report_date") or ""), "2026-03-15")
            self.assertEqual(str(report_meta.get("operational_day") or ""), "2026-03-14")
            self.assertTrue(str(report_meta.get("email_subject") or "").strip())
            self.assertTrue(str(report_meta.get("email_body_text") or "").strip())
            self.assertIn("financial_interpretation", report_meta)
            self.assertTrue(isinstance(report_meta.get("render_warnings", []), list))
            self.assertTrue(os.path.isfile(os.path.join(tmp_dir, "report_meta.json")))


if __name__ == "__main__":
    unittest.main()
