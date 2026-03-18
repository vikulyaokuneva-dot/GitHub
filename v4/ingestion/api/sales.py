"""Sales API raw loader.

Input: WBApiClient + RunContext.
Output: RawSourcePayload for sales source.
Does not normalize or compute KPI.
"""

from __future__ import annotations

from ...core.contracts import RawSourcePayload, RunContext, SourceKind, SourceStatus, SourceStatusCode
from .client import WBApiClient
from .endpoints import SALES


def load_sales(client: WBApiClient, run_context: RunContext) -> RawSourcePayload:
    requested_date = run_context.requested_date_iso
    resolved_date = run_context.resolved_date_iso

    params = {"dateFrom": resolved_date} if resolved_date else {}
    response = client.get_json(SALES, params=params, allow_statuses={204: []})

    rows = client.extract_rows(response.payload, ("data", "items", "rows")) if response.ok else []
    warnings: list[str] = []

    if response.ok and rows:
        status_code = SourceStatusCode.OK
    elif response.ok:
        status_code = SourceStatusCode.MISSING
        warnings.append("sales source returned empty payload")
    else:
        status_code = SourceStatusCode.ERROR

    status = SourceStatus(
        source_name="sales",
        kind=SourceKind.API,
        status=status_code,
        is_required=True,
        rows_loaded=(len(rows) if response.ok else None),
        endpoint=SALES.path,
        requested_date=requested_date,
        resolved_date=resolved_date,
        error_code=response.error_code,
        error_message=response.error_message,
        warnings=warnings,
        debug={
            "endpoint_name": SALES.name,
            "status_code": response.status_code,
            "attempts": response.attempts,
            "request_params": params,
        },
    )

    payload = {
        "rows": rows if response.ok else None,
        "raw": response.payload,
        "request": {"params": params},
    }
    return RawSourcePayload(source_name="sales", payload=payload, status=status)
