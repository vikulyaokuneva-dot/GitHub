from __future__ import annotations

from datetime import date
import unittest
from unittest.mock import patch

from v4.core.contracts import (
    RawSourcePayload,
    RunContext,
    RunMode,
    SourceKind,
    SourceStatus,
    SourceStatusCode,
)
from v4.ingestion.bundle import build_api_raw_bundle


def make_payload(
    source_name: str,
    *,
    status: SourceStatusCode,
    is_required: bool,
    kind: SourceKind = SourceKind.API,
) -> RawSourcePayload:
    return RawSourcePayload(
        source_name=source_name,
        payload={"rows": None},
        status=SourceStatus(
            source_name=source_name,
            kind=kind,
            status=status,
            is_required=is_required,
            rows_loaded=None,
        ),
    )


class TestBundlePartialBehavior(unittest.TestCase):
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

    def test_optional_failure_keeps_bundle_valid(self) -> None:
        ctx = self._context()
        with (
            patch("v4.ingestion.bundle.WBApiClient", return_value=object()),
            patch("v4.ingestion.bundle.load_orders", return_value=make_payload("orders", status=SourceStatusCode.OK, is_required=True)),
            patch("v4.ingestion.bundle.load_sales", return_value=make_payload("sales", status=SourceStatusCode.OK, is_required=True)),
            patch("v4.ingestion.bundle.load_realization", return_value=make_payload("realization", status=SourceStatusCode.OK, is_required=True)),
            patch("v4.ingestion.bundle.load_stocks", return_value=make_payload("stocks", status=SourceStatusCode.ERROR, is_required=False)),
            patch("v4.ingestion.bundle.load_ads_campaigns", return_value=make_payload("ads_campaigns", status=SourceStatusCode.OK, is_required=False)),
            patch("v4.ingestion.bundle.load_ads_stats", return_value=make_payload("ads_stats", status=SourceStatusCode.MISSING, is_required=False)),
            patch("v4.ingestion.bundle.load_ads_bundle", return_value=make_payload("ads", status=SourceStatusCode.PARTIAL, is_required=False)),
            patch("v4.ingestion.bundle.load_funnel", return_value=make_payload("funnel", status=SourceStatusCode.MISSING, is_required=False)),
        ):
            result = build_api_raw_bundle(ctx)

        self.assertEqual(result.source_flags["stocks"], SourceStatusCode.ERROR)
        self.assertTrue(result.raw_bundle.diagnostics["required_sources_ok"])
        self.assertIn("ads", result.raw_bundle.sources)

    def test_required_failure_reflected_in_diagnostics(self) -> None:
        ctx = self._context()
        with (
            patch("v4.ingestion.bundle.WBApiClient", return_value=object()),
            patch("v4.ingestion.bundle.load_orders", return_value=make_payload("orders", status=SourceStatusCode.ERROR, is_required=True)),
            patch("v4.ingestion.bundle.load_sales", return_value=make_payload("sales", status=SourceStatusCode.OK, is_required=True)),
            patch("v4.ingestion.bundle.load_realization", return_value=make_payload("realization", status=SourceStatusCode.OK, is_required=True)),
            patch("v4.ingestion.bundle.load_stocks", return_value=make_payload("stocks", status=SourceStatusCode.OK, is_required=False)),
            patch("v4.ingestion.bundle.load_ads_campaigns", return_value=make_payload("ads_campaigns", status=SourceStatusCode.MISSING, is_required=False)),
            patch("v4.ingestion.bundle.load_ads_stats", return_value=make_payload("ads_stats", status=SourceStatusCode.MISSING, is_required=False)),
            patch("v4.ingestion.bundle.load_ads_bundle", return_value=make_payload("ads", status=SourceStatusCode.MISSING, is_required=False)),
            patch("v4.ingestion.bundle.load_funnel", return_value=make_payload("funnel", status=SourceStatusCode.MISSING, is_required=False)),
        ):
            result = build_api_raw_bundle(ctx)

        self.assertEqual(result.source_flags["orders"], SourceStatusCode.ERROR)
        self.assertFalse(result.raw_bundle.diagnostics["required_sources_ok"])
        self.assertGreaterEqual(result.raw_bundle.diagnostics["warnings_count"], 1)


if __name__ == "__main__":
    unittest.main()
