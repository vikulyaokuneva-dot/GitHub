from __future__ import annotations

import unittest

from v4.extraction_compat import (
    _find_first_list,
    _normalize_items,
    _try_json_loads,
    extract_rows_with_meta,
)


class TestExtractionCompat(unittest.TestCase):
    def test_try_json_loads_parses_json_strings(self) -> None:
        payload = _try_json_loads('{"rows":[{"id":1}]}')
        self.assertIsInstance(payload, dict)
        assert isinstance(payload, dict)
        self.assertIn("rows", payload)

    def test_find_first_list_recurses_nested_payload(self) -> None:
        rows = _find_first_list({"result": {"data": {"items": [{"id": 1}]}}})
        self.assertEqual(rows, [{"id": 1}])

    def test_normalize_items_supports_list_and_single_dict_fallback(self) -> None:
        rows = _normalize_items([{"id": 1}, {"id": 2}])
        self.assertEqual(len(rows), 2)

        fallback_rows = _normalize_items(
            {"nmId": 123, "views": 10},
            allow_single_dict=True,
            row_like_keys=("nmId", "views"),
        )
        self.assertEqual(len(fallback_rows), 1)
        self.assertEqual(fallback_rows[0].get("nmId"), 123)

    def test_extract_rows_with_meta_returns_origin_and_mode(self) -> None:
        rows, meta = extract_rows_with_meta(
            {"payload": {"result": {"products": [{"id": 7}]}}},
            preferred_keys=("rows", "products", "result"),
        )
        self.assertEqual(rows, [{"id": 7}])
        self.assertEqual(meta.get("mode"), "recursive_list")
        self.assertEqual(meta.get("origin"), "payload.result.products")
        self.assertTrue(meta.get("compat_used"))


if __name__ == "__main__":
    unittest.main()

