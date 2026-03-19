from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from v4.config.settings import get_settings
from v4.entry.preflight import run as run_preflight


class TestPreflightCheckPath(unittest.TestCase):
    def tearDown(self) -> None:
        get_settings.cache_clear()

    def test_preflight_daily_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = str(Path(tmpdir) / "out")
            with patch.dict(
                os.environ,
                {
                    "V4_OUTPUT_ROOT": tmpdir,
                    "V4_TEMP_ROOT": str(Path(tmpdir) / "tmp"),
                    "WB_API_TOKEN": "token",
                },
                clear=False,
            ):
                get_settings.cache_clear()
                result = run_preflight(
                    {
                        "mode": "daily",
                        "seller_id": "seller_001",
                        "run_date": "2026-03-19",
                        "output_dir": output_dir,
                        "production_mode": "v4",
                        "dry_run": False,
                    }
                )

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["seller_id"], "seller_001")
        self.assertEqual(Path(result["resolved_output_dir"]).resolve(), Path(output_dir).resolve())
        check_names = {item["name"] for item in result["checks"]}
        self.assertIn("production_mode_resolution", check_names)
        self.assertIn("artifact_path_safety", check_names)

    def test_preflight_fails_without_required_token_in_real_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "V4_OUTPUT_ROOT": tmpdir,
                    "V4_TEMP_ROOT": str(Path(tmpdir) / "tmp"),
                    "WB_API_TOKEN": "",
                },
                clear=False,
            ):
                get_settings.cache_clear()
                result = run_preflight(
                    {
                        "mode": "daily",
                        "seller_id": "seller_001",
                        "run_date": "2026-03-19",
                        "output_dir": str(Path(tmpdir) / "out"),
                        "dry_run": False,
                    }
                )

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "FAILED")
        self.assertTrue(any("WB_API_TOKEN" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()

