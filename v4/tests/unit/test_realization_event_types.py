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


if __name__ == "__main__":
    unittest.main()
