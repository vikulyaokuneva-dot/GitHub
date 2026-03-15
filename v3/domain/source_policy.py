from __future__ import annotations

from typing import Any, Dict, Iterable


SOURCE_API = "api"
SOURCE_SUPPLIER_GOODS = "supplier_goods"
SOURCE_LOCAL_REPORT = "local_report"
SOURCE_FALLBACK = "fallback"
SOURCE_UNKNOWN = "unknown"

_KNOWN_SOURCES = {
    SOURCE_API,
    SOURCE_SUPPLIER_GOODS,
    SOURCE_LOCAL_REPORT,
    SOURCE_FALLBACK,
    SOURCE_UNKNOWN,
}


def build_source_flags(source: str) -> Dict[str, bool]:
    normalized = _normalize_source(source)
    return {
        "api": normalized == SOURCE_API,
        "supplier_goods": normalized == SOURCE_SUPPLIER_GOODS,
        "local_report": normalized == SOURCE_LOCAL_REPORT,
        "fallback": normalized == SOURCE_FALLBACK,
        "unknown": normalized == SOURCE_UNKNOWN,
    }


def _normalize_source(raw_source: Any) -> str:
    value = str(raw_source or "").strip().lower()
    if not value:
        return SOURCE_UNKNOWN
    if value in _KNOWN_SOURCES:
        return value
    if "supplier_goods" in value:
        return SOURCE_SUPPLIER_GOODS
    if "api" in value:
        return SOURCE_API
    if "local" in value:
        return SOURCE_LOCAL_REPORT
    if "fallback" in value:
        return SOURCE_FALLBACK
    if "unknown" in value:
        return SOURCE_UNKNOWN
    return SOURCE_UNKNOWN


def _api_endpoint_success(api_debug: Dict[str, Any], endpoint_names: Iterable[str]) -> bool:
    names = {str(name).strip().lower() for name in endpoint_names}
    endpoints = api_debug.get("endpoints", [])
    if isinstance(endpoints, list):
        for item in endpoints:
            if not isinstance(item, dict):
                continue
            endpoint = str(item.get("endpoint") or "").strip().lower()
            if endpoint in names and bool(item.get("success", False)) and int(item.get("rows_loaded", 0) or 0) > 0:
                return True
    for name in names:
        if int(api_debug.get(f"{name}_rows", 0) or 0) > 0:
            return True
    return False


def _has_local_financial_rows(input_debug: Dict[str, Any]) -> bool:
    discovered = input_debug.get("discovered", {})
    if isinstance(discovered, dict):
        sales_files = discovered.get("sales", [])
        supplier_files = discovered.get("supplier_goods", [])
        if isinstance(sales_files, list) and sales_files:
            return True
        if isinstance(supplier_files, list) and supplier_files:
            return True
    primary_sales_source = str(input_debug.get("primary_sales_source") or "").strip()
    return bool(primary_sales_source)


def _financial_base_source(
    *,
    supplier_goods_daily: Dict[str, Any],
    api_debug: Dict[str, Any],
    input_debug: Dict[str, Any],
    financial_kpi: Dict[str, Any],
    metric_key: str,
) -> str:
    if bool(supplier_goods_daily.get("found", False)):
        return SOURCE_SUPPLIER_GOODS
    if _api_endpoint_success(api_debug, ("realization",)):
        return SOURCE_API
    financial_rows = int(api_debug.get("financial_rows", 0) or 0)
    if financial_rows > 0 and (
        bool(api_debug.get("local_financial_fallback_used", False))
        or _has_local_financial_rows(input_debug)
    ):
        return SOURCE_LOCAL_REPORT
    return SOURCE_UNKNOWN


def choose_orders_count_source(*, daily_kpi: Dict[str, Any]) -> str:
    return _normalize_source(daily_kpi.get("data_source_orders_count") or daily_kpi.get("data_source_orders"))


def choose_buyouts_count_source(*, daily_kpi: Dict[str, Any]) -> str:
    return _normalize_source(daily_kpi.get("data_source_buyouts_count") or daily_kpi.get("data_source_buyouts"))


def choose_revenue_source(
    *,
    supplier_goods_daily: Dict[str, Any],
    api_debug: Dict[str, Any],
    input_debug: Dict[str, Any],
    financial_kpi: Dict[str, Any],
) -> str:
    return _financial_base_source(
        supplier_goods_daily=supplier_goods_daily,
        api_debug=api_debug,
        input_debug=input_debug,
        financial_kpi=financial_kpi,
        metric_key="revenue",
    )


