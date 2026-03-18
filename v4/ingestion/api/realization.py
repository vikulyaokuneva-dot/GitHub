"""Realization API raw loader.

Input: WBApiClient + RunContext.
Output: RawSourcePayload for realization source.
Does not normalize or compute KPI.
"""

from __future__ import annotations

from ...core.contracts import RawSourcePayload, RunContext, SourceKind, SourceStatus, SourceStatusCode
from .client import WBApiClient
from .endpoints import REALIZATION


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
    if response.ok and rows:
        status_code = SourceStatusCode.OK
    elif response.ok:
        status_code = SourceStatusCode.MISSING
        warnings.append("realization source returned empty payload")
    else:
        status_code = SourceStatusCode.ERROR

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
    }
    return RawSourcePayload(source_name="realization", payload=payload, status=status)
