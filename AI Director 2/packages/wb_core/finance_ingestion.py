"""Durable raw-object ingestion for the existing Finance Detail source."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from typing import Protocol

from packages.data.canonical import CanonicalFinanceDetailRecord
from packages.data.normalization import normalize_finance_detail

from .contracts import (
    FINANCE_DETAIL_ENDPOINT,
    DuplicateRawObjectError,
    RawObject,
    RawObjectRepository,
    RawPayload,
    TenantAccountScope,
)


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
        """Reuse the durable raw of exactly this date, otherwise fetch once.

        A durable raw is authoritative only for its own ``operational_date``:
        the candidate list is filtered by that exact date (plus the endpoint
        identity the repository filter already applies), so a raw captured for
        another day can never satisfy this audit.

        Existing does not mean usable: a candidate that the current finance
        loader contract cannot normalize is skipped instead of being trusted
        silently, and the ordinary live path takes over (one WB request). If
        that live answer is unusable too, the failure surfaces as ``RuntimeError``
        so the audit reports an unavailable source rather than a fabricated
        or partially trusted P&L.
        """

        for candidate in self._durable_candidates(scope=scope, operational_date=operational_date):
            try:
                return normalize_finance_detail(candidate)
            except ValueError:
                # Unusable durable raw: never used as finance evidence. The
                # live path below is the existing fallback, and the pipeline
                # keeps reporting the excluded object as an explicit
                # diagnostic instead of dropping it silently.
                continue

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
        try:
            self._repository.save(raw_object)
        except DuplicateRawObjectError:
            # Byte-identical payload for this exact date is already durable:
            # re-open it instead of failing on the immutable identity.
            pass
        stored = self._repository.get(scope=scope, object_id=raw_object.object_id)
        try:
            return normalize_finance_detail(stored)
        except ValueError as error:
            raise RuntimeError(
                f"finance_detail raw for {operational_date.isoformat()} failed validation and cannot be used: {error}"
            ) from error

    def _durable_candidates(
        self, *, scope: TenantAccountScope, operational_date: date
    ) -> tuple[RawObject, ...]:
        """Durable raws of exactly this operational date in deterministic order."""

        return tuple(
            raw_object
            for raw_object in self._repository.list(scope=scope, endpoint_name=FINANCE_DETAIL_ENDPOINT.name)
            if raw_object.operational_date == operational_date
        )
