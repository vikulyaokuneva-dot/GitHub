"""API ingestion package exports for v4."""

from .client import ApiCallResult, WBApiClient
from .orders import load_orders
from .sales import load_sales
from .realization import load_realization
from .stocks import load_stocks
from .ads import load_ads_bundle, load_ads_campaigns, load_ads_stats
from .funnel import load_funnel

__all__ = [
    "ApiCallResult",
    "WBApiClient",
    "load_orders",
    "load_sales",
    "load_realization",
    "load_stocks",
    "load_ads_campaigns",
    "load_ads_stats",
    "load_ads_bundle",
    "load_funnel",
]
