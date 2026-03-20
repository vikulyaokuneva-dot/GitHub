from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
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
from v4.outputs.artifacts.writer import AUDIT_DISCLAIMER, build_artifact_payloads, save_artifact_payloads


class TestOutputsSummaryContract(unittest.TestCase):
    def _bundles(self) -> tuple[FactsBundle, DecisionsBundle]:
        context = RunContext(
            seller_id="seller_001",
            cabinet_name=None,
            mode=RunMode.AUDIT_FILE,
            requested_date=date(2026, 3, 15),
            resolved_date=date(2026, 3, 15),
            timezone="Europe/Moscow",
            wb_api_token_present=False,
        )
        facts = FactsBundle(
            run_context=context,
            sections={
                "stock": FactSection(
                    section_name="stock",
                    title="Stock",
                    status="partial",
                    items=[FactItem("total_stock_units", "Stock units", FactValue(12, "partial", "stocks"))],
                ),
                "financial": FactSection(
                    section_name="financial",
                    title="Financial",
                    status="confirmed",
                    items=[FactItem("net_profit_like", "Net profit", FactValue(10.0, "confirmed", "financial"))],
                ),
            },
            data_quality={"partial_sections": ["stock"], "unavailable_sections": []},
            warnings=["facts warning"],
        )
        decisions = DecisionsBundle(
            run_context=context,
            items=[
                DecisionItem(
                    code="low_margin",
                    title="Low margin",
                    summary="margin is close to threshold",
                    priority=DecisionPriority.P2,
                    status=DecisionStatus.PARTIAL,
                    section="financial",
                    reason="threshold",
                )
            ],
            warnings=["decisions warning"],
        )
        return facts, decisions

    def test_outputs_summary_structure_and_normalization(self) -> None:
        facts, decisions = self._bundles()

        payloads = build_artifact_payloads(facts, decisions, mode="AUDIT")
        summary = payloads["outputs_summary"]

        self.assertEqual(
            set(summary.keys()),
            {
                "build_timestamp",
                "build_timestamp_note",
                "mode",
                "seller_id",
                "cabinet_id",
                "cabinet_name",
                "output_dir_label",
                "input_path_label",
                "feature_flags",
                "path_labels",
                "sections_present",
                "decision_counts_by_priority",
                "warnings_count",
                "partial_flag",
                "missing_sources",
                "partial_sources",
                "source_reason_map",
                "source_coverage_summary",
                "financial_model_mode",
                "financial_confidence",
                "profitability_method",
                "audit_note",
            },
        )
        self.assertIsNone(summary["build_timestamp"])
        self.assertEqual(summary["mode"], "audit")
        self.assertEqual(summary["seller_id"], "seller_001")
        self.assertEqual(summary["sections_present"], ["financial", "stock"])
        self.assertEqual(summary["decision_counts_by_priority"], {"P1": 0, "P2": 1, "P3": 0})
        self.assertEqual(summary["warnings_count"], 2)
        self.assertTrue(summary["partial_flag"])
        self.assertIn("source_reason_map", summary)
        self.assertEqual(summary["audit_note"], AUDIT_DISCLAIMER)

    def test_saved_outputs_summary_roundtrip(self) -> None:
        facts, decisions = self._bundles()
        payloads = build_artifact_payloads(facts, decisions, mode="audit")

        self.assertEqual(payloads["facts"]["run_context"]["requested_date"], "2026-03-15")
        self.assertEqual(payloads["facts"]["run_context"]["resolved_date"], "2026-03-15")
        self.assertEqual(payloads["facts"]["run_context"]["mode"], "audit_file_mode")
        self.assertEqual(payloads["decisions"]["items"][0]["priority"], "P2")
        self.assertEqual(payloads["decisions"]["items"][0]["status"], "partial")
        self.assertEqual(payloads["outputs_summary"]["audit_note"], AUDIT_DISCLAIMER)

        with tempfile.TemporaryDirectory() as tmpdir:
            written = save_artifact_payloads(payloads, tmpdir)
            summary_path = Path(written["outputs_summary"])
            saved_summary = json.loads(summary_path.read_text(encoding="utf-8"))

        self.assertEqual(saved_summary, payloads["outputs_summary"])


if __name__ == "__main__":
    unittest.main()
