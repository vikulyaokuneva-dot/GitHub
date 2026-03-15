import math
import unittest

from v3.outputs.render_policy import format_int_or_unknown, format_money_or_unknown, format_pct_or_unknown


class TestRenderPolicyMissingValues(unittest.TestCase):
    def test_missing_literals_are_formatted_as_unknown(self) -> None:
        values = [None, float("nan"), "null", "NaN", "unknown", "not_confirmed"]
        for value in values:
            self.assertEqual(format_int_or_unknown(value, unknown_label="нет данных"), "нет данных")
            self.assertEqual(format_money_or_unknown(value, unknown_label="нет данных"), "нет данных")
            self.assertEqual(
                format_pct_or_unknown(value, unknown_label="недостаточно данных для расчета"),
                "недостаточно данных для расчета",
            )

    def test_non_missing_values_still_format(self) -> None:
        self.assertEqual(format_int_or_unknown(12, unknown_label="нет данных"), "12")
        self.assertEqual(format_money_or_unknown(1250, unknown_label="нет данных", decimals=0), "1 250")
        self.assertEqual(format_pct_or_unknown(15.55, unknown_label="нет данных", decimals=1), "15.6 %")


if __name__ == "__main__":
    unittest.main()
