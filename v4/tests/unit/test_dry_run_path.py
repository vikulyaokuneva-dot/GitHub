from __future__ import annotations

import unittest
from unittest.mock import patch

from v4.entry.daily import run as run_daily
from v4.production.switch import run_production_daily


class TestDryRunPath(unittest.TestCase):
    def test_daily_dry_run_skips_delivery_side_effects(self) -> None:
        fake_result = {
            "run_context": {},
            "diagnostics": {"summary": {"mode": "daily_api_mode", "partial_flag": False}},
            "metrics": {},
            "facts": {},
            "decisions": {},
            "outputs": {"artifacts": {"saved_files": {}}},
            "warnings": [],
        }
        with (
            patch("v4.entry.daily.run_daily_pipeline", return_value=fake_result),
            patch("v4.entry.daily.run_delivery_stage") as delivery_stage_mock,
        ):
            result = run_daily(
                {
                    "seller_id": "seller_001",
                    "run_date": "2026-03-19",
                    "dry_run": True,
                    "output_dir": ".tmp/v4_test_dry_run",
                    "render_pdf": True,
                    "email_preview": True,
                }
            )

        delivery_stage_mock.assert_not_called()
        self.assertIn("delivery", result)
        delivery_diag = result["delivery"]["diagnostics"]
        self.assertTrue(delivery_diag["dry_run"])
        self.assertIn("skipped", " ".join(delivery_diag["warnings"]))
        self.assertTrue(result["diagnostics"]["summary"]["dry_run"])

    def test_legacy_production_mode_is_blocked_for_dry_run(self) -> None:
        with self.assertRaises(ValueError):
            run_production_daily(
                seller_id="seller_001",
                run_date="2026-03-19",
                output_dir=".tmp/v4_test_dry_run",
                cli_mode="legacy",
                dry_run=True,
                run_overrides={
                    "enable_cli_production_override": True,
                    "enable_legacy_production": True,
                },
            )


if __name__ == "__main__":
    unittest.main()

