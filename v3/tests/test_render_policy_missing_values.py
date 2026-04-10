import unittest

from v3.outputs.render_policy import (
    SECTION_STATE_COMPACT_NOTE,
    SECTION_STATE_FULL,
    SECTION_STATE_HIDDEN,
    SECTION_STATE_PARTIAL,
    build_kpi_display_payload,
    build_section_display_state,
    format_int_or_unknown,
    format_money_or_unknown,
    format_pct_or_unknown,
    normalize_section_state,
)


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

    def test_kpi_display_payload_prefers_fallback(self) -> None:
        payload = build_kpi_display_payload(
            value=None,
            fallback_value=4250,
            missing_reason="Нет точного значения",
            label="Чистая прибыль",
            fallback_label="Прибыль без себестоимости",
            value_type="money",
        )
        self.assertEqual(payload.get("state"), SECTION_STATE_PARTIAL)
        self.assertEqual(payload.get("label"), "Прибыль без себестоимости")
        self.assertEqual(payload.get("value"), 4250)
        self.assertEqual(payload.get("source"), "fallback")

    def test_section_state_normalization(self) -> None:
        state_payload = build_section_display_state(
            has_full_data=False,
            has_partial_data=False,
            note="Нет полной воронки",
            allow_hidden=False,
        )
        self.assertEqual(state_payload.get("state"), SECTION_STATE_COMPACT_NOTE)
        self.assertEqual(normalize_section_state("FULL"), SECTION_STATE_FULL)
        self.assertEqual(normalize_section_state("unknown", default=SECTION_STATE_HIDDEN), SECTION_STATE_HIDDEN)


if __name__ == "__main__":
    unittest.main()
