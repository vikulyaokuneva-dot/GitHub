"""Contracts for WB transport provenance and immutable raw-object access."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import date, datetime, timezone
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Final, Mapping, Protocol, TypeAlias, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

RawPayload: TypeAlias = dict[str, Any] | list[Any]
RawRequestScope: TypeAlias = dict[str, Any]

_CREDENTIAL_FIELD_MARKERS: Final = (
    "authorization",
    "api_key",
    "apikey",
    "token",
    "client_secret",
    "secret",
    "password",
    "cookie",
    "credential",
)
_CREDENTIAL_VALUE_PREFIXES: Final = ("bearer ", "basic ", "sk-")


class TenantAccountScope(BaseModel):
    """Trusted server-side ownership scope for all account operations."""

    model_config = ConfigDict(frozen=True)

    tenant_id: UUID
    account_id: UUID


class EndpointDomain(StrEnum):
    """Logical WB endpoint ownership used before source normalization."""

    ANALYTICS = "analytics"
    FINANCE = "finance"


class EndpointDataClass(StrEnum):
    """Whether endpoint data is operational, financial, or reference data."""

    OPERATIONAL = "operational"
    FINANCIAL = "financial"


class PayloadKind(StrEnum):
    """Top-level raw payload shape expected from an endpoint."""

    OBJECT = "object"
    ARRAY = "array"


class OperationalDateSemantics(StrEnum):
    """How the endpoint's request relates to a WB business date."""

    REQUESTED_BUSINESS_DAY = "requested_business_day"
    REQUESTED_FINANCIAL_DAY = "requested_financial_day"


class PaginationSemantics(StrEnum):
    """Pagination strategy declared by endpoint metadata."""

    OFFSET_LIMIT = "offset_limit"


class RawObjectType(StrEnum):
    """Raw object types admitted by the initial read-only scenario."""

    SALES_FUNNEL_PRODUCTS = "sales_funnel_products"
    FINANCE_DETAIL = "finance_detail"
    ORDERS = "orders"
    SALES = "sales"
    STOCKS = "stocks"
    ADVERTISING_PERFORMANCE = "advertising_performance"


