from __future__ import annotations

"""
Compatibility wrapper.

Canonical daily KPI resolver lives in `v3/daily_kpi_resolver.py`.
This module intentionally re-exports the same constants and function
to avoid duplicate logic and prevent import breakage.
"""

from ..daily_kpi_resolver import (  # noqa: F401
    DAILY_SOURCE_FALLBACK,
    DAILY_SOURCE_ORDERS_API,
    DAILY_SOURCE_REALIZATION_API,
    DAILY_SOURCE_SALES_API,
    DAILY_SOURCE_SUPPLIER_GOODS,
    DAILY_SOURCE_UNKNOWN,
    resolve_daily_kpi,
)

__all__ = [
    "DAILY_SOURCE_SUPPLIER_GOODS",
    "DAILY_SOURCE_ORDERS_API",
    "DAILY_SOURCE_SALES_API",
    "DAILY_SOURCE_REALIZATION_API",
    "DAILY_SOURCE_FALLBACK",
    "DAILY_SOURCE_UNKNOWN",
    "resolve_daily_kpi",
]
