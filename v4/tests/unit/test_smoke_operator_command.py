from __future__ import annotations

import unittest
from unittest.mock import patch

from v4.entry.cli import main


class TestSmokeOperatorCommand(unittest.TestCase):
    def test_smoke_command_returns_failed_code_when_smoke_failed(self) -> None:
        with patch("v4.entry.cli.run_smoke", return_value={"status": "FAILED", "mode": "daily", "dry_run": True}):
            code = main(["smoke", "--mode", "daily", "--seller", "seller_001"])
        self.assertEqual(code, 2)

    def test_smoke_command_passes_production_mode_and_shadow_flags(self) -> None:
        with patch(
            "v4.entry.cli.run_smoke",
            return_value={"status": "SUCCESS", "mode": "daily", "dry_run": True},
        ) as smoke_mock:
            code = main(
                [
                    "smoke",
                    "--mode",
                    "daily",
                    "--seller",
                    "seller_001",
                    "--production-mode",
                    "v4",
                    "--shadow",
                ]
            )
        self.assertEqual(code, 0)
        payload = smoke_mock.call_args.args[0]
        self.assertEqual(payload["production_mode"], "v4")
        self.assertTrue(payload["shadow_mode"])


if __name__ == "__main__":
    unittest.main()

