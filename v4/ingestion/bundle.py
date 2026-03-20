"""Raw API bundle builder.

Input: RunContext.
Output: IngestionResult with per-source raw payloads and statuses.
Does not normalize data and does not compute KPI.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..core.contracts import (
    IngestionResult,
    RawBundle,
    RawSourcePayload,
    RunContext,
    RunMode,
    SourceKind,
    SourceStatus,
    SourceStatusCode,
)
from ..pipeline.modes.daily_api_mode import MODE_DESCRIPTOR as DAILY_MODE_DESCRIPTOR
from ..warnings_utils import append_warning, dedupe_warnings, extend_warnings
from .api import (
    WBApiClient,
    load_ads_bundle,
    load_ads_campaigns,
    load_ads_stats,
    load_funnel,
    load_orders,
    load_realization,
    load_sales,
    load_stocks,
)


def _status_payload(
    *,
    source_name: str,
    kind: SourceKind,
    status: SourceStatusCode,
    is_required: bool,
    run_context: RunContext,
    error_code: str | None = None,
    error_message: str | None = None,
    warnings: list[str] | None = None,
    debug: dict[str, Any] | None = None,
) -> RawSourcePayload:
    source_status = SourceStatus(
        source_name=source_name,
        kind=kind,
        status=status,
        is_required=is_required,
        rows_loaded=None,
        endpoint=None,
        requested_date=run_context.requested_date_iso,
        resolved_date=run_context.resolved_date_iso,
        error_code=error_code,
        error_message=error_message,
        warnings=list(warnings or []),
        debug=dict(debug or {}),
    )
    return RawSourcePayload(source_name=source_name, payload=None, status=source_status)


def _safe_load(
    loader: Callable[[], RawSourcePayload],
    *,
    source_name: str,
    is_required: bool,
    run_context: RunContext,
) -> RawSourcePayload:
    try:
        payload = loader()
        if not isinstance(payload, RawSourcePayload):
            return _status_payload(
                source_name=source_name,
                kind=SourceKind.UNKNOWN,
                status=SourceStatusCode.ERROR,
                is_required=is_required,
                run_context=run_context,
                error_code="invalid_loader_return",
                error_message="loader must return RawSourcePayload",
            )
        return payload
    except Exception as exc:
        return _status_payload(
            source_name=source_name,
            kind=SourceKind.API,
            status=SourceStatusCode.ERROR,
            is_required=is_required,
            run_context=run_context,
            error_code="loader_exception",
            error_message=str(exc),
        )


def _required_sources_ok(sources: dict[str, RawSourcePayload]) -> bool:
    for source_name in DAILY_MODE_DESCRIPTOR.required_sources:
        status = sources.get(source_name)
        if status is None:
            return False
        if status.status.status not in (SourceStatusCode.OK, SourceStatusCode.PARTIAL):
            return False
    return True


def _optional_sources_available(sources: dict[str, RawSourcePayload]) -> list[str]:
    available: list[str] = []
    for source_name in DAILY_MODE_DESCRIPTOR.optional_sources:
        payload = sources.get(source_name)
        if payload is None:
            continue
        if payload.status.status in (SourceStatusCode.OK, SourceStatusCode.PARTIAL):
            available.append(source_name)
    return available


def _status_code_text(value: object) -> str:
    if hasattr(value, "value"):
        return str(getattr(value, "value"))
    return str(value)


def _source_reason_from_payload(payload: RawSourcePayload) -> str:
    status = payload.status
    debug = status.debug if isinstance(status.debug, dict) else {}
    for key in ("reason", f"{payload.source_name}_reason"):
        value = debug.get(key)
        if str(value or "").strip():
            return str(value).strip().lower()

    error_code = str(status.error_code or "").strip().lower()
    status_text = _status_code_text(status.status).strip().lower()

    if error_code in {"http_401", "http_403", "auth_error", "auth_failed", "unauthorized", "forbidden"}:
        return "auth_failed"
    if status_text == "error":
        return "request_failed"
    if status_text == "missing":
        return "empty_payload"
    if status_text == "partial":
        return "partial_source"
    if status_text == "ok":
        return "ok"
    return "source_missing"


def _coverage_kind(*, status_text: str, reason: str) -> str:
    if reason in {"auth_error", "auth_failed", "request_failed", "parse_failed", "normalized_empty"}:
        return "source_failed"
    if reason in {"no_data_for_date", "no_realization_in_window"}:
        return "source_unavailable_for_selected_date"
    if status_text == "missing" and reason in {"empty_payload", "ok_empty_payload"}:
        return "source_empty_but_valid"
    if status_text in {"missing", "not_implemented"}:
        return "source_missing"
    if status_text == "error":
        return "source_failed"
    if status_text == "partial":
        return "source_partial"
    return "source_available"


def build_api_raw_bundle(run_context: RunContext) -> IngestionResult:
    if run_context.mode != RunMode.DAILY_API:
        raise ValueError("build_api_raw_bundle supports only daily_api_mode")

    sources: dict[str, RawSourcePayload] = {}
    warnings: list[str] = []

    if not run_context.wb_api_token_present:
        all_sources = [
            *DAILY_MODE_DESCRIPTOR.required_sources,
            *DAILY_MODE_DESCRIPTOR.optional_sources,
        ]
        for source_name in all_sources:
            sources[source_name] = _status_payload(
                source_name=source_name,
                kind=SourceKind.API,
                status=SourceStatusCode.MISSING,
                is_required=source_name in DAILY_MODE_DESCRIPTOR.required_sources,
                run_context=run_context,
                error_code="token_missing",
                error_message="WB_API_TOKEN not configured",
                warnings=["source skipped: WB API token not present"],
            )
        append_warning(warnings, "WB API token is missing; API ingestion skipped")
    else:
        try:
            client = WBApiClient()
        except Exception as exc:
            all_sources = [
                *DAILY_MODE_DESCRIPTOR.required_sources,
                *DAILY_MODE_DESCRIPTOR.optional_sources,
            ]
            for source_name in all_sources:
                sources[source_name] = _status_payload(
                    source_name=source_name,
                    kind=SourceKind.API,
                    status=SourceStatusCode.ERROR,
                    is_required=source_name in DAILY_MODE_DESCRIPTOR.required_sources,
                    run_context=run_context,
                    error_code="client_init_failed",
                    error_message=str(exc),
                    warnings=["source skipped: failed to initialize WB API client"],
                )
            append_warning(warnings, f"WB API client init failed: {exc}")
            client = None

    if run_context.wb_api_token_present and sources and all(
        payload.status.error_code == "client_init_failed" for payload in sources.values()
    ):
        client = None

    if run_context.wb_api_token_present and "client" in locals() and client is not None:

        sources["orders"] = _safe_load(
            lambda: load_orders(client, run_context),
            source_name="orders",
            is_required=True,
            run_context=run_context,
        )
        sources["sales"] = _safe_load(
            lambda: load_sales(client, run_context),
            source_name="sales",
            is_required=True,
            run_context=run_context,
        )
        sources["realization"] = _safe_load(
            lambda: load_realization(client, run_context),
            source_name="realization",
            is_required=True,
            run_context=run_context,
        )
        sources["stocks"] = _safe_load(
            lambda: load_stocks(client, run_context),
            source_name="stocks",
            is_required=False,
            run_context=run_context,
        )

        ads_campaigns = _safe_load(
            lambda: load_ads_campaigns(client, run_context),
            source_name="ads_campaigns",
            is_required=False,
            run_context=run_context,
        )

        campaign_ids: list[int] = []
        if isinstance(ads_campaigns.payload, dict):
            raw_ids = ads_campaigns.payload.get("campaign_ids")
            if isinstance(raw_ids, list):
                campaign_ids = [
                    int(value)
                    for value in raw_ids
                    if isinstance(value, int) or str(value).isdigit()
                ]

        ads_stats = _safe_load(
            lambda: load_ads_stats(client, run_context, campaign_ids=campaign_ids),
            source_name="ads_stats",
            is_required=False,
            run_context=run_context,
        )

        ads_bundle = _safe_load(
            lambda: load_ads_bundle(
                client,
                run_context,
                campaigns_payload=ads_campaigns,
                stats_payload=ads_stats,
            ),
            source_name="ads",
            is_required=False,
            run_context=run_context,
        )

        sources["ads_campaigns"] = ads_campaigns
        sources["ads_stats"] = ads_stats
        sources["ads"] = ads_bundle

        sources["funnel"] = _safe_load(
            lambda: load_funnel(client, run_context),
            source_name="funnel",
            is_required=False,
            run_context=run_context,
        )

    for payload in sources.values():
        extend_warnings(warnings, payload.status.warnings, namespace=payload.source_name)

    for required_source in DAILY_MODE_DESCRIPTOR.required_sources:
        status = sources.get(required_source)
        if status is None:
            append_warning(warnings, f"required source '{required_source}' is missing in bundle")
            continue
        if status.status.status not in (SourceStatusCode.OK, SourceStatusCode.PARTIAL):
            append_warning(
                warnings,
                "required source failure: "
                f"{required_source} status={status.status.status.value}"
            )

    source_flags = {
        source_name: payload.status.status
        for source_name, payload in sources.items()
    }
    source_reason_map = {
        source_name: _source_reason_from_payload(payload)
        for source_name, payload in sources.items()
    }
    source_status_map = {
        source_name: _status_code_text(payload.status.status).strip().lower()
        for source_name, payload in sources.items()
    }
    missing_sources = [
        source_name
        for source_name, status_text in source_status_map.items()
        if status_text not in {"ok", "partial"}
    ]
    partial_sources = [
        source_name
        for source_name, status_text in source_status_map.items()
        if status_text == "partial"
    ]
    source_coverage_summary = {
        source_name: _coverage_kind(status_text=source_status_map[source_name], reason=source_reason_map.get(source_name, ""))
        for source_name in sources.keys()
    }
    warnings = dedupe_warnings(warnings)

    required_ok = _required_sources_ok(sources)
    optional_available = _optional_sources_available(sources)
    loaded_count = sum(
        1
        for payload in sources.values()
        if payload.status.status in (SourceStatusCode.OK, SourceStatusCode.PARTIAL)
    )
    error_count = sum(
        1
        for payload in sources.values()
        if payload.status.status == SourceStatusCode.ERROR
    )

    diagnostics = {
        "mode": run_context.mode.value,
        "seller_id": run_context.seller_id,
        "requested_date": run_context.requested_date_iso,
        "resolved_date": run_context.resolved_date_iso,
        "required_sources": list(DAILY_MODE_DESCRIPTOR.required_sources),
        "optional_sources": list(DAILY_MODE_DESCRIPTOR.optional_sources),
        "required_sources_ok": required_ok,
        "optional_sources_available": optional_available,
        "missing_sources": missing_sources,
        "partial_sources": partial_sources,
        "source_reason_map": source_reason_map,
        "source_coverage_summary": source_coverage_summary,
        "warnings_count": len(warnings),
        "sources_loaded_count": loaded_count,
        "sources_error_count": error_count,
    }

    raw_bundle = RawBundle(run_context=run_context, sources=sources, diagnostics=diagnostics)
    return IngestionResult(raw_bundle=raw_bundle, source_flags=source_flags, warnings=warnings)
