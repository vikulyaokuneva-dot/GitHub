from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from v4.core.contracts import RunContext, RunMode
from v4.pipeline.runners.audit_runner import run_audit_pipeline


class TestAuditRunner(unittest.TestCase):
    def test_runner_calls_stages_in_order_and_passes_output_dir(self) -> None:
        context = RunContext(
            seller_id="seller_001",
            cabinet_name=None,
            mode=RunMode.AUDIT_FILE,
            requested_date="2026-03-15",
            resolved_date="2026-03-15",
            timezone="Europe/Moscow",
            wb_api_token_present=False,
        )

        call_order: list[str] = []

        ingestion = SimpleNamespace(
            source_flags={},
            warnings=["w_ingestion"],
            raw_bundle=SimpleNamespace(diagnostics={"detected_files": {}, "missing_expected_files": []}),
        )
        normalized = SimpleNamespace()
        metrics = SimpleNamespace(warnings=[])
        facts = SimpleNamespace(warnings=[], sections={}, data_quality={})
        decisions = SimpleNamespace(warnings=[], items=[])
        outputs = {
            "artifacts": {"saved_files": {}},
            "email": SimpleNamespace(warnings=[]),
            "pdf": SimpleNamespace(warnings=[]),
        }

        with (
            patch("v4.pipeline.runners.audit_runner._coerce_run_context", return_value=context),
            patch("v4.pipeline.runners.audit_runner.build_file_raw_bundle", side_effect=lambda *_args, **_kwargs: call_order.append("ingestion") or ingestion),
            patch("v4.pipeline.runners.audit_runner.run_normalize_stage", side_effect=lambda *_args, **_kwargs: call_order.append("normalize") or normalized),
            patch("v4.pipeline.runners.audit_runner.run_metrics_stage", side_effect=lambda *_args, **_kwargs: call_order.append("metrics") or metrics),
            patch("v4.pipeline.runners.audit_runner.run_facts_stage", side_effect=lambda *_args, **_kwargs: call_order.append("facts") or facts),
            patch("v4.pipeline.runners.audit_runner.run_decisions_stage", side_effect=lambda *_args, **_kwargs: call_order.append("decisions") or decisions),
            patch("v4.pipeline.runners.audit_runner.run_outputs_stage", side_effect=lambda *args, **kwargs: call_order.append("outputs") or outputs) as outputs_mock,
            patch("v4.pipeline.runners.audit_runner.build_audit_job_diagnostics", return_value={"partial_flag": True}),
            patch("v4.pipeline.runners.audit_runner.build_audit_summary", return_value={"mode": "audit_file_mode"}),
        ):
            result = run_audit_pipeline(
                input_path="./audit_input",
                run_context={"seller_id": "seller_001"},
                output_dir="tmp_out",
            )

        self.assertEqual(call_order, ["ingestion", "normalize", "metrics", "facts", "decisions", "outputs"])
        outputs_mock.assert_called_once()
        self.assertEqual(outputs_mock.call_args.kwargs["mode"], "audit")
        self.assertEqual(outputs_mock.call_args.kwargs["output_dir"], "tmp_out")

        self.assertIn("run_context", result)
        self.assertIn("diagnostics", result)
        self.assertIn("metrics", result)
        self.assertIn("facts", result)
        self.assertIn("decisions", result)
        self.assertIn("outputs", result)


if __name__ == "__main__":
    unittest.main()
