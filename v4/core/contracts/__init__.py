"""Public contracts for v4 layer boundaries."""

from .raw import (
    IngestionResult,
    RawBundle,
    RawSourcePayload,
    RunContext,
    RunMode,
    SourceKind,
    SourceStatus,
    SourceStatusCode,
    coerce_iso_date,
)
from .normalized import (
    NormalizedAdsCampaignRecord,
    NormalizedAdsStatRecord,
    NormalizedBundle,
    NormalizedFunnelRecord,
    NormalizedOrderRecord,
    NormalizedRealizationRecord,
    NormalizedRecord,
    NormalizedSaleRecord,
    NormalizedStockRecord,
)
from .metrics import (
    AdsMetricsSection,
    DailyMetricsSection,
    FinancialMetricsSection,
    FunnelMetricsSection,
    MetricStatus,
    MetricValue,
    MetricsBundle,
    StockMetricsSection,
)
from .facts import FactItem, FactSection, FactsBundle, FactValue
from .decisions import DecisionItem, DecisionsBundle
from .report import ReportPayload

__all__ = [
    "IngestionResult",
    "RawBundle",
    "RawSourcePayload",
    "RunContext",
    "RunMode",
    "SourceKind",
    "SourceStatus",
    "SourceStatusCode",
    "coerce_iso_date",
    "NormalizedRecord",
    "NormalizedOrderRecord",
    "NormalizedSaleRecord",
    "NormalizedRealizationRecord",
    "NormalizedStockRecord",
    "NormalizedAdsCampaignRecord",
    "NormalizedAdsStatRecord",
    "NormalizedFunnelRecord",
    "NormalizedBundle",
    "MetricStatus",
    "MetricValue",
    "FinancialMetricsSection",
    "DailyMetricsSection",
    "FunnelMetricsSection",
    "AdsMetricsSection",
    "StockMetricsSection",
    "MetricsBundle",
    "FactValue",
    "FactItem",
    "FactSection",
    "FactsBundle",
    "DecisionItem",
    "DecisionsBundle",
    "ReportPayload",
]
