from __future__ import annotations

from datetime import UTC, date, datetime
from collections.abc import Mapping
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError

from packages.wb_core.contracts import (
    DuplicateRawObjectError,
    EndpointDataClass,
    EndpointDomain,
    EndpointMetadata,
    InMemoryRawObjectRepository,
    OperationalDateSemantics,
    PayloadKind,
    PaginationSemantics,
    RawObject,
    RawObjectNotFoundError,
    RawObjectType,
    SALES_FUNNEL_PRODUCTS_ENDPOINT,
    TenantAccountScope,
)
from packages.wb_core.synthetic_scenario import (
    SYNTHETIC_OBJECT_ID,
    SYNTHETIC_OPERATIONAL_DATE,
    SYNTHETIC_RETRIEVED_AT,
    synthetic_raw_object,
    synthetic_repository,
    synthetic_scope,
)


def _scope() -> TenantAccountScope:
    return TenantAccountScope(tenant_id=uuid4(), account_id=uuid4())


def _raw_object(*, scope: TenantAccountScope | None = None, object_id: str = "a" * 64) -> RawObject:
    return RawObject(
        object_id=object_id,
        scope=scope or _scope(),
        endpoint=SALES_FUNNEL_PRODUCTS_ENDPOINT,
        object_type=RawObjectType.SALES_FUNNEL_PRODUCTS,
        source="wildberries",
        retrieved_at=datetime(2026, 8, 24, 10, 30, tzinfo=UTC),
        operational_date=date(2026, 8, 20),
        request_scope={"offset": 0, "limit": 1000},
        payload={"data": {"products": [{"nmId": 1001, "retailAmount": 1234.56}]}},
        schema_version="analytics-v3",
    )


def _payload_mapping(payload: dict[str, Any]) -> dict[str, Any]:
    return payload


def test_endpoint_metadata_declares_the_initial_operational_scenario() -> None:
    metadata = SALES_FUNNEL_PRODUCTS_ENDPOINT

    assert metadata.name == "sales_funnel_products"
    assert metadata.http_method == "POST"
    assert metadata.logical_domain == EndpointDomain.ANALYTICS
    assert metadata.object_type == RawObjectType.SALES_FUNNEL_PRODUCTS
    assert metadata.expected_payload_kind == PayloadKind.OBJECT
    assert metadata.operational_date_semantics == OperationalDateSemantics.REQUESTED_BUSINESS_DAY
    assert metadata.pagination_semantics == PaginationSemantics.OFFSET_LIMIT
    assert metadata.data_class == EndpointDataClass.OPERATIONAL
    assert metadata.schema_version == "analytics-v3"


def test_repository_save_get_and_list_are_scoped_and_deterministic() -> None:
    repository = InMemoryRawObjectRepository()
    scope = _scope()
    later_id = "f" * 64
    earlier_id = "0" * 64
    repository.save(_raw_object(scope=scope, object_id=later_id))
    repository.save(_raw_object(scope=scope, object_id=earlier_id))

    assert repository.get(scope=scope, object_id=later_id).object_id == later_id
    assert [item.object_id for item in repository.list(scope=scope)] == [earlier_id, later_id]
    assert [item.object_id for item in repository.list(scope=scope, endpoint_name="sales_funnel_products")] == [
        earlier_id,
        later_id,
    ]
    assert repository.list(scope=scope, endpoint_name="unknown") == ()


def test_repository_rejects_duplicate_identity_and_hides_other_scope() -> None:
    repository = InMemoryRawObjectRepository()
    owner_scope = _scope()
    other_scope = _scope()
    raw_object = _raw_object(scope=owner_scope)
    repository.save(raw_object)

    with pytest.raises(DuplicateRawObjectError, match=raw_object.object_id):
        repository.save(raw_object)
    with pytest.raises(RawObjectNotFoundError):
        repository.get(scope=other_scope, object_id=raw_object.object_id)
    assert repository.list(scope=other_scope) == ()


def test_repository_rejects_missing_object() -> None:
    with pytest.raises(RawObjectNotFoundError, match="not found"):
        InMemoryRawObjectRepository().get(scope=_scope(), object_id="b" * 64)


def test_raw_object_isolated_from_external_payload_mutation() -> None:
    payload = {"data": {"products": [{"nmId": 1001, "retailAmount": 1234.56}]}}
    raw_object = RawObject(
        object_id="a" * 64,
        scope=_scope(),
        endpoint=SALES_FUNNEL_PRODUCTS_ENDPOINT,
        object_type=RawObjectType.SALES_FUNNEL_PRODUCTS,
        source="wildberries",
        retrieved_at=datetime(2026, 8, 24, 10, 30, tzinfo=UTC),
        operational_date=date(2026, 8, 20),
        request_scope={"offset": 0},
        payload=payload,
        schema_version="analytics-v3",
    )

    payload["data"]["products"][0]["retailAmount"] = 9999.99

    assert raw_object.payload["data"]["products"][0]["retailAmount"] == 1234.56


