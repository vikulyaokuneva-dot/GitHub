"""Domain __init__.py

All business-domain models and contracts.
Zero dependencies on infrastructure or frameworks.
"""

from .contracts import (
    # Raw data contracts
    RawAdsData,
    RawOrdersData,
    RawMarginsData,
    RawReturnsData,
    RawRatingsData,
    RawDataBundle,
    # Normalized data
    NormalizedAds,
    NormalizedSKU,
    NormalizedDataBundle,
    # Metrics
    AdMetrics,
    SKUMetrics,
    PortfolioMetrics,
    MetricsBundle,
    # Facts & Decisions
    FactType,
    Fact,
    Recommendation,
    FactsBundle,
    # Processing result
    ProcessingStatus,
    ProcessingResult,
)
from .cabinet import Cabinet, CabinetContext, CabinetConfig
from .enums import RunMode, DataSource, ProcessingPhase

__all__ = [
    # Raw data
    "RawAdsData",
    "RawOrdersData",
    "RawMarginsData",
    "RawReturnsData",
    "RawRatingsData",
    "RawDataBundle",
    # Normalized data
    "NormalizedAds",
    "NormalizedSKU",
    "NormalizedDataBundle",
    # Metrics
    "AdMetrics",
    "SKUMetrics",
    "PortfolioMetrics",
    "MetricsBundle",
    # Facts & Decisions
    "FactType",
    "Fact",
    "Recommendation",
    "FactsBundle",
    # Processing
    "ProcessingStatus",
    "ProcessingResult",
    # Cabinet
    "Cabinet",
    "CabinetContext",
    "CabinetConfig",
    # Enums
    "RunMode",
    "DataSource",
    "ProcessingPhase",
]
