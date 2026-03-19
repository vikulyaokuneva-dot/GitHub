from __future__ import annotations

import unittest

from v4.config.features import FEATURE_DEFAULTS, resolve_feature_flags
from v4.config.sellers import SellerConfig


class TestFeatureFlags(unittest.TestCase):
    def test_default_flags_are_deterministic(self) -> None:
        resolved = resolve_feature_flags()
        self.assertEqual(set(resolved.keys()), set(FEATURE_DEFAULTS.keys()))
        self.assertEqual(resolved, FEATURE_DEFAULTS)

    def test_seller_and_run_overrides_are_applied(self) -> None:
        seller = SellerConfig(
            seller_id="seller_x",
            display_name="Seller X",
            feature_overrides={"enable_delivery": True, "enable_pdf_render": True},
        )
        resolved = resolve_feature_flags(
            run_context={"mode": "daily_api_mode"},
            seller_config=seller,
            run_overrides={"enable_pdf_render": False, "enable_email_preview": True},
        )

        self.assertTrue(resolved["enable_delivery"])
        self.assertFalse(resolved["enable_pdf_render"])
        self.assertTrue(resolved["enable_email_preview"])


if __name__ == "__main__":
    unittest.main()