def test_read_payload_is_immutable_and_repository_remains_safe() -> None:
    repository = InMemoryRawObjectRepository()
    raw_object = _raw_object()
    repository.save(raw_object)

    returned = repository.get(scope=raw_object.scope, object_id=raw_object.object_id)
    returned_payload = returned.payload
    assert isinstance(returned_payload, Mapping)
    assert isinstance(returned_payload["data"], Mapping)
    assert isinstance(returned_payload["data"]["products"], tuple)

    with pytest.raises(TypeError):
        returned_payload["data"] = {}
    with pytest.raises(TypeError):
        cast(dict[str, Any], returned_payload["data"])["products"][0]["retailAmount"] = 0.01

    stored = repository.get(scope=raw_object.scope, object_id=raw_object.object_id)
    assert _payload_mapping(stored.payload)["data"]["products"][0]["retailAmount"] == 1234.56


@pytest.mark.parametrize(
    "payload",
    [
        {"Authorization": "Bearer forbidden"},
        {"apiKey": "forbidden"},
        {"nested": {"client_secret": "forbidden"}},
        {"password": "forbidden"},
        {"cookie": "forbidden"},
        {"wb_credentials": "forbidden"},
        {"nested": {"value": "Bearer forbidden"}},
        {"nested": {"value": "WB_API_TOKEN=forbidden"}},
    ],
)
def test_raw_object_rejects_credential_like_payloads(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="credential-like"):
        RawObject(
            object_id="c" * 64,
            scope=_scope(),
            endpoint=SALES_FUNNEL_PRODUCTS_ENDPOINT,
            object_type=RawObjectType.SALES_FUNNEL_PRODUCTS,
            source="wildberries",
            retrieved_at=datetime(2026, 8, 24, 10, 30, tzinfo=UTC),
            operational_date=date(2026, 8, 20),
            request_scope={"offset": 0},
            payload=payload,
            schema_version="analytics-v3",
        )


def test_raw_object_keeps_operational_date_separate_from_retrieval_timestamp() -> None:
    raw_object = synthetic_raw_object()

    assert raw_object.operational_date == SYNTHETIC_OPERATIONAL_DATE
    assert raw_object.retrieved_at == SYNTHETIC_RETRIEVED_AT
    assert raw_object.retrieved_at.date() != raw_object.operational_date
    assert raw_object.retrieved_at.tzinfo is UTC


def test_raw_object_requires_utc_retrieved_at_and_endpoint_consistency() -> None:
    with pytest.raises(ValidationError, match="UTC"):
        RawObject(
            object_id="d" * 64,
            scope=_scope(),
            endpoint=SALES_FUNNEL_PRODUCTS_ENDPOINT,
            object_type=RawObjectType.SALES_FUNNEL_PRODUCTS,
            source="wildberries",
            retrieved_at=datetime(2026, 8, 24, 10, 30),
            operational_date=date(2026, 8, 20),
            request_scope={"offset": 0},
            payload={"data": {}},
            schema_version="analytics-v3",
        )
    with pytest.raises(ValidationError, match="schema_version"):
        RawObject(
            object_id="e" * 64,
            scope=_scope(),
            endpoint=SALES_FUNNEL_PRODUCTS_ENDPOINT,
            object_type=RawObjectType.SALES_FUNNEL_PRODUCTS,
            source="wildberries",
            retrieved_at=datetime(2026, 8, 24, 10, 30, tzinfo=UTC),
            operational_date=date(2026, 8, 20),
            request_scope={"offset": 0},
            payload={"data": {}},
            schema_version="wrong-version",
        )


def test_synthetic_scenario_round_trip_is_reproducible_and_read_only() -> None:
    repository = synthetic_repository()
    raw_object = repository.get(scope=synthetic_scope(), object_id=SYNTHETIC_OBJECT_ID)

    assert raw_object.endpoint == SALES_FUNNEL_PRODUCTS_ENDPOINT
    assert raw_object.operational_date == date(2026, 8, 20)
    assert raw_object.retrieved_at == datetime(2026, 8, 24, 10, 30, tzinfo=UTC)
    assert _payload_mapping(raw_object.request_scope)["selected_period"]["start"] == "2026-08-20"
    assert _payload_mapping(raw_object.payload)["data"]["products"][0]["statistic"]["selected"]["openCount"] == 42
