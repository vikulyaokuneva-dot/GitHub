from __future__ import annotations

import unittest

from v4.core.contracts import MetricValue, MetricsBundle, RunContext, RunMode, StockMetricsSection
from v4.outputs.facts.builder import build_facts_bundle


def _metric(value, status="confirmed", source="stocks", note=None) -> MetricValue:
    return MetricValue(value=value, status=status, source=source, note=note)


class TestStockFactsMapping(unittest.TestCase):
    def test_stock_metrics_map_preserving_none(self) -> None:
        stock = StockMetricsSection(
            total_stock_units=_metric(None, status="partial", note="known quantities are incomplete"),
            in_stock_items_count=_metric(10),
            out_of_stock_items_count=_metric(2),
            distinct_nm_ids_count=_metric(8),
            distinct_warehouses_count=_metric(3),
            stock_coverage_note="partial stock quantities",
            source_quality={"stocks": "partial"},
            warnings=["stock records contain missing quantity values"],
            note="stock metrics available with warnings",
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
        metrics = MetricsBundle(run_context=context, stock=stock)

        facts = build_facts_bundle(metrics)
        section = facts.sections["stock"]
        items = {item.key: item for item in section.items}

        self.assertIsNone(items["total_stock_units"].value.value)
        self.assertEqual(items["total_stock_units"].value.status, "partial")
        self.assertNotEqual(items["total_stock_units"].value.value, 0)
        self.assertEqual(section.diagnostics.get("stock_coverage_note"), "partial stock quantities")


if __name__ == "__main__":
    unittest.main()
