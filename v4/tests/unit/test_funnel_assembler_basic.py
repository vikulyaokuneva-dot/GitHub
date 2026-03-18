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


class TestFunnelAssemblerBasic(unittest.TestCase):
    def test_basic_funnel_aggregation_and_conversions(self) -> None:
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
                NormalizedFunnelRecord(1, "2026-03-15", 100.0, 50.0, 25.0, 10.0, 5.0, "funnel", "f1"),
                NormalizedFunnelRecord(2, "2026-03-15", 200.0, 100.0, 50.0, 20.0, 10.0, "funnel", "f2"),
            ],
            source_statuses={
                "funnel": SourceStatus("funnel", SourceKind.API, SourceStatusCode.OK, False),
            },
        )

        funnel = assemble_funnel_metrics(normalized)

        self.assertEqual(funnel.impressions.value, 300.0)
        self.assertEqual(funnel.opens.value, 150.0)
        self.assertEqual(funnel.cart_adds.value, 75.0)
        self.assertEqual(funnel.orders.value, 30.0)
        self.assertEqual(funnel.buys.value, 15.0)
        self.assertEqual(funnel.ctr_open_from_impressions.value, 0.5)
        self.assertEqual(funnel.cr_cart_from_opens.value, 0.5)
        self.assertEqual(funnel.cr_orders_from_cart.value, 0.4)
        self.assertEqual(funnel.cr_buys_from_orders.value, 0.5)
        self.assertEqual(funnel.cr_buys_from_impressions.value, 0.05)


if __name__ == "__main__":
    unittest.main()
