"""Sales API raw loader.

Input: WBApiClient + RunContext.
Output: RawSourcePayload for sales source.
Does not normalize or compute KPI.
"""

from __future__ import annotations

from typing import Any

from ...core.contracts import RawSourcePayload, RunContext, SourceKind, SourceStatus, SourceStatusCode
from ...extraction_compat import find_first_list, try_json_loads
from .client import WBApiClient
from .endpoints import SALES


def _response_failure_reason(*, status_code: int | None, error_code: str | None) -> str:
    if status_code in {401, 403}:
        return "auth_failed"
    token = str(error_code or "").strip().lower()
    if token in {"http_401", "http_403", "auth_error", "auth_failed", "unauthorized", "forbidden"}:
        return "auth_failed"
    return "request_failed"


def _payload_is_empty(payload: Any) -> bool:
    parsed = try_json_loads(payload)
    if parsed is None:
        return True
    if isinstance(parsed, (list, dict, str, bytes, tuple, set)):
        return len(parsed) == 0
    return False


def _payload_shape(payload: Any) -> str:
    parsed = try_json_loads(payload)
    if parsed is None:
        return "none"
    if isinstance(parsed, list):
        return "list"
    if isinstance(parsed, dict):
        return "dict"
    return type(parsed).__name__


def _raw_record_count(payload: Any) -> int:
    parsed = try_json_loads(payload)
    if isinstance(parsed, list):
        return len(parsed)
    if isinstance(parsed, dict):
        for key in ("data", "items", "rows", "products", "result", "list", "stocks"):
            rows = parsed.get(key)
            if isinstance(rows, list):
                return len(rows)
        nested = find_first_list(parsed)
        if isinstance(nested, list):
            return len(nested)
        return len(parsed)
    return 0


def _explicit_empty_rows(payload: Any) -> bool:
    parsed = try_json_loads(payload)
    if isinstance(parsed, list):
        return len(parsed) == 0
    if isinstance(parsed, dict):
        for key in ("data", "items", "rows", "products", "result", "list", "stocks"):
            if key in parsed and isinstance(parsed.get(key), list) and len(parsed.get(key)) == 0:
                return True
    return False


def load_sales(client: WBApiClient, run_context: RunContext) -> RawSourcePayload:
    requested_date = run_context.requested_date_iso
    resolved_date = run_context.resolved_date_iso

    params = {"dateFrom": resolved_date} if resolved_date else {}
    response = client.get_json(SALES, params=params, allow_statuses={204: []})

    extraction_meta: dict[str, Any] = {
        "mode": "none",
        "origin": None,
        "compat_used": False,
        "explicit_empty_list": False,
        "payload_shape": _payload_shape(response.payload),
    }
    rows: list[dict[str, Any]] = []
    if response.ok:
        rows, extraction_meta = client.extract_rows_with_diagnostics(
            response.payload,
            ("data", "items", "rows"),
        )
    warnings: list[str] = []
    payload_empty = _payload_is_empty(response.payload)
    explicit_empty_rows = _explicit_empty_rows(response.payload) or bool(extraction_meta.get("explicit_empty_list"))
    extraction_empty_on_nonempty_payload = bool(
        response.ok and not payload_empty and not explicit_empty_rows and not rows
    )
    reason = "request_failed"
    status_error_code = response.error_code
    status_error_message = response.error_message

    if response.ok and rows:
        status_code = SourceStatusCode.OK
        reason = "ok_with_rows"
    elif response.ok and extraction_empty_on_nonempty_payload:
        status_code = SourceStatusCode.ERROR
        reason = "parse_failed"
        status_error_code = "parse_failed"
        status_error_message = "sales payload is non-empty but row extraction returned zero rows"
        warnings.append("sales payload is non-empty but row extraction returned zero rows")
    elif response.ok:
        status_code = SourceStatusCode.MISSING
        reason = "ok_empty_payload"
        status_error_code = None
        status_error_message = None
        warnings.append("sales source returned empty payload")
    else:
        status_code = SourceStatusCode.ERROR
        reason = _response_failure_reason(status_code=response.status_code, error_code=response.error_code)
        if reason == "auth_failed":
            warnings.append("sales source authentication failed")
        else:
            warnings.append("sales source request failed")

    status = SourceStatus(
        source_name="sales",
        kind=SourceKind.API,
        status=status_code,
        is_required=True,
        rows_loaded=(len(rows) if response.ok else None),
        endpoint=SALES.path,
        requested_date=requested_date,
        resolved_date=resolved_date,
        error_code=status_error_code if status_code == SourceStatusCode.ERROR else None,
        error_message=status_error_message if status_code == SourceStatusCode.ERROR else None,
        warnings=warnings,
        debug={
            "endpoint_name": SALES.name,
            "status_code": response.status_code,
            "attempts": response.attempts,
            "request_params": params,
            "reason": reason,
            "sales_reason": reason,
            "sales_rows_extracted": len(rows),
            "sales_record_count_raw": _raw_record_count(response.payload),
            "sales_payload_shape": _payload_shape(response.payload),
            "sales_payload_empty": payload_empty,
            "sales_extraction_mode": extraction_meta.get("mode"),
            "sales_payload_origin": extraction_meta.get("origin"),
            "sales_compat_used": bool(extraction_meta.get("compat_used", False)),
        },
    )

    payload = {
        "rows": rows if response.ok else None,
        "raw": response.payload,
        "request": {"params": params},
        "reason": reason,
        "extraction": dict(extraction_meta),
    }
    return RawSourcePayload(source_name="sales", payload=payload, status=status)
