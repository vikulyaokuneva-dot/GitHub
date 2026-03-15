import tempfile
import unittest

from v3.outputs.daily_report_stage import run_daily_report_stage


class TestDailyReportKpiMissingLabels(unittest.TestCase):
    def test_kpi_block_uses_human_labels_for_missing_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            payload = {
                "out_dir": tmp_dir,
                "seller_id": "seller_001",
                "run_date": "2026-03-15",
                "job": {"email_summary": {"key_insights": ["ok"], "recommendations": ["ok"]}},
                "daily_kpi": {
                    "orders_count_confirmed": False,
                    "buyouts_count_confirmed": False,
                    "buyouts_amount_confirmed": False,
                },
                "render_kpi": {
                    "orders_count": None,
                    "buyouts_count": None,
                    "avg_check": None,
                    "margin_pct": None,
                    "profitability_pct": None,
                    "revenue": None,
                    "net_profit": None,
                },
                "cabinet_funnel": {"funnel": {"view_to_order_conversion": None, "cpo": None}},
                "portfolio_ads_summary": {"portfolio_CPO": None},
            }
            try:
                out = run_daily_report_stage(payload)
            except FileNotFoundError:
                self.skipTest("TTF font for PDF is not available in this environment")
                return

            report_meta = out.get("report_meta", {}) if isinstance(out, dict) else {}
            previews = report_meta.get("page_previews", []) if isinstance(report_meta, dict) else []
            page_2_lines = []
            for page in previews:
                if int(page.get("page", 0) or 0) == 2:
                    page_2_lines = [str(line) for line in page.get("lines", [])]
                    break

            text = "\n".join(page_2_lines)
            self.assertIn("Заказы | нет данных", text)
            self.assertIn("Выкупы | нет данных", text)
            self.assertIn("Конверсия в заказ | недостаточно данных для расчета", text)
            self.assertIn("Маржа | недостаточно данных для расчета", text)
            self.assertIn("CPO | недостаточно данных для расчета", text)
            self.assertNotIn("?", text)


if __name__ == "__main__":
    unittest.main()
