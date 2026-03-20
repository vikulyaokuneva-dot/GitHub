"""Funnel API raw loader.

Input: WBApiClient + RunContext.
Output: RawSourcePayload for funnel source.
Does not normalize or compute KPI.
"""

from __future__ import annotations

from typing import Any

from ...core.contracts import RawSourcePayload, RunContext, SourceKind, SourceStatus, SourceStatusCode
from ...extraction_compat import try_json_loads
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


def _payload_is_empty(payload: Any) -> bool:
    payload = try_json_loads(payload)
    if payload is None:
        return True
    if isinstance(payload, (list, dict, str, bytes, tuple, set)):
        return len(payload) == 0
    return False


def _explicit_empty_rows(payload: Any) -> bool:
    payload = try_json_loads(payload)
    if isinstance(payload, list):
        return len(payload) == 0
    if isinstance(payload, dict):
        for key in ("data", "items", "products", "rows"):
            if key in payload and isinstance(payload.get(key), list) and len(payload.get(key)) == 0:
                return True
    return False


def _infer_funnel_payload_shape(payload: Any, origin: str | None) -> str:
    payload = try_json_loads(payload)
    origin_text = str(origin or "").strip().lower()
    if "statistic" in origin_text and "selected" in origin_text:
        return "statistic_selected"
    if isinstance(payload, dict):
        statistic = payload.get("statistic")
        if isinstance(statistic, dict) and isinstance(
            statistic.get("selected") or statistic.get("current") or statistic.get("now"),
            dict,
        ):
            return "statistic_selected"
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            statistic = item.get("statistic")
            if isinstance(statistic, dict) and isinstance(
                statistic.get("selected") or statistic.get("current") or statistic.get("now"),
                dict,
            ):
                return "statistic_selected"
    if isinstance(payload, dict):
        if any(key in payload for key in ("data", "items", "products", "result", "rows")):
            return "structured"
    return "flat"


_FUNNEL_ROW_LIKE_KEYS: tuple[str, ...] = (
    "nmId",
    "nm_id",
    "nmid",
    "id",
    "entity_id",
    "views",
    "openCount",
    "openCardCount",
    "add_to_cart",
    "cartCount",
    "addToCartCount",
    "orders",
    "orderCount",
    "buys",
    "buyoutCount",
    "orderSum",
    "buyoutSum",
    "statistic",
    "product",
)


def load_funnel(client: WBApiClient, run_context: RunContext) -> RawSourcePayload:
    body = _build_funnel_body(run_context)
    response = client.post_json(FUNNEL, json_body=body, allow_statuses={204: []})
    rows: list[dict[str, Any]] = []
    extraction_meta: dict[str, Any] = {
        "mode": "none",
        "origin": None,
        "compat_used": False,
        "payload_shape": "none",
        "explicit_empty_list": False,
    }
    if response.ok:
        rows, extraction_meta = client.extract_rows_with_diagnostics(
            response.payload,
            ("data", "items", "products", "rows"),
            allow_single_dict=True,
            row_like_keys=_FUNNEL_ROW_LIKE_KEYS,
        )

    warnings: list[str] = []
    reason = "ok"
    if response.ok and rows:
        status_code = SourceStatusCode.OK
    elif response.ok:
        status_code = SourceStatusCode.MISSING
        payload_empty = _payload_is_empty(response.payload)
        explicit_empty = _explicit_empty_rows(response.payload) or bool(extraction_meta.get("explicit_empty_list"))
        if not payload_empty and not explicit_empty:
            reason = "parse_failed"
            warnings.append("funnel payload is non-empty but row extraction returned zero rows")
        elif run_context.resolved_date_iso or run_context.requested_date_iso:
            reason = "no_data_for_date"
            warnings.append("funnel source has no data for selected date")
        else:
            reason = "empty_payload"
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
            "funnel_compat_used": bool(extraction_meta.get("compat_used", False)),
            "funnel_payload_shape": _infer_funnel_payload_shape(response.payload, extraction_meta.get("origin")),
            "funnel_payload_origin": extraction_meta.get("origin"),
            "funnel_extraction_mode": extraction_meta.get("mode"),
            "funnel_rows_extracted": len(rows),
        },
    )

    payload = {
        "rows": rows if response.ok else None,
        "raw": response.payload,
        "request": {"body": body},
        "reason": reason,
    }
    return RawSourcePayload(source_name="funnel", payload=payload, status=status)
