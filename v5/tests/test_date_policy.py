"""Tests for v5 date policy."""

from datetime import date

from ..date_policy import (
    DAILY_D_MINUS_1_REASON,
    resolve_processing_dates,
)


def test_daily_without_explicit_date_uses_yesterday() -> None:
    resolution = resolve_processing_dates(
        mode="daily",
        requested_date=None,
        berlin_today=date(2026, 4, 2),
    )
    assert resolution.run_date == date(2026, 4, 2)
    assert resolution.report_date == date(2026, 4, 1)
    assert resolution.date_shift_applied is True
    assert resolution.date_shift_reason == DAILY_D_MINUS_1_REASON
    assert resolution.warnings == []


def test_daily_with_explicit_today_adjusts_to_yesterday_with_warning() -> None:
    resolution = resolve_processing_dates(
        mode="daily",
        requested_date=date(2026, 4, 2),
        berlin_today=date(2026, 4, 2),
    )
    assert resolution.report_date == date(2026, 4, 1)
    assert resolution.date_shift_applied is True
    assert resolution.date_shift_reason == DAILY_D_MINUS_1_REASON
    assert len(resolution.warnings) == 1
    assert resolution.warnings[0]["code"] == "daily_date_adjusted_from_today"


def test_daily_with_future_date_adjusts_to_yesterday_with_warning() -> None:
    resolution = resolve_processing_dates(
        mode="daily",
        requested_date=date(2026, 4, 5),
        berlin_today=date(2026, 4, 2),
    )
    assert resolution.report_date == date(2026, 4, 1)
    assert resolution.date_shift_applied is True
    assert resolution.date_shift_reason == DAILY_D_MINUS_1_REASON
    assert len(resolution.warnings) == 1
    assert resolution.warnings[0]["code"] == "daily_date_adjusted_from_future"


def test_audit_with_explicit_date_uses_exact_date_without_shift() -> None:
    resolution = resolve_processing_dates(
        mode="audit",
        requested_date=date(2026, 4, 2),
        berlin_today=date(2026, 4, 9),
    )
    assert resolution.run_date == date(2026, 4, 9)
    assert resolution.report_date == date(2026, 4, 2)
    assert resolution.date_shift_applied is False
    assert resolution.date_shift_reason == ""
    assert resolution.warnings == []
