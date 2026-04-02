"""Date policy for pipeline runs."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


def get_report_date() -> date:
    """Return D-1 date in Europe/Berlin timezone."""
    berlin_today = datetime.now(ZoneInfo("Europe/Berlin")).date()
    return berlin_today - timedelta(days=1)

