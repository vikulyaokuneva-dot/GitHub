from __future__ import annotations

import unittest

from v4.core.contracts import FactItem, FactSection, FactsBundle, FactValue, RunContext, RunMode
from v4.outputs.pdf.view_model import (
    build_kpi_cards,
    format_money,
    format_percent,
    map_ads_section,
    map_finance_section,
    map_funnel_section,
    map_stock_section,
)


def _context() -> RunContext:
    return RunContext(
        seller_id="seller_001",
        cabinet_name=None,
        mode=RunMode.DAILY_API,
        requested_date="2026-03-15",
        resolved_date="2026-03-15",
        timezone="Europe/Moscow",
        wb_api_token_present=True,
    )


class TestPdfViewModel(unittest.TestCase):
    def test_format_money_and_percent_support_estimate_suffix(self) -> None:
        self.assertEqual(format_money(None), "нет данных")
        self.assertEqual(format_money(1234), "1 234 ₽")
        self.assertEqual(format_money(1234, status="estimated"), "1 234 ₽ (оценка)")

        self.assertEqual(format_percent(None), "нет данных")
        self.assertEqual(format_percent(12.34), "12.34%")
        self.assertEqual(format_percent(0.1234), "12.34%")
        self.assertEqual(format_percent(12.34, status="estimated"), "12.34% (оценка)")

    def test_mappers_build_russian_blocks(self) -> None:
        facts = FactsBundle(
            run_context=_context(),
            sections={
                "financial": FactSection(
                    section_name="financial",
                    title="Financial",
                    status="partial",
                    diagnostics={"financial_model_mode": "estimated", "profitability_estimate_used": True},
                    items=[
                        FactItem("seller_payout", "Seller payout", FactValue(1000.0, "confirmed", "financial")),
                        FactItem("net_profit_like", "Net profit", FactValue(200.0, "partial", "financial")),
                        FactItem("margin", "Margin", FactValue(0.2, "partial", "financial")),
                        FactItem("revenue_gross", "Revenue gross", FactValue(3000.0, "confirmed", "financial")),
                    ],
                ),
                "ads": FactSection(
                    section_name="ads",
                    title="Ads",
                    status="unavailable",
                    items=[],
                ),
                "funnel": FactSection(
                    section_name="funnel",
                    title="Funnel",
                    status="partial",
                    items=[FactItem("impressions", "Impressions", FactValue(10.0, "confirmed", "funnel"))],
                ),
                "stock": FactSection(
                    section_name="stock",
                    title="Stock",
                    status="partial",
                    items=[
                        FactItem("total_stock_units", "Stock units", FactValue(50, "confirmed", "stock")),
                        FactItem("in_stock_items_count", "In stock", FactValue(8, "confirmed", "stock")),
                        FactItem("out_of_stock_items_count", "Out of stock", FactValue(2, "confirmed", "stock")),
                    ],
                ),
            },
            diagnostics={"source_reason_map": {"ads": "request_failed"}},
        )

        cards = build_kpi_cards(facts)
        self.assertEqual(len(cards), 4)
        self.assertEqual(cards[0]["label"], "К перечислению продавцу")

        finance_rows = map_finance_section(facts)
        margin_row = next(row for row in finance_rows if row["label"] == "Маржа")
        self.assertIn("(оценка)", margin_row["value"])

        funnel_rows = map_funnel_section(facts)
        self.assertEqual(len(funnel_rows), 4)
        self.assertEqual(funnel_rows[1]["value"], "нет данных")

        ads_block = map_ads_section(facts)
        self.assertFalse(ads_block["has_data"])
        self.assertIn("Данные по рекламе отсутствуют", str(ads_block["message"]))

        stock_rows = map_stock_section(facts)
        self.assertEqual(len(stock_rows), 3)
        self.assertEqual(stock_rows[0]["label"], "Остаток")


if __name__ == "__main__":
    unittest.main()

