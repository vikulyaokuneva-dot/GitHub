"""Central endpoint registry for v4 API ingestion.

Input: endpoint name lookup by loaders.
Output: immutable endpoint descriptors.
Does not perform HTTP calls.
"""

from __future__ import annotations

from dataclasses import dataclass

BASE_STATISTICS = "statistics"
BASE_ADVERT = "advert"
BASE_ANALYTICS = "analytics"


@dataclass(frozen=True)
class WBEndpoint:
    """HTTP endpoint descriptor used by WBApiClient."""

    name: str
    base: str
    path: str
    method: str = "GET"


ORDERS = WBEndpoint(name="orders", base=BASE_STATISTICS, path="/api/v1/supplier/orders", method="GET")
SALES = WBEndpoint(name="sales", base=BASE_STATISTICS, path="/api/v1/supplier/sales", method="GET")
REALIZATION = WBEndpoint(
    name="realization",
    base=BASE_STATISTICS,
    path="/api/v5/supplier/reportDetailByPeriod",
    method="GET",
)
STOCKS = WBEndpoint(name="stocks", base=BASE_STATISTICS, path="/api/v1/supplier/stocks", method="GET")
ADS_CAMPAIGNS = WBEndpoint(name="ads_campaigns", base=BASE_ADVERT, path="/api/advert/v2/adverts", method="GET")
ADS_STATS = WBEndpoint(name="ads_stats", base=BASE_ADVERT, path="/adv/v3/fullstats", method="GET")
FUNNEL = WBEndpoint(
    name="funnel",
    base=BASE_ANALYTICS,
    path="/api/analytics/v3/sales-funnel/products",
    method="POST",
)

ALL_ENDPOINTS: dict[str, WBEndpoint] = {
    ORDERS.name: ORDERS,
    SALES.name: SALES,
    REALIZATION.name: REALIZATION,
    STOCKS.name: STOCKS,
    ADS_CAMPAIGNS.name: ADS_CAMPAIGNS,
    ADS_STATS.name: ADS_STATS,
    FUNNEL.name: FUNNEL,
}
