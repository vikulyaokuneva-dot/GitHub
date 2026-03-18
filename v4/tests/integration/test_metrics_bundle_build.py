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


class TestMetricsBundleBuild(unittest.TestCase):
    def test_bundle_preserves_flags_warnings_and_diagnostics(self) -> None:
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
        source_statuses = {
            "orders": SourceStatus("orders", SourceKind.API, SourceStatusCode.OK, True),
            "sales": SourceStatus("sales", SourceKind.API, SourceStatusCode.OK, True),
            "realization": SourceStatus("realization", SourceKind.API, SourceStatusCode.PARTIAL, True),
        }

        normalized = NormalizedBundle(
            run_context=context,
            orders=[NormalizedOrderRecord("o1", None, 1, None, 1, 100.0, "2026-03-15", "orders", None)],
            sales=[NormalizedSaleRecord("s1", None, 1, 1, 100.0, 90.0, "2026-03-15", "sale", False, "sales", None)],
            realization=[NormalizedRealizationRecord("r1", None, 1, "2026-03-14", "sale", 90.0, 1.0, "realization", None)],
            source_statuses=source_statuses,
            warnings=["normalized warning"],
            diagnostics={"normalized_sources_count": 3},
        )

        metrics = build_metrics_bundle(normalized)

        self.assertIsNotNone(metrics.financial)
        self.assertIsNotNone(metrics.daily)
        self.assertIsNotNone(metrics.funnel)
        self.assertEqual(metrics.source_flags["orders"], "ok")
        self.assertEqual(metrics.source_flags["realization"], "partial")
        self.assertIn("financial_status", metrics.diagnostics)
        self.assertIn("realization_fallback_used", metrics.diagnostics)
        self.assertIn("funnel_status", metrics.diagnostics)
        self.assertIn("normalized warning", metrics.warnings)
        self.assertEqual(
            metrics.diagnostics["metrics_sections_built"],
            ["financial", "daily", "funnel", "ads", "stock"],
        )


if __name__ == "__main__":
    unittest.main()
