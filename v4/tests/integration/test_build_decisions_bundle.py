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
from v4.pipeline.stages.decisions_stage import run as run_decisions_stage


class TestBuildDecisionsBundle(unittest.TestCase):
    def test_integration_build_decisions_bundle(self) -> None:
        context = RunContext(
            seller_id="seller_001",
            cabinet_name=None,
            mode=RunMode.DAILY_API,
            requested_date="2026-03-15",
            resolved_date="2026-03-15",
            timezone="Europe/Moscow",
            wb_api_token_present=True,
        )

        financial = FactSection(
            section_name="financial",
            title="Financial",
            status="confirmed",
            items=[
                FactItem(
                    key="net_profit_like",
                    title="Net profit-like",
                    value=FactValue(value=-50.0, status="confirmed", source="financial", note=None),
                    category="financial",
                )
            ],
        )
        stock = FactSection(
            section_name="stock",
            title="Stock",
            status="partial",
            items=[
                FactItem(
                    key="out_of_stock_items_count",
                    title="Out-of-stock items count",
                    value=FactValue(value=2, status="partial", source="stock", note="partial stock"),
                    category="stock",
                )
            ],
            warnings=["partial stock data"],
        )

        facts = FactsBundle(
            run_context=context,
            sections={"financial": financial, "stock": stock},
            data_quality={
                "partial_sections": ["stock"],
                "unavailable_sections": ["ads"],
            },
            warnings=["facts warning"],
            diagnostics={"facts_sections_built": ["financial", "stock"]},
        )

        decisions = build_decisions_bundle(facts)

        codes = {item.code for item in decisions.items}
        self.assertIn("negative_profit", codes)
        self.assertIn("out_of_stock_risk", codes)
        self.assertIn("partial_data_warning", codes)
        self.assertEqual(decisions.summary["total_decisions"], len(decisions.items))
        self.assertIn("rules_evaluated", decisions.diagnostics)

        staged = run_decisions_stage(facts)
        self.assertEqual(len(staged.items), len(decisions.items))
        self.assertTrue(any(item.status == DecisionStatus.INFO for item in staged.items))


if __name__ == "__main__":
    unittest.main()
