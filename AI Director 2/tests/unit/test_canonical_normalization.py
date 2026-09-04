from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast

import pytest

from packages.data.canonical import (
    CanonicalCurrency,
    CanonicalInputState,
    CanonicalValueKind,
)
from packages.data.normalization import (
    NormalizationError,
    SALES_FUNNEL_PRODUCTS_FIELD_MAPPING,
    SalesFunnelProductsNormalizer,
    normalize_sales_funnel_products,
)
from packages.wb_core.contracts import RawObject, RawObjectType, SALES_FUNNEL_PRODUCTS_ENDPOINT
from packages.wb_core.synthetic_scenario import (
    SYNTHETIC_OBJECT_ID,
    SYNTHETIC_OPERATIONAL_DATE,
    SYNTHETIC_RETRIEVED_AT,
    synthetic_raw_object,
    synthetic_scope,
)


def _raw_object_with_selected(selected: dict[str, Any], *, operational_date: date | None = date(2026, 8, 20)) -> RawObject:
    return RawObject(
        object_id=SYNTHETIC_OBJECT_ID,
        scope=synthetic_scope(),
        endpoint=SALES_FUNNEL_PRODUCTS_ENDPOINT,
        object_type=RawObjectType.SALES_FUNNEL_PRODUCTS,
        source="wildberries",
        retrieved_at=datetime(2026, 8, 24, 10, 30, tzinfo=UTC),
        operational_date=operational_date,
        request_scope={"selected_period": {"start": "2026-08-20", "end": "2026-08-20"}},
        payload={
            "data": {
                "products": [
                    {
                        "product": {"nmId": 1001, "vendorCode": "SYNTH-ART-1001"},
                        "statistic": {"selected": selected},
                    }
                ]
            }
        },
        schema_version="analytics-v3",
    )


def _records(raw_object: RawObject) -> tuple[Any, ...]:
    return normalize_sales_funnel_products(raw_object)


def test_normalizer_maps_the_synthetic_raw_object_to_one_canonical_record() -> None:
    record = _records(synthetic_raw_object())[0]

    assert record.source_metadata.source == "wildberries"
    assert record.source_metadata.scope == synthetic_scope()
    assert record.source_metadata.source_object_id == SYNTHETIC_OBJECT_ID
    assert record.source_metadata.endpoint_name == "sales_funnel_products"
    assert record.source_metadata.source_record_index == 0
    assert record.operational_date == SYNTHETIC_OPERATIONAL_DATE
    assert record.source_metadata.retrieved_at == SYNTHETIC_RETRIEVED_AT
    assert record.nm_id == "1001"
    assert record.seller_sku == "SYNTH-ART-1001"
    assert record.quantity == 2
    assert record.source_open_count == 42
    assert record.source_cart_count == 7
    assert record.source_open_count_input.state == CanonicalInputState.VALUE
    assert record.source_cart_count_input.state == CanonicalInputState.VALUE
    assert record.source_amount == Decimal("1234.56")
    assert isinstance(record.source_amount, Decimal)
    assert record.currency == CanonicalCurrency.RUB
    assert record.currency_raw == "RUB"


def test_field_mapping_is_explicit_and_tracks_raw_provenance() -> None:
    record = _records(synthetic_raw_object())[0]

    assert SALES_FUNNEL_PRODUCTS_FIELD_MAPPING["data.products[].product.nmId"] == "nm_id"
    assert SALES_FUNNEL_PRODUCTS_FIELD_MAPPING["data.products[].statistic.selected.orderSum"] == "source_amount"
    assert record.quantity_input.raw_path == "statistic.selected.orderCount"
    assert record.source_open_count_input.raw_path == "statistic.selected.openCount"
    assert record.source_cart_count_input.raw_path == "statistic.selected.cartCount"
    assert record.source_amount_input.raw_path == "statistic.selected.orderSum"
    assert record.currency_input.raw_path == "statistic.selected.currency"


def test_normalizer_preserves_operational_and_retrieval_dates_without_derivation() -> None:
    record = _records(synthetic_raw_object())[0]

    assert record.operational_date == date(2026, 8, 20)
    assert record.source_metadata.retrieved_at == datetime(2026, 8, 24, 10, 30, tzinfo=UTC)
    assert record.source_metadata.retrieved_at.date() != record.operational_date


