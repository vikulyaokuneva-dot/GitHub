from __future__ import annotations

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
from v4.outputs.email.contracts import EmailPayload
from v4.outputs.pdf.contracts import PdfPayload
from v4.pipeline.stages.outputs_stage import run as run_outputs_stage


class TestOutputsStage(unittest.TestCase):
    def _bundles(self) -> tuple[FactsBundle, DecisionsBundle]:
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
                    status="confirmed",
                    items=[
                        FactItem("revenue_gross", "Revenue gross", FactValue(1000.0, "confirmed", "financial")),
                        FactItem("seller_payout", "Seller payout", FactValue(800.0, "confirmed", "financial")),
                        FactItem("net_profit_like", "Net profit-like", FactValue(50.0, "confirmed", "financial")),
                    ],
                )
            },
            data_quality={"partial_sections": [], "unavailable_sections": []},
            warnings=[],
            diagnostics={"facts_sections_built": ["financial"]},
        )
        decisions = DecisionsBundle(
            run_context=context,
            items=[
                DecisionItem(
                    code="low_margin",
                    title="Low margin risk",
                    summary="net profit-like near zero",
                    priority=DecisionPriority.P2,
                    status=DecisionStatus.CONFIRMED,
                    section="financial",
                    reason="threshold rule",
                )
            ],
            summary={"total_decisions": 1},
        )
        return facts, decisions

    def test_outputs_stage_with_output_dir_writes_files(self) -> None:
        facts, decisions = self._bundles()

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_outputs_stage(facts, decisions, mode="daily", output_dir=tmpdir)

            self.assertIn("artifacts", result)
            self.assertIn("email", result)
            self.assertIn("pdf", result)
            self.assertIn("diagnostics", result)

            self.assertIsInstance(result["email"], EmailPayload)
            self.assertIsInstance(result["pdf"], PdfPayload)

            saved = result["artifacts"]["saved_files"]
            self.assertEqual(set(saved.keys()), {"facts", "decisions", "outputs_summary"})
            for file_path in saved.values():
                self.assertTrue(Path(file_path).exists())

    def test_outputs_stage_without_output_dir_does_not_write(self) -> None:
        facts, decisions = self._bundles()

        result = run_outputs_stage(facts, decisions, mode="daily", output_dir=None)

        self.assertEqual(result["artifacts"]["saved_files"], {})
        self.assertIn("payloads", result["artifacts"])


if __name__ == "__main__":
    unittest.main()
