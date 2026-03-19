from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from v4.pipeline.runners.multi_cabinet_runner import run_audit_for_sellers


class TestMultiCabinetAuditRunner(unittest.TestCase):
    def test_batch_audit_with_input_map_and_isolated_outputs(self) -> None:
        def _fake_audit_runner(*, input_path, run_context, output_dir):
            if run_context["seller_id"] == "seller_001":
                return {"diagnostics": {"summary": {"partial_flag": False}}, "warnings": []}
            raise RuntimeError("simulated audit failure")

        with tempfile.TemporaryDirectory() as tmpdir:
            input_map = {
                "seller_001": "./input_a",
                "unknown_seller": "./input_b",
            }
            with patch("v4.pipeline.runners.multi_cabinet_runner.run_audit_pipeline", side_effect=_fake_audit_runner):
                result = run_audit_for_sellers(
                    input_map=input_map,
                    run_date="2026-03-15",
                    output_root=tmpdir,
                    timezone="Europe/Moscow",
                    dry_run=True,
                )

            self.assertEqual(result["mode"], "audit")
            self.assertIn("seller_001", result["succeeded_sellers"])
            self.assertIn("unknown_seller", result["failed_sellers"])
            out_dir = Path(result["output_dirs"]["seller_001"]).resolve()
            out_dir.relative_to(Path(tmpdir).resolve())
            self.assertIn("results", result)

    def test_batch_audit_partial_classification(self) -> None:
        def _fake_audit_runner(*, input_path, run_context, output_dir):
            return {"diagnostics": {"summary": {"partial_flag": True}}, "warnings": ["w_partial"]}

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("v4.pipeline.runners.multi_cabinet_runner.run_audit_pipeline", side_effect=_fake_audit_runner):
                result = run_audit_for_sellers(
                    input_map={"seller_001": "./input_a"},
                    run_date="2026-03-15",
                    output_root=tmpdir,
                    dry_run=True,
                )

        self.assertIn("seller_001", result["partial_sellers"])
        self.assertEqual(result["failed_sellers"], [])


if __name__ == "__main__":
    unittest.main()

