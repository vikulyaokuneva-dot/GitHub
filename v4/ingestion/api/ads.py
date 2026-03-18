"""Ads API raw loaders.

Input: WBApiClient + RunContext.
Output: RawSourcePayload for ads campaigns/stats/bundle sources.
Does not normalize or compute KPI.
"""

from __future__ import annotations

from typing import Any, Iterable

from ...core.contracts import RawSourcePayload, RunContext, SourceKind, SourceStatus, SourceStatusCode
from .client import WBApiClient
from .endpoints import ADS_CAMPAIGNS, ADS_STATS


def _extract_campaign_ids(payload: Any) -> list[int]:
    ids: list[int] = []

    def _ingest_items(items: Iterable[Any]) -> None:
        for item in items:
            if not isinstance(item, dict):
                continue
            raw = item.get("advertId")
            if raw is None:
                raw = item.get("id")
            if raw is None:
                continue
            try:
                ids.append(int(raw))
            except Exception:
                continue

    if isinstance(payload, list):
        _ingest_items(payload)
    elif isinstance(payload, dict):
        adverts = payload.get("adverts")
        if isinstance(adverts, list):
            _ingest_items(adverts)
        else:
            for value in payload.values():
                if isinstance(value, list):
                    _ingest_items(value)

    return sorted(set(ids))


def _status_snapshot(status: SourceStatus) -> dict[str, Any]:
    return {
        "source_name": status.source_name,
        "status": status.status.value,
        "error_code": status.error_code,
        "error_message": status.error_message,
        "rows_loaded": status.rows_loaded,
    }


def load_ads_campaigns(client: WBApiClient, run_context: RunContext) -> RawSourcePayload:
    requested_date = run_context.requested_date_iso
    resolved_date = run_context.resolved_date_iso

    response = client.get_json(
        ADS_CAMPAIGNS,
        params={},
        allow_statuses={204: [], 403: {}},
    )

    campaign_ids = _extract_campaign_ids(response.payload if response.ok else None)
    warnings: list[str] = []

    if response.ok and campaign_ids:
        status_code = SourceStatusCode.OK
    elif response.ok:
        status_code = SourceStatusCode.MISSING
        warnings.append("ads campaigns are unavailable or empty")
        if response.status_code == 403:
            warnings.append("ads campaigns endpoint returned 403")
    else:
        status_code = SourceStatusCode.ERROR

    status = SourceStatus(
        source_name="ads_campaigns",
        kind=SourceKind.API,
        status=status_code,
        is_required=False,
        rows_loaded=(len(campaign_ids) if response.ok else None),
        endpoint=ADS_CAMPAIGNS.path,
        requested_date=requested_date,
        resolved_date=resolved_date,
        error_code=response.error_code,
        error_message=response.error_message,
        warnings=warnings,
        debug={
            "endpoint_name": ADS_CAMPAIGNS.name,
            "status_code": response.status_code,
            "attempts": response.attempts,
            "campaigns_count": len(campaign_ids),
        },
    )

    payload = {
        "campaign_ids": campaign_ids if response.ok else None,
        "raw": response.payload,
    }
    return RawSourcePayload(source_name="ads_campaigns", payload=payload, status=status)


