import tempfile
import unittest

from v3.outputs.daily_report_stage import run_daily_report_stage


class TestDailyReportFinancialLagPdf(unittest.TestCase):
    def _base_payload(self, tmp_dir: str) -> dict:
        return {
            "out_dir": tmp_dir,
            "seller_id": "seller_001",
            "run_date": "2026-04-15",
            "job": {"email_summary": {"key_insights": ["ok"], "recommendations": ["ok"]}},
            "event_date_model": {
                "report_date": "2026-04-15",
                "operational_date": "2026-04-14",
                "financial_date": "2026-04-12",
            },
            "data_quality": {
                "financial_finality_status": "lagged",
                "report_reliability_level": "medium",
                "financial_date_misaligned": True,
            },
            "daily_status_matrix": {"orders": "confirmed", "buyouts": "confirmed", "financials": "lagged"},
            "daily_kpi": {
                "orders_count_confirmed": True,
                "buyouts_count_confirmed": True,
                "buyouts_amount_confirmed": True,
            },
            "financial_kpi": {
                "financial_date_misaligned": True,
                "financial_alignment_status": "lagged_fallback",
                "financial_actual_date": "2026-04-12",
                "financial_target_date": "2026-04-14",
                "revenue": 2580.0,
                "net_profit": 610.0,
                "components": {"revenue": {"available": True}, "net_profit": {"available": True}},
            },
            "render_kpi": {
                "orders_count": 3,
                "buyouts_count": 3,
                "orders_amount": 3399.91,
                "buyouts_amount": 2580.0,
                "revenue": 2580.0,
                "net_profit": 610.0,
                "margin_pct": 23.64,
                "profitability_pct": 19.0,
            },
            "cabinet_funnel": {"funnel": {"view_to_order_conversion": 4.2, "orders": 3, "buyouts": 3}},
            "portfolio_ads_summary": {"portfolio_ad_spend": 200.0, "portfolio_revenue_from_ads": 700.0},
        }

    def test_report_payload_marks_lagged_financials_for_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            payload = self._base_payload(tmp_dir)
            try:
                out = run_daily_report_stage(payload)
            except FileNotFoundError:
                self.skipTest("TTF font for PDF is not available in this environment")
                return

            visual = out.get("visual_payload", {}) if isinstance(out, dict) else {}
            alignment = visual.get("financial_alignment", {}) if isinstance(visual, dict) else {}
            self.assertTrue(bool(alignment.get("financial_lagged", False)))
            self.assertEqual(str(alignment.get("financial_alignment_status") or ""), "lagged_fallback")
            self.assertEqual(str(alignment.get("financial_actual_date") or ""), "2026-04-12")
            self.assertEqual(str(alignment.get("financial_target_date") or ""), "2026-04-14")

            report_meta = out.get("report_meta", {}) if isinstance(out, dict) else {}
            fin_meta = report_meta.get("daily_financial_kpi", {}) if isinstance(report_meta, dict) else {}
            self.assertTrue(bool(fin_meta.get("financial_lagged", False)))
            self.assertEqual(str(fin_meta.get("financial_alignment_status") or ""), "lagged_fallback")
            self.assertEqual(str(fin_meta.get("financial_actual_date") or ""), "2026-04-12")
            self.assertEqual(str(fin_meta.get("financial_target_date") or ""), "2026-04-14")

    def test_hero_kpi_does_not_treat_lagged_financials_as_same_day(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            payload = self._base_payload(tmp_dir)
            try:
                out = run_daily_report_stage(payload)
            except FileNotFoundError:
                self.skipTest("TTF font for PDF is not available in this environment")
                return

            visual = out.get("visual_payload", {}) if isinstance(out, dict) else {}
            cards = visual.get("kpi_cards", []) if isinstance(visual, dict) else []
            self.assertTrue(isinstance(cards, list) and cards)

            labels = [str(card.get("label") or "") for card in cards if isinstance(card, dict)]
            labels_lower = [item.lower() for item in labels]
            self.assertTrue(any("лаговый финансовый срез wb" in item for item in labels_lower))
            self.assertFalse(any(str(card.get("label") or "") == "К перечислению продавцу" for card in cards if isinstance(card, dict)))
            self.assertTrue(any("заказы" in item for item in labels_lower))
            self.assertTrue(any("выкупы" in item for item in labels_lower))

    def test_finance_section_contains_lag_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            payload = self._base_payload(tmp_dir)
            try:
                out = run_daily_report_stage(payload)
            except FileNotFoundError:
                self.skipTest("TTF font for PDF is not available in this environment")
                return

            visual = out.get("visual_payload", {}) if isinstance(out, dict) else {}
            alignment = visual.get("financial_alignment", {}) if isinstance(visual, dict) else {}
            warning_text = str(alignment.get("warning_text") or "").lower()
            self.assertIn("финансовые данные wb доступны только за 2026-04-12", warning_text)
            self.assertIn("операционному дню 2026-04-14", warning_text)

            report_meta = out.get("report_meta", {}) if isinstance(out, dict) else {}
            previews = report_meta.get("page_previews", []) if isinstance(report_meta, dict) else []
            page_2_lines = []
            for page in previews:
                if int(page.get("page", 0) or 0) == 2:
                    page_2_lines = [str(line) for line in page.get("lines", [])]
                    break
            text = "\n".join(page_2_lines).lower()
            self.assertIn("финансовая структура (лаговый срез wb)", text)
            self.assertIn("внимание | финансовые данные wb доступны только за 2026-04-12", text)


if __name__ == "__main__":
    unittest.main()
