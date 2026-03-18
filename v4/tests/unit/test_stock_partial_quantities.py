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


class TestStockPartialQuantities(unittest.TestCase):
    def test_missing_quantity_sets_partial_and_warnings(self) -> None:
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
                NormalizedStockRecord("r2", None, 1002, "WH-A", "L", None, "2026-03-15", "stocks", "s2"),
                NormalizedStockRecord("r3", None, None, None, "XL", 0, "2026-03-15", "stocks", "s3"),
            ],
            source_statuses={
                "stocks": SourceStatus("stocks", SourceKind.API, SourceStatusCode.OK, False),
            },
        )

        stock = assemble_stock_metrics(normalized)

        self.assertEqual(stock.total_stock_units.value, 10.0)
        self.assertEqual(stock.total_stock_units.status, "partial")
        self.assertEqual(stock.in_stock_items_count.value, 1)
        self.assertEqual(stock.out_of_stock_items_count.value, 1)
        self.assertIn(stock.distinct_nm_ids_count.status, {"partial", "confirmed"})
        self.assertTrue(any("missing quantity" in warning.lower() for warning in stock.warnings))


if __name__ == "__main__":
    unittest.main()
