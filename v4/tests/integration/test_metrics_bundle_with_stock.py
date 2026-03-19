from __future__ import annotations

import unittest
from datetime import date

from v4.core.contracts import (
    NormalizedBundle,
    NormalizedOrderRecord,
    NormalizedRealizationRecord,
    NormalizedSaleRecord,
    NormalizedStockRecord,
    RunContext,
    RunMode,
    SourceKind,
    SourceStatus,
    SourceStatusCode,
)
from v4.metrics.core.engine import build_metrics_bundle


class TestMetricsBundleWithStock(unittest.TestCase):
    def test_engine_builds_stock_and_diagnostics(self) -> None:
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
            orders=[NormalizedOrderRecord("o1", None, 1, None, 1, 100.0, "2026-03-15", "orders", None)],
            sales=[NormalizedSaleRecord("s1", None, 1, 1, 100.0, 90.0, "2026-03-15", "sale", False, "sales", None)],
            realization=[NormalizedRealizationRecord("r1", None, 1, "2026-03-15", "sale", 90.0, 1.0, "realization", None, "sale")],
            stocks=[
                NormalizedStockRecord("stk1", None, 1001, "WH-A", "M", 4, "2026-03-15", "stocks", "sr1"),
            ],
            source_statuses={
                "orders": SourceStatus("orders", SourceKind.API, SourceStatusCode.OK, True),
                "sales": SourceStatus("sales", SourceKind.API, SourceStatusCode.OK, True),
                "realization": SourceStatus("realization", SourceKind.API, SourceStatusCode.OK, True),
                "funnel": SourceStatus("funnel", SourceKind.API, SourceStatusCode.MISSING, False),
                "ads_campaigns": SourceStatus("ads_campaigns", SourceKind.API, SourceStatusCode.MISSING, False),
                "ads_stats": SourceStatus("ads_stats", SourceKind.API, SourceStatusCode.MISSING, False),
                "stocks": SourceStatus("stocks", SourceKind.API, SourceStatusCode.OK, False),
            },
        )

        metrics = build_metrics_bundle(normalized)

        self.assertIsNotNone(metrics.stock)
        self.assertIn("stock_status", metrics.diagnostics)
        self.assertIn("stock_records_count", metrics.diagnostics)
        self.assertIn("stock_warnings_count", metrics.diagnostics)
        self.assertEqual(metrics.diagnostics["metrics_sections_built"], ["financial", "daily", "funnel", "ads", "stock", "health"])


if __name__ == "__main__":
    unittest.main()
