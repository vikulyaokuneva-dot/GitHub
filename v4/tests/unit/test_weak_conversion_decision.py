from __future__ import annotations

import unittest
from datetime import date

from v4.core.contracts import (
    DecisionPriority,
    DecisionStatus,
    FactItem,
    FactSection,
    FactsBundle,
    FactValue,
    RunContext,
    RunMode,
)
from v4.decisions.builder import build_decisions_bundle


def _context() -> RunContext:
    d = date(2026, 3, 15)
    return RunContext(
        seller_id="seller_001",
        cabinet_name=None,
        mode=RunMode.DAILY_API,
        requested_date=d,
        resolved_date=d,
        timezone="Europe/Moscow",
        wb_api_token_present=True,
    )


class TestWeakConversionDecision(unittest.TestCase):
    def test_weak_conversion_rule_triggers(self) -> None:
        funnel = FactSection(
            section_name="funnel",
            title="Funnel",
            status="confirmed",
            items=[
                FactItem(
                    key="cr_buys_from_orders",
                    title="CR buys/orders",
                    value=FactValue(value=0.05, status="confirmed", source="funnel", note=None),
                    category="funnel",
                )
            ],
        )
        facts = FactsBundle(
            run_context=_context(),
            sections={"funnel": funnel},
            data_quality={"partial_sections": [], "unavailable_sections": []},
        )

        decisions = build_decisions_bundle(facts)
        item = next((d for d in decisions.items if d.code == "weak_conversion"), None)

        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.status, DecisionStatus.CONFIRMED)
        self.assertEqual(item.priority, DecisionPriority.P1)

    def test_partial_conversion_evidence_stays_partial(self) -> None:
        funnel = FactSection(
            section_name="funnel",
            title="Funnel",
            status="partial",
            items=[
                FactItem(
                    key="cr_buys_from_orders",
                    title="CR buys/orders",
                    value=FactValue(value=None, status="partial", source="funnel", note="missing denominator"),
                    category="funnel",
                )
            ],
        )
        facts = FactsBundle(
            run_context=_context(),
            sections={"funnel": funnel},
            data_quality={"partial_sections": ["funnel"], "unavailable_sections": []},
        )

        decisions = build_decisions_bundle(facts)
        item = next((d for d in decisions.items if d.code == "weak_conversion"), None)

        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.status, DecisionStatus.PARTIAL)


if __name__ == "__main__":
    unittest.main()

