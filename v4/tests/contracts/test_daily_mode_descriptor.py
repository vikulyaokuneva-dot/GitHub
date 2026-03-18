from __future__ import annotations

import unittest

from v4.pipeline.modes.daily_api_mode import MODE_DESCRIPTOR, describe


class TestDailyModeDescriptor(unittest.TestCase):
    def test_required_and_optional_sources(self) -> None:
        self.assertEqual(set(MODE_DESCRIPTOR.required_sources), {"orders", "sales", "realization"})
        self.assertEqual(set(MODE_DESCRIPTOR.optional_sources), {"stocks", "ads", "funnel"})

    def test_describe_shape(self) -> None:
        data = describe()
        self.assertEqual(data["mode"], "daily_api_mode")
        self.assertIn("required_sources", data)
        self.assertIn("optional_sources", data)


if __name__ == "__main__":
    unittest.main()
