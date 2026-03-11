from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class NormalizedOrderRow:
    date: str
    sku: str
    nm_id: str
    order_id: str
    quantity: float
    price: float
    warehouse: str
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedSalesRow:
    date: str
    sku: str
    nm_id: str
    order_ref: str
    quantity: float
    revenue: float
    buys: float
    orders: float
    cost_price: float
    wb_commission: float
    logistics: float
    storage: float
    penalties: float
    deductions: float
    ads_spend: float
    profit: float
    warehouse: str
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedStockRow:
    sku: str
    nm_id: str
    quantity: float
    warehouse: str
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedSupplierGoodsFinancialRow:
    sku: str
    nm_id: str
    revenue_to_transfer: float
    wb_commission: float
    logistics: float
    storage: float
    deductions: float
    returns_qty: float
    source_file: str
    is_aggregate: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedAdsRow:
    date: str
    sku: str
    nm_id: str
    spend: float
    impressions: float
    clicks: float
    orders: float
    revenue: float
    is_campaign_total: bool
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedBundle:
    source_mode: str
    sales: List[NormalizedSalesRow] = field(default_factory=list)
    ads: List[NormalizedAdsRow] = field(default_factory=list)
    stocks: List[NormalizedStockRow] = field(default_factory=list)
    orders_api: List[NormalizedOrderRow] = field(default_factory=list)
    sales_api: List[NormalizedSalesRow] = field(default_factory=list)
    realization_api: List[NormalizedSalesRow] = field(default_factory=list)
    stocks_api: List[NormalizedStockRow] = field(default_factory=list)
    supplier_goods_financial: List[NormalizedSupplierGoodsFinancialRow] = field(default_factory=list)
    debug: Dict[str, Any] = field(default_factory=dict)
