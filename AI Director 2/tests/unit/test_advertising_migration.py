from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from packages.advertising.service import build_advertising_read_model
from packages.data.canonical import AdvertisingAttributionScope, CanonicalInputState
from packages.data.normalization import NormalizationError, normalize_advertising_performance
from packages.wb_core.contracts import ADVERTISING_PERFORMANCE_ENDPOINT, RawObject
from packages.wb_core.synthetic_scenario import synthetic_scope

OPERATIONAL_DATE = date(2026, 8, 20)


def _raw_object(rows: list[dict[str, object]]) -> RawObject:
    return RawObject(
        object_id="e" * 64,
        scope=synthetic_scope(),
        endpoint=ADVERTISING_PERFORMANCE_ENDPOINT,
        object_type=ADVERTISING_PERFORMANCE_ENDPOINT.object_type,
        source="wildberries",
        retrieved_at=datetime(2026, 8, 24, 10, 30, tzinfo=UTC),
        operational_date=OPERATIONAL_DATE,
        request_scope={"dateFrom": OPERATIONAL_DATE.isoformat()},
        payload={"data": rows},
        schema_version=ADVERTISING_PERFORMANCE_ENDPOINT.schema_version,
    )


def test_direct_sku_spend_is_the_only_sku_attributed_scope() -> None:
    facts = normalize_advertising_performance(
        _raw_object(
            [
                {"advertId": 10, "nmId": 1001, "sum": "15.50", "impressions": 100, "clicks": 5, "orders": 1},
                {"advertId": 10, "attributionScope": "campaign", "sum": "40.00", "impressions": 200},
                {"attributionScope": "period", "sum": "20.00"},
                {"attributionScope": "associated", "sum": "10.00"},
                {"attributionScope": "unknown", "sum": "5.00"},
            ]
        )
    )
    read_model = build_advertising_read_model(reversed(facts))
    totals = {item.attribution_scope: item for item in read_model.scope_totals}

    assert read_model.direct_sku_spend == {"1001": Decimal("15.50")}
    assert totals[AdvertisingAttributionScope.CAMPAIGN].spend == Decimal("40.00")
    assert totals[AdvertisingAttributionScope.PERIOD].spend == Decimal("20.00")
    assert totals[AdvertisingAttributionScope.ASSOCIATED].spend == Decimal("10.00")
    assert totals[AdvertisingAttributionScope.UNKNOWN].spend == Decimal("5.00")
    assert all("1001" not in str(item.model_dump()) for item in read_model.scope_totals[1:])


def test_missing_ad_spend_remains_missing_not_zero() -> None:
    fact = normalize_advertising_performance(_raw_object([{ "nmId": 1001, "clicks": 1 }]))[0]
    read_model = build_advertising_read_model((fact,))

    assert fact.spend_input.state == CanonicalInputState.MISSING
    assert read_model.direct_sku_spend == {"1001": None}
    direct_total = next(item for item in read_model.scope_totals if item.attribution_scope == AdvertisingAttributionScope.DIRECT_SKU)
    assert direct_total.spend is None


def test_direct_sku_scope_requires_nm_id_and_unknown_scope_is_preserved() -> None:
    with pytest.raises(NormalizationError, match="requires nmId"):
        normalize_advertising_performance(_raw_object([{ "attributionScope": "direct_sku", "sum": "10" }]))

    fact = normalize_advertising_performance(_raw_object([{ "sum": "10" }]))[0]
    assert fact.attribution_scope == AdvertisingAttributionScope.UNKNOWN
    assert fact.nm_id is None
