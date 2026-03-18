"""Realization lag-fallback resolution for financial contour.

Input: NormalizedBundle and run context.
Output: transparent realization window selection diagnostics.
Does not compute KPI values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ...core.contracts import MetricStatus, NormalizedBundle, RunContext


@dataclass(frozen=True)
class RealizationWindowResolution:
    """Resolved realization date selection for financial assembly."""

    target_date: str | None
    actual_date: str | None
    fallback_used: bool
    lag_days: int | None
    status: str
    warnings: list[str] = field(default_factory=list)


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    text = str(value).strip()[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _target_date(run_context: RunContext) -> str | None:
    return run_context.resolved_date_iso or run_context.requested_date_iso


def resolve_realization_window(
    normalized_bundle: NormalizedBundle,
    run_context: RunContext | None = None,
) -> RealizationWindowResolution:
    """Resolve best available realization date with backward lag fallback.

    Selection rules:
    1) exact target date if available,
    2) nearest previous available date,
    3) unavailable when no suitable date exists.
    """

    context = run_context or normalized_bundle.run_context
    target_date = _target_date(context)
    warnings: list[str] = []

    available_dates = sorted(
        {
            str(record.event_date)[:10]
            for record in normalized_bundle.realization
            if record.event_date
        }
    )

    if not available_dates:
        warnings.append("realization records are unavailable for lag resolution")
        return RealizationWindowResolution(
            target_date=target_date,
            actual_date=None,
            fallback_used=False,
            lag_days=None,
            status=MetricStatus.UNAVAILABLE.value,
            warnings=warnings,
        )

    if target_date and target_date in available_dates:
        return RealizationWindowResolution(
            target_date=target_date,
            actual_date=target_date,
            fallback_used=False,
            lag_days=0,
            status=MetricStatus.CONFIRMED.value,
            warnings=warnings,
        )

    if not target_date:
        actual = available_dates[-1]
        warnings.append("target realization date is missing; latest available date is used")
        return RealizationWindowResolution(
            target_date=None,
            actual_date=actual,
            fallback_used=False,
            lag_days=None,
            status=MetricStatus.PARTIAL.value,
            warnings=warnings,
        )

    parsed_target = _parse_iso_date(target_date)
    previous_candidates = [d for d in available_dates if d <= target_date]

    if previous_candidates:
        actual = previous_candidates[-1]
        parsed_actual = _parse_iso_date(actual)
        lag_days: int | None = None
        if parsed_target is not None and parsed_actual is not None:
            lag_days = (parsed_target - parsed_actual).days
        warnings.append("realization lag fallback applied: using previous available date")
        return RealizationWindowResolution(
            target_date=target_date,
            actual_date=actual,
            fallback_used=True,
            lag_days=lag_days,
            status=MetricStatus.PARTIAL.value,
            warnings=warnings,
        )

    warnings.append("realization exists only after target date; fallback to previous day is unavailable")
    return RealizationWindowResolution(
        target_date=target_date,
        actual_date=None,
        fallback_used=False,
        lag_days=None,
        status=MetricStatus.UNAVAILABLE.value,
        warnings=warnings,
    )