def load_ads_stats(
    client: WBApiClient,
    run_context: RunContext,
    campaign_ids: list[int] | None = None,
) -> RawSourcePayload:
    requested_date = run_context.requested_date_iso
    resolved_date = run_context.resolved_date_iso
    ids = sorted(set(int(x) for x in (campaign_ids or []) if isinstance(x, int) or str(x).isdigit()))

    if not ids:
        status = SourceStatus(
            source_name="ads_stats",
            kind=SourceKind.API,
            status=SourceStatusCode.MISSING,
            is_required=False,
            rows_loaded=None,
            endpoint=ADS_STATS.path,
            requested_date=requested_date,
            resolved_date=resolved_date,
            warnings=["ads stats skipped because campaign ids are missing"],
            debug={"campaigns_count": 0, "stats_count": None, "requested_interval": [resolved_date, resolved_date]},
        )
        return RawSourcePayload(source_name="ads_stats", payload={"rows": None, "raw_chunks": []}, status=status)

    rows: list[Any] = []
    raw_chunks: list[Any] = []
    unresolved_campaign_ids: list[int] = []
    warnings: list[str] = []
    failed_chunks = 0

    chunk_size = 50
    for start in range(0, len(ids), chunk_size):
        chunk = ids[start : start + chunk_size]
        params = {
            "ids": ",".join(str(campaign_id) for campaign_id in chunk),
            "beginDate": resolved_date,
            "endDate": resolved_date,
        }
        response = client.get_json(ADS_STATS, params=params, allow_statuses={204: [], 403: []})

        if response.ok:
            raw_chunks.append(response.payload)
            if isinstance(response.payload, list):
                rows.extend(response.payload)
            elif response.payload is not None:
                rows.append(response.payload)

            if response.status_code == 403:
                unresolved_campaign_ids.extend(chunk)
                warnings.append("ads stats endpoint returned 403 for one or more campaign chunks")
            elif response.status_code == 204:
                unresolved_campaign_ids.extend(chunk)
        else:
            failed_chunks += 1
            unresolved_campaign_ids.extend(chunk)
            warnings.append(
                f"ads stats chunk failed: code={response.error_code} status={response.status_code}"
            )

    stats_count = len(rows)
    unresolved_campaign_ids = sorted(set(unresolved_campaign_ids))

    if stats_count > 0 and failed_chunks == 0 and not unresolved_campaign_ids:
        status_code = SourceStatusCode.OK
    elif stats_count > 0:
        status_code = SourceStatusCode.PARTIAL
    elif failed_chunks > 0:
        status_code = SourceStatusCode.ERROR
    else:
        status_code = SourceStatusCode.MISSING

    status = SourceStatus(
        source_name="ads_stats",
        kind=SourceKind.API,
        status=status_code,
        is_required=False,
        rows_loaded=(stats_count if stats_count > 0 else None),
        endpoint=ADS_STATS.path,
        requested_date=requested_date,
        resolved_date=resolved_date,
        error_code=("chunk_failure" if failed_chunks > 0 else None),
        error_message=("one or more ads stats chunks failed" if failed_chunks > 0 else None),
        warnings=warnings,
        debug={
            "endpoint_name": ADS_STATS.name,
            "campaigns_count": len(ids),
            "stats_count": stats_count,
            "failed_chunks": failed_chunks,
            "unresolved_campaign_ids": unresolved_campaign_ids,
            "requested_interval": [resolved_date, resolved_date],
        },
    )

    payload = {
        "rows": rows if stats_count > 0 else None,
        "raw_chunks": raw_chunks,
        "campaign_ids": ids,
        "unresolved_campaign_ids": unresolved_campaign_ids,
    }
    return RawSourcePayload(source_name="ads_stats", payload=payload, status=status)


def load_ads_bundle(
    client: WBApiClient,
    run_context: RunContext,
    campaigns_payload: RawSourcePayload | None = None,
    stats_payload: RawSourcePayload | None = None,
) -> RawSourcePayload:
    campaigns = campaigns_payload or load_ads_campaigns(client, run_context)

    campaign_ids: list[int] = []
    if isinstance(campaigns.payload, dict):
        raw_ids = campaigns.payload.get("campaign_ids")
        if isinstance(raw_ids, list):
            campaign_ids = [int(value) for value in raw_ids if isinstance(value, int) or str(value).isdigit()]

    stats = stats_payload or load_ads_stats(client, run_context, campaign_ids=campaign_ids)

    c_status = campaigns.status.status
    s_status = stats.status.status

    if c_status == SourceStatusCode.OK and s_status == SourceStatusCode.OK:
        bundle_status = SourceStatusCode.OK
    elif c_status == SourceStatusCode.ERROR and s_status == SourceStatusCode.ERROR:
        bundle_status = SourceStatusCode.ERROR
    elif c_status == SourceStatusCode.MISSING and s_status == SourceStatusCode.MISSING:
        bundle_status = SourceStatusCode.MISSING
    elif c_status == SourceStatusCode.NOT_IMPLEMENTED or s_status == SourceStatusCode.NOT_IMPLEMENTED:
        bundle_status = SourceStatusCode.NOT_IMPLEMENTED
    else:
        bundle_status = SourceStatusCode.PARTIAL

    warnings = [*campaigns.status.warnings, *stats.status.warnings]
    rows_loaded = stats.status.rows_loaded
    if rows_loaded is None:
        rows_loaded = campaigns.status.rows_loaded

    status = SourceStatus(
        source_name="ads",
        kind=SourceKind.API,
        status=bundle_status,
        is_required=False,
        rows_loaded=rows_loaded,
        endpoint=f"{ADS_CAMPAIGNS.path} + {ADS_STATS.path}",
        requested_date=run_context.requested_date_iso,
        resolved_date=run_context.resolved_date_iso,
        warnings=warnings,
        debug={
            "campaigns": _status_snapshot(campaigns.status),
            "stats": _status_snapshot(stats.status),
            "campaigns_count": campaigns.status.rows_loaded,
            "stats_count": stats.status.rows_loaded,
            "requested_interval": [run_context.resolved_date_iso, run_context.resolved_date_iso],
            "unresolved_campaign_ids": (
                stats.payload.get("unresolved_campaign_ids")
                if isinstance(stats.payload, dict)
                else None
            ),
        },
    )

    payload = {
        "campaigns": campaigns.payload,
        "stats": stats.payload,
        "campaign_ids": campaign_ids,
    }
    return RawSourcePayload(source_name="ads", payload=payload, status=status)
