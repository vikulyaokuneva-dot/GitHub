from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from v4.core.contracts import (
    DecisionItem,
    DecisionPriority,
    DecisionStatus,
    DecisionsBundle,
    FactItem,
    FactSection,
    FactsBundle,
    FactValue,
    RunContext,
    RunMode,
)
from v4.outputs.artifacts.writer import build_artifact_payloads, save_artifact_payloads


class TestArtifactsWriter(unittest.TestCase):
    def _build_bundles(self) -> tuple[FactsBundle, DecisionsBundle]:
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
            sections={
                "financial": FactSection(
                    section_name="financial",
                    title="Financial",
                    status="partial",
                    items=[
                        FactItem(
                            key="net_profit_like",
                            title="Net profit-like",
                            value=FactValue(value=None, status="partial", source="financial", note="missing components"),
                            category="financial",
                        )
                    ],
                    warnings=["financial partial"],
                )
            },
            data_quality={"partial_sections": ["financial"], "unavailable_sections": []},
            warnings=["facts warning"],
        )
        decisions = DecisionsBundle(
            run_context=context,
            items=[
                DecisionItem(
                    code="negative_profit",
                    title="Negative profit",
                    summary="profit-like below zero",
                    priority=DecisionPriority.P1,
                    status=DecisionStatus.PARTIAL,
                    section="financial",
                    reason="net_profit_like < 0",
                    evidence=[{"fact_section": "financial", "fact_key": "net_profit_like", "fact_value": None, "fact_status": "partial"}],
                    recommended_actions=["recheck financial inputs"],
                )
            ],
            warnings=["decisions warning"],
        )
        return facts, decisions

    def test_artifact_payloads_serialization(self) -> None:
        facts, decisions = self._build_bundles()

        payloads = build_artifact_payloads(facts, decisions)

        self.assertIn("facts", payloads)
        self.assertIn("decisions", payloads)
        self.assertIn("outputs_summary", payloads)
        self.assertIsNone(payloads["facts"]["sections"]["financial"]["items"][0]["value"]["value"])
        self.assertEqual(payloads["decisions"]["items"][0]["priority"], "P1")
        self.assertEqual(payloads["decisions"]["items"][0]["status"], "partial")

    def test_save_artifact_payloads_writes_files(self) -> None:
        facts, decisions = self._build_bundles()
        payloads = build_artifact_payloads(facts, decisions)

        with tempfile.TemporaryDirectory() as tmpdir:
            written = save_artifact_payloads(payloads, tmpdir)
            self.assertEqual(set(written.keys()), {"facts", "decisions", "outputs_summary"})
            for path in written.values():
                file_path = Path(path)
                self.assertTrue(file_path.exists())
                loaded = json.loads(file_path.read_text(encoding="utf-8"))
                self.assertIsNotNone(loaded)


if __name__ == "__main__":
    unittest.main()
