from __future__ import annotations

import unittest

from v4.warnings_utils import dedupe_warnings, namespace_warning


class TestWarningUtils(unittest.TestCase):
    def test_dedupe_collapses_repeated_namespace_prefix(self) -> None:
        warnings = dedupe_warnings(
            [
                "health: profitability component unavailable",
                "health: health:profitability component unavailable",
            ]
        )
        self.assertEqual(warnings, ["health: profitability component unavailable"])

    def test_namespace_preserves_existing_source_prefix(self) -> None:
        text = namespace_warning("financial", "realization: source returned empty payload")
        self.assertEqual(text, "realization: source returned empty payload")


if __name__ == "__main__":
    unittest.main()
