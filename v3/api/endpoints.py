from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

BASE_STATISTICS = "statistics"
BASE_ADVERT = "advert"


@dataclass(frozen=True)
class WBEndpoint:
    name: str
    base: str
    path: str


ORDERS = WBEndpoint(name="orders", base=BASE_STATISTICS, path="/api/v1/supplier/orders")
SALES = WBEndpoint(name="sales", base=BASE_STATISTICS, path="/api/v1/supplier/sales")
STOCKS = WBEndpoint(name="stocks", base=BASE_STATISTICS, path="/api/v1/supplier/stocks")
REALIZATION = WBEndpoint(name="realization", base=BASE_STATISTICS, path="/api/v5/supplier/reportDetailByPeriod")
ADS = WBEndpoint(name="ads", base=BASE_ADVERT, path="/api/advert/v2/adverts")

ALL_ENDPOINTS: Dict[str, WBEndpoint] = {
    ORDERS.name: ORDERS,
    SALES.name: SALES,
    STOCKS.name: STOCKS,
    REALIZATION.name: REALIZATION,
    ADS.name: ADS,
}

