"""Realization API raw loader.

Input: WBApiClient + RunContext.
Output: RawSourcePayload for realization source.
Does not normalize or compute KPI.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any

from ...core.contracts import RawSourcePayload, RunContext, SourceKind, SourceStatus, SourceStatusCode
from ...extraction_compat import find_first_list, try_json_loads
from .client import WBApiClient
from .endpoints import REALIZATION


_DEFAULT_MAX_FINANCE_LAG_DAYS = 3


def _to_int(value: Any, *, default: int, minimum: int = 0) -> int:
    try:
        parsed = int(str(value).strip())
    except Exception:
        return default
    return max(parsed, minimum)


def _parse_iso_date(value: str | None) -> date | None:
    text = str(value or "").strip()[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _candidate_dates(target_date_iso: str | None, max_lag_days: int) -> list[str | None]:
    if not target_date_iso:
        return [None]
    parsed_target = _parse_iso_date(target_date_iso)
    if parsed_target is None:
        return [target_date_iso]
    return [(parsed_target - timedelta(days=lag)).isoformat() for lag in range(0, max_lag_days + 1)]


def _build_request_params(source_date: str | None) -> dict[str, Any]:
    params: dict[str, Any] = {
        "dateFrom": source_date,
        "dateTo": source_date,
        "limit": 100000,
        "rrdid": 0,
    }
    if not source_date:
        params.pop("dateFrom", None)
        params.pop("dateTo", None)
    return params


def _response_failure_reason(*, status_code: int | None, error_code: str | None) -> str:
    if status_code in {401, 403}:
        return "auth_failed"
    token = str(error_code or "").strip().lower()
    if token in {"http_401", "http_403", "auth_error", "auth_failed", "unauthorized", "forbidden"}:
        return "auth_failed"
    return "request_failed"


def _payload_is_empty(payload: Any) -> bool:
    payload = try_json_loads(payload)
    if payload is None:
        return True
    if isinstance(payload, (list, dict, str, bytes, tuple, set)):
        return len(payload) == 0
    return False


def _payload_shape(payload: Any) -> str:
    payload = try_json_loads(payload)
    if payload is None:
        return "none"
    if isinstance(payload, list):
        return "list"
    if isinstance(payload, dict):
        return "dict"
    return type(payload).__name__


def _raw_record_count(payload: Any) -> int:
    payload = try_json_loads(payload)
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("data", "items", "rows", "products", "result", "list", "stocks"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return len(rows)
        nested = find_first_list(payload)
        if isinstance(nested, list):
            return len(nested)
        return len(payload)
    return 0


def _explicit_empty_rows(payload: Any) -> bool:
    payload = try_json_loads(payload)
    if isinstance(payload, list):
        return len(payload) == 0
    if isinstance(payload, dict):
        for key in ("data", "items", "rows", "products", "result", "list", "stocks"):
            if key in payload and isinstance(payload.get(key), list) and len(payload.get(key)) == 0:
                return True
    return False


def _lag_days(target_date_iso: str | None, source_date_iso: str | None) -> int | None:
    parsed_target = _parse_iso_date(target_date_iso)
    parsed_source = _parse_iso_date(source_date_iso)
    if parsed_target is None or parsed_source is None:
        return None
    return (parsed_target - parsed_source).days


def load_realization(client: WBApiClient, run_context: RunContext) -> RawSourcePayload:
    requested_date = run_context.requested_date_iso
    resolved_date = run_context.resolved_date_iso
    target_date = resolved_date or requested_date

    max_lag_days = _to_int(
        os.getenv("WB_MAX_FINANCE_LAG_DAYS"),
        default=_DEFAULT_MAX_FINANCE_LAG_DAYS,
        minimum=0,
    )
    candidate_dates = _candidate_dates(target_date, max_lag_days)

    warnings: list[str] = []
    reason = "request_failed"
    status_code = SourceStatusCode.ERROR

    selected_response = None
    selected_rows: list[dict[str, Any]] = []
    selected_source_date: str | None = None
    selected_request_params: dict[str, Any] = {}
    selected_raw_count = 0
    selected_extraction_meta: dict[str, Any] = {}
    fallback_used = False
    lag_days: int | None = None
    total_attempts = 0
    attempt_log: list[dict[str, Any]] = []

    for index, source_date in enumerate(candidate_dates):
        params = _build_request_params(source_date)
        response = client.get_json(REALIZATION, params=params, allow_statuses={204: []})
        total_attempts += int(response.attempts or 0)

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
        raw_count = _raw_record_count(response.payload)
        payload_empty = _payload_is_empty(response.payload)
        explicit_empty_rows = _explicit_empty_rows(response.payload) or bool(extraction_meta.get("explicit_empty_list"))
        extraction_empty_on_nonempty_payload = bool(
            response.ok and not payload_empty and not explicit_empty_rows and not rows
        )

        attempt_reason = "ok_with_rows"
        if not response.ok:
            attempt_reason = _response_failure_reason(status_code=response.status_code, error_code=response.error_code)
        elif rows:
            attempt_reason = "fallback_used" if index > 0 else "ok_with_rows"
        elif extraction_empty_on_nonempty_payload:
            attempt_reason = "parse_failed"
        elif source_date:
            attempt_reason = "no_data_for_date"
        else:
            attempt_reason = "ok_empty_payload"

        attempt_log.append(
            {
                "source_date": source_date,
                "request_params": dict(params),
                "http_status": response.status_code,
                "ok": bool(response.ok),
                "attempts": response.attempts,
                "error_code": response.error_code,
                "reason": attempt_reason,
                "record_count_raw": raw_count,
                "rows_extracted": len(rows),
                "payload_shape": _payload_shape(response.payload),
                "payload_empty": payload_empty,
                "explicit_empty_rows": explicit_empty_rows,
                "extraction_mode": extraction_meta.get("mode"),
                "payload_origin": extraction_meta.get("origin"),
                "compat_used": bool(extraction_meta.get("compat_used", False)),
            }
        )

        selected_response = response
        selected_request_params = dict(params)
        selected_source_date = source_date
        selected_raw_count = raw_count
        selected_extraction_meta = dict(extraction_meta)

        if not response.ok:
            status_code = SourceStatusCode.ERROR
            reason = attempt_reason
            if reason == "auth_failed":
                warnings.append("realization source authentication failed")
            else:
                warnings.append("realization source request failed")
            break

        if rows:
            selected_rows = rows
            lag_days = _lag_days(target_date, source_date)
            fallback_used = bool(index > 0 and (lag_days is None or lag_days > 0))
            status_code = SourceStatusCode.PARTIAL if fallback_used else SourceStatusCode.OK
            reason = "fallback_used" if fallback_used else "ok_with_rows"
            if fallback_used:
                warnings.append("realization lag fallback applied: using previous available date")
            break

        if extraction_empty_on_nonempty_payload:
            status_code = SourceStatusCode.ERROR
            reason = "parse_failed"
            warnings.append("realization payload is non-empty but row extraction returned zero rows")
            break
    else:
        status_code = SourceStatusCode.MISSING
        selected_source_date = None
        lag_days = None
        fallback_used = False
        if target_date and len(candidate_dates) > 1:
            reason = "no_realization_in_window"
            warnings.append("realization source has no data in fallback window")
        elif target_date:
            reason = "no_data_for_date"
            warnings.append("realization source has no data for selected date")
        else:
            reason = "ok_empty_payload"
            warnings.append("realization source returned empty payload")

    debug_payload = selected_response.payload if selected_response is not None else None
    debug_status_code = selected_response.status_code if selected_response is not None else None
    debug_attempts = selected_response.attempts if selected_response is not None else None
    debug_error_code = selected_response.error_code if selected_response is not None else None
    debug_error_message = selected_response.error_message if selected_response is not None else None

    status_error_code = debug_error_code
    status_error_message = debug_error_message
    if status_code == SourceStatusCode.ERROR and reason == "parse_failed":
        status_error_code = "parse_failed"
        status_error_message = "realization payload is non-empty but row extraction returned zero rows"
    if status_code != SourceStatusCode.ERROR:
        status_error_code = None
        status_error_message = None

    if status_code in {SourceStatusCode.OK, SourceStatusCode.PARTIAL} and lag_days is None:
        lag_days = _lag_days(target_date, selected_source_date)
    if status_code != SourceStatusCode.PARTIAL:
        fallback_used = bool(status_code == SourceStatusCode.OK and reason == "fallback_used")
        if status_code != SourceStatusCode.OK:
            lag_days = None

    response_ok = bool(selected_response.ok) if selected_response is not None else False
    rows_for_payload: list[dict[str, Any]] | None = None
    if status_code in {SourceStatusCode.OK, SourceStatusCode.PARTIAL}:
        rows_for_payload = list(selected_rows)
    elif status_code == SourceStatusCode.MISSING and response_ok:
        rows_for_payload = []

    if status_code == SourceStatusCode.OK and reason != "ok_with_rows":
        reason = "ok_with_rows"
    if status_code == SourceStatusCode.PARTIAL and reason != "fallback_used":
        reason = "fallback_used"
    if status_code == SourceStatusCode.MISSING and reason not in {"no_data_for_date", "ok_empty_payload", "no_realization_in_window"}:
        reason = "no_realization_in_window" if target_date and len(candidate_dates) > 1 else "no_data_for_date"
    if status_code == SourceStatusCode.ERROR and reason not in {"request_failed", "auth_failed", "parse_failed"}:
        reason = "request_failed"
        if not warnings:
            warnings.append("realization source request failed")

    if status_code == SourceStatusCode.PARTIAL and not warnings:
        warnings.append("realization lag fallback applied: using previous available date")
    if status_code == SourceStatusCode.MISSING and not warnings:
        if reason == "no_realization_in_window":
            warnings.append("realization source has no data in fallback window")
        elif reason == "no_data_for_date":
            warnings.append("realization source has no data for selected date")
        else:
            warnings.append("realization source returned empty payload")

    status = SourceStatus(
        source_name="realization",
        kind=SourceKind.API,
        status=status_code,
        is_required=True,
        rows_loaded=(len(selected_rows) if response_ok else None),
        endpoint=REALIZATION.path,
        requested_date=requested_date,
        resolved_date=resolved_date,
        error_code=status_error_code,
        error_message=status_error_message,
        warnings=warnings,
        debug={
            "endpoint_name": REALIZATION.name,
            "status_code": debug_status_code,
            "attempts": debug_attempts,
            "request_params": selected_request_params,
            "requested_date": requested_date,
            "resolved_date": resolved_date,
            "target_date": target_date,
            "fallback_used": fallback_used,
            "source_date": selected_source_date,
            "lag_days": lag_days,
            "reason": reason,
            "realization_reason": reason,
            "realization_http_status": debug_status_code,
            "realization_attempts": total_attempts,
            "realization_record_count_raw": selected_raw_count,
            "realization_request_params": selected_request_params,
            "realization_fallback_used": fallback_used,
            "realization_source_date": selected_source_date,
            "realization_lag_days": lag_days,
            "realization_target_date": target_date,
            "realization_max_lag_days": max_lag_days,
            "realization_rows_extracted": len(selected_rows),
            "realization_payload_shape": _payload_shape(debug_payload),
            "realization_payload_empty": _payload_is_empty(debug_payload),
            "realization_empty_by_status": debug_status_code == 204,
            "realization_extraction_mode": selected_extraction_meta.get("mode"),
            "realization_payload_origin": selected_extraction_meta.get("origin"),
            "realization_compat_used": bool(selected_extraction_meta.get("compat_used", False)),
            "realization_attempt_log": attempt_log,
        },
    )

    payload = {
        "rows": rows_for_payload,
        "raw": debug_payload,
        "request": {
            "params": selected_request_params,
            "attempt_log": attempt_log,
        },
        "realization_meta": {
            "requested_date": requested_date,
            "resolved_date": resolved_date,
            "target_date": target_date,
            "fallback_used": fallback_used,
            "source_date": selected_source_date,
            "lag_days": lag_days,
            "max_lag_days": max_lag_days,
            "attempt_count": len(attempt_log),
        },
        "reason": reason,
        "extraction": dict(selected_extraction_meta),
    }
    return RawSourcePayload(source_name="realization", payload=payload, status=status)
