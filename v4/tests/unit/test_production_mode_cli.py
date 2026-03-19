from __future__ import annotations

import unittest
from unittest.mock import patch

from v4.entry import cli


class TestProductionModeCli(unittest.TestCase):
    def test_cli_parses_production_mode_flags(self) -> None:
        with patch("v4.entry.cli.run_daily", return_value={"ok": True}) as run_daily_mock:
            code = cli.main(
                [
                    "daily",
                    "--seller",
                    "seller_001",
                    "--date",
                    "2026-03-15",
                    "--production-mode",
                    "v4",
                    "--allow-fallback-to-legacy",
                ]
            )

        self.assertEqual(code, 0)
        payload = run_daily_mock.call_args.args[0]
        self.assertEqual(payload["production_mode"], "v4")
        self.assertTrue(payload["allow_fallback_to_legacy"])

    def test_cli_handles_shadow_mode_flag(self) -> None:
        with patch("v4.entry.cli.run_daily", return_value={"ok": True}) as run_daily_mock:
            code = cli.main(
                [
                    "daily",
                    "--seller",
                    "seller_001",
                    "--shadow-mode",
                ]
            )

        self.assertEqual(code, 0)
        payload = run_daily_mock.call_args.args[0]
        self.assertTrue(payload["shadow_mode"])

    def test_conflicting_flags_are_safe(self) -> None:
        with patch("v4.entry.cli.run_daily", return_value={"ok": True}) as run_daily_mock:
            code = cli.main(
                [
                    "daily",
                    "--seller",
                    "seller_001",
                    "--production-mode",
                    "legacy",
                    "--shadow-mode",
                ]
            )

        self.assertEqual(code, 0)
        payload = run_daily_mock.call_args.args[0]
        self.assertEqual(payload["production_mode"], "legacy")
        self.assertTrue(payload["shadow_mode"])


if __name__ == "__main__":
    unittest.main()

