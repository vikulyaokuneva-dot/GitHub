from __future__ import annotations

import unittest

from v4.core.contracts import (
    DecisionPriority,
    DecisionStatus,
    DecisionsBundle,
    FactItem,
    FactSection,
    FactsBundle,
    FactValue,
    RunContext,
    RunMode,
    DecisionItem,
)
from v4.outputs.email.builder import build_email_payload


def _context() -> RunContext:
    return RunContext(
        seller_id="seller_001",
        cabinet_name="Main",
        mode=RunMode.DAILY_API,
        requested_date="2026-03-19",
        resolved_date="2026-03-19",
        timezone="Europe/Moscow",
        wb_api_token_present=True,
        dry_run=False,
    )


def _facts() -> FactsBundle:
    ctx = _context()
    return FactsBundle(
        run_context=ctx,
        sections={
            "financial": FactSection(
                section_name="financial",
                title="Financial",
                status="partial",
                items=[
                    FactItem("revenue_gross", "Revenue", FactValue(1200.0, "confirmed", "financial")),
                    FactItem("seller_payout", "Payout", FactValue(800.0, "confirmed", "financial")),
                    FactItem("net_profit_like", "Net", FactValue(100.0, "partial", "financial")),
                ],
            ),
            "stock": FactSection(
                section_name="stock",
                title="Stock",
                status="confirmed",
                items=[
                    FactItem("total_stock_units", "Stock", FactValue(150, "confirmed", "stocks")),
                    FactItem("in_stock_items_count", "In-stock", FactValue(12, "confirmed", "stocks")),
                    FactItem("out_of_stock_items_count", "OOS", FactValue(1, "confirmed", "stocks")),
                ],
            ),
            "health": FactSection(
                section_name="health",
                title="Health",
                status="partial",
                items=[
                    FactItem("business_health_score", "Score", FactValue(62.0, "partial", "health")),
                    FactItem("score_status", "Status", FactValue("partial", "partial", "health")),
                ],
            ),
        },
        data_quality={"partial_sections": ["health"], "unavailable_sections": ["funnel", "ads"]},
        warnings=["partial data"],
    )


def _decisions() -> DecisionsBundle:
    ctx = _context()
    return DecisionsBundle(
        run_context=ctx,
        items=[
            DecisionItem(
                code="low_margin",
                title="Low margin",
                summary="margin risk",
                priority=DecisionPriority.P2,
                status=DecisionStatus.PARTIAL,
                section="financial",
                reason="low margin evidence",
            )
        ],
    )


class TestFullEmailContainsSections(unittest.TestCase):
    def test_full_email_sections_present(self) -> None:
        payload = build_email_payload(
            _facts(),
            _decisions(),
            mode="daily",
            diagnostics={"summary": {"partial_flag": True}},
            full_debug=True,
        )
        titles = [section.title for section in payload.sections]
        expected = {
            "HEADER",
            "DATA AVAILABILITY",
            "FINANCIAL SUMMARY",
            "DAILY KPI",
            "FUNNEL",
            "ADS",
            "STOCK",
            "HEALTH",
            "DECISIONS",
            "DIAGNOSTICS",
            "FOOTER",
        }
        self.assertTrue(expected.issubset(set(titles)))


if __name__ == "__main__":
    unittest.main()

