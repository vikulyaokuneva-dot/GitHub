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

    def test_non_api_mode_keeps_partial_sections_and_business_reasons(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            payload = {
                "out_dir": tmp_dir,
                "seller_id": "seller_001",
                "run_date": "2026-03-15",
                "source_mode": "local_reports",
                "data_mode": "raw_reports_fallback",
                "non_api_mode": True,
                "job": {"email_summary": {"key_insights": ["ok"], "recommendations": ["ok"]}},
                "render_kpi": {
                    "orders_count": None,
                    "net_profit": None,
                    "revenue": 10000,
                },
                "daily_kpi": {
                    "daily_orders_count": 42,
                    "orders_count_confirmed": False,
                    "buyouts_count_confirmed": False,
                },
                "financial_kpi": {
                    "components": {
                        "revenue": {"available": True},
                        "commission": {"available": True},
                        "logistics": {"available": True},
                        "tax": {"available": True},
                        "ads_spend": {"available": True},
                        "cost_price": {"available": False},
                        "net_profit": {"available": False},
                    },
                    "seller_payout": 10000,
                    "wb_commission": 900,
                    "logistics": 650,
                    "tax": 320,
                    "ads_spend": 540,
                    "cost_price": None,
                    "net_profit": None,
                },
                "cabinet_funnel": {
                    "funnel": {
                        "views": 3200,
                        "add_to_cart": 210,
                        "orders": 42,
                        "buyouts": 30,
                    }
                },
                "portfolio_ads_summary": {
                    "portfolio_ad_spend": 540,
                    "portfolio_revenue_from_ads": 2100,
                    "analysis_mode": "preview",
                },
                "ads_rows_count": 12,
                "decision_groups": {
                    "scale": [],
                    "fix": [
                        {
                            "sku": "SKU1",
                            "action": "improve_listing",
                            "reason": "Недостаточно данных для уверенной диагностики",
                            "ads_spend": 120.0,
                            "ads_orders": 0,
                        }
                    ],
                    "watch": [],
                    "liquidate": [],
                },
                "sku_watchlists": {
                    "watchlists": {
                        "ad_inefficiency": [{"sku": "SKU1", "reason": "Риск неэффективной рекламы"}],
                        "top_risk": [{"sku": "SKU2", "reason": "Риск"}],
                    }
                },
            }
            try:
                out = run_daily_report_stage(payload)
            except FileNotFoundError:
                self.skipTest("TTF font for PDF is not available in this environment")
                return

            visual_payload = out.get("visual_payload", {}) if isinstance(out, dict) else {}
            self.assertIsInstance(visual_payload, dict)
            kpi_cards = visual_payload.get("kpi_cards", [])
            self.assertTrue(any(str(card.get("label")) == "Прибыль без себестоимости" for card in kpi_cards if isinstance(card, dict)))
            self.assertTrue(any(str(card.get("label")) == "Заказы (оценка)" for card in kpi_cards if isinstance(card, dict)))

            section_states = visual_payload.get("section_states", {})
            self.assertIn(section_states.get("ads_efficiency"), {"full", "partial", "compact_note"})
            self.assertIn(section_states.get("funnel"), {"full", "partial", "compact_note"})

            key_problem_reasons = visual_payload.get("key_problem_reasons", {})
            joined_reasons = " ".join(str(v) for v in key_problem_reasons.values())
            self.assertNotIn("non-API mode", joined_reasons)

            recs = visual_payload.get("ai_recommendations", {})
            rec_rows = []
            for bucket in ("p1", "p2", "p3"):
                rows = recs.get(bucket, []) if isinstance(recs, dict) else []
                if isinstance(rows, list):
                    rec_rows.extend([row for row in rows if isinstance(row, dict)])
            self.assertTrue(rec_rows)
            self.assertTrue(all("недостаточно данных" not in str(row.get("reason", "")).lower() for row in rec_rows))


if __name__ == "__main__":
    unittest.main()
