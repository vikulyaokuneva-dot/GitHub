"""Production raw-to-canonical ingestion boundary for one WB endpoint."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any, Protocol

from packages.data.canonical import CanonicalSalesFunnelProduct
from packages.data.normalization import normalize_sales_funnel_products

from .contracts import RawObject, RawObjectRepository, RawObjectType, SALES_FUNNEL_PRODUCTS_ENDPOINT, TenantAccountScope


class WBSalesFunnelTransport(Protocol):
    """Read-only transport contract; compatibility code owns the legacy client binding."""

    def fetch_sales_funnel_products(self, *, operational_date: date) -> Mapping[str, Any]:
        """Fetch one raw WB sales-funnel response for the requested Moscow business date."""


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


def _object_id(*, scope: TenantAccountScope, operational_date: date, request_scope: dict[str, Any], payload: Mapping[str, Any]) -> str:
    identity = {
        "account_id": str(scope.account_id),
        "endpoint": SALES_FUNNEL_PRODUCTS_ENDPOINT.name,
        "operational_date": operational_date.isoformat(),
        "payload": _json_ready(payload),
        "request_scope": _json_ready(request_scope),
        "schema_version": SALES_FUNNEL_PRODUCTS_ENDPOINT.schema_version,
        "tenant_id": str(scope.tenant_id),
    }
    encoded = json.dumps(identity, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class WBSalesFunnelIngestionService:
    """Persist a raw response, read it back, then structurally normalize it."""

    def __init__(self, *, repository: RawObjectRepository, transport: WBSalesFunnelTransport) -> None:
        self._repository = repository
        self._transport = transport

    def ingest(self, *, scope: TenantAccountScope, operational_date: date, retrieved_at: datetime | None = None) -> tuple[CanonicalSalesFunnelProduct, ...]:
        """Run the first production vertical slice with no finance or reporting work."""

        raw_payload = self._transport.fetch_sales_funnel_products(operational_date=operational_date)
        payload = _json_ready(raw_payload)
        if not isinstance(payload, dict):
            raise ValueError("sales_funnel_products response must be a JSON object")
        request_scope = {
            "selectedPeriod": {"start": operational_date.isoformat(), "end": operational_date.isoformat()},
            "nmIds": [],
            "brandNames": [],
            "subjectIds": [],
            "tagIds": [],
            "skipDeletedNm": True,
            "limit": 1000,
            "offset": 0,
        }
        raw_object = RawObject(
            object_id=_object_id(
                scope=scope,
                operational_date=operational_date,
                request_scope=request_scope,
                payload=payload,
            ),
            scope=scope,
            endpoint=SALES_FUNNEL_PRODUCTS_ENDPOINT,
            object_type=RawObjectType.SALES_FUNNEL_PRODUCTS,
            source=SALES_FUNNEL_PRODUCTS_ENDPOINT.source,
            retrieved_at=retrieved_at or datetime.now(UTC),
            operational_date=operational_date,
            request_scope=request_scope,
            payload=payload,
            schema_version=SALES_FUNNEL_PRODUCTS_ENDPOINT.schema_version,
        )
        self._repository.save(raw_object)
        stored = self._repository.get(scope=scope, object_id=raw_object.object_id)
        return normalize_sales_funnel_products(stored)
