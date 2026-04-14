import tempfile
import unittest

from v3.outputs.daily_report_stage import run_daily_report_stage
from v3.pdf_render import write_daily_bi_pdf


class TestDailyReportTerritorialSection(unittest.TestCase):
    def _base_payload(self, tmp_dir: str) -> dict:
        return {
            "out_dir": tmp_dir,
            "seller_id": "seller_001",
            "run_date": "2026-04-13",
            "job": {"email_summary": {"key_insights": ["ok"], "recommendations": ["ok"]}},
        }

    def test_territorial_section_usable_has_recommendations_and_sku_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            territorial_summary = {
                "analysis_status": "usable",
                "recommendation_status": "actionable",
                "confidence_level": "high",
                "coverage_pct": 78.5,
                "demand_coverage_pct": 82.0,
                "stock_coverage_pct": 71.0,
                "unknown_share_pct": 21.5,
                "total_skus_analyzed": 3,
                "blocked_analysis_skus": 1,
                "actionable_recommendation_skus": 1,
                "recommendation_candidate_skus": 1,
                "blocked_reason_counts": {"minimum_sample_not_met": 1},
                "top_demand_regions": [{"region": "Moscow", "orders": 15, "share_pct": 45.0}],
            }
            payload = self._base_payload(tmp_dir)
            payload.update(
                {
                    "territorial_summary": territorial_summary,
                    "territorial_distribution": {
                        "summary": territorial_summary,
                        "analysis_status": "usable",
                        "recommendation_status": "actionable",
                        "recommendation_candidates": [
                            {
                                "sku": "SKU-1",
                                "recommendation_candidates": [
                                    {
                                        "destination_region": "Moscow",
                                        "demand_share_pct": 45.0,
                                        "stock_share_pct": 20.0,
                                        "gap_share_pct": 25.0,
                                        "priority": "high",
                                        "reason": "non_local_demand_exceeds_supply_share",
                                    }
                                ],
                            }
                        ],
                        "items": [
                            {
                                "sku": "SKU-1",
                                "analysis_status": "usable",
                                "recommendation_status": "actionable",
                                "localization_share": 35.0,
                                "non_local_orders_estimate": 12,
                                "top_demand_regions": [{"region": "Moscow", "orders": 15, "share_pct": 45.0}],
                                "recommendation_candidates": [
                                    {
                                        "destination_region": "Moscow",
                                        "demand_share_pct": 45.0,
                                        "stock_share_pct": 20.0,
                                        "gap_share_pct": 25.0,
                                        "priority": "high",
                                        "reason": "non_local_demand_exceeds_supply_share",
                                    }
                                ],
                                "total_orders": 20,
                            }
                        ],
                    },
                }
            )
            try:
                out = run_daily_report_stage(payload)
            except FileNotFoundError:
                self.skipTest("TTF font for PDF is not available in this environment")
                return

            visual = ((out or {}).get("visual_payload") or {}).get("territorial_localization", {})
            self.assertTrue(bool(visual.get("show")))
            self.assertEqual(str(visual.get("analysis_status") or ""), "usable")
            self.assertTrue(bool(visual.get("recommendation_rows", [])))
            self.assertTrue(bool(visual.get("sku_rows", [])))
            self.assertTrue(bool(visual.get("top_demand_regions_rows", [])))

            section_states = ((out or {}).get("visual_payload") or {}).get("section_states", {})
            self.assertIn(str(section_states.get("territorial_localization") or ""), {"full", "partial", "compact_note"})

            report_meta = (out or {}).get("report_meta", {})
            territorial_preview = report_meta.get("territorial_section_preview", {}) if isinstance(report_meta, dict) else {}
            self.assertGreater(int(territorial_preview.get("recommendation_rows_count", 0) or 0), 0)

    def test_territorial_section_blocked_explains_reasons_without_raw_codes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            territorial_summary = {
                "analysis_status": "blocked_by_data",
                "recommendation_status": "blocked_by_data",
                "confidence_level": "low",
                "coverage_pct": 12.0,
                "demand_coverage_pct": 0.0,
                "stock_coverage_pct": 20.0,
                "unknown_share_pct": 88.0,
                "total_skus_analyzed": 4,
                "blocked_analysis_skus": 4,
                "actionable_recommendation_skus": 0,
                "blocked_reason_counts": {
                    "missing_demand_geography": 3,
                    "low_stock_geography_coverage": 2,
                },
                "top_demand_regions": [{"region": "SPB", "orders": 4, "share_pct": 50.0}],
            }
            payload = self._base_payload(tmp_dir)
            payload.update(
                {
                    "territorial_summary": territorial_summary,
                    "territorial_distribution": {
                        "summary": territorial_summary,
                        "analysis_status": "blocked_by_data",
                        "recommendation_status": "blocked_by_data",
                        "items": [
                            {
                                "sku": "SKU-2",
                                "analysis_status": "blocked_by_data",
                                "recommendation_status": "blocked_by_data",
                                "blocked_reasons": ["missing_demand_geography", "missing_stock_geography"],
                            }
                        ],
                    },
                }
            )
            try:
                out = run_daily_report_stage(payload)
            except FileNotFoundError:
                self.skipTest("TTF font for PDF is not available in this environment")
                return

            visual = ((out or {}).get("visual_payload") or {}).get("territorial_localization", {})
            self.assertTrue(bool(visual.get("show")))
            self.assertEqual(str(visual.get("analysis_status") or ""), "blocked_by_data")
            self.assertEqual(str(visual.get("state") or ""), "compact_note")
            blocked_rows = visual.get("blocked_reason_rows", []) if isinstance(visual, dict) else []
            self.assertTrue(blocked_rows)
            self.assertTrue(all("_" not in str(row.get("reason") or "") for row in blocked_rows if isinstance(row, dict)))
            self.assertTrue(bool(visual.get("summary_lines", [])))

    def test_pdf_renderer_adds_territorial_pages_when_payload_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf_path = f"{tmp_dir}/report.pdf"
            payload = {
                "seller_id": "seller_001",
                "run_date": "2026-04-13",
                "operational_day": "2026-04-13",
                "preview_dir": tmp_dir,
                "kpi_cards": [
                    {"label": "Revenue", "value": 1000, "value_type": "money"},
                    {"label": "Profit", "value": 300, "value_type": "money"},
                ],
                "funnel": {"views": 1000, "add_to_cart": 120, "orders": 50, "buyouts": 35},
                "sku_status": {"growth": 2, "normal": 5, "risk": 1, "liquidation": 0},
                "ads_efficiency": {"ad_spend": 100, "ad_revenue": 500},
                "territorial_localization": {
                    "show": True,
                    "analysis_status_label": "Данные достаточны",
                    "summary_lines": ["Можно использовать рекомендации."],
                    "quality_rows": [{"metric": "Покрытие локализации", "value": "78.5%"}],
                    "blocked_reason_rows": [{"reason": "Недостаточно данных по размещению остатков", "count": "1"}],
                    "top_demand_regions_rows": [{"region": "Moscow", "orders": "15", "share": "45.0%"}],
                    "recommendation_rows": [
                        {
                            "sku": "SKU-1",
                            "region": "Moscow",
                            "demand_share": "45.0%",
                            "stock_share": "20.0%",
                            "gap": "25.0%",
                            "priority": "Высокий",
                            "comment": "Спрос в регионе выше доли текущих остатков",
                        }
                    ],
                    "sku_rows": [
                        {
                            "sku": "SKU-1",
                            "status": "Данные достаточны",
                            "local_share": "35.0%",
                            "non_local_orders": "12",
                            "top_region": "Moscow",
                            "recommendation": "Сместить в Moscow",
                        }
                    ],
                    "insight_counts": {"non_local_skus": 1, "mismatch_skus": 1, "candidate_skus": 1},
                },
            }
            try:
                info = write_daily_bi_pdf(pdf_path, payload)
            except FileNotFoundError:
                self.skipTest("TTF font for PDF is not available in this environment")
                return

            self.assertEqual(str(info.get("pages") or ""), "9")
            previews = info.get("preview_images", [])
            self.assertTrue(isinstance(previews, list))
            self.assertGreaterEqual(len(previews), 9)


if __name__ == "__main__":
    unittest.main()