def choose_wb_commission_source(
    *,
    supplier_goods_daily: Dict[str, Any],
    api_debug: Dict[str, Any],
    input_debug: Dict[str, Any],
    financial_kpi: Dict[str, Any],
) -> str:
    return _financial_base_source(
        supplier_goods_daily=supplier_goods_daily,
        api_debug=api_debug,
        input_debug=input_debug,
        financial_kpi=financial_kpi,
        metric_key="wb_commission",
    )


def choose_logistics_source(
    *,
    supplier_goods_daily: Dict[str, Any],
    api_debug: Dict[str, Any],
    input_debug: Dict[str, Any],
    financial_kpi: Dict[str, Any],
) -> str:
    return _financial_base_source(
        supplier_goods_daily=supplier_goods_daily,
        api_debug=api_debug,
        input_debug=input_debug,
        financial_kpi=financial_kpi,
        metric_key="logistics",
    )


def choose_ads_spend_source(
    *,
    api_debug: Dict[str, Any],
    ads_loaded_from_file: bool,
    ads_rows_count: int,
    financial_kpi: Dict[str, Any],
) -> str:
    if _api_endpoint_success(api_debug, ("ads", "ads_legacy")):
        return SOURCE_API
    if ads_loaded_from_file and int(ads_rows_count) > 0:
        return SOURCE_LOCAL_REPORT
    if abs(float(financial_kpi.get("ads_spend", 0.0) or 0.0)) > 1e-9:
        return SOURCE_FALLBACK
    return SOURCE_UNKNOWN


def resolve_source_policy(
    *,
    source_mode: str,
    daily_kpi: Dict[str, Any],
    financial_kpi: Dict[str, Any],
    supplier_goods_daily: Dict[str, Any],
    api_debug: Dict[str, Any],
    input_debug: Dict[str, Any],
    ads_loaded_from_file: bool,
    ads_rows_count: int,
) -> Dict[str, Any]:
    _ = source_mode
    safe_daily_kpi = daily_kpi if isinstance(daily_kpi, dict) else {}
    safe_financial_kpi = financial_kpi if isinstance(financial_kpi, dict) else {}
    safe_supplier_goods = supplier_goods_daily if isinstance(supplier_goods_daily, dict) else {}
    safe_api_debug = api_debug if isinstance(api_debug, dict) else {}
    safe_input_debug = input_debug if isinstance(input_debug, dict) else {}

    revenue_source = choose_revenue_source(
        supplier_goods_daily=safe_supplier_goods,
        api_debug=safe_api_debug,
        input_debug=safe_input_debug,
        financial_kpi=safe_financial_kpi,
    )

    sources = {
        "orders_count": choose_orders_count_source(daily_kpi=safe_daily_kpi),
        "buyouts_count": choose_buyouts_count_source(daily_kpi=safe_daily_kpi),
        # Keep amount/storage source keys for compatibility with current entry.py payload.
        "orders_amount": _normalize_source(safe_daily_kpi.get("data_source_orders_amount")),
        "buyouts_amount": _normalize_source(safe_daily_kpi.get("data_source_buyouts_amount")),
        "revenue": revenue_source,
        "wb_commission": choose_wb_commission_source(
            supplier_goods_daily=safe_supplier_goods,
            api_debug=safe_api_debug,
            input_debug=safe_input_debug,
            financial_kpi=safe_financial_kpi,
        ),
        "logistics": choose_logistics_source(
            supplier_goods_daily=safe_supplier_goods,
            api_debug=safe_api_debug,
            input_debug=safe_input_debug,
            financial_kpi=safe_financial_kpi,
        ),
        "storage": _financial_base_source(
            supplier_goods_daily=safe_supplier_goods,
            api_debug=safe_api_debug,
            input_debug=safe_input_debug,
            financial_kpi=safe_financial_kpi,
            metric_key="storage",
        ),
        "ads_spend": choose_ads_spend_source(
            api_debug=safe_api_debug,
            ads_loaded_from_file=bool(ads_loaded_from_file),
            ads_rows_count=int(ads_rows_count),
            financial_kpi=safe_financial_kpi,
        ),
    }
    source_flags = {metric: build_source_flags(source) for metric, source in sources.items()}
    return {
        "policy_version": "wb_source_policy_v1",
        "sources": sources,
        "source_flags": source_flags,
    }




