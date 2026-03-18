from __future__ import annotations

import unittest

from v4.core.contracts import DecisionStatus, FactsBundle, RunContext, RunMode
from v4.decisions.builder import build_decisions_bundle


class TestPartialDataWarningDecision(unittest.TestCase):
    def test_partial_data_warning_decision(self) -> None:
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
            sections={},
            data_quality={
                "partial_sections": ["financial"],
                "unavailable_sections": ["ads"],
            },
        )

        decisions = build_decisions_bundle(facts)
        item = next((d for d in decisions.items if d.code == "partial_data_warning"), None)

        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.status, DecisionStatus.INFO)
        self.assertGreaterEqual(len(item.evidence), 2)


if __name__ == "__main__":
    unittest.main()
