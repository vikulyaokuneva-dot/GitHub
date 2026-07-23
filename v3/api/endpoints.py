from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

BASE_STATISTICS = "statistics"
BASE_ADVERT = "advert"
BASE_ANALYTICS = "analytics"


@dataclass(frozen=True)
class WBEndpoint:
    name: str
    base: str
    path: str


ORDERS = WBEndpoint(name="orders", base=BASE_STATISTICS, path="/api/v1/supplier/orders")
SALES = WBEndpoint(name="sales", base=BASE_STATISTICS, path="/api/v1/supplier/sales")
STOCKS = WBEndpoint(
    name="stocks_wb_warehouses",
    base=BASE_ANALYTICS,
    path="/api/analytics/v1/stocks-report/wb-warehouses",
)
REALIZATION = WBEndpoint(name="realization", base=BASE_STATISTICS, path="/api/v5/supplier/reportDetailByPeriod")
ADS = WBEndpoint(name="ads", base=BASE_ADVERT, path="/api/advert/v2/adverts")
FINANCE_SALES_REPORTS_DETAILED = WBEndpoint(
    name="finance_sales_reports_detailed",
    base=BASE_STATISTICS,
    path="/api/finance/v1/sales-reports/detailed",
)
FINANCE_SALES_REPORTS_LIST = WBEndpoint(
    name="finance_sales_reports_list",
    base=BASE_STATISTICS,
    path="/api/finance/v1/sales-reports/list",
)

SALES_FUNNEL_HISTORY = WBEndpoint(
    name="sales_funnel_history",
    base=BASE_ANALYTICS,
    path="/api/analytics/v3/sales-funnel/products/history",
)

STOCKS_WB_WAREHOUSES = WBEndpoint(
    name="stocks_wb_warehouses",
    base=BASE_ANALYTICS,
    path="/api/analytics/v1/stocks-report/wb-warehouses",
)

STOCKS_PRODUCTS = WBEndpoint(
    name="stocks_products",
    base=BASE_STATISTICS,
    path="/api/v2/stocks-report/products/products",
)

STOCKS_OFFICES = WBEndpoint(
    name="stocks_offices",
    base=BASE_STATISTICS,
    path="/api/v2/stocks-report/offices",
)

ACCOUNT_BALANCE = WBEndpoint(
    name="account_balance",
    base=BASE_STATISTICS,
    path="/api/v1/account/balance",
)

SEARCH_PRODUCT_TEXTS = WBEndpoint(
    name="search_product_texts",
    base=BASE_ANALYTICS,
    path="/api/v2/search-report/product/search-texts",
)

SEARCH_PRODUCT_ORDERS = WBEndpoint(
    name="search_product_orders",
    base=BASE_ANALYTICS,
    path="/api/v2/search-report/product/orders",
)

ALL_ENDPOINTS: Dict[str, WBEndpoint] = {
    ORDERS.name: ORDERS,
    SALES.name: SALES,
    STOCKS.name: STOCKS,
    REALIZATION.name: REALIZATION,
    ADS.name: ADS,
    FINANCE_SALES_REPORTS_DETAILED.name: FINANCE_SALES_REPORTS_DETAILED,
    FINANCE_SALES_REPORTS_LIST.name: FINANCE_SALES_REPORTS_LIST,
    SALES_FUNNEL_HISTORY.name: SALES_FUNNEL_HISTORY,
    STOCKS_WB_WAREHOUSES.name: STOCKS_WB_WAREHOUSES,
    STOCKS_PRODUCTS.name: STOCKS_PRODUCTS,
    STOCKS_OFFICES.name: STOCKS_OFFICES,
    ACCOUNT_BALANCE.name: ACCOUNT_BALANCE,
    SEARCH_PRODUCT_TEXTS.name: SEARCH_PRODUCT_TEXTS,
    SEARCH_PRODUCT_ORDERS.name: SEARCH_PRODUCT_ORDERS,
}
