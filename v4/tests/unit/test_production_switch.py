from __future__ import annotations

import unittest
from unittest.mock import patch

from v4.config.sellers import SellerConfig
from v4.production.switch import resolve_production_mode


class TestProductionSwitch(unittest.TestCase):
    def test_default_mode_is_legacy(self) -> None:
        decision = resolve_production_mode(seller_id="seller_001")
        self.assertEqual(decision.selected_mode.value, "legacy")
        self.assertEqual(decision.source_of_decision, "global_config")

    def test_explicit_cli_override_has_highest_precedence(self) -> None:
        decision = resolve_production_mode(
            seller_id="seller_001",
            cli_mode="v4",
            run_overrides={
                "enable_cli_production_override": True,
                "enable_v4_production": True,
                "enable_legacy_production": True,
            },
        )
        self.assertEqual(decision.selected_mode.value, "v4")
        self.assertEqual(decision.source_of_decision, "cli_override")

    def test_seller_override_applies_when_no_cli(self) -> None:
        seller = SellerConfig(
            seller_id="seller_001",
            display_name="Seller",
            mode_overrides={"production_mode": "v4"},
            feature_overrides={"enable_v4_production": True},
        )
        with patch("v4.production.switch.get_cabinet_by_seller", return_value=seller):
            decision = resolve_production_mode(
                seller_id="seller_001",
                run_overrides={"enable_legacy_production": True},
            )
        self.assertEqual(decision.selected_mode.value, "v4")
        self.assertEqual(decision.source_of_decision, "seller_config")


if __name__ == "__main__":
    unittest.main()

