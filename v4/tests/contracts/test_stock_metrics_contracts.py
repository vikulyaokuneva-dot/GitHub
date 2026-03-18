from __future__ import annotations

import unittest

from v4.core.contracts import MetricStatus, MetricValue, MetricsBundle, RunContext, RunMode, StockMetricsSection


class TestStockMetricsContracts(unittest.TestCase):
    def test_stock_section_and_bundle_support_field(self) -> None:
        metric = MetricValue(value=10.0, status=MetricStatus.CONFIRMED.value, source="stocks")
        stock = StockMetricsSection(
            total_stock_units=metric,
            in_stock_items_count=metric,
            out_of_stock_items_count=metric,
            distinct_nm_ids_count=metric,
            distinct_warehouses_count=metric,
            stock_coverage_note="coverage based on current stock snapshot",
            source_quality={"stocks": "ok"},
            warnings=[],
            note=None,
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
        bundle = MetricsBundle(run_context=context, stock=stock)

        self.assertIsNotNone(bundle.stock)
        assert bundle.stock is not None
        self.assertEqual(bundle.stock.total_stock_units.value, 10.0)

    def test_none_not_replaced_with_zero(self) -> None:
        section = StockMetricsSection()
        self.assertIsNone(section.total_stock_units.value)
        self.assertNotEqual(section.total_stock_units.value, 0)


if __name__ == "__main__":
    unittest.main()
