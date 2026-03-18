"""Helper functions for funnel metrics assembly.

Input: normalized funnel records and source states.
Output: safe MetricValue objects for volumes and ratios.
Does not fetch data and does not compute non-funnel metrics.
"""

from __future__ import annotations

from ...core.contracts import MetricStatus, MetricValue, NormalizedBundle, NormalizedFunnelRecord


def funnel_source_state(normalized_bundle: NormalizedBundle) -> str:
    status = normalized_bundle.source_statuses.get("funnel")
    if status is None:
        return "missing"
    raw = getattr(status, "status", None)
    if hasattr(raw, "value"):
        return str(raw.value)
    return str(raw or "missing").strip().lower() or "missing"


def source_is_usable(source_state: str) -> bool:
    return source_state in {"ok", "partial"}


def make_metric(
    value: float | int | None,
    *,
    status: MetricStatus,
    source: str | None,
    note: str | None = None,
) -> MetricValue:
    return MetricValue(value=value, status=status.value, source=source, note=note)


def aggregate_volume_metric(
    *,
    records: list[NormalizedFunnelRecord],
    field_name: str,
    source_state: str,
) -> tuple[MetricValue, list[str]]:
    warnings: list[str] = []

    if not source_is_usable(source_state):
        return (
            make_metric(
                None,
                status=MetricStatus.UNAVAILABLE,
                source="funnel",
                note="funnel source is unavailable",
            ),
            warnings,
        )

    if not records:
        warnings.append("funnel source has no records for this run")
        return (
            make_metric(
                None,
                status=MetricStatus.UNAVAILABLE,
                source="funnel",
                note="funnel records are unavailable",
            ),
            warnings,
        )

    numeric_values: list[float] = []
    missing_count = 0
    for record in records:
        raw = getattr(record, field_name, None)
        if raw is None:
            missing_count += 1
            continue
        try:
            numeric_values.append(float(raw))
        except (TypeError, ValueError):
            missing_count += 1

    if not numeric_values:
        warnings.append(f"funnel field '{field_name}' has no reliable numeric values")
        return (
            make_metric(
                None,
                status=MetricStatus.PARTIAL,
                source="funnel",
                note=f"field {field_name} is missing in source rows",
            ),
            warnings,
        )

    total = round(sum(numeric_values), 4)
    metric_status = MetricStatus.CONFIRMED
    note = None
    if source_state == "partial" or missing_count > 0:
        metric_status = MetricStatus.PARTIAL
        note = f"field {field_name} is partially populated"
        warnings.append(f"funnel field '{field_name}' is partially populated")

    return make_metric(total, status=metric_status, source="funnel", note=note), warnings


def safe_ratio_metric(
    *,
    numerator: MetricValue,
    denominator: MetricValue,
    source_state: str,
    ratio_name: str,
) -> tuple[MetricValue, list[str]]:
    warnings: list[str] = []

    if not source_is_usable(source_state):
        return (
            make_metric(
                None,
                status=MetricStatus.UNAVAILABLE,
                source="funnel",
                note="funnel source is unavailable",
            ),
            warnings,
        )

    if denominator.value is None:
        warnings.append(f"{ratio_name}: denominator is unavailable")
        status = MetricStatus.PARTIAL if denominator.status != MetricStatus.UNAVAILABLE.value else MetricStatus.UNAVAILABLE
        return (
            make_metric(
                None,
                status=status,
                source="funnel",
                note=f"{ratio_name} denominator is unavailable",
            ),
            warnings,
        )

    if numerator.value is None:
        warnings.append(f"{ratio_name}: numerator is unavailable")
        status = MetricStatus.PARTIAL if numerator.status != MetricStatus.UNAVAILABLE.value else MetricStatus.UNAVAILABLE
        return (
            make_metric(
                None,
                status=status,
                source="funnel",
                note=f"{ratio_name} numerator is unavailable",
            ),
            warnings,
        )

    try:
        den = float(denominator.value)
        num = float(numerator.value)
    except (TypeError, ValueError):
        warnings.append(f"{ratio_name}: invalid numeric inputs")
        return (
            make_metric(
                None,
                status=MetricStatus.PARTIAL,
                source="funnel",
                note=f"{ratio_name} inputs are invalid",
            ),
            warnings,
        )

    if den <= 0:
        warnings.append(f"{ratio_name}: denominator is zero or negative")
        return (
            make_metric(
                None,
                status=MetricStatus.PARTIAL,
                source="funnel",
                note=f"{ratio_name} denominator is zero or invalid",
            ),
            warnings,
        )

    ratio_value = round(num / den, 6)
    status = MetricStatus.CONFIRMED
    note = None
    if (
        source_state == "partial"
        or numerator.status != MetricStatus.CONFIRMED.value
        or denominator.status != MetricStatus.CONFIRMED.value
    ):
        status = MetricStatus.PARTIAL
        note = f"{ratio_name} is partially reliable"

    return make_metric(ratio_value, status=status, source="funnel", note=note), warnings
