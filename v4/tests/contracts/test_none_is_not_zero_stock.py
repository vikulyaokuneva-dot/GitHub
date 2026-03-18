from __future__ import annotations

import unittest
from datetime import date

from v4.core.contracts import (
    NormalizedBundle,
    RunContext,
    RunMode,
    SourceKind,
    SourceStatus,
    SourceStatusCode,
)
from v4.metrics.stock.assembler import assemble_stock_metrics


class TestNoneIsNotZeroStock(unittest.TestCase):
    def test_missing_values_remain_none(self) -> None:
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
            source_statuses={
                "stocks": SourceStatus("stocks", SourceKind.API, SourceStatusCode.MISSING, False),
            },
        )

        stock = assemble_stock_metrics(normalized)

        self.assertIsNone(stock.total_stock_units.value)
        self.assertIsNone(stock.in_stock_items_count.value)
        self.assertNotEqual(stock.total_stock_units.value, 0)
        self.assertNotEqual(stock.in_stock_items_count.value, 0)


if __name__ == "__main__":
    unittest.main()
