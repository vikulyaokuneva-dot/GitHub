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
    RawSourcePayload,
    RunContext,
    RunMode,
    SourceKind,
    SourceStatus,
    SourceStatusCode,
)
from v4.diagnostics.audit_job_builder import build_audit_job_diagnostics


class TestAuditJobDiagnostics(unittest.TestCase):
    def _context(self) -> RunContext:
        return RunContext(
            seller_id="seller_001",
            cabinet_name=None,
            mode=RunMode.AUDIT_FILE,
            requested_date="2026-03-15",
            resolved_date="2026-03-15",
            timezone="Europe/Moscow",
            wb_api_token_present=False,
            dry_run=True,
        )

    def test_audit_job_diagnostics_aggregates_expected_fields(self) -> None:
        context = self._context()
        source_status = SourceStatus(
            source_name="realization",
            kind=SourceKind.FILE,
            status=SourceStatusCode.OK,
            is_required=True,
            rows_loaded=1,
            warnings=["w_source"],
        )
        raw_bundle = RawBundle(
            run_context=context,
            sources={"realization": RawSourcePayload("realization", {"rows": [{}]}, source_status)},
            diagnostics={
                "detected_files": {"daily_report": "daily_report.csv"},
                "missing_expected_files": ["funnel_report", "ads_report"],
                "file_source_flags": {
                    "daily_report": "ok",
                    "funnel_report": "missing",
                    "ads_report": "missing",
                },
            },
        )
        ingestion = IngestionResult(
            raw_bundle=raw_bundle,
            source_flags={"realization": SourceStatusCode.OK, "funnel": SourceStatusCode.MISSING},
            warnings=["w_ingestion"],
        )

        metrics = MetricsBundle(run_context=context, warnings=["w_metrics"])

        facts = FactsBundle(
            run_context=context,
            sections={
                "financial": FactSection(section_name="financial", title="Financial", status="partial"),
                "funnel": FactSection(section_name="funnel", title="Funnel", status="unavailable"),
            },
            data_quality={"partial_sections": ["financial"], "unavailable_sections": ["funnel"]},
            warnings=["w_facts"],
        )

        decisions = DecisionsBundle(
            run_context=context,
            items=[
                DecisionItem(
                    code="partial_data_warning",
                    title="Partial data",
                    summary="facts are partial",
                    priority=DecisionPriority.P2,
                    status=DecisionStatus.INFO,
                    section="quality",
                    reason="partial sections present",
                )
            ],
            warnings=["w_decisions"],
        )

        outputs_result = {
            "artifacts": {
                "saved_files": {
                    "facts": "/tmp/facts.json",
                    "decisions": "/tmp/decisions.json",
                }
            }
        }

        diagnostics = build_audit_job_diagnostics(
            run_context=context,
            input_path="/tmp/input",
            ingestion_result=ingestion,
            metrics_bundle=metrics,
            facts_bundle=facts,
            decisions_bundle=decisions,
            outputs_result=outputs_result,
        )

        self.assertEqual(diagnostics["mode"], "audit_file_mode")
        self.assertEqual(diagnostics["warnings_count"], 4)
        self.assertTrue(diagnostics["partial_flag"])
        self.assertIn("funnel", diagnostics["missing_sources"])
        self.assertIn("financial", diagnostics["section_statuses"])
        self.assertEqual(diagnostics["decision_counts_by_priority"]["P2"], 1)
        self.assertIn("daily_report", diagnostics["detected_files"])
        self.assertIn("funnel_report", diagnostics["missing_expected_files"])


if __name__ == "__main__":
    unittest.main()
