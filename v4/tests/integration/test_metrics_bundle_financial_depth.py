from __future__ import annotations

from datetime import date
import unittest

from v4.core.contracts import (
    NormalizedBundle,
    NormalizedOrderRecord,
    NormalizedRealizationRecord,
    NormalizedSaleRecord,
    RunContext,
    RunMode,
    SourceKind,
    SourceStatus,
    SourceStatusCode,
)
from v4.metrics.core.engine import build_metrics_bundle


class TestMetricsBundleFinancialDepth(unittest.TestCase):
    def test_extended_financial_diagnostics_present(self) -> None:
        d = date(2026, 3, 15)
        context = RunContext(
            seller_id="seller_001",
            cabinet_name=None,
            mode=RunMode.DAILY_API,
            requested_date=d,
            resolved_date=d,
            timezone="Europe/Moscow",
            wb_api_token_present=True,
        )
        normalized = NormalizedBundle(
            run_context=context,
            orders=[NormalizedOrderRecord("o1", None, 1, None, 1, 100.0, "2026-03-15", "orders", None)],
            sales=[NormalizedSaleRecord("s1", None, 1, 1, 100.0, 95.0, "2026-03-15", "sale", False, "sales", None)],
            realization=[
                NormalizedRealizationRecord("r1", None, 1, "2026-03-15", "sale", 95.0, 1.0, "realization", None, "Продажа"),
                NormalizedRealizationRecord("r2", None, 1, "2026-03-15", "logistics", 5.0, None, "realization", None, "Логистика"),
            ],
            source_statuses={
                "orders": SourceStatus("orders", SourceKind.API, SourceStatusCode.OK, True),
                "sales": SourceStatus("sales", SourceKind.API, SourceStatusCode.OK, True),
                "realization": SourceStatus("realization", SourceKind.API, SourceStatusCode.OK, True),
            },
        )

        metrics = build_metrics_bundle(normalized)

        self.assertIsNotNone(metrics.financial)
        self.assertIn("financial_component_quality", metrics.diagnostics)
        self.assertIn("financial_profit_formula_used", metrics.diagnostics)
        self.assertIn("realization_warnings_count", metrics.diagnostics)
        self.assertIn("fallback_used", metrics.diagnostics)


if __name__ == "__main__":
    unittest.main()
