from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class RawIngestionBundle:
    source_mode: str
    sales_rows: List[Dict[str, Any]] = field(default_factory=list)
    ads_rows: List[Dict[str, Any]] = field(default_factory=list)
    stocks_rows: List[Dict[str, Any]] = field(default_factory=list)
    api_orders_rows: List[Dict[str, Any]] = field(default_factory=list)
    api_sales_rows: List[Dict[str, Any]] = field(default_factory=list)
    api_realization_rows: List[Dict[str, Any]] = field(default_factory=list)
    api_stocks_rows: List[Dict[str, Any]] = field(default_factory=list)
    supplier_goods_daily: Dict[str, Any] = field(default_factory=dict)
    discovered_files: Dict[str, List[str]] = field(default_factory=dict)
    input_debug: Dict[str, Any] = field(default_factory=dict)
    api_debug: Dict[str, Any] = field(default_factory=dict)


def build_raw_bundle(
    *,
    source_mode: str,
    sales_rows: List[Dict[str, Any]],
    ads_rows: List[Dict[str, Any]],
    stocks_rows: List[Dict[str, Any]],
    api_orders_rows: List[Dict[str, Any]],
    api_sales_rows: List[Dict[str, Any]],
    api_realization_rows: List[Dict[str, Any]],
    api_stocks_rows: List[Dict[str, Any]],
    supplier_goods_daily: Dict[str, Any],
    discovered_files: Dict[str, List[str]],
    input_debug: Dict[str, Any],
    api_debug: Dict[str, Any],
) -> RawIngestionBundle:
    return RawIngestionBundle(
        source_mode=str(source_mode or ""),
        sales_rows=list(sales_rows or []),
        ads_rows=list(ads_rows or []),
        stocks_rows=list(stocks_rows or []),
        api_orders_rows=list(api_orders_rows or []),
        api_sales_rows=list(api_sales_rows or []),
        api_realization_rows=list(api_realization_rows or []),
        api_stocks_rows=list(api_stocks_rows or []),
        supplier_goods_daily=dict(supplier_goods_daily or {}),
        discovered_files=dict(discovered_files or {}),
        input_debug=dict(input_debug or {}),
        api_debug=dict(api_debug or {}),
    )
