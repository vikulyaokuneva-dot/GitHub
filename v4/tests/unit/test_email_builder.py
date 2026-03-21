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
from v4.outputs.email.builder import build_email_payload


class TestEmailBuilder(unittest.TestCase):
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
                        FactItem("revenue_gross", "Revenue gross", FactValue(1000.0, "confirmed", "financial")),
                        FactItem("seller_payout", "Seller payout", FactValue(None, "partial", "financial", "lag")),
                        FactItem("net_profit_like", "Net profit-like", FactValue(-50.0, "partial", "financial")),
                    ],
                ),
                "stock": FactSection(
                    section_name="stock",
                    title="Stock",
                    status="partial",
                    items=[
                        FactItem("total_stock_units", "Stock units", FactValue(120, "partial", "stocks")),
                        FactItem("in_stock_items_count", "In stock", FactValue(10, "confirmed", "stocks")),
                        FactItem("out_of_stock_items_count", "Out of stock", FactValue(2, "confirmed", "stocks")),
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
                    summary="profit-like is below zero",
                    priority=DecisionPriority.P1,
                    status=DecisionStatus.PARTIAL,
                    section="financial",
                    reason="net_profit_like < 0",
                )
            ],
        )
        return facts, decisions

    def test_email_payload_daily(self) -> None:
        facts, decisions = self._bundles()

        payload = build_email_payload(facts, decisions, mode="daily")

        self.assertIn("seller_001", payload.subject)
        titles = [section.title for section in payload.sections]
        self.assertIn("Финансы", titles)
        self.assertIn("Ключевые решения", titles)
        self.assertIn("Остатки / stock", titles)
        self.assertIn("Качество данных", titles)
        self.assertTrue(any("частич" in line.lower() for line in payload.summary_lines))
        self.assertFalse(any("audit_file_mode" in line for line in payload.summary_lines))

    def test_email_payload_audit_disclaimer(self) -> None:
        facts, decisions = self._bundles()

        payload = build_email_payload(facts, decisions, mode="audit")

        self.assertEqual(payload.mode, "audit")
        self.assertTrue(
            any(
                "Отчет построен в audit_file_mode; выводы ограничены доступными файлами." in line
                for line in payload.summary_lines
            )
        )

    def test_email_financial_section_marks_estimated_proxy_mode(self) -> None:
        facts, decisions = self._bundles()
        financial = facts.sections["financial"]
        financial.diagnostics = {
            "financial_model_mode": "estimated",
            "financial_confidence": "low",
            "profitability_method": "seller_payout_proxy",
            "profitability_estimate_used": True,
            "profitability_estimate_warning": "estimated/proxy: calculated without realization components",
        }

        payload = build_email_payload(facts, decisions, mode="daily")
        finance_section = next(section for section in payload.sections if section.title == "Финансы")

        self.assertTrue(any("оценка" in line.lower() for line in finance_section.lines))
        self.assertTrue(any("estimated/proxy" in line for line in finance_section.lines))


if __name__ == "__main__":
    unittest.main()
