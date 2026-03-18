from __future__ import annotations

from datetime import date
import unittest

from v4.core.contracts import (
    NormalizedBundle,
    NormalizedRealizationRecord,
    RunContext,
    RunMode,
    SourceKind,
    SourceStatus,
    SourceStatusCode,
)
from v4.metrics.financial.assembler import assemble_financial_metrics


class TestFinancialPartialQuality(unittest.TestCase):
    def test_ambiguous_events_result_in_partial_quality(self) -> None:
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
        bundle = NormalizedBundle(
            run_context=context,
            realization=[
                NormalizedRealizationRecord("s", None, 1, "2026-03-15", "sale", 120.0, 1.0, "realization", None, None),
                NormalizedRealizationRecord("x", None, 1, "2026-03-15", "other", 11.0, None, "realization", None, None),
                NormalizedRealizationRecord("d", None, 1, "2026-03-15", "deduction", 5.0, None, "realization", None, None),
            ],
            source_statuses={
                "orders": SourceStatus("orders", SourceKind.API, SourceStatusCode.MISSING, True),
                "sales": SourceStatus("sales", SourceKind.API, SourceStatusCode.MISSING, True),
                "realization": SourceStatus("realization", SourceKind.API, SourceStatusCode.OK, True),
            },
        )

        financial = assemble_financial_metrics(bundle)

        self.assertEqual(financial.component_quality.get("commission"), "partial")
        self.assertEqual(financial.component_quality.get("acquiring"), "partial")
        self.assertEqual(financial.component_quality.get("pvz"), "partial")
        self.assertEqual(financial.component_quality.get("penalties"), "partial")
        self.assertGreaterEqual(financial.other_costs_amount.value or 0.0, 0.0)
        self.assertTrue(any("ambiguous" in warning.lower() or "partial" in warning.lower() for warning in financial.warnings))


if __name__ == "__main__":
    unittest.main()
