from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Final, Protocol

from packages.wb_core.contracts import (
    ADVERTISING_PERFORMANCE_ENDPOINT,
    ORDERS_ENDPOINT,
    SALES_ENDPOINT,
    SALES_FUNNEL_PRODUCTS_ENDPOINT,
    STOCKS_ENDPOINT,
    RawObject,
    TenantAccountScope,
)
from packages.wb_core.sqlite_repository import SQLiteRawObjectRepository


class WBDailyLoadersTransport(Protocol):
    """Read-only daily loader transport; compatibility code owns the legacy binding."""

    def load_orders(self, *, operational_date: date) -> dict[str, Any]: ...

    def load_sales(self, *, operational_date: date) -> dict[str, Any]: ...

    def load_stocks(self, *, operational_date: date) -> dict[str, Any]: ...

    def load_cabinet_commerce(self, *, operational_date: date) -> dict[str, Any]: ...

    def load_ads(self, *, operational_date: date) -> dict[str, Any]: ...


_CREDENTIAL_FIELD_MARKERS: Final = (
    "token",
    "api_key",
    "apikey",
    "authorization",
    "auth",
    "secret",
    "password",
    "cookie",
    "credential",
)
_DEBUG_ONLY_KEYS: Final = ("_loader_debug",)


def _is_credential_shaped_key(key: str) -> bool:
    lowered = key.strip().lower()
    return any(marker in lowered for marker in _CREDENTIAL_FIELD_MARKERS)


def sanitize_loader_payload(value: Any) -> Any:
    """Deterministically strip credential/debug keys from a loader payload.

    Applies recursively (dicts and lists). The RawObject validator remains the
    authoritative credential-free contract; this boundary just guarantees that
    transport/debug metadata never reaches it.
    """

    if isinstance(value, dict):
        return {
            key: sanitize_loader_payload(item)
            for key, item in value.items()
            if key not in _DEBUG_ONLY_KEYS and not _is_credential_shaped_key(key)
        }
    if isinstance(value, list):
        return [sanitize_loader_payload(item) for item in value]
    return value


