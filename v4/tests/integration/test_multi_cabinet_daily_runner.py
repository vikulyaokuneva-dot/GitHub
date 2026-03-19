from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from v4.pipeline.runners.multi_cabinet_runner import run_daily_for_sellers


class TestMultiCabinetDailyRunner(unittest.TestCase):
    def test_batch_daily_isolated_output_dirs_and_partial_failure_tolerance(self) -> None:
        def _fake_daily_runner(*, run_context, output_dir):
            seller_id = run_context["seller_id"]
            if seller_id == "seller_001":
                return {
                    "diagnostics": {"summary": {"partial_flag": False}},
                    "warnings": [],
                }
            raise RuntimeError("simulated seller failure")

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("v4.pipeline.runners.multi_cabinet_runner.run_daily_pipeline", side_effect=_fake_daily_runner):
                result = run_daily_for_sellers(
                    seller_ids=["seller_001", "unknown_seller"],
                    run_date="2026-03-15",
                    output_root=tmpdir,
                    timezone="Europe/Moscow",
                    dry_run=True,
                )

            self.assertEqual(result["mode"], "daily")
            self.assertIn("seller_001", result["succeeded_sellers"])
            self.assertIn("unknown_seller", result["failed_sellers"])
            out_dir = Path(result["output_dirs"]["seller_001"]).resolve()
            out_dir.relative_to(Path(tmpdir).resolve())

    def test_batch_daily_one_failure_does_not_break_other_seller(self) -> None:
        def _fake_daily_runner(*, run_context, output_dir):
            if run_context["seller_id"] == "seller_001":
                return {"diagnostics": {"summary": {"partial_flag": True}}, "warnings": ["w_partial"]}
            raise RuntimeError("boom")

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("v4.pipeline.runners.multi_cabinet_runner.run_daily_pipeline", side_effect=_fake_daily_runner):
                result = run_daily_for_sellers(
                    seller_ids=["seller_001", "seller_001"],
                    run_date="2026-03-15",
                    output_root=tmpdir,
                    dry_run=True,
                )

        self.assertIn("seller_001", result["partial_sellers"])
        self.assertEqual(result["failed_sellers"], [])


if __name__ == "__main__":
    unittest.main()

