"""Date policy utilities for v5 pipelines."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo


BERLIN_TZ = ZoneInfo("Europe/Berlin")
DAILY_D_MINUS_1_REASON = (
    "daily mode uses previous day because WB current-day data is incomplete"
)


def get_berlin_today(now: datetime | None = None) -> date:
    """Return current date in Europe/Berlin timezone."""
    dt = now or datetime.now(BERLIN_TZ)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=BERLIN_TZ)
    return dt.astimezone(BERLIN_TZ).date()


@dataclass(frozen=True)
class DateResolution:
    """Resolved run/report dates plus shift diagnostics."""

    mode: Literal["daily", "audit"]
    run_date: date
    report_date: date
    date_shift_applied: bool
    date_shift_reason: str
    warnings: list[dict[str, Any]] = field(default_factory=list)


def resolve_processing_dates(
    mode: Literal["daily", "audit"],
    requested_date: date | None = None,
    *,
    berlin_today: date | None = None,
) -> DateResolution:
    """Resolve run/report date policy for v5."""
    run_date = berlin_today or get_berlin_today()

    if mode == "audit":
        report_date = requested_date or run_date
        return DateResolution(
            mode=mode,
            run_date=run_date,
            report_date=report_date,
            date_shift_applied=False,
            date_shift_reason="",
            warnings=[],
        )

    # daily mode
    yesterday = run_date - timedelta(days=1)
    if requested_date is None:
        return DateResolution(
            mode=mode,
            run_date=run_date,
            report_date=yesterday,
            date_shift_applied=True,
            date_shift_reason=DAILY_D_MINUS_1_REASON,
            warnings=[],
        )

    if requested_date >= run_date:
        is_future = requested_date > run_date
        warning_code = (
            "daily_date_adjusted_from_future"
            if is_future
            else "daily_date_adjusted_from_today"
        )
        warning_message = (
            f"Daily requested date {requested_date.isoformat()} was adjusted to "
            f"{yesterday.isoformat()} (D-1 policy)."
        )
        return DateResolution(
            mode=mode,
            run_date=run_date,
            report_date=yesterday,
            date_shift_applied=True,
            date_shift_reason=DAILY_D_MINUS_1_REASON,
            warnings=[
                {
                    "code": warning_code,
                    "severity": "medium",
                    "message": warning_message,
                }
            ],
        )

    return DateResolution(
        mode=mode,
        run_date=run_date,
        report_date=requested_date,
        date_shift_applied=False,
        date_shift_reason="",
        warnings=[],
    )
