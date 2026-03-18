from __future__ import annotations

import unittest

from v4.core.contracts import (
    DecisionItem,
    DecisionPriority,
    DecisionStatus,
    DecisionsBundle,
    FactSection,
    FactsBundle,
    IngestionResult,
    MetricsBundle,
    RawBundle,
    RunContext,
    RunMode,
    SourceStatusCode,
)
from v4.diagnostics.job_builder import build_job_diagnostics
from v4.diagnostics.summary import build_job_summary


class TestJobDiagnosticsBuilder(unittest.TestCase):
    def test_job_diagnostics_aggregation(self) -> None:
        context = RunContext(
            seller_id="seller_001",
            cabinet_name=None,
            mode=RunMode.DAILY_API,
            requested_date="2026-03-15",
            resolved_date="2026-03-15",
            timezone="Europe/Moscow",
            wb_api_token_present=False,
        )

        ingestion = IngestionResult(
            raw_bundle=RawBundle(run_context=context, sources={}, diagnostics={}),
            source_flags={
                "orders": SourceStatusCode.OK,
                "sales": SourceStatusCode.MISSING,
                "realization": SourceStatusCode.PARTIAL,
                "stocks": SourceStatusCode.MISSING,
            },
            warnings=["input warning"],
        )

        metrics = MetricsBundle(run_context=context, warnings=["metrics warning"])
        facts = FactsBundle(
            run_context=context,
            sections={
                "financial": FactSection(section_name="financial", title="Financial", status="partial"),
                "stock": FactSection(section_name="stock", title="Stock", status="unavailable"),
            },
            data_quality={"partial_sections": ["financial"], "unavailable_sections": ["stock"]},
            warnings=["facts warning"],
        )
        decisions = DecisionsBundle(
            run_context=context,
            items=[
                DecisionItem(
                    code="d1",
                    title="Decision 1",
                    summary="s1",
                    priority=DecisionPriority.P1,
                    status=DecisionStatus.CONFIRMED,
                    section="financial",
                    reason="r1",
                ),
                DecisionItem(
                    code="d2",
                    title="Decision 2",
                    summary="s2",
                    priority=DecisionPriority.P2,
                    status=DecisionStatus.PARTIAL,
                    section="stock",
                    reason="r2",
                ),
            ],
            warnings=["decisions warning"],
        )
        outputs_result = {
            "artifacts": {
                "saved_files": {
                    "facts": "tmp/facts.json",
                    "decisions": "tmp/decisions.json",
                }
            }
        }

        diagnostics = build_job_diagnostics(
            run_context=context,
            ingestion_result=ingestion,
            metrics_bundle=metrics,
            facts_bundle=facts,
            decisions_bundle=decisions,
            outputs_result=outputs_result,
        )
        summary = build_job_summary(diagnostics)

        self.assertEqual(diagnostics["decision_counts_by_priority"]["P1"], 1)
        self.assertEqual(diagnostics["decision_counts_by_priority"]["P2"], 1)
        self.assertIn("sales", diagnostics["missing_sources"])
        self.assertIn("section_statuses", diagnostics)
        self.assertGreaterEqual(diagnostics["warnings_count"], 4)
        self.assertTrue(diagnostics["partial_flag"])
        self.assertTrue(summary["artifacts_written"])


if __name__ == "__main__":
    unittest.main()
