from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from v4.scripts.smoke_run_audit import AUDIT_DISCLAIMER, run_smoke


class TestSmokeRunAuditScript(unittest.TestCase):
    def test_smoke_run_ok_with_output_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            facts_path = Path(tmpdir) / "facts.json"
            decisions_path = Path(tmpdir) / "decisions.json"
            summary_path = Path(tmpdir) / "outputs_summary.json"
            facts_path.write_text("{}", encoding="utf-8")
            decisions_path.write_text("{}", encoding="utf-8")
            summary_path.write_text("{}", encoding="utf-8")

            fake_result = {
                "run_context": {},
                "diagnostics": {"summary": {"mode": "audit_file_mode", "partial_flag": True}},
                "metrics": {},
                "facts": {},
                "decisions": {},
                "outputs": {
                    "artifacts": {
                        "saved_files": {
                            "facts": str(facts_path),
                            "decisions": str(decisions_path),
                            "outputs_summary": str(summary_path),
                        }
                    },
                    "email": type("Email", (), {"summary_lines": [AUDIT_DISCLAIMER], "warnings": []})(),
                    "pdf": type("Pdf", (), {"warnings": []})(),
                },
                "warnings": ["w1"],
            }

            with patch("v4.scripts.smoke_run_audit.run_audit_pipeline", return_value=fake_result):
                code = run_smoke(
                    input_path="./input",
                    seller_id="seller_001",
                    run_date="2026-03-15",
                    timezone="Europe/Moscow",
                    output_dir=tmpdir,
                    dry_run=True,
                )

        self.assertEqual(code, 0)

    def test_smoke_run_without_output_dir_must_not_write(self) -> None:
        fake_result = {
            "run_context": {},
            "diagnostics": {"summary": {"mode": "audit_file_mode", "partial_flag": False}},
            "metrics": {},
            "facts": {},
            "decisions": {},
            "outputs": {
                "artifacts": {"saved_files": {}},
                "email": type("Email", (), {"summary_lines": [AUDIT_DISCLAIMER], "warnings": []})(),
                "pdf": type("Pdf", (), {"warnings": []})(),
            },
            "warnings": [],
        }
        with patch("v4.scripts.smoke_run_audit.run_audit_pipeline", return_value=fake_result):
            code = run_smoke(
                input_path="./input",
                seller_id="seller_001",
                run_date=None,
                timezone="Europe/Moscow",
                output_dir=None,
                dry_run=True,
            )

        self.assertEqual(code, 0)

    def test_smoke_run_detects_outside_output_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as outdir:
            outside = Path(tmpdir) / "facts.json"
            outside.write_text("{}", encoding="utf-8")
            fake_result = {
                "run_context": {},
                "diagnostics": {"summary": {"mode": "audit_file_mode", "partial_flag": False}},
                "metrics": {},
                "facts": {},
                "decisions": {},
                "outputs": {
                    "artifacts": {"saved_files": {"facts": str(outside)}},
                    "email": type("Email", (), {"summary_lines": [AUDIT_DISCLAIMER], "warnings": []})(),
                    "pdf": type("Pdf", (), {"warnings": []})(),
                },
                "warnings": [],
            }
            with patch("v4.scripts.smoke_run_audit.run_audit_pipeline", return_value=fake_result):
                code = run_smoke(
                    input_path="./input",
                    seller_id="seller_001",
                    run_date=None,
                    timezone="Europe/Moscow",
                    output_dir=outdir,
                    dry_run=True,
                )

        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
