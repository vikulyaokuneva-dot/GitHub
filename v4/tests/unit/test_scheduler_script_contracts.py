from __future__ import annotations

import unittest
from unittest.mock import patch

from v4.scripts.scheduled_daily_run import main


class TestSchedulerScriptContracts(unittest.TestCase):
    def test_script_stops_when_preflight_fails(self) -> None:
        with patch(
            "v4.scripts.scheduled_daily_run.run_preflight",
            return_value={"ok": False, "errors": ["bad config"]},
        ):
            code = main(["--seller", "seller_001", "--production-mode", "v4"])

        self.assertEqual(code, 2)

    def test_script_runs_daily_after_successful_preflight(self) -> None:
        with (
            patch(
                "v4.scripts.scheduled_daily_run.run_preflight",
                return_value={
                    "ok": True,
                    "seller_id": "seller_001",
                    "resolved_output_dir": ".tmp/v4_sched",
                },
            ),
            patch(
                "v4.scripts.scheduled_daily_run.run_daily",
                return_value={"diagnostics": {"summary": {"mode": "daily_api_mode", "dry_run": True}}},
            ) as run_daily_mock,
        ):
            code = main(["--seller", "seller_001", "--production-mode", "v4", "--dry-run"])

        self.assertEqual(code, 0)
        payload = run_daily_mock.call_args.args[0]
        self.assertEqual(payload["seller_id"], "seller_001")
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["production_mode"], "v4")

    def test_script_passes_force_email_to_preflight_and_daily(self) -> None:
        with (
            patch(
                "v4.scripts.scheduled_daily_run.run_preflight",
                return_value={
                    "ok": True,
                    "seller_id": "seller_001",
                    "resolved_output_dir": ".tmp/v4_sched",
                },
            ) as preflight_mock,
            patch(
                "v4.scripts.scheduled_daily_run.run_daily",
                return_value={"diagnostics": {"summary": {"mode": "daily_api_mode", "dry_run": False}}},
            ) as run_daily_mock,
        ):
            code = main(["--seller", "seller_001", "--production-mode", "v4", "--force-email", "--full-email-debug"])

        self.assertEqual(code, 0)
        preflight_payload = preflight_mock.call_args.args[0]
        self.assertTrue(preflight_payload["force_email"])
        self.assertTrue(preflight_payload["full_email_debug"])
        daily_payload = run_daily_mock.call_args.args[0]
        self.assertTrue(daily_payload["force_email"])
        self.assertTrue(daily_payload["full_email_debug"])


if __name__ == "__main__":
    unittest.main()
