"""Normalized contracts.

Input: RawBundle.
Output: NormalizedBundle with canonical source-level records.
Does not compute KPI or perform report rendering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .raw import RunContext, SourceStatus


@dataclass(frozen=True)
class NormalizedRecord:
    """Compatibility base record for generic normalized collections."""

    source_tag: str
    raw_ref: str | None = None


@dataclass(frozen=True)
class NormalizedOrderRecord:
    """Canonical order-level record from raw orders source."""

    record_id: str | None
    seller_id: str | None
    nm_id: str | int | None
    subject_name: str | None
    quantity: int | float | None
    price: float | None
    order_date: str | None
    source_tag: str
    raw_ref: str | None


@dataclass(frozen=True)
class NormalizedSaleRecord:
    """Canonical sale-level record from raw sales source."""

    record_id: str | None
    seller_id: str | None
    nm_id: str | int | None
    quantity: int | float | None
    sale_amount: float | None
    payout_amount: float | None
    sale_date: str | None
    operation_type: str | None
    is_return: bool | None
    source_tag: str
    raw_ref: str | None


@dataclass(frozen=True)
class NormalizedRealizationRecord:
    """Canonical realization event record for financial contour foundation."""

    record_id: str | None
    seller_id: str | None
    nm_id: str | int | None
    event_date: str | None
    event_type: str | None
    amount: float | None
    quantity: float | None
    source_tag: str
    raw_ref: str | None


@dataclass(frozen=True)
class NormalizedStockRecord:
    """Canonical stock snapshot record."""

    record_id: str | None
    seller_id: str | None
    nm_id: str | int | None
    warehouse_name: str | None
    size: str | None
    quantity: int | float | None
    stock_date: str | None
    source_tag: str
    raw_ref: str | None


@dataclass(frozen=True)
class NormalizedAdsCampaignRecord:
    """Canonical ads campaign metadata record."""

    campaign_id: str | int | None
    campaign_name: str | None
    campaign_type: str | None
    status: str | None
    start_date: str | None
    end_date: str | None
    source_tag: str
    raw_ref: str | None


@dataclass(frozen=True)
class NormalizedAdsStatRecord:
    """Canonical ads stat record."""

    campaign_id: str | int | None
    stat_date: str | None
    impressions: float | None
    clicks: float | None
    spend: float | None
    orders: float | None
    revenue: float | None
    source_tag: str
    raw_ref: str | None


@dataclass(frozen=True)
class NormalizedFunnelRecord:
    """Canonical funnel performance record."""

    entity_id: str | int | None
    event_date: str | None
    impressions: float | None
    opens: float | None
    cart_adds: float | None
    orders: float | None
    buys: float | None
    source_tag: str
    raw_ref: str | None


@dataclass
class NormalizedBundle:
    """Normalized layer payload between raw ingestion and metrics.

    Rule: None remains None.
    Rule: source statuses/warnings/diagnostics are preserved.
    """

    run_context: RunContext
    orders: list[NormalizedOrderRecord] = field(default_factory=list)
    sales: list[NormalizedSaleRecord] = field(default_factory=list)
    realization: list[NormalizedRealizationRecord] = field(default_factory=list)
    stocks: list[NormalizedStockRecord] = field(default_factory=list)
    ads_campaigns: list[NormalizedAdsCampaignRecord] = field(default_factory=list)
    ads_stats: list[NormalizedAdsStatRecord] = field(default_factory=list)
    funnel: list[NormalizedFunnelRecord] = field(default_factory=list)
    source_statuses: dict[str, SourceStatus] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def context(self) -> RunContext:
        """Back-compat alias for older contracts."""

        return self.run_context

    @property
    def source_status(self) -> dict[str, SourceStatus]:
        """Back-compat alias for older contracts."""

        return self.source_statuses

    @property
    def records(self) -> dict[str, list[Any]]:
        """Compatibility view compatible with stage-1 generic record map."""

        return {
            "orders": list(self.orders),
            "sales": list(self.sales),
            "realization": list(self.realization),
            "stocks": list(self.stocks),
            "ads_campaigns": list(self.ads_campaigns),
            "ads_stats": list(self.ads_stats),
            "funnel": list(self.funnel),
        }
