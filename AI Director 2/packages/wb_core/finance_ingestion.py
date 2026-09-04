"""Durable raw-object ingestion for the existing Finance Detail source."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from typing import Any, Protocol

from packages.data.canonical import CanonicalFinanceDetailRecord
from packages.data.normalization import normalize_finance_detail

from .contracts import FINANCE_DETAIL_ENDPOINT, RawObject, RawObjectRepository, RawPayload, TenantAccountScope


class WBFinanceDetailTransport(Protocol):
    """Read-only finance-detail transport with decoded JSON and original response bytes."""

    def fetch_finance_detail(self, *, operational_date: date) -> tuple[RawPayload, bytes]:
        """Fetch a finance-detail object without modifying its JSON root or payload."""


def _object_id(*, scope: TenantAccountScope, operational_date: date, payload_bytes: bytes) -> str:
    identity = {
        "account_id": str(scope.account_id),
        "endpoint": FINANCE_DETAIL_ENDPOINT.name,
        "operational_date": operational_date.isoformat(),
        "payload_sha256": hashlib.sha256(payload_bytes).hexdigest(),
        "tenant_id": str(scope.tenant_id),
    }
    return hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


class WBFinanceDetailIngestionService:
    """Persist the real finance object, reopen it, then invoke the existing normalizer."""

    def __init__(self, *, repository: RawObjectRepository, transport: WBFinanceDetailTransport) -> None:
        self._repository = repository
        self._transport = transport

    def ingest(
        self, *, scope: TenantAccountScope, operational_date: date, retrieved_at: datetime | None = None
    ) -> tuple[CanonicalFinanceDetailRecord, ...]:
        existing = tuple(
            raw_object
            for raw_object in self._repository.list(scope=scope, endpoint_name=FINANCE_DETAIL_ENDPOINT.name)
            if raw_object.operational_date == operational_date
        )
        if existing:
            return normalize_finance_detail(existing[0])
        payload, raw_payload_bytes = self._transport.fetch_finance_detail(operational_date=operational_date)
        request_scope = {
            "dateFrom": operational_date.isoformat(),
            "dateTo": operational_date.isoformat(),
            "period": "daily",
            "limit": 100000,
            "rrdId": 0,
        }
        raw_object = RawObject(
            object_id=_object_id(scope=scope, operational_date=operational_date, payload_bytes=raw_payload_bytes),
            scope=scope,
            endpoint=FINANCE_DETAIL_ENDPOINT,
            object_type=FINANCE_DETAIL_ENDPOINT.object_type,
            source=FINANCE_DETAIL_ENDPOINT.source,
            retrieved_at=retrieved_at or datetime.now(UTC),
            operational_date=operational_date,
            request_scope=request_scope,
            payload=payload,
            raw_payload_bytes=raw_payload_bytes,
            schema_version=FINANCE_DETAIL_ENDPOINT.schema_version,
        )
        self._repository.save(raw_object)
        return normalize_finance_detail(self._repository.get(scope=scope, object_id=raw_object.object_id))
