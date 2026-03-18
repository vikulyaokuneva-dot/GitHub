"""Ads local report parser for audit mode.

Input: file path.
Output: raw ads campaigns/stats payload for normalization.
Does not compute KPI.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...core.contracts import SourceKind, SourceStatus, SourceStatusCode
from .registry import read_tabular_rows


def _pick(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in row and row.get(key) not in (None, ""):
            return row.get(key)
    return None


def _parse_json_payload(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(payload, dict):
        return payload
    return None


def parse(path: str) -> tuple[dict[str, Any], SourceStatus]:
    file_path = Path(path)
    warnings: list[str] = []

    if file_path.suffix.lower() == ".json":
        json_payload = _parse_json_payload(file_path)
        if isinstance(json_payload, dict) and ("campaigns" in json_payload or "stats" in json_payload):
            campaigns = json_payload.get("campaigns")
            stats = json_payload.get("stats")
            campaign_ids = json_payload.get("campaign_ids")
            if not isinstance(campaign_ids, list):
                campaign_ids = []
            status_code = SourceStatusCode.OK if campaigns or stats else SourceStatusCode.MISSING
            if campaigns and not stats:
                status_code = SourceStatusCode.PARTIAL
                warnings.append("ads report contains campaigns without stats")
            if stats and not campaigns:
                status_code = SourceStatusCode.PARTIAL
                warnings.append("ads report contains stats without campaigns")
            status = SourceStatus(
                source_name="ads_report",
                kind=SourceKind.FILE,
                status=status_code,
                is_required=False,
                rows_loaded=None,
                warnings=warnings,
                debug={"path": str(file_path), "json_direct_payload": True},
            )
            return {"campaigns": campaigns, "stats": stats, "campaign_ids": campaign_ids}, status

    try:
        raw_rows = read_tabular_rows(file_path)
    except Exception as exc:
        status = SourceStatus(
            source_name="ads_report",
            kind=SourceKind.FILE,
            status=SourceStatusCode.ERROR,
            is_required=False,
            rows_loaded=None,
            error_code="ads_report_parse_failed",
            error_message=str(exc),
            warnings=["ads report parse failed"],
            debug={"path": str(file_path)},
        )
        return {"campaigns": {"raw": []}, "stats": {"rows": []}, "campaign_ids": []}, status

    campaigns_raw: list[dict[str, Any]] = []
    stats_rows: list[dict[str, Any]] = []
    campaign_ids: set[int] = set()

    for row in raw_rows:
        campaign_id = _pick(row, ("campaign_id", "campaignId", "advertId", "id"))
        campaign_name = _pick(row, ("campaign_name", "campaignName", "name"))
        campaign_status = _pick(row, ("campaign_status", "status", "state"))
        if campaign_id is not None or campaign_name is not None:
            campaigns_raw.append(
                {
                    "campaignId": campaign_id,
                    "name": campaign_name,
                    "status": campaign_status,
                    "type": _pick(row, ("campaign_type", "type", "advertType")),
                }
            )
        try:
            if campaign_id is not None:
                campaign_ids.add(int(str(campaign_id)))
        except Exception:
            pass

        if any(_pick(row, (key,)) is not None for key in ("impressions", "views", "clicks", "spend", "orders", "revenue")):
            stats_rows.append(
                {
                    "campaignId": campaign_id,
                    "date": _pick(row, ("date", "day", "stat_date")),
                    "impressions": _pick(row, ("impressions", "views")),
                    "clicks": _pick(row, ("clicks",)),
                    "spend": _pick(row, ("spend", "cost", "sum")),
                    "orders": _pick(row, ("orders", "orderCount")),
                    "revenue": _pick(row, ("revenue", "orderSum")),
                }
            )

    status_code = SourceStatusCode.MISSING
    if campaigns_raw or stats_rows:
        status_code = SourceStatusCode.OK
    if campaigns_raw and not stats_rows:
        status_code = SourceStatusCode.PARTIAL
        warnings.append("ads report has campaign metadata without stat rows")
    if stats_rows and not campaigns_raw:
        status_code = SourceStatusCode.PARTIAL
        warnings.append("ads report has stat rows without campaign metadata")

    status = SourceStatus(
        source_name="ads_report",
        kind=SourceKind.FILE,
        status=status_code,
        is_required=False,
        rows_loaded=len(raw_rows) if raw_rows else None,
        warnings=warnings,
        debug={
            "path": str(file_path),
            "rows_total": len(raw_rows),
            "campaigns_rows": len(campaigns_raw),
            "stats_rows": len(stats_rows),
        },
    )
    payload = {
        "campaigns": {"raw": campaigns_raw, "campaign_ids": sorted(campaign_ids)},
        "stats": {"rows": stats_rows},
        "campaign_ids": sorted(campaign_ids),
    }
    return payload, status

