from __future__ import annotations

import unittest
from datetime import date

from v4.core.contracts import (
    AdsMetricsSection,
    MetricStatus,
    MetricValue,
    NormalizedBundle,
    RunContext,
    RunMode,
    SourceKind,
    SourceStatus,
    SourceStatusCode,
)
from v4.metrics.ads.summary_assembler import assemble_ads_metrics


class TestAdsNoneNotZero(unittest.TestCase):
    def test_contract_default_none_is_not_zero(self) -> None:
        section = AdsMetricsSection()
        self.assertIsNone(section.impressions.value)
        self.assertNotEqual(section.impressions.value, 0)

    def test_missing_stats_does_not_become_zero(self) -> None:
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
                "ads_campaigns": SourceStatus("ads_campaigns", SourceKind.API, SourceStatusCode.OK, False),
                "ads_stats": SourceStatus("ads_stats", SourceKind.API, SourceStatusCode.MISSING, False),
            },
        )

        ads = assemble_ads_metrics(normalized)

        self.assertIsNone(ads.impressions.value)
        self.assertEqual(ads.impressions.status, MetricStatus.UNAVAILABLE.value)
        self.assertIsNone(ads.clicks.value)
        self.assertIsNone(ads.ctr.value)
        self.assertIsNone(ads.cpc.value)
        self.assertIsNone(ads.conversion_click_to_order.value)


if __name__ == "__main__":
    unittest.main()

