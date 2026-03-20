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


class TestPartialFactProducesPartialDecision(unittest.TestCase):
    def test_partial_fact_produces_partial_decision(self) -> None:
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
            status="partial",
            items=[
                FactItem(
                    key="net_profit_like",
                    title="Net profit-like",
                    value=FactValue(value=-10.0, status="partial", source="financial", note="partial source"),
                    category="financial",
                    diagnostics={"provenance": {"confidence": "low", "derivation_method": "seller_payout_proxy"}},
                )
            ],
            warnings=["partial financial evidence"],
        )
        facts = FactsBundle(
            run_context=context,
            sections={"financial": financial_section},
            data_quality={"partial_sections": ["financial"], "unavailable_sections": []},
        )

        decisions = build_decisions_bundle(facts)

        item = next((d for d in decisions.items if d.code == "negative_profit"), None)
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.status, DecisionStatus.PARTIAL)
        self.assertIn("estimated", item.summary.lower())


if __name__ == "__main__":
    unittest.main()
