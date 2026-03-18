from __future__ import annotations

import unittest

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


class TestOutOfStockDecision(unittest.TestCase):
    def test_out_of_stock_decision(self) -> None:
        context = RunContext(
            seller_id="seller_001",
            cabinet_name=None,
            mode=RunMode.DAILY_API,
            requested_date="2026-03-15",
            resolved_date="2026-03-15",
            timezone="Europe/Moscow",
            wb_api_token_present=True,
        )

        stock_section = FactSection(
            section_name="stock",
            title="Stock",
            status="confirmed",
            items=[
                FactItem(
                    key="out_of_stock_items_count",
                    title="Out-of-stock items count",
                    value=FactValue(value=3, status="confirmed", source="stock", note=None),
                    category="stock",
                ),
                FactItem(
                    key="in_stock_items_count",
                    title="In-stock items count",
                    value=FactValue(value=10, status="confirmed", source="stock", note=None),
                    category="stock",
                ),
            ],
        )
        facts = FactsBundle(
            run_context=context,
            sections={"stock": stock_section},
            data_quality={"partial_sections": [], "unavailable_sections": []},
        )

        decisions = build_decisions_bundle(facts)
        item = next((d for d in decisions.items if d.code == "out_of_stock_risk"), None)

        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.status, DecisionStatus.CONFIRMED)
        self.assertEqual(item.priority, DecisionPriority.P1)


if __name__ == "__main__":
    unittest.main()
