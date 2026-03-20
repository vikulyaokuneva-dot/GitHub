"""Ads metrics summary assembler.

Input: NormalizedBundle.
Output: AdsMetricsSection.
Does not depend on financial/funnel contours.
"""

from __future__ import annotations

from ...core.contracts import (
    AdsMetricsSection,
    MetricStatus,
    MetricValue,
    NormalizedAdsCampaignRecord,
    NormalizedAdsStatRecord,
    NormalizedBundle,
)
from ...warnings_utils import dedupe_warnings, extend_warnings


def _metric(
    value: float | int | None,
    *,
    status: MetricStatus,
    source: str | None,
    note: str | None = None,
) -> MetricValue:
    return MetricValue(value=value, status=status.value, source=source, note=note)


def _source_state(bundle: NormalizedBundle, source_name: str) -> str:
    status = bundle.source_statuses.get(source_name)
    if status is None:
        return "missing"
    raw = getattr(status, "status", None)
    if hasattr(raw, "value"):
        return str(raw.value)
    text = str(raw or "missing").strip().lower()
    return text or "missing"


def _source_usable(state: str) -> bool:
    return state in {"ok", "partial"}


def _status_for_usable_source(state: str) -> MetricStatus:
    return MetricStatus.PARTIAL if state == "partial" else MetricStatus.CONFIRMED


def _source_warnings(normalized_bundle: NormalizedBundle) -> list[str]:
    warnings: list[str] = []
    for key in ("ads_campaigns", "ads_stats", "ads"):
        source_status = normalized_bundle.source_statuses.get(key)
        if source_status is None:
            continue
        extend_warnings(warnings, source_status.warnings, namespace=key)

    extend_warnings(
        warnings,
        (
            warning
            for warning in normalized_bundle.warnings
            if "ads" in str(warning).lower()
        ),
    )
    return dedupe_warnings(warnings)


def _is_active_campaign(record: NormalizedAdsCampaignRecord) -> bool | None:
    status_text = str(record.status or "").strip().lower()
    if not status_text:
        return None
    if status_text in {"active", "running", "enabled", "on", "1", "true", "актив"}:
        return True
    if status_text in {"paused", "stopped", "off", "0", "false", "inactive", "неактив"}:
        return False
    if "актив" in status_text or "run" in status_text:
        return True
    return False


def _campaign_count_metrics(
    campaigns: list[NormalizedAdsCampaignRecord],
    campaigns_state: str,
) -> tuple[MetricValue, MetricValue, list[str]]:
    warnings: list[str] = []

    if not _source_usable(campaigns_state):
        unavailable = _metric(
            None,
            status=MetricStatus.UNAVAILABLE,
            source="ads_campaigns",
            note="campaigns source is unavailable",
        )
        return unavailable, unavailable, warnings

    status = _status_for_usable_source(campaigns_state)
    campaigns_count_value = len(campaigns)

    active_known = 0
    active_count = 0
    for campaign in campaigns:
        is_active = _is_active_campaign(campaign)
        if is_active is None:
            continue
        active_known += 1
        if is_active:
            active_count += 1

    campaigns_count_metric = _metric(campaigns_count_value, status=status, source="ads_campaigns")

    if campaigns and active_known == 0:
        warnings.append("active campaign status is missing for all campaign records")
        active_metric = _metric(
            None,
            status=MetricStatus.PARTIAL,
            source="ads_campaigns",
            note="campaign status field is not populated",
        )
    else:
        active_status = status
        note = None
        if active_known < len(campaigns):
            active_status = MetricStatus.PARTIAL
            note = "active status is partially populated"
            warnings.append("active campaign status is partially populated")
        active_metric = _metric(active_count, status=active_status, source="ads_campaigns", note=note)

    return campaigns_count_metric, active_metric, warnings


def _aggregate_stats_field(
    stats_records: list[NormalizedAdsStatRecord],
    stats_state: str,
    field_name: str,
) -> tuple[MetricValue, list[str]]:
    warnings: list[str] = []

    if not _source_usable(stats_state):
        return (
            _metric(
                None,
                status=MetricStatus.UNAVAILABLE,
                source="ads_stats",
                note="stats source is unavailable",
            ),
            warnings,
        )

    if not stats_records:
        warnings.append(f"ads stats has no records for field '{field_name}'")
        return (
            _metric(
                None,
                status=MetricStatus.PARTIAL,
                source="ads_stats",
                note="stats source has no rows for this run",
            ),
            warnings,
        )

    values: list[float] = []
    missing_count = 0
    for row in stats_records:
        raw = getattr(row, field_name)
        if raw is None:
            missing_count += 1
            continue
        try:
            values.append(float(raw))
        except (TypeError, ValueError):
            missing_count += 1

    if not values:
        warnings.append(f"ads stats field '{field_name}' has no reliable numeric values")
        return (
            _metric(
                None,
                status=MetricStatus.PARTIAL,
                source="ads_stats",
                note=f"field {field_name} is missing",
            ),
            warnings,
        )

    total = round(sum(values), 6)
    status = _status_for_usable_source(stats_state)
    note = None
    if missing_count > 0 or status == MetricStatus.PARTIAL:
        status = MetricStatus.PARTIAL
        note = f"field {field_name} is partially populated"
        warnings.append(f"ads stats field '{field_name}' is partially populated")

    return _metric(total, status=status, source="ads_stats", note=note), warnings


