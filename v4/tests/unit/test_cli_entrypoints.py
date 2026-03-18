from __future__ import annotations

import unittest
from unittest.mock import patch

from v4.entry import cli, daily


class TestCliEntrypoints(unittest.TestCase):
    def test_daily_entry_calls_runner(self) -> None:
        with patch("v4.entry.daily.run_daily_pipeline", return_value={"ok": True}) as runner:
            result = daily.run(
                {
                    "seller_id": "seller_001",
                    "run_date": "2026-03-15",
                    "output_dir": "tmp_out",
                }
            )

        self.assertEqual(result, {"ok": True})
        runner.assert_called_once()
        self.assertEqual(runner.call_args.kwargs["run_context"]["seller_id"], "seller_001")
        self.assertEqual(runner.call_args.kwargs["output_dir"], "tmp_out")

    def test_cli_daily_with_output_dir(self) -> None:
        with patch("v4.entry.cli.run_daily", return_value={"ok": True}) as run_daily_mock:
            code = cli.main([
                "daily",
                "--seller",
                "seller_001",
                "--date",
                "2026-03-15",
                "--output-dir",
                "tmp_out",
            ])

        self.assertEqual(code, 0)
        run_daily_mock.assert_called_once()
        payload = run_daily_mock.call_args.args[0]
        self.assertEqual(payload["output_dir"], "tmp_out")

    def test_cli_daily_without_output_dir(self) -> None:
        with patch("v4.entry.cli.run_daily", return_value={"ok": True}) as run_daily_mock:
            code = cli.main([
                "daily",
                "--seller",
                "seller_001",
            ])

        self.assertEqual(code, 0)
        run_daily_mock.assert_called_once()
        payload = run_daily_mock.call_args.args[0]
        self.assertIsNone(payload["output_dir"])


if __name__ == "__main__":
    unittest.main()
