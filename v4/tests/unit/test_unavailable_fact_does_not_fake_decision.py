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


class TestUnavailableFactDoesNotFakeDecision(unittest.TestCase):
    def test_unavailable_fact_does_not_fake_decision(self) -> None:
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
            status="unavailable",
            items=[
                FactItem(
                    key="net_profit_like",
                    title="Net profit-like",
                    value=FactValue(value=None, status="unavailable", source="financial", note="missing"),
                    category="financial",
                )
            ],
        )
        facts = FactsBundle(
            run_context=context,
            sections={"financial": financial_section},
            data_quality={"partial_sections": [], "unavailable_sections": ["financial"]},
        )

        decisions = build_decisions_bundle(facts)

        negative = [d for d in decisions.items if d.code == "negative_profit"]
        self.assertTrue(negative)
        self.assertTrue(all(d.status != DecisionStatus.CONFIRMED for d in negative))
        self.assertEqual(negative[0].status, DecisionStatus.UNAVAILABLE)


if __name__ == "__main__":
    unittest.main()
