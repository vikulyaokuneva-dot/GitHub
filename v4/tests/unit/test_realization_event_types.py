from __future__ import annotations

import unittest

from v4.core.contracts import RawSourcePayload, SourceKind, SourceStatus, SourceStatusCode
from v4.normalization.normalizers import normalize_realization_source


class TestRealizationEventTypes(unittest.TestCase):
    def test_realization_event_type_mapping(self) -> None:
        source = RawSourcePayload(
            source_name="realization",
            payload={
                "rows": [
                    {"rrd_id": "1", "supplier_oper_name": "Продажа", "nm_id": 1},
                    {"rrd_id": "2", "supplier_oper_name": "Логистика", "nm_id": 2},
                    {"rrd_id": "3", "supplier_oper_name": "Непонятная операция", "nm_id": 3},
                ]
            },
            status=SourceStatus(
                source_name="realization",
                kind=SourceKind.API,
                status=SourceStatusCode.OK,
                is_required=True,
                rows_loaded=3,
            ),
        )

        rows = normalize_realization_source(source)
        mapping = {row.record_id: row.event_type for row in rows}

        self.assertEqual(mapping["1"], "sale")
        self.assertEqual(mapping["2"], "logistics")
        self.assertEqual(mapping["3"], "other")

    def test_realization_alias_fields_are_normalized(self) -> None:
        source = RawSourcePayload(
            source_name="realization",
            payload={
                "rows": [
                    {
                        "rrd_id": "10",
                        "operationTypeName": "Sale",
                        "nm": 555,
                        "retailPriceWithDiscRub": 1200.5,
                        "ppvzSalesCommission": 120.0,
                        "deliveryRub": 40.0,
                        "storageFee": 5.0,
                        "penaltyAmount": 1.0,
                        "ppvzForPay": 1034.5,
                    },
                    {
                        "rrd_id": "11",
                        "doc_type_name": "Penalty",
                        "nmId": 556,
                        "toPay": -10.0,
                    },
                ]
            },
            status=SourceStatus(
                source_name="realization",
                kind=SourceKind.API,
                status=SourceStatusCode.OK,
                is_required=True,
                rows_loaded=2,
            ),
        )

        rows = normalize_realization_source(source)
        self.assertEqual(len(rows), 2)

        sale_row = rows[0]
        self.assertEqual(sale_row.nm_id, 555)
        self.assertEqual(sale_row.event_type, "sale")
        self.assertEqual(sale_row.revenue_amount, 1200.5)
        self.assertEqual(sale_row.commission_amount, 120.0)
        self.assertEqual(sale_row.logistics_amount, 40.0)
        self.assertEqual(sale_row.storage_amount, 5.0)
        self.assertEqual(sale_row.penalties_amount, 1.0)
        self.assertEqual(sale_row.payout_amount, 1034.5)

        penalty_row = rows[1]
        self.assertEqual(penalty_row.event_type, "penalty")
        self.assertEqual(penalty_row.nm_id, 556)
        self.assertEqual(penalty_row.payout_amount, -10.0)


if __name__ == "__main__":
    unittest.main()
