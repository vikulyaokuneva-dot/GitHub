from __future__ import annotations

import unittest
from datetime import date

from v4.core.contracts import NormalizedBundle, RunContext, RunMode, SourceKind, SourceStatus, SourceStatusCode
from v4.metrics.stock.assembler import assemble_stock_metrics


class TestStockSourceUnavailable(unittest.TestCase):
    def test_source_missing_is_safe(self) -> None:
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

        self.assertEqual(stock.source_quality.get("stocks"), "missing")
        self.assertEqual(stock.total_stock_units.status, "unavailable")
        self.assertIsNone(stock.total_stock_units.value)
        self.assertEqual(stock.stock_coverage_note, "stock source unavailable")

    def test_source_not_implemented_is_safe(self) -> None:
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
                "stocks": SourceStatus("stocks", SourceKind.API, SourceStatusCode.NOT_IMPLEMENTED, False),
            },
        )

        stock = assemble_stock_metrics(normalized)

        self.assertEqual(stock.source_quality.get("stocks"), "not_implemented")
        self.assertEqual(stock.total_stock_units.status, "unavailable")
        self.assertIsNone(stock.total_stock_units.value)


if __name__ == "__main__":
    unittest.main()
