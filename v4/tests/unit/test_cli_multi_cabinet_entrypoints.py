from __future__ import annotations

import unittest
from unittest.mock import patch

from v4.entry import cli


class TestCliMultiCabinetEntrypoints(unittest.TestCase):
    def test_cli_daily_accepts_seller_and_sellers(self) -> None:
        with patch("v4.entry.cli.run_daily", return_value={"ok": True}) as run_daily_mock:
            code = cli.main(
                [
                    "daily",
                    "--sellers",
                    "seller_001,seller_002",
                    "--date",
                    "2026-03-15",
                    "--output-dir",
                    "tmp_out",
                ]
            )

        self.assertEqual(code, 0)
        payload = run_daily_mock.call_args.args[0]
        self.assertEqual(payload["seller_ids"], "seller_001,seller_002")
        self.assertIsNone(payload["seller_id"])

    def test_cli_audit_accepts_input_map_for_multi(self) -> None:
        with patch("v4.entry.cli.run_audit", return_value={"ok": True}) as run_audit_mock:
            code = cli.main(
                [
                    "audit",
                    "--input-map",
                    "seller_001=./in1,seller_002=./in2",
                    "--sellers",
                    "seller_001,seller_002",
                    "--date",
                    "2026-03-15",
                    "--output-dir",
                    "tmp_out",
                ]
            )

        self.assertEqual(code, 0)
        payload = run_audit_mock.call_args.args[0]
        self.assertEqual(payload["input_map"], "seller_001=./in1,seller_002=./in2")
        self.assertEqual(payload["seller_ids"], "seller_001,seller_002")

    def test_cli_single_seller_modes_still_work(self) -> None:
        with patch("v4.entry.cli.run_daily", return_value={"ok": True}) as run_daily_mock:
            code_daily = cli.main(["daily", "--seller", "seller_001"])
        self.assertEqual(code_daily, 0)
        self.assertEqual(run_daily_mock.call_args.args[0]["seller_id"], "seller_001")

        with patch("v4.entry.cli.run_audit", return_value={"ok": True}) as run_audit_mock:
            code_audit = cli.main(["audit", "--input-path", "./input", "--seller", "seller_001"])
        self.assertEqual(code_audit, 0)
        self.assertEqual(run_audit_mock.call_args.args[0]["seller_id"], "seller_001")


if __name__ == "__main__":
    unittest.main()

