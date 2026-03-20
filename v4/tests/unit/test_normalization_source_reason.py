from __future__ import annotations

import unittest

from v4.core.contracts import (
    RawBundle,
    RawSourcePayload,
    RunContext,
    RunMode,
    SourceKind,
    SourceStatus,
    SourceStatusCode,
)
from v4.normalization.normalizers import build_normalized_bundle


def _context() -> RunContext:
    return RunContext(
        seller_id="seller_001",
        cabinet_name=None,
        mode=RunMode.DAILY_API,
        requested_date="2026-03-19",
        resolved_date="2026-03-19",
        timezone="Europe/Moscow",
        wb_api_token_present=True,
    )


class TestNormalizationSourceReason(unittest.TestCase):
    def test_funnel_parse_failed_reason_when_raw_nonempty_and_normalized_empty(self) -> None:
        raw_bundle = RawBundle(
            run_context=_context(),
            sources={
                "funnel": RawSourcePayload(
                    source_name="funnel",
                    payload={"rows": [1, 2, 3], "raw": [1, 2, 3], "reason": "ok"},
                    status=SourceStatus(
                        source_name="funnel",
                        kind=SourceKind.API,
                        status=SourceStatusCode.OK,
                        is_required=False,
                        rows_loaded=3,
                        debug={"funnel_reason": "ok"},
                    ),
                )
            },
            diagnostics={"source_reason_map": {"funnel": "ok"}},
        )

        normalized = build_normalized_bundle(raw_bundle)

        self.assertEqual(normalized.source_statuses["funnel"].status, SourceStatusCode.OK)
        self.assertEqual(normalized.diagnostics.get("funnel_reason"), "parse_failed")
        self.assertEqual(normalized.diagnostics.get("source_reason_map", {}).get("funnel"), "parse_failed")
        self.assertTrue(any("normalization produced no funnel records" in warning for warning in normalized.warnings))


if __name__ == "__main__":
    unittest.main()
