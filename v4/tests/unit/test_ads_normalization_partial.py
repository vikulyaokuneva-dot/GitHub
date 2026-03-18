from __future__ import annotations

import unittest

from v4.core.contracts import RawSourcePayload, SourceKind, SourceStatus, SourceStatusCode
from v4.normalization.normalizers import normalize_ads_source


class TestAdsNormalizationPartial(unittest.TestCase):
    def test_campaigns_present_stats_missing(self) -> None:
        source = RawSourcePayload(
            source_name="ads",
            payload={
                "campaigns": {
                    "campaign_ids": [101],
                    "raw": [{"id": 101, "name": "Campaign 101", "type": "search", "status": "active"}],
                },
                "stats": {
                    "rows": None,
                    "raw_chunks": [],
                },
                "campaign_ids": [101],
            },
            status=SourceStatus(
                source_name="ads",
                kind=SourceKind.API,
                status=SourceStatusCode.PARTIAL,
                is_required=False,
                rows_loaded=1,
            ),
        )

        campaigns, stats = normalize_ads_source(source)

        self.assertEqual(len(campaigns), 1)
        self.assertEqual(campaigns[0].campaign_id, 101)
        self.assertEqual(campaigns[0].campaign_name, "Campaign 101")
        self.assertEqual(campaigns[0].source_tag, "ads_campaigns")
        self.assertEqual(stats, [])


if __name__ == "__main__":
    unittest.main()