class WBDailyIngestionService:
    """
    Fetches the raw WB responses required by the V2 daily pipeline and
    persists them as immutable RawObjects.

    This class is intentionally an ingestion boundary:
        WB API -> RawObject -> SQLite

    It must not calculate financials, aggregate business metrics, or render
    reports.
    """

    def __init__(
        self,
        *,
        repository: SQLiteRawObjectRepository,
        loaders: WBDailyLoadersTransport,
    ) -> None:
        self._repository = repository
        self._loaders = loaders

    def ingest(
        self,
        *,
        scope: TenantAccountScope,
        operational_date: date,
        retrieved_at: datetime | None = None,
    ) -> tuple[str, ...]:
        """Ingest every daily source, one endpoint at a time.

        A transport failure of a single WB source is recorded as an explicit
        ``source_unavailable`` diagnostic and the remaining sources continue.
        The failure is never persisted as empty data and never silently
        dropped: absence of a source stays absence, visible to the audit.
        """

        captured_at = retrieved_at or datetime.now(UTC)

        steps: tuple[tuple[str, Any], ...] = (
            (ORDERS_ENDPOINT.name, self._ensure_orders),
            (SALES_ENDPOINT.name, self._ensure_sales),
            (STOCKS_ENDPOINT.name, self._ensure_stocks),
            (SALES_FUNNEL_PRODUCTS_ENDPOINT.name, self._ensure_funnel),
            (ADVERTISING_PERFORMANCE_ENDPOINT.name, self._ensure_advertising),
        )

        diagnostics: list[str] = []
        for endpoint_name, ensure in steps:
            try:
                ensure(scope, operational_date, captured_at)
            except RuntimeError as error:
                diagnostics.append(f"source_unavailable:{endpoint_name}: {error}")
        return tuple(diagnostics)

    def _existing(
        self,
        *,
        scope: TenantAccountScope,
        endpoint_name: str,
        operational_date: date,
    ) -> bool:
        return any(
            raw.operational_date == operational_date
            for raw in self._repository.list(
                scope=scope,
                endpoint_name=endpoint_name,
            )
        )

    def _save(
        self,
        *,
        scope: TenantAccountScope,
        operational_date: date,
        retrieved_at: datetime,
        endpoint: Any,
        request_scope: dict[str, Any],
        payload: dict[str, Any] | list[Any],
        payload_bytes: bytes,
    ) -> None:
        raw_object = RawObject(
            object_id=self._object_id(
                scope=scope,
                endpoint=endpoint,
                operational_date=operational_date,
                payload_bytes=payload_bytes,
            ),
            scope=scope,
            endpoint=endpoint,
            object_type=endpoint.object_type,
            source=endpoint.source,
            retrieved_at=retrieved_at,
            operational_date=operational_date,
            request_scope=request_scope,
            payload=payload,
            raw_payload_bytes=payload_bytes,
            schema_version=endpoint.schema_version,
        )
        self._repository.save(raw_object)

    @staticmethod
    def _object_id(
        *,
        scope: TenantAccountScope,
        endpoint: Any,
        operational_date: date,
        payload_bytes: bytes,
    ) -> str:
        import hashlib

        material = (
            f"{scope.model_dump_json()}|"
            f"{endpoint.name}|"
            f"{operational_date.isoformat()}|"
        ).encode() + payload_bytes
        return hashlib.sha256(material).hexdigest()

    def _ensure_orders(
        self,
        scope: TenantAccountScope,
        operational_date: date,
        retrieved_at: datetime,
    ) -> None:
        if self._existing(
            scope=scope,
            endpoint_name=ORDERS_ENDPOINT.name,
            operational_date=operational_date,
        ):
            return

        result = self._loaders.load_orders(operational_date=operational_date)
        self._persist_loader_result(
            scope=scope,
            operational_date=operational_date,
            retrieved_at=retrieved_at,
            endpoint=ORDERS_ENDPOINT,
            result=result,
            request_scope={
                "dateFrom": operational_date.isoformat(),
                "flag": 0,
            },
        )

    def _ensure_sales(
        self,
        scope: TenantAccountScope,
        operational_date: date,
        retrieved_at: datetime,
    ) -> None:
        if self._existing(
            scope=scope,
            endpoint_name=SALES_ENDPOINT.name,
            operational_date=operational_date,
        ):
            return

        result = self._loaders.load_sales(operational_date=operational_date)
        self._persist_loader_result(
            scope=scope,
            operational_date=operational_date,
            retrieved_at=retrieved_at,
            endpoint=SALES_ENDPOINT,
            result=result,
            request_scope={
                "dateFrom": operational_date.isoformat(),
                "flag": 1,
            },
        )

    def _ensure_stocks(
        self,
        scope: TenantAccountScope,
        operational_date: date,
        retrieved_at: datetime,
    ) -> None:
        if self._existing(
            scope=scope,
            endpoint_name=STOCKS_ENDPOINT.name,
            operational_date=operational_date,
        ):
            return

        result = self._loaders.load_stocks(operational_date=operational_date)
        self._persist_loader_result(
            scope=scope,
            operational_date=operational_date,
            retrieved_at=retrieved_at,
            endpoint=STOCKS_ENDPOINT,
            result=result,
            request_scope={
                "dateFrom": operational_date.isoformat(),
            },
        )

    def _ensure_funnel(
        self,
        scope: TenantAccountScope,
        operational_date: date,
        retrieved_at: datetime,
    ) -> None:
        if self._existing(
            scope=scope,
            endpoint_name=SALES_FUNNEL_PRODUCTS_ENDPOINT.name,
            operational_date=operational_date,
        ):
            return

        result = self._loaders.load_cabinet_commerce(operational_date=operational_date)

        self._persist_loader_result(
            scope=scope,
            operational_date=operational_date,
            retrieved_at=retrieved_at,
            endpoint=SALES_FUNNEL_PRODUCTS_ENDPOINT,
            result=result,
            request_scope={
                "dateFrom": operational_date.isoformat(),
                "dateTo": operational_date.isoformat(),
            },
        )

    def _ensure_advertising(
        self,
        scope: TenantAccountScope,
        operational_date: date,
        retrieved_at: datetime,
    ) -> None:
        if self._existing(
            scope=scope,
            endpoint_name=ADVERTISING_PERFORMANCE_ENDPOINT.name,
            operational_date=operational_date,
        ):
            return

        result = self._loaders.load_ads(operational_date=operational_date)

        self._persist_loader_result(
            scope=scope,
            operational_date=operational_date,
            retrieved_at=retrieved_at,
            endpoint=ADVERTISING_PERFORMANCE_ENDPOINT,
            result=result,
            request_scope={
                "dateFrom": operational_date.isoformat(),
                "dateTo": operational_date.isoformat(),
            },
        )

    def _persist_loader_result(
        self,
        *,
        scope: TenantAccountScope,
        operational_date: date,
        retrieved_at: datetime,
        endpoint: Any,
        result: dict[str, Any],
        request_scope: dict[str, Any],
    ) -> None:
        """
        Compatibility boundary for existing loaders.

        IMPORTANT:
        The V2 RawObject must contain the actual WB response, not a rendered
        report or financial calculation.

        If the loader exposes raw response bytes, use them. Otherwise serialize
        the loader payload deterministically so the V2 repository still has an
        immutable byte representation.

        Loader transport/debug metadata (including ``_loader_debug`` and any
        credential-shaped keys) is removed before persistence: only WB data
        required for replay/analysis may enter a RawObject. Sanitization is
        deterministic and never weakens the RawObject credential-free
        validator, which stays authoritative.
        """
        import json

        debug = result.get("debug")
        if isinstance(debug, dict) and debug.get("success") is False:
            # A failed WB request must never be persisted as an empty raw
            # object: "no data" and "request failed" are different states,
            # and persisting the failure would also lock idempotency against
            # a later successful refetch.
            reason = str(
                debug.get("final_failure_reason")
                or debug.get("error_text")
                or "loader transport failed"
            )
            raise RuntimeError(
                f"{endpoint.name} WB request failed with status {debug.get('status_code')}: {reason[:200]}"
            )

        payload = result.get("payload")

        if payload is None:
            payload = {"data": result.get("rows_raw", [])}
        payload = sanitize_loader_payload(payload)

        if not isinstance(payload, (dict, list)):
            payload = {"data": result.get("rows_raw", [])}

        payload_bytes = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        self._save(
            scope=scope,
            operational_date=operational_date,
            retrieved_at=retrieved_at,
            endpoint=endpoint,
            request_scope=request_scope,
            payload=payload,
            payload_bytes=payload_bytes,
        )