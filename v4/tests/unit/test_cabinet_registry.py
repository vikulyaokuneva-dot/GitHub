from __future__ import annotations

import unittest

from v4.cabinets.registry import (
    get_cabinet_by_seller,
    get_enabled_cabinets,
    resolve_single_or_multiple_sellers,
    validate_seller_id,
)


class TestCabinetRegistry(unittest.TestCase):
    def test_validate_and_lookup_seller(self) -> None:
        self.assertTrue(validate_seller_id("seller_001"))
        self.assertFalse(validate_seller_id("unknown_seller"))

        cabinet = get_cabinet_by_seller("seller_001")
        self.assertIsNotNone(cabinet)
        assert cabinet is not None
        self.assertEqual(cabinet.seller_id, "seller_001")

    def test_get_enabled_and_resolve_single_or_multiple(self) -> None:
        enabled = get_enabled_cabinets()
        self.assertTrue(any(item.seller_id == "seller_001" for item in enabled))

        single = resolve_single_or_multiple_sellers(seller_id="seller_001")
        self.assertEqual([item.seller_id for item in single], ["seller_001"])

        multi = resolve_single_or_multiple_sellers(seller_ids=["seller_001"])
        self.assertEqual([item.seller_id for item in multi], ["seller_001"])

    def test_resolve_raises_for_unknown_seller(self) -> None:
        with self.assertRaises(KeyError):
            resolve_single_or_multiple_sellers(seller_ids=["unknown_seller"])


if __name__ == "__main__":
    unittest.main()

