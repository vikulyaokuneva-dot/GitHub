from __future__ import annotations

import unittest

from v4.core.contracts import FactItem, FactSection, FactsBundle, FactValue, RunContext, RunMode


class TestFactsContracts(unittest.TestCase):
    def test_fact_contracts_creation(self) -> None:
        value = FactValue(value=10.0, status="confirmed", source="financial", note=None)
        item = FactItem(
            key="orders_count",
            title="Orders count",
            value=value,
            category="financial",
            tags=["financial", "metric"],
            diagnostics={},
        )
        section = FactSection(
            section_name="financial",
            title="Financial",
            items=[item],
            status="confirmed",
            warnings=[],
            diagnostics={},
        )

        context = RunContext(
            seller_id="seller_001",
            cabinet_name=None,
            mode=RunMode.DAILY_API,
            requested_date="2026-03-15",
            resolved_date="2026-03-15",
            timezone="Europe/Moscow",
            wb_api_token_present=True,
        )
        bundle = FactsBundle(
            run_context=context,
            sections={"financial": section},
            data_quality={},
            warnings=[],
            diagnostics={},
        )

        self.assertEqual(bundle.sections["financial"].items[0].value.value, 10.0)

    def test_none_not_replaced_with_zero(self) -> None:
        value = FactValue(value=None, status="unavailable", source=None, note="missing")
        self.assertIsNone(value.value)
        self.assertNotEqual(value.value, 0)


if __name__ == "__main__":
    unittest.main()
