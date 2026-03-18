from __future__ import annotations

import unittest

from v4.core.contracts import AdsMetricsSection, MetricValue, MetricsBundle, RunContext, RunMode
from v4.outputs.facts.builder import build_facts_bundle


def _metric(value, status="confirmed", source="ads", note=None) -> MetricValue:
    return MetricValue(value=value, status=status, source=source, note=note)


class TestAdsFactsMapping(unittest.TestCase):
    def test_ads_metrics_map_preserving_status(self) -> None:
        ads = AdsMetricsSection(
            campaigns_count=_metric(5),
            active_campaigns_count=_metric(3),
            impressions=_metric(10000.0, source="ads_stats"),
            clicks=_metric(500.0, source="ads_stats"),
            spend=_metric(1200.0, source="ads_stats"),
            ctr=_metric(0.05, source="ads_stats"),
            cpc=_metric(2.4, source="ads_stats"),
            orders=_metric(None, status="partial", source="ads_stats", note="orders partially available"),
            revenue=_metric(None, status="unavailable", source="ads_stats", note="revenue unavailable"),
            conversion_click_to_order=_metric(None, status="partial", source="ads_stats", note="denominator issue"),
            source_quality={"campaigns": "ok", "stats": "partial"},
            warnings=["ads stats field orders partially populated"],
            note="ads metrics are partial",
        )

        context = RunContext(
            seller_id="seller_001",
            cabinet_name=None,
            mode=RunMode.DAILY_API,
            requested_date="2026-03-15",
            resolved_date="2026-03-15",
            timezone="Europe/Moscow",
            wb_api_token_present=True,
        )
        metrics = MetricsBundle(run_context=context, ads=ads)

        facts = build_facts_bundle(metrics)
        section = facts.sections["ads"]
        items = {item.key: item for item in section.items}

        self.assertEqual(items["campaigns_count"].value.value, 5)
        self.assertEqual(items["orders"].value.status, "partial")
        self.assertIsNone(items["revenue"].value.value)
        self.assertEqual(items["revenue"].value.status, "unavailable")
        self.assertEqual(section.status, "partial")


if __name__ == "__main__":
    unittest.main()
