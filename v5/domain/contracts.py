"""
Domain layer: Data contracts and models.

All business-domain structures are defined here.
Zero dependencies on frameworks or infrastructure.
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Any, Literal, Optional
from enum import Enum


# ============================================================================
# Raw Data Contracts (from API or Reports)
# ============================================================================

@dataclass
class RawAdsData:
    """Raw ads data from API or reports"""
    ad_id: str
    name: str
    sku_ids: list[str]  # Multiple SKUs per ad
    budget_daily: float
    status: str  # "active", "paused", etc.
    views: int
    clicks: int
    spend: float
    date: date


@dataclass
class RawOrdersData:
    """Raw orders data"""
    order_id: str
    sku_id: str
    ad_id: Optional[str]
    quantity: int
    revenue: float
    commission: float
    date: date
    operation_type: str = ""
    operation_basis: str = ""
    document_type: str = ""
    gross_revenue: float = 0.0
    realized_revenue: float = 0.0
    seller_payout: float = 0.0
    logistics: float = 0.0
    storage: float = 0.0
    penalties: float = 0.0
    deductions: float = 0.0
    loyalty_program: float = 0.0
    loyalty_points_withheld: float = 0.0
    acquiring: float = 0.0
    pvz_service: float = 0.0
    other_adjustments: float = 0.0
    rebill_logistic_cost: float = 0.0
    source_file: str = ""
    raw_row_index: int = -1
    is_valid_sku: bool = True
    excluded_reason: str = ""


@dataclass
class RawMarginsData:
    """Raw margins/profitability data"""
    sku_id: str
    cost_price: float
    selling_price: float
    margin_percent: float
    date: date


@dataclass
class RawReturnsData:
    """Raw returns data"""
    return_id: str
    order_id: str
    sku_id: str
    reason: str
    revenue_lost: float
    date: date


@dataclass
class RawRatingsData:
    """Raw ratings data"""
    sku_id: str
    rating: float
    review_count: int
    negative_reviews: int
    date: date


@dataclass
class RawDataBundle:
    """Bundle of raw data from a single source (API or file)"""
    cabinet_id: str
    period_date: date
    source: Literal["api", "report"]
    
    ads: list[RawAdsData] = field(default_factory=list)
    orders: list[RawOrdersData] = field(default_factory=list)
    margins: list[RawMarginsData] = field(default_factory=list)
    returns: list[RawReturnsData] = field(default_factory=list)
    ratings: list[RawRatingsData] = field(default_factory=list)
    debug: dict[str, Any] = field(default_factory=dict)


# ============================================================================
# Normalized Data (unified format, independent of source)
# ============================================================================

@dataclass
class NormalizedAds:
    """Normalized ads data"""
    ad_id: str
    name: str
    sku_ids: list[str]
    budget_daily: float
    status: str
    
    # Basic metrics
    impressions: int
    clicks: int
    spend: float
    
    # Calculated normalized metrics
    ctr: float  # Click-through rate
    spend_per_impression: float


@dataclass
class NormalizedSKU:
    """Normalized SKU data"""
    sku_id: str
    name: str
    
    # Sales
    orders: int
    revenue: float
    
    # Profitability
    cost_price: float
    margin_percent: float
    profit: float
    
    # Quality
    rating: float
    review_count: int
    return_rate: float


@dataclass
class NormalizedDataBundle:
    """Unified data bundle (same format regardless of source)"""
    cabinet_id: str
    period_date: date
    
    ads: list[NormalizedAds] = field(default_factory=list)
    skus: list[NormalizedSKU] = field(default_factory=list)


# ============================================================================
# Metrics (calculated KPIs)
# ============================================================================

@dataclass
class AdMetrics:
    """Calculated metrics for a single ad"""
    ad_id: str
    
    # Core metrics
    ctr: float  # Click-through rate
    cpc: float  # Cost per click
    roas: float  # Return on ad spend
    
    # Efficiency
    efficiency_score: float  # 0-100
    
    # Anomalies
    has_anomaly: bool = False
    anomaly_severity: int = 0  # 1-10


@dataclass
class SKUMetrics:
    """Calculated metrics for a single SKU"""
    sku_id: str
    
    # Sales metrics
    daily_orders: float
    daily_revenue: float
    
    # Profitability
    daily_profit: float
    margin_percent: float
    
    # Growth
    growth_rate: float  # % change from previous period
    
    # Quality
    rating: float
    negative_review_rate: float


@dataclass
class PortfolioMetrics:
    """Portfolio-level metrics"""
    total_spend: float
    total_revenue: float
    total_profit: float
    
    avg_roas: float
    avg_cpc: float
    avg_ctr: float
    
    portfolio_efficiency_score: float
    
    # Order metrics aggregated from SKU data
    daily_orders_count: int = 0
    daily_buyouts_count: int = 0
    orders_count_confirmed: bool = True  # True when loaded from file
    financial_summary: dict[str, Any] = field(default_factory=dict)


@dataclass
class MetricsBundle:
    """Bundle of calculated metrics"""
    cabinet_id: str
    period_date: date
    
    ad_metrics: list[AdMetrics] = field(default_factory=list)
    sku_metrics: list[SKUMetrics] = field(default_factory=list)
    portfolio_metrics: Optional[PortfolioMetrics] = None
    financial_summary: dict[str, Any] = field(default_factory=dict)


# ============================================================================
# Facts and Decisions
# ============================================================================

class FactType(Enum):
    """Types of facts/insights"""
    OPPORTUNITY = "opportunity"
    RISK = "risk"
    ANOMALY = "anomaly"
    TREND = "trend"


@dataclass
class Fact:
    """A fact, insight or anomaly"""
    type: FactType
    title: str
    description: str
    severity: int  # 1-10
    affected_ids: list[str]  # ad_ids or sku_ids


@dataclass
class Recommendation:
    """Actionable recommendation"""
    title: str
    description: str
    priority: int  # 1-10, 10 = highest
    action_type: str  # "increase_budget", "decrease_cpc", etc.


@dataclass
class FactsBundle:
    """Bundle of facts and recommendations"""
    cabinet_id: str
    period_date: date
    
    facts: list[Fact] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)


# ============================================================================
# Processing Result
# ============================================================================

class ProcessingStatus(Enum):
    """Status of processing"""
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass
class ProcessingResult:
    """Result of a processing run"""
    status: ProcessingStatus
    cabinet_id: str
    run_date: date
    mode: Literal["daily", "audit"]
    
    message: str = ""
    errors: list[str] = field(default_factory=list)
    
    # Optionally include bundles
    raw_bundle: Optional[RawDataBundle] = None
    normalized_bundle: Optional[NormalizedDataBundle] = None
    metrics_bundle: Optional[MetricsBundle] = None
    facts_bundle: Optional[FactsBundle] = None
