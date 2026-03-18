"""Normalization model aliases.

Input: normalized contracts.
Output: stable exports for normalization layer modules.
Does not perform transformations.
"""

from __future__ import annotations

from ..core.contracts import (
    NormalizedAdsCampaignRecord,
    NormalizedAdsStatRecord,
    NormalizedBundle,
    NormalizedFunnelRecord,
    NormalizedOrderRecord,
    NormalizedRealizationRecord,
    NormalizedSaleRecord,
    NormalizedStockRecord,
)

__all__ = [
    "NormalizedOrderRecord",
    "NormalizedSaleRecord",
    "NormalizedRealizationRecord",
    "NormalizedStockRecord",
    "NormalizedAdsCampaignRecord",
    "NormalizedAdsStatRecord",
    "NormalizedFunnelRecord",
    "NormalizedBundle",
]
