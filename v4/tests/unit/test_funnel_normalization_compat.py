from __future__ import annotations

import unittest

from v4.core.contracts import RawSourcePayload, SourceKind, SourceStatus, SourceStatusCode
from v4.normalization.normalizers import normalize_funnel_source


class TestFunnelNormalizationCompat(unittest.TestCase):
    def test_normalize_from_raw_when_rows_empty(self) -> None:
        source = RawSourcePayload(
            source_name="funnel",
            payload={
                "rows": [],
                "raw": {
                    "data": {
                        "items": [
                            {
                                "product": {"nmId": 123},
                                "statistic": {
                                    "selected": {
                                        "openCardCount": 100.0,
                                        "addToCartCount": 20.0,
                                        "orderCount": 10.0,
                                        "buyoutCount": 8.0,
                                        "orderSum": 5000.0,
                                        "buyoutSum": 4200.0,
                                    }
                                },
                            }
                        ]
                    }
                },
            },
            status=SourceStatus(
                source_name="funnel",
                kind=SourceKind.API,
                status=SourceStatusCode.OK,
                is_required=False,
                rows_loaded=0,
            ),
        )

        rows = normalize_funnel_source(source)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.entity_id, 123)
        self.assertEqual(row.opens, 100.0)
        self.assertEqual(row.cart_adds, 20.0)
        self.assertEqual(row.orders, 10.0)
        self.assertEqual(row.buys, 8.0)
        self.assertEqual(row.revenue_orders, 5000.0)
        self.assertEqual(row.revenue_buyouts, 4200.0)


if __name__ == "__main__":
    unittest.main()

