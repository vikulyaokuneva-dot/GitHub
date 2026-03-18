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
    DailyMetricsSection,
    FinancialMetricsSection,
    MetricStatus,
    MetricValue,
    MetricsBundle,
)
from .facts import FactsBundle
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
    "MetricsBundle",
    "FactsBundle",
    "DecisionItem",
    "DecisionsBundle",
    "ReportPayload",
]
