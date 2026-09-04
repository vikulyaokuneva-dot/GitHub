"""Durable raw-array ingestion for the declared operational endpoints."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any, Protocol

from packages.data.canonical import CanonicalOperationalOrder, CanonicalOperationalSale
from packages.data.normalization import normalize_orders, normalize_sales

from .contracts import ORDERS_ENDPOINT, SALES_ENDPOINT, EndpointMetadata, RawObject, RawObjectRepository, TenantAccountScope


class WBOrdersTransport(Protocol):
    """Read-only orders transport which provides decoded JSON plus exact response bytes."""

    def fetch_orders(self, *, operational_date: date) -> tuple[list[dict[str, Any]], bytes]:
        """Fetch the raw top-level array without a synthetic wrapper."""


class WBSalesTransport(Protocol):
    """Read-only sales transport which provides decoded JSON plus exact response bytes."""

    def fetch_sales(self, *, operational_date: date) -> tuple[list[dict[str, Any]], bytes]:
        """Fetch the raw top-level array without a synthetic wrapper."""


def _object_id(
    *, scope: TenantAccountScope, endpoint: EndpointMetadata, operational_date: date, payload_bytes: bytes
) -> str:
    digest_input = {
        "account_id": str(scope.account_id),
        "endpoint": endpoint.name,
        "operational_date": operational_date.isoformat(),
        "payload_sha256": hashlib.sha256(payload_bytes).hexdigest(),
        "tenant_id": str(scope.tenant_id),
    }
    return hashlib.sha256(json.dumps(digest_input, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


class WBOrdersIngestionService:
    """Persist an untouched orders JSON array before its canonical normalization."""

    def __init__(self, *, repository: RawObjectRepository, transport: WBOrdersTransport) -> None:
        self._repository = repository
        self._transport = transport

    def ingest(
        self, *, scope: TenantAccountScope, operational_date: date, retrieved_at: datetime | None = None
    ) -> tuple[CanonicalOperationalOrder, ...]:
        payload, raw_payload_bytes = self._transport.fetch_orders(operational_date=operational_date)
        request_scope = {"dateFrom": operational_date.isoformat(), "flag": 0}
        raw_object = RawObject(
            object_id=_object_id(
                scope=scope, endpoint=ORDERS_ENDPOINT, operational_date=operational_date, payload_bytes=raw_payload_bytes
            ),
            scope=scope,
            endpoint=ORDERS_ENDPOINT,
            object_type=ORDERS_ENDPOINT.object_type,
            source=ORDERS_ENDPOINT.source,
            retrieved_at=retrieved_at or datetime.now(UTC),
            operational_date=operational_date,
            request_scope=request_scope,
            payload=payload,
            raw_payload_bytes=raw_payload_bytes,
            schema_version=ORDERS_ENDPOINT.schema_version,
        )
        self._repository.save(raw_object)
        return normalize_orders(self._repository.get(scope=scope, object_id=raw_object.object_id))


class WBSalesIngestionService:
    """Persist an untouched sales JSON array before its canonical normalization."""

    def __init__(self, *, repository: RawObjectRepository, transport: WBSalesTransport) -> None:
        self._repository = repository
        self._transport = transport

    def ingest(
        self, *, scope: TenantAccountScope, operational_date: date, retrieved_at: datetime | None = None
    ) -> tuple[CanonicalOperationalSale, ...]:
        payload, raw_payload_bytes = self._transport.fetch_sales(operational_date=operational_date)
        request_scope = {"dateFrom": operational_date.isoformat(), "flag": 1}
        raw_object = RawObject(
            object_id=_object_id(
                scope=scope, endpoint=SALES_ENDPOINT, operational_date=operational_date, payload_bytes=raw_payload_bytes
            ),
            scope=scope,
            endpoint=SALES_ENDPOINT,
            object_type=SALES_ENDPOINT.object_type,
            source=SALES_ENDPOINT.source,
            retrieved_at=retrieved_at or datetime.now(UTC),
            operational_date=operational_date,
            request_scope=request_scope,
            payload=payload,
            raw_payload_bytes=raw_payload_bytes,
            schema_version=SALES_ENDPOINT.schema_version,
        )
        self._repository.save(raw_object)
        return normalize_sales(self._repository.get(scope=scope, object_id=raw_object.object_id))
