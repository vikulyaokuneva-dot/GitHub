from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from v4.core.contracts import RunContext, RunMode
from v4.pipeline.runners.daily_runner import run_daily_pipeline


class TestDailyRunner(unittest.TestCase):
    def test_runner_calls_stages_in_order_and_passes_output_dir(self) -> None:
        context = RunContext(
            seller_id="seller_001",
            cabinet_name=None,
            mode=RunMode.DAILY_API,
            requested_date="2026-03-15",
            resolved_date="2026-03-15",
            timezone="Europe/Moscow",
            wb_api_token_present=False,
        )

        call_order: list[str] = []

        ingestion = SimpleNamespace(source_flags={}, warnings=[])
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
            patch("v4.pipeline.runners.daily_runner._coerce_run_context", return_value=context),
            patch("v4.pipeline.runners.daily_runner.run_input_stage", side_effect=lambda *_args, **_kwargs: call_order.append("input") or ingestion),
            patch("v4.pipeline.runners.daily_runner.run_normalize_stage", side_effect=lambda *_args, **_kwargs: call_order.append("normalize") or normalized),
            patch("v4.pipeline.runners.daily_runner.run_metrics_stage", side_effect=lambda *_args, **_kwargs: call_order.append("metrics") or metrics),
            patch("v4.pipeline.runners.daily_runner.run_facts_stage", side_effect=lambda *_args, **_kwargs: call_order.append("facts") or facts),
            patch("v4.pipeline.runners.daily_runner.run_decisions_stage", side_effect=lambda *_args, **_kwargs: call_order.append("decisions") or decisions),
            patch("v4.pipeline.runners.daily_runner.run_outputs_stage", side_effect=lambda *args, **kwargs: call_order.append("outputs") or outputs) as outputs_mock,
            patch("v4.pipeline.runners.daily_runner.build_job_diagnostics", return_value={"partial_flag": True}),
            patch("v4.pipeline.runners.daily_runner.build_job_summary", return_value={"warnings_count": 0}),
        ):
            result = run_daily_pipeline(run_context={"seller_id": "seller_001"}, output_dir="tmp_out")

        self.assertEqual(call_order, ["input", "normalize", "metrics", "facts", "decisions", "outputs"])
        outputs_mock.assert_called_once()
        self.assertEqual(outputs_mock.call_args.kwargs["output_dir"], "tmp_out")

        self.assertIn("run_context", result)
        self.assertIn("diagnostics", result)
        self.assertIn("metrics", result)
        self.assertIn("facts", result)
        self.assertIn("decisions", result)
        self.assertIn("outputs", result)


if __name__ == "__main__":
    unittest.main()
