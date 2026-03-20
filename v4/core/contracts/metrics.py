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


def _default_unavailable_metric() -> MetricValue:
    return MetricValue(
        value=None,
        status=MetricStatus.UNAVAILABLE.value,
        source=None,
        note=None,
    )


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

    revenue_gross: MetricValue = field(default_factory=_default_unavailable_metric)
    commission_amount: MetricValue = field(default_factory=_default_unavailable_metric)
    acquiring_amount: MetricValue = field(default_factory=_default_unavailable_metric)
    pvz_amount: MetricValue = field(default_factory=_default_unavailable_metric)
    penalties_amount: MetricValue = field(default_factory=_default_unavailable_metric)
    acceptance_amount: MetricValue = field(default_factory=_default_unavailable_metric)
    paid_acceptance_amount: MetricValue = field(default_factory=_default_unavailable_metric)
    other_costs_amount: MetricValue = field(default_factory=_default_unavailable_metric)
    gross_profit_like: MetricValue = field(default_factory=_default_unavailable_metric)
    net_profit_like: MetricValue = field(default_factory=_default_unavailable_metric)
    margin: MetricValue = field(default_factory=_default_unavailable_metric)
    profit_formula_note: str | None = None

    realization_target_date: str | None = None
    realization_actual_date: str | None = None
    fallback_used: bool | None = None
    lag_days: int | None = None
    financial_model_mode: str | None = None
    financial_confidence: str | None = None
    financial_source_date: str | None = None
    realization_rows_count: int | None = None
    realization_extraction_mode: str | None = None
    realization_detected_operations: list[str] = field(default_factory=list)
    financial_mode: str | None = None
    financial_missing_components: list[str] = field(default_factory=list)
    financial_available_components: list[str] = field(default_factory=list)
    profitability_estimate_used: bool | None = None
    profitability_estimate_method: str | None = None
    profitability_estimate_formula: str | None = None
    profitability_estimate_dependencies: list[str] = field(default_factory=list)
    profitability_estimate_warning: str | None = None
    profitability_method: str | None = None
    profitability_dependencies: list[str] = field(default_factory=list)
    profitability_blockers: list[str] = field(default_factory=list)
    metric_provenance: dict[str, dict[str, Any]] = field(default_factory=dict)

    source_quality: dict[str, str] = field(default_factory=dict)
    component_quality: dict[str, str] = field(default_factory=dict)
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
class FunnelMetricsSection:
    """Funnel contour metrics aggregated on run level."""

    impressions: MetricValue = field(default_factory=_default_unavailable_metric)
    opens: MetricValue = field(default_factory=_default_unavailable_metric)
    cart_adds: MetricValue = field(default_factory=_default_unavailable_metric)
    orders: MetricValue = field(default_factory=_default_unavailable_metric)
    buys: MetricValue = field(default_factory=_default_unavailable_metric)

    ctr_open_from_impressions: MetricValue = field(default_factory=_default_unavailable_metric)
    cr_cart_from_opens: MetricValue = field(default_factory=_default_unavailable_metric)
    cr_orders_from_cart: MetricValue = field(default_factory=_default_unavailable_metric)
    cr_buys_from_orders: MetricValue = field(default_factory=_default_unavailable_metric)
    cr_buys_from_impressions: MetricValue = field(default_factory=_default_unavailable_metric)

    source_quality: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    note: str | None = None


@dataclass
class AdsMetricsSection:
    """Ads contour metrics with campaigns/stats source separation."""

    campaigns_count: MetricValue = field(default_factory=_default_unavailable_metric)
    active_campaigns_count: MetricValue = field(default_factory=_default_unavailable_metric)

    impressions: MetricValue = field(default_factory=_default_unavailable_metric)
    clicks: MetricValue = field(default_factory=_default_unavailable_metric)
    spend: MetricValue = field(default_factory=_default_unavailable_metric)

    ctr: MetricValue = field(default_factory=_default_unavailable_metric)
    cpc: MetricValue = field(default_factory=_default_unavailable_metric)

    orders: MetricValue = field(default_factory=_default_unavailable_metric)
    revenue: MetricValue = field(default_factory=_default_unavailable_metric)
    conversion_click_to_order: MetricValue = field(default_factory=_default_unavailable_metric)

    source_quality: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    note: str | None = None


@dataclass
class StockMetricsSection:
    """Stock contour metrics aggregated on run level."""

    total_stock_units: MetricValue = field(default_factory=_default_unavailable_metric)
    in_stock_items_count: MetricValue = field(default_factory=_default_unavailable_metric)
    out_of_stock_items_count: MetricValue = field(default_factory=_default_unavailable_metric)
    distinct_nm_ids_count: MetricValue = field(default_factory=_default_unavailable_metric)
    distinct_warehouses_count: MetricValue = field(default_factory=_default_unavailable_metric)

    stock_coverage_note: str | None = None
    source_quality: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    note: str | None = None


@dataclass
class HealthMetricsSection:
    """Explainable health contour metrics based on existing normalized/metrics data."""

    business_health_score: MetricValue = field(default_factory=_default_unavailable_metric)
    sku_health_signals_count: MetricValue = field(default_factory=_default_unavailable_metric)
    problematic_sku_count: MetricValue = field(default_factory=_default_unavailable_metric)
    dead_stock_risk_count: MetricValue = field(default_factory=_default_unavailable_metric)
    overstock_risk_count: MetricValue = field(default_factory=_default_unavailable_metric)

    business_health_status_note: str | None = None
    component_scores: dict[str, MetricValue] = field(default_factory=dict)
    source_quality: dict[str, str] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    note: str | None = None


@dataclass
class MetricsBundle:
    """Top-level metrics payload for downstream layers.

    On this stage, financial, daily, funnel, ads, stock, and health sections are assembled.
    """

    run_context: RunContext
    financial: FinancialMetricsSection | None = None
    daily: DailyMetricsSection | None = None
    funnel: FunnelMetricsSection | None = None
    ads: AdsMetricsSection | None = None
    stock: StockMetricsSection | None = None
    health: HealthMetricsSection | None = None
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
            "funnel": self.funnel,
            "ads": self.ads,
            "stock": self.stock,
            "health": self.health,
        }
