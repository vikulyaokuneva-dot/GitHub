from __future__ import annotations

import unittest
from datetime import date

from v4.core.contracts import (
    NormalizedAdsCampaignRecord,
    NormalizedAdsStatRecord,
    NormalizedBundle,
    RunContext,
    RunMode,
    SourceKind,
    SourceStatus,
    SourceStatusCode,
)
from v4.metrics.ads.summary_assembler import assemble_ads_metrics


class TestAdsBasic(unittest.TestCase):
    def test_ads_aggregates_are_calculated(self) -> None:
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
            ads_campaigns=[
                NormalizedAdsCampaignRecord(101, "A", "search", "active", None, None, "ads_campaigns", "c1"),
                NormalizedAdsCampaignRecord(102, "B", "search", "paused", None, None, "ads_campaigns", "c2"),
            ],
            ads_stats=[
                NormalizedAdsStatRecord(101, "2026-03-15", 100.0, 10.0, 50.0, 2.0, 120.0, "ads_stats", "s1"),
                NormalizedAdsStatRecord(102, "2026-03-15", 200.0, 5.0, 25.0, 1.0, 80.0, "ads_stats", "s2"),
            ],
            source_statuses={
                "ads_campaigns": SourceStatus("ads_campaigns", SourceKind.API, SourceStatusCode.OK, False),
                "ads_stats": SourceStatus("ads_stats", SourceKind.API, SourceStatusCode.OK, False),
            },
        )

        ads = assemble_ads_metrics(normalized)

        self.assertEqual(ads.campaigns_count.value, 2)
        self.assertEqual(ads.active_campaigns_count.value, 1)
        self.assertEqual(ads.impressions.value, 300.0)
        self.assertEqual(ads.clicks.value, 15.0)
        self.assertEqual(ads.spend.value, 75.0)
        self.assertEqual(ads.orders.value, 3.0)
        self.assertEqual(ads.revenue.value, 200.0)
        self.assertAlmostEqual(float(ads.ctr.value), 0.05, places=6)
        self.assertAlmostEqual(float(ads.cpc.value), 5.0, places=6)
        self.assertAlmostEqual(float(ads.conversion_click_to_order.value), 0.2, places=6)


if __name__ == "__main__":
    unittest.main()

