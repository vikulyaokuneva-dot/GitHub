from __future__ import annotations

import unittest
from datetime import date

from v4.core.contracts import (
    NormalizedBundle,
    NormalizedStockRecord,
    RunContext,
    RunMode,
    SourceKind,
    SourceStatus,
    SourceStatusCode,
)
from v4.metrics.stock.assembler import assemble_stock_metrics


class TestStockAssemblerBasic(unittest.TestCase):
    def test_basic_stock_aggregation(self) -> None:
        context = RunContext(
            seller_id="seller_001",
            cabinet_name=None,
            mode=RunMode.DAILY_API,
            requested_date=date(2026, 3, 15),
            resolved_date=date(2026, 3, 15),
            timezone="Europe/Moscow",
            wb_api_token_present=True,
        )

        normalized = NormalizedBundle(
            run_context=context,
            stocks=[
                NormalizedStockRecord("r1", None, 1001, "WH-A", "M", 10, "2026-03-15", "stocks", "s1"),
                NormalizedStockRecord("r2", None, 1001, "WH-A", "L", 0, "2026-03-15", "stocks", "s2"),
                NormalizedStockRecord("r3", None, 1002, "WH-B", "M", 5, "2026-03-15", "stocks", "s3"),
            ],
            source_statuses={
                "stocks": SourceStatus("stocks", SourceKind.API, SourceStatusCode.OK, False),
            },
        )

        stock = assemble_stock_metrics(normalized)

        self.assertEqual(stock.total_stock_units.value, 15.0)
        self.assertEqual(stock.in_stock_items_count.value, 2)
        self.assertEqual(stock.out_of_stock_items_count.value, 1)
        self.assertEqual(stock.distinct_nm_ids_count.value, 2)
        self.assertEqual(stock.distinct_warehouses_count.value, 2)
        self.assertEqual(stock.source_quality.get("stocks"), "ok")


if __name__ == "__main__":
    unittest.main()