def test_normalizer_rejects_missing_operational_date_instead_of_using_retrieved_at() -> None:
    valid_raw_object = _raw_object_with_selected({"orderCount": 2})
    raw_object = RawObject.model_construct(
        object_id=valid_raw_object.object_id,
        scope=valid_raw_object.scope,
        endpoint=valid_raw_object.endpoint,
        object_type=valid_raw_object.object_type,
        source=valid_raw_object.source,
        retrieved_at=valid_raw_object.retrieved_at,
        operational_date=None,
        request_scope=valid_raw_object.request_scope,
        payload=valid_raw_object.payload,
        schema_version=valid_raw_object.schema_version,
    )

    with pytest.raises(NormalizationError, match="retrieved_at"):
        _records(raw_object)


def test_normalizer_preserves_exact_decimal_text_without_rounding() -> None:
    record = _records(_raw_object_with_selected({"orderCount": 2, "orderSum": "1234.5600", "currency": "RUB"}))[0]

    assert record.source_amount == Decimal("1234.5600")
    assert record.source_amount.as_tuple().exponent == -4
    assert not isinstance(record.source_amount, float)


@pytest.mark.parametrize(
    ("selected", "expected_state", "expected_kind", "expected_quantity"),
    [
        ({}, CanonicalInputState.MISSING, CanonicalValueKind.MISSING, None),
        ({"orderCount": None}, CanonicalInputState.NULL, CanonicalValueKind.NULL, None),
        ({"orderCount": ""}, CanonicalInputState.EMPTY_STRING, CanonicalValueKind.EMPTY_STRING, None),
        ({"orderCount": 0}, CanonicalInputState.VALUE, CanonicalValueKind.INTEGER, 0),
        ({"orderCount": "0"}, CanonicalInputState.VALUE, CanonicalValueKind.STRING, 0),
    ],
)
def test_normalizer_distinguishes_missing_null_empty_zero_and_string_zero(
    selected: dict[str, Any],
    expected_state: CanonicalInputState,
    expected_kind: CanonicalValueKind,
    expected_quantity: int | None,
) -> None:
    record = _records(_raw_object_with_selected(selected))[0]

    assert record.quantity_input.state == expected_state
    assert record.quantity_input.value_kind == expected_kind
    assert record.quantity == expected_quantity


def test_normalizer_distinguishes_missing_null_empty_and_zero_money_inputs() -> None:
    records = [
        _records(_raw_object_with_selected(selected))[0]
        for selected in (
            {},
            {"orderSum": None},
            {"orderSum": ""},
            {"orderSum": "0"},
        )
    ]

    assert [record.source_amount_input.state for record in records] == [
        CanonicalInputState.MISSING,
        CanonicalInputState.NULL,
        CanonicalInputState.EMPTY_STRING,
        CanonicalInputState.VALUE,
    ]
    assert [record.source_amount for record in records] == [None, None, None, Decimal("0")]


def test_normalizer_maps_unknown_currency_explicitly_without_guessing() -> None:
    record = _records(_raw_object_with_selected({"currency": "xyz"}))[0]

    assert record.currency == CanonicalCurrency.UNKNOWN
    assert record.currency_raw == "xyz"
    assert record.currency_input.state == CanonicalInputState.VALUE


@pytest.mark.parametrize(
    "selected",
    [
        {"orderCount": True},
        {"orderCount": "2.5"},
        {"orderSum": "not-a-number"},
        {"currency": 643},
    ],
)
def test_normalizer_rejects_malformed_source_values(selected: dict[str, Any]) -> None:
    with pytest.raises(NormalizationError):
        _records(_raw_object_with_selected(selected))


def test_canonical_record_is_immutable_and_raw_mutation_cannot_change_it() -> None:
    raw_object = synthetic_raw_object()
    record = _records(raw_object)[0]

    with pytest.raises(Exception):
        record.quantity = 99
    assert record.quantity == 2
    assert isinstance(raw_object.payload, Mapping)
    assert isinstance(raw_object.payload["data"], Mapping)
    with pytest.raises(TypeError):
        cast(dict[str, Any], raw_object.payload["data"])["products"] = []
    assert record.source_amount == Decimal("1234.56")


def test_normalizer_is_deterministic_for_the_same_raw_object() -> None:
    raw_object = synthetic_raw_object()

    first = SalesFunnelProductsNormalizer().normalize(raw_object)
    second = SalesFunnelProductsNormalizer().normalize(raw_object)

    assert first == second
    assert first[0].model_dump(mode="json") == second[0].model_dump(mode="json")
