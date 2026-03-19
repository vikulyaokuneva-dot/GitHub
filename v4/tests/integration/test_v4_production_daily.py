from __future__ import annotations

import unittest
from unittest.mock import patch

from v4.production.switch import run_production_daily


class TestV4ProductionDaily(unittest.TestCase):
    def test_production_uses_v4_when_enabled(self) -> None:
        fake_v4_result = {"run_context": {}, "diagnostics": {"summary": {"mode": "daily_api_mode"}}}
        with (
            patch("v4.production.switch.run_daily_pipeline", return_value=fake_v4_result) as v4_runner,
            patch("v4.production.switch._run_legacy_daily", return_value={"status": "success"}) as legacy_runner,
        ):
            result = run_production_daily(
                seller_id="seller_001",
                run_date="2026-03-15",
                output_dir="tmp_out",
                cli_mode="v4",
                allow_fallback_to_legacy=False,
                run_overrides={
                    "enable_cli_production_override": True,
                    "enable_v4_production": True,
                    "enable_legacy_production": True,
                },
            )

        v4_runner.assert_called_once()
        legacy_runner.assert_not_called()
        self.assertEqual(result["production"]["diagnostics"]["selected_mode"], "v4")
        self.assertEqual(result["production"]["diagnostics"]["effective_runner"], "v4_daily_pipeline")

    def test_v4_failure_without_allowed_fallback_raises(self) -> None:
        with patch("v4.production.switch.run_daily_pipeline", side_effect=RuntimeError("v4 boom")):
            with self.assertRaises(RuntimeError):
                run_production_daily(
                    seller_id="seller_001",
                    run_date="2026-03-15",
                    output_dir="tmp_out",
                    cli_mode="v4",
                    allow_fallback_to_legacy=False,
                    run_overrides={
                        "enable_cli_production_override": True,
                        "enable_v4_production": True,
                        "enable_legacy_production": True,
                        "enable_production_fallback_to_legacy": False,
                    },
                )


if __name__ == "__main__":
    unittest.main()
