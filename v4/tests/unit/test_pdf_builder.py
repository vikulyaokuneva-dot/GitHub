from __future__ import annotations

import unittest

from v4.core.contracts import (
    DecisionItem,
    DecisionPriority,
    DecisionStatus,
    DecisionsBundle,
    FactItem,
    FactSection,
    FactsBundle,
    FactValue,
    RunContext,
    RunMode,
)
from v4.outputs.pdf.builder import build_pdf_payload


class TestPdfBuilder(unittest.TestCase):
    def _bundles(self) -> tuple[FactsBundle, DecisionsBundle]:
        context = RunContext(
            seller_id="seller_001",
            cabinet_name=None,
            mode=RunMode.DAILY_API,
            requested_date="2026-03-15",
            resolved_date="2026-03-15",
            timezone="Europe/Moscow",
            wb_api_token_present=True,
        )
        facts = FactsBundle(
            run_context=context,
            sections={
                "financial": FactSection(
                    section_name="financial",
                    title="Financial",
                    status="partial",
                    items=[
                        FactItem("orders_count", "Orders", FactValue(10, "confirmed", "financial")),
                        FactItem("sales_amount", "Sales amount", FactValue(1000.0, "confirmed", "financial")),
                        FactItem("seller_payout", "Seller payout", FactValue(None, "partial", "financial", "lag")),
                        FactItem("revenue_gross", "Revenue gross", FactValue(1200.0, "confirmed", "financial")),
                        FactItem("net_profit_like", "Net profit", FactValue(None, "unavailable", "financial")),
                    ],
                ),
                "stock": FactSection(
                    section_name="stock",
                    title="Stock",
                    status="partial",
                    items=[
                        FactItem("total_stock_units", "Stock units", FactValue(None, "partial", "stocks")),
                        FactItem("in_stock_items_count", "In stock", FactValue(10, "confirmed", "stocks")),
                        FactItem("out_of_stock_items_count", "Out of stock", FactValue(2, "confirmed", "stocks")),
                        FactItem("distinct_nm_ids_count", "Distinct nm", FactValue(7, "confirmed", "stocks")),
                        FactItem("distinct_warehouses_count", "Distinct wh", FactValue(2, "confirmed", "stocks")),
                    ],
                ),
            },
            data_quality={"partial_sections": ["financial", "stock"], "unavailable_sections": ["ads"]},
            warnings=["partial data"],
        )
        decisions = DecisionsBundle(
            run_context=context,
            items=[
                DecisionItem(
                    code="negative_profit",
                    title="Negative profit",
                    summary="profit-like below zero",
                    priority=DecisionPriority.P1,
                    status=DecisionStatus.PARTIAL,
                    section="financial",
                    reason="net_profit_like unavailable/negative",
                )
            ],
        )
        return facts, decisions

    def test_pdf_payload_pages_and_display_policy(self) -> None:
        facts, decisions = self._bundles()

        payload = build_pdf_payload(facts, decisions, mode="daily")

        titles = [page.title for page in payload.pages]
        self.assertIn("Ключевые показатели дня", titles)
        self.assertIn("Финансы и реклама", titles)
        self.assertIn("Рекомендации", titles)
        self.assertIn("Остатки", titles)
        self.assertIn("Качество данных", titles)

        finance_page = next(page for page in payload.pages if page.title == "Финансы и реклама")
        rows = finance_page.blocks[0].rows
        payout_row = next(row for row in rows if row["label"] == "К перечислению продавцу")
        profit_row = next(row for row in rows if row["label"] == "Чистая прибыль")

        self.assertIn("нет данных", payout_row["value"])
        self.assertIn("нет данных", profit_row["value"])

    def test_pdf_finance_page_marks_estimated_proxy_mode(self) -> None:
        facts, decisions = self._bundles()
        for item in facts.sections["financial"].items:
            if item.key == "net_profit_like":
                item.value = FactValue(120.0, "partial", "financial")
            if item.key == "margin":
                item.value = FactValue(0.12, "partial", "financial")
        if not any(item.key == "margin" for item in facts.sections["financial"].items):
            facts.sections["financial"].items.append(
                FactItem("margin", "Margin", FactValue(0.12, "partial", "financial"))
            )
        facts.sections["financial"].diagnostics = {
            "financial_model_mode": "estimated",
            "profitability_estimate_used": True,
            "profitability_estimate_warning": "estimated/proxy: calculated without realization components",
        }

        payload = build_pdf_payload(facts, decisions, mode="daily")
        finance_page = next(page for page in payload.pages if page.title == "Финансы и реклама")
        rows = finance_page.blocks[0].rows

        self.assertTrue(any(row["label"] == "Чистая прибыль" and "(оценка" in row["value"] for row in rows))
        self.assertTrue(any(row["label"] == "Маржа" and "(оценка" in row["value"] for row in rows))
        self.assertTrue(
            any(
                row["label"] == "Комментарий к прибыли"
                and "Оценочный расчет, не основанный на финальной реализации" in row["value"]
                for row in rows
            )
        )


if __name__ == "__main__":
    unittest.main()