def _ratio_metric(
    *,
    numerator: MetricValue,
    denominator: MetricValue,
    stats_state: str,
    metric_name: str,
    note_denominator: str,
) -> tuple[MetricValue, list[str]]:
    warnings: list[str] = []

    if not _source_usable(stats_state):
        return (
            _metric(
                None,
                status=MetricStatus.UNAVAILABLE,
                source="ads_stats",
                note="stats source is unavailable",
            ),
            warnings,
        )

    if denominator.value is None:
        warnings.append(f"{metric_name}: denominator is unavailable")
        status = MetricStatus.PARTIAL if denominator.status != MetricStatus.UNAVAILABLE.value else MetricStatus.UNAVAILABLE
        return (
            _metric(None, status=status, source="ads_stats", note=note_denominator),
            warnings,
        )

    if numerator.value is None:
        warnings.append(f"{metric_name}: numerator is unavailable")
        status = MetricStatus.PARTIAL if numerator.status != MetricStatus.UNAVAILABLE.value else MetricStatus.UNAVAILABLE
        return (
            _metric(None, status=status, source="ads_stats", note=f"{metric_name} numerator unavailable"),
            warnings,
        )

    try:
        den = float(denominator.value)
        num = float(numerator.value)
    except (TypeError, ValueError):
        warnings.append(f"{metric_name}: non-numeric numerator/denominator")
        return (
            _metric(None, status=MetricStatus.PARTIAL, source="ads_stats", note=f"{metric_name} inputs invalid"),
            warnings,
        )

    if den <= 0:
        warnings.append(f"{metric_name}: denominator <= 0")
        return (
            _metric(None, status=MetricStatus.PARTIAL, source="ads_stats", note=note_denominator),
            warnings,
        )

    value = round(num / den, 6)
    status = _status_for_usable_source(stats_state)
    note = None
    if numerator.status != MetricStatus.CONFIRMED.value or denominator.status != MetricStatus.CONFIRMED.value:
        status = MetricStatus.PARTIAL
        note = f"{metric_name} is partially reliable"

    return _metric(value, status=status, source="ads_stats", note=note), warnings


def _section_note(
    *,
    campaigns_state: str,
    stats_state: str,
    warnings: list[str],
) -> str | None:
    if not _source_usable(campaigns_state) and not _source_usable(stats_state):
        return "ads campaigns and stats sources are unavailable"
    if _source_usable(campaigns_state) and not _source_usable(stats_state):
        return "ads campaigns available, stats unavailable"
    if not _source_usable(campaigns_state) and _source_usable(stats_state):
        return "ads stats available, campaigns unavailable"
    if campaigns_state == "partial" or stats_state == "partial":
        return "ads metrics are partial due to source completeness"
    if warnings:
        return "ads metrics available with warnings"
    return None


def assemble_ads_metrics(normalized_bundle: NormalizedBundle) -> AdsMetricsSection:
    """Build ads metrics section from normalized campaigns and stats.

    Campaigns and stats are treated as separate sources. Missing one side does
    not invalidate the other side.
    """

    campaigns_state = _source_state(normalized_bundle, "ads_campaigns")
    stats_state = _source_state(normalized_bundle, "ads_stats")

    source_quality = {
        "campaigns": campaigns_state,
        "stats": stats_state,
    }

    warnings = _source_warnings(normalized_bundle)

    campaigns_count, active_campaigns_count, warn = _campaign_count_metrics(
        normalized_bundle.ads_campaigns,
        campaigns_state,
    )
    warnings.extend(warn)

    impressions, warn = _aggregate_stats_field(normalized_bundle.ads_stats, stats_state, "impressions")
    warnings.extend(warn)
    clicks, warn = _aggregate_stats_field(normalized_bundle.ads_stats, stats_state, "clicks")
    warnings.extend(warn)
    spend, warn = _aggregate_stats_field(normalized_bundle.ads_stats, stats_state, "spend")
    warnings.extend(warn)
    orders, warn = _aggregate_stats_field(normalized_bundle.ads_stats, stats_state, "orders")
    warnings.extend(warn)
    revenue, warn = _aggregate_stats_field(normalized_bundle.ads_stats, stats_state, "revenue")
    warnings.extend(warn)

    ctr, warn = _ratio_metric(
        numerator=clicks,
        denominator=impressions,
        stats_state=stats_state,
        metric_name="ctr",
        note_denominator="CTR denominator (impressions) is unavailable or <= 0",
    )
    warnings.extend(warn)
    cpc, warn = _ratio_metric(
        numerator=spend,
        denominator=clicks,
        stats_state=stats_state,
        metric_name="cpc",
        note_denominator="CPC denominator (clicks) is unavailable or <= 0",
    )
    warnings.extend(warn)
    conversion_click_to_order, warn = _ratio_metric(
        numerator=orders,
        denominator=clicks,
        stats_state=stats_state,
        metric_name="conversion_click_to_order",
        note_denominator="click-to-order denominator (clicks) is unavailable or <= 0",
    )
    warnings.extend(warn)
    warnings = dedupe_warnings(warnings)

    note = _section_note(campaigns_state=campaigns_state, stats_state=stats_state, warnings=warnings)

    return AdsMetricsSection(
        campaigns_count=campaigns_count,
        active_campaigns_count=active_campaigns_count,
        impressions=impressions,
        clicks=clicks,
        spend=spend,
        ctr=ctr,
        cpc=cpc,
        orders=orders,
        revenue=revenue,
        conversion_click_to_order=conversion_click_to_order,
        source_quality=source_quality,
        warnings=warnings,
        note=note,
    )


def build(payload: NormalizedBundle | None = None) -> AdsMetricsSection:
    """Back-compat alias for stage-1 naming."""

    if payload is None:
        return AdsMetricsSection()
    return assemble_ads_metrics(payload)
