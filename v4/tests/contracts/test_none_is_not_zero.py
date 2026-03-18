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


def payload_with_none(source_name: str, is_required: bool) -> RawSourcePayload:
    return RawSourcePayload(
        source_name=source_name,
        payload={"rows": None, "raw": None, "value": None},
        status=SourceStatus(
            source_name=source_name,
            kind=SourceKind.API,
            status=SourceStatusCode.MISSING,
            is_required=is_required,
            rows_loaded=None,
        ),
    )


class TestNoneIsNotZero(unittest.TestCase):
    def test_none_preserved_in_raw_layer(self) -> None:
        context = RunContext(
            seller_id="seller_001",
            cabinet_name=None,
            mode=RunMode.DAILY_API,
            requested_date=date(2026, 3, 15),
            resolved_date=date(2026, 3, 15),
            timezone="Europe/Moscow",
            wb_api_token_present=True,
        )

        with (
            patch("v4.ingestion.bundle.WBApiClient", return_value=object()),
            patch("v4.ingestion.bundle.load_orders", return_value=payload_with_none("orders", True)),
            patch("v4.ingestion.bundle.load_sales", return_value=payload_with_none("sales", True)),
            patch("v4.ingestion.bundle.load_realization", return_value=payload_with_none("realization", True)),
            patch("v4.ingestion.bundle.load_stocks", return_value=payload_with_none("stocks", False)),
            patch("v4.ingestion.bundle.load_ads_campaigns", return_value=payload_with_none("ads_campaigns", False)),
            patch("v4.ingestion.bundle.load_ads_stats", return_value=payload_with_none("ads_stats", False)),
            patch("v4.ingestion.bundle.load_ads_bundle", return_value=payload_with_none("ads", False)),
            patch("v4.ingestion.bundle.load_funnel", return_value=payload_with_none("funnel", False)),
        ):
            result = build_api_raw_bundle(context)

        orders_payload = result.raw_bundle.sources["orders"].payload
        self.assertIsNone(orders_payload["rows"])
        self.assertIsNone(orders_payload["raw"])
        self.assertIsNone(result.raw_bundle.sources["orders"].status.rows_loaded)
        self.assertNotEqual(orders_payload.get("value"), 0)


if __name__ == "__main__":
    unittest.main()
