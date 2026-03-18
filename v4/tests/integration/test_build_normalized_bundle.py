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
from v4.normalization.normalizers import build_normalized_bundle


def _source(
    name: str,
    status_code: SourceStatusCode,
    rows: list[dict] | None,
    *,
    warning: str | None = None,
    is_required: bool = False,
) -> RawSourcePayload:
    warnings = [warning] if warning else []
    return RawSourcePayload(
        source_name=name,
        payload={"rows": rows},
        status=SourceStatus(
            source_name=name,
            kind=SourceKind.API,
            status=status_code,
            is_required=is_required,
            rows_loaded=(len(rows) if isinstance(rows, list) else None),
            warnings=warnings,
        ),
    )


class TestBuildNormalizedBundle(unittest.TestCase):
    def test_statuses_warnings_and_counts_are_preserved(self) -> None:
        context = RunContext(
            seller_id="seller_001",
            cabinet_name=None,
            mode=RunMode.DAILY_API,
            requested_date=date(2026, 3, 15),
            resolved_date=date(2026, 3, 15),
            timezone="Europe/Moscow",
            wb_api_token_present=True,
        )

        ads_payload = RawSourcePayload(
            source_name="ads",
            payload={
                "campaigns": {"campaign_ids": [1001], "raw": [{"id": 1001, "name": "Ads One"}]},
                "stats": {"rows": None, "raw_chunks": []},
            },
            status=SourceStatus(
                source_name="ads",
                kind=SourceKind.API,
                status=SourceStatusCode.PARTIAL,
                is_required=False,
                warnings=["stats are missing"],
            ),
        )

        raw_bundle = RawBundle(
            run_context=context,
            sources={
                "orders": _source(
                    "orders",
                    SourceStatusCode.OK,
                    [{"srid": "ord-1", "nmId": 111, "quantity": 1, "date": "2026-03-15"}],
                    is_required=True,
                ),
                "sales": _source(
                    "sales",
                    SourceStatusCode.MISSING,
                    None,
                    warning="sales source returned empty payload",
                    is_required=True,
                ),
                "realization": _source(
                    "realization",
                    SourceStatusCode.OK,
                    [{"rrd_id": "r-1", "supplier_oper_name": "Продажа", "nm_id": 111}],
                    is_required=True,
                ),
                "stocks": _source("stocks", SourceStatusCode.ERROR, None),
                "ads": ads_payload,
                "funnel": _source("funnel", SourceStatusCode.NOT_IMPLEMENTED, None),
            },
            diagnostics={"mode": "daily_api_mode"},
        )

        normalized = build_normalized_bundle(raw_bundle)

        self.assertEqual(normalized.source_statuses["sales"].status, SourceStatusCode.MISSING)
        self.assertIn("sales: sales source returned empty payload", normalized.warnings)
        self.assertEqual(normalized.diagnostics["normalized_orders_count"], 1)
        self.assertEqual(normalized.diagnostics["normalized_realization_count"], 1)
        self.assertEqual(normalized.diagnostics["normalized_ads_campaigns_count"], 1)
        self.assertEqual(normalized.diagnostics["normalized_ads_stats_count"], 0)
        self.assertEqual(normalized.diagnostics["normalized_sources_count"], 6)


if __name__ == "__main__":
    unittest.main()
