from __future__ import annotations

import unittest
from unittest.mock import patch

from v4.config.sellers import SellerConfig
from v4.entry import cli


class TestCliManualDailyRunCommand(unittest.TestCase):
    def test_daily_manual_command_parses_expected_flags(self) -> None:
        with patch("v4.entry.cli.run_daily", return_value={"diagnostics": {"summary": {}}}) as run_daily_mock:
            code = cli.main(
                [
                    "daily",
                    "--seller",
                    "seller_001",
                    "--date",
                    "2026-03-19",
                    "--production-mode",
                    "v4",
                    "--dry-run",
                    "--full-email-debug",
                ]
            )

        self.assertEqual(code, 0)
        payload = run_daily_mock.call_args.args[0]
        self.assertEqual(payload["seller_id"], "seller_001")
        self.assertEqual(payload["run_date"], "2026-03-19")
        self.assertEqual(payload["production_mode"], "v4")
        self.assertTrue(payload["dry_run"])
        self.assertTrue(payload["full_email_debug"])

    def test_daily_uses_single_enabled_seller_when_not_provided(self) -> None:
        enabled = [SellerConfig(seller_id="seller_001", display_name="Seller 001", is_enabled=True)]
        with (
            patch("v4.entry.cli.get_enabled_cabinets", return_value=enabled),
            patch("v4.entry.cli.run_daily", return_value={"diagnostics": {"summary": {}}}) as run_daily_mock,
        ):
            code = cli.main(["daily", "--date", "2026-03-19"])

        self.assertEqual(code, 0)
        payload = run_daily_mock.call_args.args[0]
        self.assertEqual(payload["seller_id"], "seller_001")

    def test_cli_preflight_and_smoke_commands_are_available(self) -> None:
        with patch("v4.entry.cli.run_preflight", return_value={"ok": True, "status": "SUCCESS"}) as preflight_mock:
            preflight_code = cli.main(["preflight", "--mode", "daily", "--seller", "seller_001"])

        with patch("v4.entry.cli.run_smoke", return_value={"status": "SUCCESS", "mode": "daily", "dry_run": True}):
            smoke_code = cli.main(["smoke", "--mode", "daily", "--seller", "seller_001"])

        self.assertEqual(preflight_code, 0)
        self.assertEqual(smoke_code, 0)
        preflight_payload = preflight_mock.call_args.args[0]
        self.assertEqual(preflight_payload["mode"], "daily")
        self.assertEqual(preflight_payload["seller_id"], "seller_001")


if __name__ == "__main__":
    unittest.main()
