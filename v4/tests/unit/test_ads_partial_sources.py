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


class TestAdsPartialSources(unittest.TestCase):
    def _context(self) -> RunContext:
        return RunContext(
            seller_id="seller_001",
            cabinet_name=None,
            mode=RunMode.DAILY_API,
            requested_date=date(2026, 3, 15),
            resolved_date=date(2026, 3, 15),
            timezone="Europe/Moscow",
            wb_api_token_present=True,
        )

    def test_campaigns_ok_stats_missing(self) -> None:
        normalized = NormalizedBundle(
            run_context=self._context(),
            ads_campaigns=[
                NormalizedAdsCampaignRecord(101, "A", "search", "active", None, None, "ads_campaigns", "c1"),
            ],
            ads_stats=[],
            source_statuses={
                "ads_campaigns": SourceStatus("ads_campaigns", SourceKind.API, SourceStatusCode.OK, False),
                "ads_stats": SourceStatus("ads_stats", SourceKind.API, SourceStatusCode.MISSING, False),
            },
        )

        ads = assemble_ads_metrics(normalized)

        self.assertEqual(ads.campaigns_count.status, "confirmed")
        self.assertEqual(ads.campaigns_count.value, 1)
        self.assertEqual(ads.active_campaigns_count.value, 1)
        self.assertIsNone(ads.impressions.value)
        self.assertEqual(ads.impressions.status, "unavailable")
        self.assertEqual(ads.source_quality["campaigns"], "ok")
        self.assertEqual(ads.source_quality["stats"], "missing")

    def test_stats_ok_campaigns_missing(self) -> None:
        normalized = NormalizedBundle(
            run_context=self._context(),
            ads_campaigns=[],
            ads_stats=[
                NormalizedAdsStatRecord(101, "2026-03-15", 100.0, 10.0, 50.0, 2.0, 120.0, "ads_stats", "s1"),
            ],
            source_statuses={
                "ads_campaigns": SourceStatus("ads_campaigns", SourceKind.API, SourceStatusCode.MISSING, False),
                "ads_stats": SourceStatus("ads_stats", SourceKind.API, SourceStatusCode.OK, False),
            },
        )

        ads = assemble_ads_metrics(normalized)

        self.assertIsNone(ads.campaigns_count.value)
        self.assertEqual(ads.campaigns_count.status, "unavailable")
        self.assertEqual(ads.impressions.value, 100.0)
        self.assertEqual(ads.clicks.value, 10.0)
        self.assertEqual(ads.spend.value, 50.0)
        self.assertEqual(ads.source_quality["campaigns"], "missing")
        self.assertEqual(ads.source_quality["stats"], "ok")


if __name__ == "__main__":
    unittest.main()

