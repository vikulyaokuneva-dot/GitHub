"""Funnel API raw loader.

Input: WBApiClient + RunContext.
Output: RawSourcePayload for funnel source.
Does not normalize or compute KPI.
"""

from __future__ import annotations

from ...core.contracts import RawSourcePayload, RunContext, SourceKind, SourceStatus, SourceStatusCode
from .client import WBApiClient
from .endpoints import FUNNEL


def _response_failure_reason(*, status_code: int | None, error_code: str | None) -> str:
    if status_code in {401, 403}:
        return "auth_error"
    token = str(error_code or "").strip().lower()
    if token in {"http_401", "http_403", "auth_error", "unauthorized", "forbidden"}:
        return "auth_error"
    return "request_failed"


def _build_funnel_body(run_context: RunContext) -> dict[str, object]:
    date_from = run_context.resolved_date_iso
    date_to = run_context.resolved_date_iso
    return {
        "selectedPeriod": {"start": date_from, "end": date_to},
        "nmIds": [],
        "brandNames": [],
        "subjectIds": [],
        "tagIds": [],
        "skipDeletedNm": True,
        "limit": 1000,
        "offset": 0,
    }


def load_funnel(client: WBApiClient, run_context: RunContext) -> RawSourcePayload:
    body = _build_funnel_body(run_context)
    response = client.post_json(FUNNEL, json_body=body, allow_statuses={204: []})
    rows = client.extract_rows(response.payload, ("data", "items", "products")) if response.ok else []

    warnings: list[str] = []
    reason = "ok"
    if response.ok and rows:
        status_code = SourceStatusCode.OK
    elif response.ok:
        status_code = SourceStatusCode.MISSING
        reason = "no_data_for_date" if run_context.resolved_date_iso or run_context.requested_date_iso else "empty_payload"
        if reason == "no_data_for_date":
            warnings.append("funnel source has no data for selected date")
        else:
            warnings.append("funnel source returned empty payload")
    else:
        status_code = SourceStatusCode.ERROR
        reason = _response_failure_reason(status_code=response.status_code, error_code=response.error_code)
        if reason == "auth_error":
            warnings.append("funnel source authentication failed")
        else:
            warnings.append("funnel source request failed")

    status = SourceStatus(
        source_name="funnel",
        kind=SourceKind.API,
        status=status_code,
        is_required=False,
        rows_loaded=(len(rows) if response.ok else None),
        endpoint=FUNNEL.path,
        requested_date=run_context.requested_date_iso,
        resolved_date=run_context.resolved_date_iso,
        error_code=response.error_code,
        error_message=response.error_message,
        warnings=warnings,
        debug={
            "endpoint_name": FUNNEL.name,
            "status_code": response.status_code,
            "attempts": response.attempts,
            "request_body": body,
            "reason": reason,
            "funnel_reason": reason,
        },
    )

    payload = {
        "rows": rows if response.ok else None,
        "raw": response.payload,
        "request": {"body": body},
        "reason": reason,
    }
    return RawSourcePayload(source_name="funnel", payload=payload, status=status)
