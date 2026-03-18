from __future__ import annotations

import unittest

from v4.core.contracts import RawSourcePayload, SourceKind, SourceStatus, SourceStatusCode
from v4.normalization.normalizers import normalize_orders_source


class TestOrdersNormalization(unittest.TestCase):
    def test_orders_rows_are_normalized(self) -> None:
        source = RawSourcePayload(
            source_name="orders",
            payload={
                "rows": [
                    {
                        "srid": "sr-1",
                        "sellerId": "seller_001",
                        "nmId": 12345,
                        "subjectName": "Кроссовки",
                        "quantity": 2,
                        "priceWithDisc": 1599.50,
                        "date": "2026-03-15T10:00:00",
                    },
                    {
                        "nmId": 67890,
                    },
                ]
            },
            status=SourceStatus(
                source_name="orders",
                kind=SourceKind.API,
                status=SourceStatusCode.OK,
                is_required=True,
                rows_loaded=2,
            ),
        )

        rows = normalize_orders_source(source)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].record_id, "sr-1")
        self.assertEqual(rows[0].nm_id, 12345)
        self.assertEqual(rows[0].quantity, 2.0)
        self.assertEqual(rows[0].price, 1599.5)
        self.assertEqual(rows[0].order_date, "2026-03-15")

        self.assertEqual(rows[1].nm_id, 67890)
        self.assertIsNone(rows[1].quantity)
        self.assertIsNone(rows[1].price)


if __name__ == "__main__":
    unittest.main()
