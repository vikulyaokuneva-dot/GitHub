from __future__ import annotations

import unittest
from datetime import date

from v4.core.contracts import (
    NormalizedAdsStatRecord,
    NormalizedBundle,
    RunContext,
    RunMode,
    SourceKind,
    SourceStatus,
    SourceStatusCode,
)
from v4.metrics.ads.summary_assembler import assemble_ads_metrics


class TestAdsConversions(unittest.TestCase):
    def test_ctr_cpc_and_click_to_order_conversion(self) -> None:
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
            ads_stats=[
                NormalizedAdsStatRecord(101, "2026-03-15", 1000.0, 100.0, 250.0, 20.0, 1500.0, "ads_stats", "s1"),
            ],
            source_statuses={
                "ads_campaigns": SourceStatus("ads_campaigns", SourceKind.API, SourceStatusCode.MISSING, False),
                "ads_stats": SourceStatus("ads_stats", SourceKind.API, SourceStatusCode.OK, False),
            },
        )

        ads = assemble_ads_metrics(normalized)

        self.assertAlmostEqual(float(ads.ctr.value), 0.1, places=6)
        self.assertAlmostEqual(float(ads.cpc.value), 2.5, places=6)
        self.assertAlmostEqual(float(ads.conversion_click_to_order.value), 0.2, places=6)


if __name__ == "__main__":
    unittest.main()

