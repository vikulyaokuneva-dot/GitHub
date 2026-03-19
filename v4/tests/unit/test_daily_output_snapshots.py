from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from v4.outputs.email.builder import AUDIT_DISCLAIMER
from v4.pipeline.runners.daily_runner import run_daily_pipeline


class TestDailyOutputSnapshots(unittest.TestCase):
    def test_daily_output_structure_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "daily_out"
            output_dir.mkdir(parents=True, exist_ok=True)

            with patch.dict(os.environ, {"WB_API_TOKEN": ""}, clear=False):
                result = run_daily_pipeline(
                    run_context={
                        "seller_id": "seller_001",
                        "run_date": "2026-03-15",
                        "timezone": "Europe/Moscow",
                    },
                    output_dir=str(output_dir),
                )

            self.assertEqual(set(result.keys()), {"run_context", "diagnostics", "metrics", "facts", "decisions", "outputs", "warnings"})
            self.assertEqual(result["run_context"].mode.value, "daily_api_mode")

            diagnostics = result["diagnostics"]
            self.assertIn("job", diagnostics)
            self.assertIn("summary", diagnostics)
            self.assertEqual(diagnostics["summary"]["mode"], "daily_api_mode")
            self.assertEqual(set(diagnostics["summary"]["decision_counts_by_priority"].keys()), {"P1", "P2", "P3"})

            outputs = result["outputs"]
            artifacts = outputs["artifacts"]
            saved_files = artifacts["saved_files"]
            self.assertEqual(set(saved_files.keys()), {"facts", "decisions", "outputs_summary"})

            for saved_path in saved_files.values():
                self.assertTrue(Path(saved_path).exists())
                Path(saved_path).resolve().relative_to(output_dir.resolve())

            facts_payload = json.loads(Path(saved_files["facts"]).read_text(encoding="utf-8"))
            decisions_payload = json.loads(Path(saved_files["decisions"]).read_text(encoding="utf-8"))
            outputs_summary = json.loads(Path(saved_files["outputs_summary"]).read_text(encoding="utf-8"))

            self.assertEqual(set(facts_payload.keys()), {"run_context", "sections", "data_quality", "warnings", "diagnostics"})
            self.assertEqual(set(decisions_payload.keys()), {"run_context", "items", "summary", "warnings", "diagnostics"})
            self.assertEqual(
                set(outputs_summary.keys()),
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
                    "audit_note",
                },
            )

            self.assertEqual(outputs_summary["mode"], "daily")
            self.assertIsNone(outputs_summary["audit_note"])
            self.assertEqual(set(outputs_summary["decision_counts_by_priority"].keys()), {"P1", "P2", "P3"})

            self.assertEqual(facts_payload["run_context"]["mode"], "daily_api_mode")
            self.assertEqual(decisions_payload["run_context"]["mode"], "daily_api_mode")

            email_payload = outputs["email"]
            pdf_payload = outputs["pdf"]
            self.assertEqual(email_payload.mode, "daily")
            self.assertFalse(any(AUDIT_DISCLAIMER in line for line in email_payload.summary_lines))
            self.assertEqual(pdf_payload.mode, "daily")
            self.assertFalse(pdf_payload.diagnostics["audit_disclaimer_included"])


if __name__ == "__main__":
    unittest.main()
