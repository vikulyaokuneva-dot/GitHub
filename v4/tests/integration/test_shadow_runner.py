from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from v4.shadow.runner import run_shadow_daily


class TestShadowRunner(unittest.TestCase):
    def test_shadow_runner_writes_comparison_and_v4_outputs(self) -> None:
        fake_v4_result = {
            "outputs": {
                "artifacts": {
                    "payloads": {
                        "facts": {"sections": {}},
                        "decisions": {"summary": {"by_priority": {"P1": 0, "P2": 0, "P3": 0}}},
                        "outputs_summary": {"partial_flag": False, "warnings_count": 0},
                    }
                }
            },
            "warnings": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("v4.shadow.runner.run_daily_pipeline", return_value=fake_v4_result):
                result = run_shadow_daily(
                    seller_id="seller_001",
                    run_date="2026-03-15",
                    output_root=tmpdir,
                    run_v4=True,
                    run_legacy=False,
                )

            comparison_path = Path(tmpdir) / "comparison.json"
            self.assertTrue(comparison_path.exists())
            comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
            self.assertIn("severity", comparison)
            self.assertIn("diagnostics", result)
            self.assertIn("v4_result", result)

    def test_shadow_runner_handles_missing_legacy(self) -> None:
        fake_v4_result = {
            "outputs": {
                "artifacts": {
                    "payloads": {
                        "facts": {"sections": {}},
                        "decisions": {"summary": {"by_priority": {"P1": 0, "P2": 0, "P3": 0}}},
                        "outputs_summary": {"partial_flag": False, "warnings_count": 0},
                    }
                }
            },
            "warnings": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("v4.shadow.runner.run_daily_pipeline", return_value=fake_v4_result),
                patch("v4.shadow.runner._run_legacy_daily", return_value=(None, ["legacy unavailable"])),
            ):
                result = run_shadow_daily(
                    seller_id="seller_001",
                    run_date="2026-03-15",
                    output_root=tmpdir,
                    run_v4=True,
                    run_legacy=True,
                )

            self.assertIsNone(result["legacy_result"])
            self.assertIn("legacy unavailable", result["diagnostics"]["warnings"])
            self.assertEqual(result["comparison"]["severity"], "low")


if __name__ == "__main__":
    unittest.main()

