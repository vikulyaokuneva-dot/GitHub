from __future__ import annotations

import unittest

from v4.core.contracts import (
    DecisionStatus,
    FactItem,
    FactSection,
    FactsBundle,
    FactValue,
    RunContext,
    RunMode,
)
from v4.decisions.builder import build_decisions_bundle


class TestNegativeProfitDecision(unittest.TestCase):
    def test_negative_profit_decision(self) -> None:
        context = RunContext(
            seller_id="seller_001",
            cabinet_name=None,
            mode=RunMode.DAILY_API,
            requested_date="2026-03-15",
            resolved_date="2026-03-15",
            timezone="Europe/Moscow",
            wb_api_token_present=True,
        )
        financial_section = FactSection(
            section_name="financial",
            title="Financial",
            status="confirmed",
            items=[
                FactItem(
                    key="net_profit_like",
                    title="Net profit-like",
                    value=FactValue(value=-120.0, status="confirmed", source="financial", note=None),
                    category="financial",
                )
            ],
        )
        facts = FactsBundle(
            run_context=context,
            sections={"financial": financial_section},
            data_quality={"partial_sections": [], "unavailable_sections": []},
        )

        decisions = build_decisions_bundle(facts)

        item = next((d for d in decisions.items if d.code == "negative_profit"), None)
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.status, DecisionStatus.CONFIRMED)
        self.assertEqual(item.evidence[0]["fact_section"], "financial")
        self.assertEqual(item.evidence[0]["fact_key"], "net_profit_like")
        self.assertEqual(item.evidence[0]["fact_value"], -120.0)


if __name__ == "__main__":
    unittest.main()