class EndpointMetadata(BaseModel):
    """Static metadata for one endpoint, independent of any retrieval."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$", min_length=3, max_length=100)
    http_method: str = Field(pattern=r"^(GET|POST)$")
    logical_domain: EndpointDomain
    object_type: RawObjectType
    source: str = Field(min_length=1, max_length=100)
    expected_payload_kind: PayloadKind
    operational_date_semantics: OperationalDateSemantics
    pagination_semantics: PaginationSemantics | None = None
    data_class: EndpointDataClass
    schema_version: str = Field(min_length=1, max_length=50)


SALES_FUNNEL_PRODUCTS_ENDPOINT: Final = EndpointMetadata(
    name="sales_funnel_products",
    http_method="POST",
    logical_domain=EndpointDomain.ANALYTICS,
    object_type=RawObjectType.SALES_FUNNEL_PRODUCTS,
    source="wildberries",
    expected_payload_kind=PayloadKind.OBJECT,
    operational_date_semantics=OperationalDateSemantics.REQUESTED_BUSINESS_DAY,
    pagination_semantics=PaginationSemantics.OFFSET_LIMIT,
    data_class=EndpointDataClass.OPERATIONAL,
    schema_version="analytics-v3",
)

FINANCE_DETAIL_ENDPOINT: Final = EndpointMetadata(
    name="finance_detail",
    http_method="POST",
    logical_domain=EndpointDomain.FINANCE,
    object_type=RawObjectType.FINANCE_DETAIL,
    source="wildberries",
    expected_payload_kind=PayloadKind.ARRAY,
    operational_date_semantics=OperationalDateSemantics.REQUESTED_FINANCIAL_DAY,
    data_class=EndpointDataClass.FINANCIAL,
    schema_version="finance-detailed-v1",
)

ORDERS_ENDPOINT: Final = EndpointMetadata(
    name="orders",
    http_method="GET",
    logical_domain=EndpointDomain.ANALYTICS,
    object_type=RawObjectType.ORDERS,
    source="wildberries",
    expected_payload_kind=PayloadKind.ARRAY,
    operational_date_semantics=OperationalDateSemantics.REQUESTED_BUSINESS_DAY,
    data_class=EndpointDataClass.OPERATIONAL,
    schema_version="supplier-orders-v1",
)

SALES_ENDPOINT: Final = EndpointMetadata(
    name="sales",
    http_method="GET",
    logical_domain=EndpointDomain.ANALYTICS,
    object_type=RawObjectType.SALES,
    source="wildberries",
    expected_payload_kind=PayloadKind.ARRAY,
    operational_date_semantics=OperationalDateSemantics.REQUESTED_BUSINESS_DAY,
    data_class=EndpointDataClass.OPERATIONAL,
    schema_version="supplier-sales-v1",
)

STOCKS_ENDPOINT: Final = EndpointMetadata(
    name="stocks",
    http_method="POST",
    logical_domain=EndpointDomain.ANALYTICS,
    object_type=RawObjectType.STOCKS,
    source="wildberries",
    expected_payload_kind=PayloadKind.OBJECT,
    operational_date_semantics=OperationalDateSemantics.REQUESTED_BUSINESS_DAY,
    pagination_semantics=PaginationSemantics.OFFSET_LIMIT,
    data_class=EndpointDataClass.OPERATIONAL,
    schema_version="stocks-wb-warehouses-v1",
)

ADVERTISING_PERFORMANCE_ENDPOINT: Final = EndpointMetadata(
    name="advertising_performance",
    http_method="GET",
    logical_domain=EndpointDomain.ANALYTICS,
    object_type=RawObjectType.ADVERTISING_PERFORMANCE,
    source="wildberries",
    expected_payload_kind=PayloadKind.OBJECT,
    operational_date_semantics=OperationalDateSemantics.REQUESTED_BUSINESS_DAY,
    data_class=EndpointDataClass.OPERATIONAL,
    schema_version="advertising-performance-v1",
)


def _assert_credential_free_payload(payload: object, path: str = "payload") -> None:
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            key_text = str(key).strip().lower().replace("-", "_")
            if any(marker in key_text for marker in _CREDENTIAL_FIELD_MARKERS):
                raise ValueError(f"credential-like field is forbidden at {path}.{key}")
            _assert_credential_free_payload(value, f"{path}.{key}")
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            _assert_credential_free_payload(value, f"{path}[{index}]")
    elif isinstance(payload, str):
        lowered = payload.strip().lower()
        if lowered.startswith(_CREDENTIAL_VALUE_PREFIXES) or "wb_api_token" in lowered:
            raise ValueError(f"credential-like value is forbidden at {path}")


def _copy_payload(payload: RawPayload) -> RawPayload:
    return deepcopy(payload)


def _freeze_raw_value(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_raw_value(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_raw_value(item) for item in value)
    return value


def _freeze_payload(payload: RawPayload) -> RawPayload:
    return cast(RawPayload, _freeze_raw_value(_copy_payload(payload)))


def _thaw_raw_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_raw_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_raw_value(item) for item in value]
    return deepcopy(value)


def _thaw_payload(payload: RawPayload) -> RawPayload:
    return cast(RawPayload, _thaw_raw_value(payload))


def _compatibility_payload_bytes(payload: RawPayload) -> bytes:
    """Encode fixtures created before transport byte capture was introduced."""

    return json.dumps(_thaw_payload(payload), ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


class RawObject(BaseModel):
    """Immutable raw WB object with operational and retrieval identities separated."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    object_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    scope: TenantAccountScope
    endpoint: EndpointMetadata
    object_type: RawObjectType
    source: str = Field(min_length=1, max_length=100)
    retrieved_at: datetime
    operational_date: date | None = None
    request_scope: RawRequestScope
    payload: RawPayload
    raw_payload_bytes: bytes | None = None
    schema_version: str = Field(min_length=1, max_length=50)

    @field_validator("retrieved_at")
    @classmethod
    def require_utc_retrieval_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
            raise ValueError("retrieved_at must be timezone-aware UTC")
        return value

    @field_validator("request_scope", "payload")
    @classmethod
    def reject_credentials(cls, value: RawPayload) -> RawPayload:
        _assert_credential_free_payload(value)
        return _freeze_payload(value)

    @field_validator("raw_payload_bytes")
    @classmethod
    def require_json_raw_bytes(cls, value: bytes | None) -> bytes | None:
        if value is None:
            return None
        try:
            decoded = json.loads(value.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("raw_payload_bytes must be valid UTF-8 JSON") from error
        _assert_credential_free_payload(decoded)
        return bytes(value)

    @model_validator(mode="after")
    def require_endpoint_consistency(self) -> RawObject:
        if self.object_type != self.endpoint.object_type:
            raise ValueError("object_type must match endpoint.object_type")
        if self.source != self.endpoint.source:
            raise ValueError("source must match endpoint.source")
        if self.schema_version != self.endpoint.schema_version:
            raise ValueError("schema_version must match endpoint.schema_version")
        if self.operational_date is None:
            raise ValueError("operational_date is required by endpoint metadata")
        if self.raw_payload_bytes is not None:
            try:
                decoded = json.loads(self.raw_payload_bytes.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError("raw_payload_bytes must be valid UTF-8 JSON") from error
            if decoded != _thaw_payload(self.payload):
                raise ValueError("raw_payload_bytes must represent payload without transformation")
        return self

    @property
    def payload_bytes(self) -> bytes:
        """Original source bytes, or deterministic fixture bytes for legacy tests."""

        return self.raw_payload_bytes if self.raw_payload_bytes is not None else _compatibility_payload_bytes(self.payload)

    @property
    def payload_sha256(self) -> str:
        """SHA-256 over the retained payload bytes, never over a wrapper."""

        return hashlib.sha256(self.payload_bytes).hexdigest()


class RawObjectNotFoundError(LookupError):
    """Raised when a scoped raw object is absent from a repository."""


class DuplicateRawObjectError(ValueError):
    """Raised when ingestion attempts to reuse a raw object identity."""


class RawObjectRepository(Protocol):
    """Ingestion-only write boundary and deterministic read boundary for raw objects."""

    def save(self, raw_object: RawObject) -> None:
        """Persist a newly ingested immutable raw object."""

    def get(self, *, scope: TenantAccountScope, object_id: str) -> RawObject:
        """Retrieve one raw object within its trusted tenant/account scope."""

    def list(self, *, scope: TenantAccountScope, endpoint_name: str | None = None) -> tuple[RawObject, ...]:
        """List scoped raw objects in deterministic object identity order."""


class InMemoryRawObjectRepository:
    """Test-only repository with deep-copy isolation and no I/O dependencies."""

    def __init__(self) -> None:
        self._objects: dict[tuple[UUID, UUID, str], RawObject] = {}

    @staticmethod
    def _key(*, scope: TenantAccountScope, object_id: str) -> tuple[UUID, UUID, str]:
        return scope.tenant_id, scope.account_id, object_id

    @staticmethod
    def _stored_copy(raw_object: RawObject) -> RawObject:
        return InMemoryRawObjectRepository._copy_raw_object(raw_object)

    @staticmethod
    def _read_copy(raw_object: RawObject) -> RawObject:
        return InMemoryRawObjectRepository._copy_raw_object(raw_object)

    @staticmethod
    def _copy_raw_object(raw_object: RawObject) -> RawObject:
        return RawObject(
            object_id=raw_object.object_id,
            scope=raw_object.scope,
            endpoint=raw_object.endpoint,
            object_type=raw_object.object_type,
            source=raw_object.source,
            retrieved_at=raw_object.retrieved_at,
            operational_date=raw_object.operational_date,
            request_scope=cast(RawRequestScope, _thaw_payload(raw_object.request_scope)),
            payload=_thaw_payload(raw_object.payload),
            raw_payload_bytes=raw_object.raw_payload_bytes,
            schema_version=raw_object.schema_version,
        )

    def save(self, raw_object: RawObject) -> None:
        key = self._key(scope=raw_object.scope, object_id=raw_object.object_id)
        if key in self._objects:
            raise DuplicateRawObjectError(f"raw object already exists: {raw_object.object_id}")
        self._objects[key] = self._stored_copy(raw_object)

    def get(self, *, scope: TenantAccountScope, object_id: str) -> RawObject:
        try:
            stored = self._objects[self._key(scope=scope, object_id=object_id)]
        except KeyError as error:
            raise RawObjectNotFoundError(f"raw object not found: {object_id}") from error
        return self._read_copy(stored)

    def list(self, *, scope: TenantAccountScope, endpoint_name: str | None = None) -> tuple[RawObject, ...]:
        items = [
            raw_object
            for (tenant_id, account_id, _), raw_object in self._objects.items()
            if tenant_id == scope.tenant_id
            and account_id == scope.account_id
            and (endpoint_name is None or raw_object.endpoint.name == endpoint_name)
        ]
        return tuple(self._read_copy(raw_object) for raw_object in sorted(items, key=lambda item: item.object_id))


class RawApiEvent(BaseModel):
    """Metadata for an immutable WB response stored outside the database."""

    model_config = ConfigDict(frozen=True)

    scope: TenantAccountScope
    source: str = Field(min_length=1, max_length=100)
    endpoint: str = Field(min_length=1, max_length=300)
    request_fingerprint: str = Field(min_length=16, max_length=128)
    payload_object_uri: HttpUrl
    payload_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    schema_version: str = Field(min_length=1, max_length=50)
    requested_at: datetime
    responded_at: datetime
    http_status: int = Field(ge=100, le=599)

    @field_validator("requested_at", "responded_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
            raise ValueError("timestamps must be timezone-aware UTC values")
        return value


class WBReadClient(Protocol):
    """Read-only boundary. Write actions belong to Automation Engine, not here."""

    def fetch(self, *, scope: TenantAccountScope, endpoint: str, request: dict[str, Any]) -> RawApiEvent:
        """Fetch a response, store its raw payload, and return provenance metadata."""
