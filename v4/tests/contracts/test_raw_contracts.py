from __future__ import annotations

from datetime import date
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


class TestRawContracts(unittest.TestCase):
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

    def test_missing_source_not_converted_to_ok(self) -> None:
        missing_status = SourceStatus(
            source_name="funnel",
            kind=SourceKind.API,
            status=SourceStatusCode.MISSING,
            is_required=False,
            rows_loaded=None,
        )
        bundle = RawBundle(
            run_context=self._context(),
            sources={
                "funnel": RawSourcePayload(
                    source_name="funnel",
                    payload=None,
                    status=missing_status,
                )
            },
        )

        self.assertEqual(bundle.sources["funnel"].status.status, SourceStatusCode.MISSING)
        self.assertIsNone(bundle.sources["funnel"].payload)

    def test_source_status_enum_serialization(self) -> None:
        status = SourceStatus(
            source_name="orders",
            kind=SourceKind.API,
            status=SourceStatusCode.OK,
            is_required=True,
            rows_loaded=12,
        )
        self.assertEqual(status.status.value, "ok")

    def test_raw_bundle_requires_run_context(self) -> None:
        with self.assertRaises(TypeError):
            RawBundle()  # type: ignore[call-arg]


if __name__ == "__main__":
    unittest.main()
