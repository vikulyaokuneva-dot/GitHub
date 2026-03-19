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


def _health_facts(dead_value, dead_status: str, problematic_value=2) -> FactsBundle:
    health = FactSection(
        section_name="health",
        title="Health",
        status=dead_status,
        items=[
            FactItem(
                key="dead_stock_risk_count",
                title="Dead stock risk count",
                value=FactValue(value=dead_value, status=dead_status, source="health_policy_v1", note=None),
                category="health",
            ),
            FactItem(
                key="problematic_sku_count",
                title="Problematic SKU count",
                value=FactValue(value=problematic_value, status="confirmed", source="health_policy_v1", note=None),
                category="health",
            ),
        ],
    )
    return FactsBundle(
        run_context=_context(),
        sections={"health": health},
        data_quality={"partial_sections": [], "unavailable_sections": []},
    )


class TestDeadSkuDecision(unittest.TestCase):
    def test_dead_sku_decision_with_confirmed_evidence(self) -> None:
        decisions = build_decisions_bundle(_health_facts(dead_value=3, dead_status="confirmed"))
        item = next((d for d in decisions.items if d.code == "dead_sku"), None)

        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.status, DecisionStatus.CONFIRMED)
        self.assertEqual(item.priority, DecisionPriority.P2)
        self.assertTrue(item.evidence)
        self.assertEqual(item.evidence[0]["fact_section"], "health")
        self.assertEqual(item.evidence[0]["fact_key"], "dead_stock_risk_count")

    def test_partial_evidence_does_not_fake_confirmed_dead_sku(self) -> None:
        decisions = build_decisions_bundle(_health_facts(dead_value=None, dead_status="partial"))
        item = next((d for d in decisions.items if d.code == "dead_sku"), None)

        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.status, DecisionStatus.PARTIAL)
        self.assertNotEqual(item.status, DecisionStatus.CONFIRMED)


if __name__ == "__main__":
    unittest.main()

