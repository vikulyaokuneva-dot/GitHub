"""Regression: legacy advertising aggregate adapts to the AD2 contract at the compat boundary.

Real legacy ``load_ads`` rows look like::

    {"date": ..., "sku": "1001021", "nm_id": "1001021", "ads_spend": 123.45,
     "impressions": 1000.0, "clicks": 50.0, "add_to_cart": 5.0, "orders": 2.0,
     "ctr": 5.0, "cpo": 61.72, "source": "ads_api"}

The compat boundary only renames fields that exist (``ads_spend`` -> ``sum``,
``nm_id`` -> ``nmId``); it invents no advertId, no scope and no amounts.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from packages.advertising.service import build_advertising_read_model
from packages.compat.wb_sales_funnel_transport import (
    LegacyWBApiLoadersTransport,
    map_legacy_advertising_row,
)
from packages.data.canonical import AdvertisingAttributionScope, CanonicalInputState
from packages.data.normalization import normalize_advertising_performance
from packages.wb_core.contracts import ADVERTISING_PERFORMANCE_ENDPOINT, RawObject
from packages.wb_core.synthetic_scenario import synthetic_scope

OPERATIONAL_DATE = date(2026, 9, 2)


def _legacy_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "date": OPERATIONAL_DATE.isoformat(),
        "sku": "1001021",
        "nm_id": "1001021",
        "ads_spend": 123.45,
        "impressions": 1000.0,
        "clicks": 50.0,
        "add_to_cart": 5.0,
        "orders": 2.0,
        "ctr": 5.0,
        "cpo": 61.72,
        "source": "ads_api",
    }
    row.update(overrides)
    return row


def _raw_object(rows: list[dict[str, object]]) -> RawObject:
    return RawObject(
        object_id="e" * 64,
        scope=synthetic_scope(),
        endpoint=ADVERTISING_PERFORMANCE_ENDPOINT,
        object_type=ADVERTISING_PERFORMANCE_ENDPOINT.object_type,
        source="wildberries",
        retrieved_at=datetime(2026, 9, 4, 10, 30, tzinfo=UTC),
        operational_date=OPERATIONAL_DATE,
        request_scope={"dateFrom": OPERATIONAL_DATE.isoformat()},
        payload={"data": rows},
        schema_version=ADVERTISING_PERFORMANCE_ENDPOINT.schema_version,
    )


class _FakeAdsClient:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.advert_base_url = "https://advert.example.test"

    def request_json(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(str(kwargs.get("endpoint_name")))
        if kwargs.get("endpoint_name") == "ads_adverts":
            return {"success": True, "payload": {"adverts": [{"advertId": 101}]}}
        return {
            "success": True,
            "payload": [
                {
                    "days": [
                        {
                            "nm": [
                                {
                                    "nmId": 1001021,
                                    "sum": 123.45,
                                    "impressions": 1000.0,
                                    "clicks": 50.0,
                                    "orders": 2.0,
                                }
                            ]
                        }
                    ]
                }
            ],
        }


def test_map_legacy_advertising_row_renames_only_present_fields() -> None:
    mapped = map_legacy_advertising_row(_legacy_row())

    assert mapped["sum"] == 123.45
    assert mapped["nmId"] == "1001021"
    assert "ads_spend" not in mapped and "nm_id" not in mapped
    # untouched legacy fields survive verbatim; nothing invented
    assert mapped["impressions"] == 1000.0
    assert mapped["clicks"] == 50.0
    assert mapped["orders"] == 2.0
    assert mapped["ctr"] == 5.0
    assert mapped["source"] == "ads_api"
    assert "advertId" not in mapped
    assert "attributionScope" not in mapped


def test_map_legacy_advertising_row_without_nm_id_invents_nothing() -> None:
    mapped = map_legacy_advertising_row(_legacy_row(sku="", nm_id=""))

    assert mapped["sum"] == 123.45
    # nm_id="" is still a key — it gets renamed; the normalizer treats "" as None
    assert mapped["nmId"] == ""
    assert "attributionScope" not in mapped


def test_mapped_legacy_row_normalizes_as_direct_sku_spend() -> None:
    facts = normalize_advertising_performance(_raw_object([map_legacy_advertising_row(_legacy_row())]))
    read_model = build_advertising_read_model(facts)

    assert len(facts) == 1
    assert facts[0].attribution_scope == AdvertisingAttributionScope.DIRECT_SKU
    assert facts[0].nm_id == "1001021"
    assert facts[0].spend == Decimal("123.45")
    assert read_model.direct_sku_spend == {"1001021": Decimal("123.45")}


def test_mapped_legacy_row_without_nm_id_falls_back_to_unknown_scope() -> None:
    facts = normalize_advertising_performance(_raw_object([map_legacy_advertising_row(_legacy_row(sku="", nm_id=""))]))

    assert facts[0].attribution_scope == AdvertisingAttributionScope.UNKNOWN
    assert facts[0].nm_id is None
    assert facts[0].spend == Decimal("123.45")


def test_mapped_legacy_row_without_spend_stays_missing_not_zero() -> None:
    row = _legacy_row()
    del row["ads_spend"]
    facts = normalize_advertising_performance(_raw_object([map_legacy_advertising_row(row)]))

    assert facts[0].spend_input.state == CanonicalInputState.MISSING
    assert facts[0].spend is None


def test_loaders_transport_maps_legacy_ads_rows_through_real_loader_flow() -> None:
    client = _FakeAdsClient()
    result = LegacyWBApiLoadersTransport(client).load_ads(operational_date=OPERATIONAL_DATE)

    assert client.calls == ["ads_adverts", "ads_stats"]
    rows = result["rows_raw"]
    assert len(rows) == 1
    row = rows[0]
    # AD2 contract keys are present after mapping
    assert row["sum"] == 123.45
    assert row["nmId"] == "1001021"
    assert row["impressions"] == 1000.0
    assert row["clicks"] == 50.0
    assert row["orders"] == 2.0
    # legacy keys renamed away
    assert "ads_spend" not in row
    assert "nm_id" not in row

    facts = normalize_advertising_performance(_raw_object(rows))
    read_model = build_advertising_read_model(facts)
    assert read_model.direct_sku_spend == {"1001021": Decimal("123.45")}
