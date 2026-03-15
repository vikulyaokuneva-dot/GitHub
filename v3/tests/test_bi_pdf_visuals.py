import os
import tempfile
import unittest

from v3.pdf_render import write_daily_bi_pdf


class TestBiPdfVisuals(unittest.TestCase):
    def test_write_daily_bi_pdf_generates_pdf_and_previews(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf_path = os.path.join(tmp_dir, "report.pdf")
            payload = {
                "seller_id": "seller_001",
                "run_date": "2026-03-16",
                "operational_day": "2026-03-15",
                "preview_dir": tmp_dir,
                "kpi_cards": [
                    {"label": "Выручка", "value": 1837, "value_type": "money"},
                    {"label": "Чистая прибыль", "value": 661, "value_type": "money"},
                    {"label": "Расход на рекламу", "value": 644, "value_type": "money"},
                    {"label": "Заказы", "value": 5, "value_type": "int"},
                ],
                "expense_structure": {
                    "commission": 310,
                    "logistics": 120,
                    "storage": 38,
                    "ads": 644,
                    "cost_price": 540,
                    "tax": 77,
                },
                "funnel": {
                    "views": 4100,
                    "add_to_cart": 420,
                    "orders": 95,
                    "buyouts": 70,
                },
                "sku_status": {
                    "growth": 7,
                    "normal": 23,
                    "risk": 6,
                    "liquidation": 2,
                },
                "ads_efficiency": {
                    "ad_spend": 644,
                    "ad_revenue": 1837,
                },
            }
            try:
                font_info = write_daily_bi_pdf(pdf_path, payload)
            except FileNotFoundError:
                self.skipTest("TTF font for PDF is not available in this environment")
                return

            self.assertTrue(os.path.isfile(pdf_path))
            self.assertEqual(str(font_info.get("pages")), "3")
            previews = font_info.get("preview_images", [])
            self.assertTrue(isinstance(previews, list))
            self.assertGreaterEqual(len(previews), 3)
            for preview in previews[:3]:
                self.assertTrue(os.path.isfile(str(preview)))


if __name__ == "__main__":
    unittest.main()
