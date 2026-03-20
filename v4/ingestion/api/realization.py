"""Realization API raw loader.

Input: WBApiClient + RunContext.
Output: RawSourcePayload for realization source.
Does not normalize or compute KPI.
"""

from __future__ import annotations

from ...core.contracts import RawSourcePayload, RunContext, SourceKind, SourceStatus, SourceStatusCode
from .client import WBApiClient
from .endpoints import REALIZATION


def _response_failure_reason(*, status_code: int | None, error_code: str | None) -> str:
    if status_code in {401, 403}:
        return "auth_error"
    token = str(error_code or "").strip().lower()
    if token in {"http_401", "http_403", "auth_error", "unauthorized", "forbidden"}:
        return "auth_error"
    return "request_failed"


def load_realization(client: WBApiClient, run_context: RunContext) -> RawSourcePayload:
    requested_date = run_context.requested_date_iso
    resolved_date = run_context.resolved_date_iso

    params = {
        "dateFrom": resolved_date,
        "dateTo": resolved_date,
        "limit": 100000,
        "rrdid": 0,
    }
    if not resolved_date:
        params.pop("dateFrom", None)
        params.pop("dateTo", None)

    response = client.get_json(REALIZATION, params=params, allow_statuses={204: []})
    rows = client.extract_rows(response.payload, ("data", "items", "rows")) if response.ok else []

    warnings: list[str] = []
    reason = "ok"
    if response.ok and rows:
        status_code = SourceStatusCode.OK
    elif response.ok:
        status_code = SourceStatusCode.MISSING
        reason = "no_data_for_date" if resolved_date or requested_date else "empty_payload"
        if reason == "no_data_for_date":
            warnings.append("realization source has no data for selected date")
        else:
            warnings.append("realization source returned empty payload")
    else:
        status_code = SourceStatusCode.ERROR
        reason = _response_failure_reason(status_code=response.status_code, error_code=response.error_code)
        if reason == "auth_error":
            warnings.append("realization source authentication failed")
        else:
            warnings.append("realization source request failed")

    status = SourceStatus(
        source_name="realization",
        kind=SourceKind.API,
        status=status_code,
        is_required=True,
        rows_loaded=(len(rows) if response.ok else None),
        endpoint=REALIZATION.path,
        requested_date=requested_date,
        resolved_date=resolved_date,
        error_code=response.error_code,
        error_message=response.error_message,
        warnings=warnings,
        debug={
            "endpoint_name": REALIZATION.name,
            "status_code": response.status_code,
            "attempts": response.attempts,
            "request_params": params,
            "requested_date": requested_date,
            "resolved_date": resolved_date,
            "fallback_used": False,
            "source_date": None,
            "reason": reason,
            "realization_reason": reason,
        },
    )

    payload = {
        "rows": rows if response.ok else None,
        "raw": response.payload,
        "request": {"params": params},
        "realization_meta": {
            "requested_date": requested_date,
            "resolved_date": resolved_date,
            "fallback_used": False,
            "source_date": None,
        },
        "reason": reason,
    }
    return RawSourcePayload(source_name="realization", payload=payload, status=status)
