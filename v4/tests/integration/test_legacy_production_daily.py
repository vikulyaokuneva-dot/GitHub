from __future__ import annotations

import unittest
from unittest.mock import patch

from v4.production.switch import run_production_daily


class TestLegacyProductionDaily(unittest.TestCase):
    def test_production_uses_legacy_by_default(self) -> None:
        fake_legacy_result = {"status": "success", "mode": "daily"}
        with (
            patch("v4.production.switch._run_legacy_daily", return_value=fake_legacy_result) as legacy_runner,
            patch("v4.production.switch.run_daily_pipeline", return_value={"ok": True}) as v4_runner,
        ):
            result = run_production_daily(
                seller_id="seller_001",
                run_date="2026-03-15",
                output_dir="tmp_out",
                cli_mode=None,
                allow_fallback_to_legacy=False,
                run_overrides={
                    "enable_legacy_production": True,
                    "enable_v4_production": False,
                },
            )

        legacy_runner.assert_called_once()
        v4_runner.assert_not_called()
        self.assertEqual(result["production"]["diagnostics"]["selected_mode"], "legacy")
        self.assertEqual(result["production"]["diagnostics"]["effective_runner"], "legacy_daily_batch")


if __name__ == "__main__":
    unittest.main()

