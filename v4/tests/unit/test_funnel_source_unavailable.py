from __future__ import annotations

import unittest
from datetime import date

from v4.core.contracts import NormalizedBundle, RunContext, RunMode, SourceKind, SourceStatus, SourceStatusCode
from v4.metrics.funnel.assembler import assemble_funnel_metrics


class TestFunnelSourceUnavailable(unittest.TestCase):
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
                "funnel": SourceStatus("funnel", SourceKind.API, SourceStatusCode.NOT_IMPLEMENTED, False),
            },
        )

        funnel = assemble_funnel_metrics(normalized)

        self.assertEqual(funnel.source_quality.get("funnel"), "not_implemented")
        self.assertEqual(funnel.impressions.status, "unavailable")
        self.assertIsNone(funnel.impressions.value)
        self.assertIsNotNone(funnel.note)


if __name__ == "__main__":
    unittest.main()
