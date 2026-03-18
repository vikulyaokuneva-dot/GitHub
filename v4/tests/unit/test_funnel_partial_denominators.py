from __future__ import annotations

import unittest
from datetime import date

from v4.core.contracts import (
    NormalizedBundle,
    NormalizedFunnelRecord,
    RunContext,
    RunMode,
    SourceKind,
    SourceStatus,
    SourceStatusCode,
)
from v4.metrics.funnel.assembler import assemble_funnel_metrics


class TestFunnelPartialDenominators(unittest.TestCase):
    def test_zero_or_missing_denominator_does_not_create_false_zero_rate(self) -> None:
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
            funnel=[
                NormalizedFunnelRecord(1, "2026-03-15", 0.0, 10.0, None, 4.0, 2.0, "funnel", "f1"),
                NormalizedFunnelRecord(2, "2026-03-15", None, None, None, 1.0, 1.0, "funnel", "f2"),
            ],
            source_statuses={
                "funnel": SourceStatus("funnel", SourceKind.API, SourceStatusCode.PARTIAL, False),
            },
        )

        funnel = assemble_funnel_metrics(normalized)

        self.assertIsNone(funnel.ctr_open_from_impressions.value)
        self.assertIn(funnel.ctr_open_from_impressions.status, {"partial", "unavailable"})
        self.assertIsNone(funnel.cr_cart_from_opens.value)
        self.assertIn(funnel.cr_cart_from_opens.status, {"partial", "unavailable"})
        self.assertTrue(any("denominator" in warning.lower() for warning in funnel.warnings))


if __name__ == "__main__":
    unittest.main()
