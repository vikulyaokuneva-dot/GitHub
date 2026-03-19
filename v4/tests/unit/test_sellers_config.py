from __future__ import annotations

import unittest

from v4.config.sellers import get_seller_config, list_sellers, resolve_enabled_sellers


class TestSellersConfig(unittest.TestCase):
    def test_list_sellers_and_enabled_resolution(self) -> None:
        all_sellers = list_sellers(include_disabled=True)
        enabled_sellers = list_sellers(include_disabled=False)

        self.assertGreaterEqual(len(all_sellers), 1)
        self.assertGreaterEqual(len(enabled_sellers), 1)
        self.assertTrue(all(seller.is_enabled for seller in enabled_sellers))

    def test_get_seller_config_and_overrides_are_deterministic(self) -> None:
        seller = get_seller_config("seller_001")
        self.assertEqual(seller.seller_id, "seller_001")
        self.assertIsInstance(seller.feature_overrides, dict)
        self.assertIsInstance(seller.mode_overrides, dict)

    def test_resolve_enabled_sellers_filters_requested_ids(self) -> None:
        resolved = resolve_enabled_sellers(["seller_001"])
        self.assertEqual([seller.seller_id for seller in resolved], ["seller_001"])


if __name__ == "__main__":
    unittest.main()

