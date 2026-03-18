from __future__ import annotations

import unittest

from v4.core.contracts import RawSourcePayload, SourceKind, SourceStatus, SourceStatusCode
from v4.normalization.normalizers import normalize_funnel_source


class TestFunnelNotImplemented(unittest.TestCase):
    def test_not_implemented_source_returns_empty(self) -> None:
        source = RawSourcePayload(
            source_name="funnel",
            payload={
                "rows": [{"nmId": 123, "views": 10}],
            },
            status=SourceStatus(
                source_name="funnel",
                kind=SourceKind.API,
                status=SourceStatusCode.NOT_IMPLEMENTED,
                is_required=False,
                rows_loaded=None,
            ),
        )

        rows = normalize_funnel_source(source)

        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
