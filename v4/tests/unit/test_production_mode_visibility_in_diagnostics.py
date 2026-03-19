from __future__ import annotations

import unittest
from unittest.mock import patch

from v4.entry.daily import run as run_daily


class TestProductionModeVisibilityInDiagnostics(unittest.TestCase):
    def test_direct_v4_path_has_mode_marker_in_summary(self) -> None:
        fake_result = {
            "run_context": {},
            "diagnostics": {"summary": {"mode": "daily_api_mode", "partial_flag": False}},
            "metrics": {},
            "facts": {},
            "decisions": {},
            "outputs": {"artifacts": {"saved_files": {}}},
            "warnings": [],
        }
        with patch("v4.entry.daily.run_daily_pipeline", return_value=fake_result):
            result = run_daily({"seller_id": "seller_001", "run_date": "2026-03-19", "dry_run": True})

        summary = result["diagnostics"]["summary"]
        self.assertEqual(summary["selected_production_mode"], "v4_direct")
        self.assertTrue(summary["dry_run"])

    def test_production_switch_path_keeps_selected_mode_visible(self) -> None:
        fake_result = {
            "run_result": {"ok": True},
            "production": {
                "diagnostics": {
                    "selected_mode": "v4",
                    "switch_reason": "explicit CLI production override",
                    "rollback_happened": False,
                    "dry_run": False,
                },
                "summary": {},
            },
        }
        with patch("v4.entry.daily.run_production_daily", return_value=fake_result):
            result = run_daily(
                {
                    "seller_id": "seller_001",
                    "run_date": "2026-03-19",
                    "production_mode": "v4",
                    "dry_run": True,
                }
            )

        self.assertEqual(result["production"]["diagnostics"]["selected_mode"], "v4")
        self.assertTrue(result["production"]["diagnostics"]["dry_run"])


if __name__ == "__main__":
    unittest.main()

