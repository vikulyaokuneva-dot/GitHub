"""Metrics contracts.

Input: NormalizedBundle.
Output: MetricsBundle sections for downstream layers.
Does not render outputs and does not make decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .raw import RunContext, SourceStatus


class MetricStatus(str, Enum):
    """Canonical status for metric values."""

    CONFIRMED = "confirmed"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class MetricValue:
    """Typed metric value with provenance.

    Rule: value=None means missing/insufficient and must not be converted to 0.
    """

    value: float | int | None
    status: str
    source: str | None
    note: str | None = None


@dataclass
class FinancialMetricsSection:
    """Financial contour foundation metrics."""

    orders_count: MetricValue
    sales_count: MetricValue
    returns_count: MetricValue
    orders_amount: MetricValue
    sales_amount: MetricValue
    seller_payout: MetricValue
    logistics_cost: MetricValue
    storage_cost: MetricValue
    deductions_amount: MetricValue
    net_realization_amount: MetricValue

    realization_target_date: str | None
    realization_actual_date: str | None
    fallback_used: bool | None
    lag_days: int | None

    source_quality: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class DailyMetricsSection:
    """Daily subset exposed from financial contour."""

    orders_count: MetricValue
    sales_count: MetricValue
    returns_count: MetricValue
    orders_amount: MetricValue
    sales_amount: MetricValue


@dataclass
class MetricsBundle:
    """Top-level metrics payload for downstream layers.

    On this stage, only financial and daily sections are assembled.
    """

    run_context: RunContext
    financial: FinancialMetricsSection | None = None
    daily: DailyMetricsSection | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
    source_flags: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    source_statuses: dict[str, SourceStatus] = field(default_factory=dict)

    @property
    def context(self) -> RunContext:
        """Back-compat alias for previous call sites."""

        return self.run_context

    @property
    def source_status(self) -> dict[str, SourceStatus]:
        """Back-compat alias for previous call sites."""

        return self.source_statuses

    @property
    def sections(self) -> dict[str, Any]:
        """Compatibility map style used by stage-1 skeleton code."""

        return {
            "financial": self.financial,
            "daily": self.daily,
        }
