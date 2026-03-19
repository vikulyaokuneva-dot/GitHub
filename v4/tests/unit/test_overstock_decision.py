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


class TestOverstockDecision(unittest.TestCase):
    def test_overstock_rule_triggers_conservatively(self) -> None:
        health = FactSection(
            section_name="health",
            title="Health",
            status="confirmed",
            items=[
                FactItem(
                    key="overstock_risk_count",
                    title="Overstock risk count",
                    value=FactValue(value=2, status="confirmed", source="health_policy_v1", note=None),
                    category="health",
                ),
                FactItem(
                    key="problematic_sku_count",
                    title="Problematic SKU count",
                    value=FactValue(value=2, status="confirmed", source="health_policy_v1", note=None),
                    category="health",
                ),
            ],
        )
        facts = FactsBundle(
            run_context=_context(),
            sections={"health": health},
            data_quality={"partial_sections": [], "unavailable_sections": []},
        )

        decisions = build_decisions_bundle(facts)
        item = next((d for d in decisions.items if d.code == "overstock"), None)

        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.status, DecisionStatus.CONFIRMED)
        self.assertEqual(item.priority, DecisionPriority.P2)

    def test_partial_overstock_evidence_is_not_confirmed(self) -> None:
        health = FactSection(
            section_name="health",
            title="Health",
            status="partial",
            items=[
                FactItem(
                    key="overstock_risk_count",
                    title="Overstock risk count",
                    value=FactValue(value=None, status="partial", source="health_policy_v1", note="insufficient movement"),
                    category="health",
                ),
                FactItem(
                    key="problematic_sku_count",
                    title="Problematic SKU count",
                    value=FactValue(value=1, status="partial", source="health_policy_v1", note=None),
                    category="health",
                ),
            ],
        )
        facts = FactsBundle(
            run_context=_context(),
            sections={"health": health},
            data_quality={"partial_sections": ["health"], "unavailable_sections": []},
        )

        decisions = build_decisions_bundle(facts)
        item = next((d for d in decisions.items if d.code == "overstock"), None)

        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.status, DecisionStatus.PARTIAL)
        self.assertNotEqual(item.status, DecisionStatus.CONFIRMED)


if __name__ == "__main__":
    unittest.main()

