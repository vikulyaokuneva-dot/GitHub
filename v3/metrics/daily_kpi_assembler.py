from __future__ import annotations

from typing import Any, Dict, List

from ..daily_kpi_resolver import (
    DAILY_SOURCE_FALLBACK,
    DAILY_SOURCE_ORDERS_API,
    DAILY_SOURCE_REALIZATION_API,
    DAILY_SOURCE_SALES_API,
)
from ..domain.source_policy import SOURCE_UNKNOWN
from ..domain.source_policy import resolve_source_policy


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def assemble_daily_kpi(
    *,
    daily_kpi: Dict[str, Any],
    totals: Dict[str, Any],
    financial_kpi: Dict[str, Any],
    supplier_goods_daily: Dict[str, Any],
    api_debug: Dict[str, Any],
    input_debug: Dict[str, Any],
    source_mode: str,
    ads_loaded_from_file: bool,
    ads_rows_count: int,
) -> Dict[str, Any]:
    safe_daily_kpi = daily_kpi if isinstance(daily_kpi, dict) else {}
    safe_totals = totals if isinstance(totals, dict) else {}
    safe_financial_kpi = financial_kpi if isinstance(financial_kpi, dict) else {}
    safe_supplier = supplier_goods_daily if isinstance(supplier_goods_daily, dict) else {}
    safe_api_debug = api_debug if isinstance(api_debug, dict) else {}
    safe_input_debug = input_debug if isinstance(input_debug, dict) else {}

    source_policy = resolve_source_policy(
        source_mode=source_mode,
        daily_kpi=safe_daily_kpi,
        financial_kpi=safe_financial_kpi,
        supplier_goods_daily=safe_supplier,
        api_debug=safe_api_debug,
        input_debug=safe_input_debug,
        ads_loaded_from_file=bool(ads_loaded_from_file),
        ads_rows_count=int(ads_rows_count),
    )
    source_map = source_policy.get("sources", {}) if isinstance(source_policy, dict) else {}
    if not isinstance(source_map, dict):
        source_map = {}
    source_flags = source_policy.get("source_flags", {}) if isinstance(source_policy, dict) else {}
    if not isinstance(source_flags, dict):
        source_flags = {}

    data_sources = {
        "orders_count": str(source_map.get("orders_count") or SOURCE_UNKNOWN),
        "buyouts_count": str(source_map.get("buyouts_count") or SOURCE_UNKNOWN),
        "orders_amount": str(source_map.get("orders_amount") or SOURCE_UNKNOWN),
        "buyouts_amount": str(source_map.get("buyouts_amount") or SOURCE_UNKNOWN),
        "revenue": str(source_map.get("revenue") or SOURCE_UNKNOWN),
        "wb_commission": str(source_map.get("wb_commission") or SOURCE_UNKNOWN),
        "logistics": str(source_map.get("logistics") or SOURCE_UNKNOWN),
        "storage": str(source_map.get("storage") or SOURCE_UNKNOWN),
        "ads_spend": str(source_map.get("ads_spend") or SOURCE_UNKNOWN),
    }

    orders_count_confirmed = bool(safe_daily_kpi.get("orders_count_confirmed", False))
    buyouts_count_confirmed = bool(safe_daily_kpi.get("buyouts_count_confirmed", False))
    confirmed_orders_total = int(safe_daily_kpi.get("daily_orders_count", 0) or 0) if orders_count_confirmed else 0
    confirmed_buyouts_total = int(safe_daily_kpi.get("daily_buyouts_count", 0) or 0) if buyouts_count_confirmed else 0

    safe_daily_kpi["data_source_orders_count"] = data_sources["orders_count"]
    safe_daily_kpi["data_source_buyouts_count"] = data_sources["buyouts_count"]
    safe_daily_kpi["data_source_orders_amount"] = data_sources["orders_amount"]
    safe_daily_kpi["data_source_buyouts_amount"] = data_sources["buyouts_amount"]
    safe_daily_kpi["data_source_orders"] = str(safe_daily_kpi.get("data_source_orders_count") or SOURCE_UNKNOWN)
    safe_daily_kpi["data_source_buyouts"] = str(safe_daily_kpi.get("data_source_buyouts_count") or SOURCE_UNKNOWN)

    safe_totals["orders"] = int(confirmed_orders_total)
    safe_totals["buys"] = int(confirmed_buyouts_total)
    safe_totals["orders_confirmed"] = bool(orders_count_confirmed)
    safe_totals["buys_confirmed"] = bool(buyouts_count_confirmed)
    safe_totals["data_source_orders"] = data_sources["orders_count"]
    safe_totals["data_source_buys"] = data_sources["buyouts_count"]
    safe_totals["orders_unconfirmed"] = not bool(orders_count_confirmed)
    safe_totals["buys_unconfirmed"] = not bool(buyouts_count_confirmed)

    sales_activity_qty_hint = int(safe_totals.get("sales_activity_qty", 0) or 0)
    item_qty_hint = int(safe_totals.get("item_qty", sales_activity_qty_hint) or 0)
    sku_activity_count = int(safe_totals.get("sku_activity_count", 0) or 0)

    commerce_activity = {
        "item_qty": int(item_qty_hint),
        "sales_activity_qty": int(sales_activity_qty_hint),
        "sku_activity_count": int(sku_activity_count),
        "confirmed_daily_orders_count": int(confirmed_orders_total),
        "confirmed_daily_buyouts_count": int(confirmed_buyouts_total),
        "orders_gap_vs_activity": int(sales_activity_qty_hint - confirmed_orders_total),
        "buyouts_gap_vs_activity": int(sales_activity_qty_hint - confirmed_buyouts_total),
    }

    commerce_kpi = {
        "daily_orders_count": int(safe_daily_kpi.get("daily_orders_count", 0) or 0),
        "daily_orders_amount": round(_safe_float(safe_daily_kpi.get("daily_orders_amount", 0.0)), 2),
        "daily_buyouts_count": int(safe_daily_kpi.get("daily_buyouts_count", 0) or 0),
        "daily_buyouts_amount": round(_safe_float(safe_daily_kpi.get("daily_buyouts_amount", 0.0)), 2),
        "avg_check": round(
            (
                _safe_float(safe_daily_kpi.get("daily_buyouts_amount", 0.0))
                / _safe_float(safe_daily_kpi.get("daily_buyouts_count", 0))
            )
            if _safe_float(safe_daily_kpi.get("daily_buyouts_count", 0)) > 0
            else 0.0,
            2,
        ),
        "data_source_orders_count": data_sources["orders_count"],
        "data_source_orders_amount": data_sources["orders_amount"],
        "data_source_buyouts_count": data_sources["buyouts_count"],
        "data_source_buyouts_amount": data_sources["buyouts_amount"],
        "orders_count_confirmed": bool(safe_daily_kpi.get("orders_count_confirmed", False)),
        "buyouts_count_confirmed": bool(safe_daily_kpi.get("buyouts_count_confirmed", False)),
        "orders_amount_confirmed": bool(safe_daily_kpi.get("orders_amount_confirmed", False)),
        "buyouts_amount_confirmed": bool(safe_daily_kpi.get("buyouts_amount_confirmed", False)),
    }

    warning_additions: List[Dict[str, Any]] = []
    orders_sources = {data_sources["orders_count"], data_sources["orders_amount"]}
    buyouts_sources = {data_sources["buyouts_count"], data_sources["buyouts_amount"]}
    kpi_sources = {source for source in (orders_sources | buyouts_sources) if source}
    api_sources = {
        DAILY_SOURCE_ORDERS_API,
        DAILY_SOURCE_SALES_API,
        DAILY_SOURCE_REALIZATION_API,
    }
    if any(source in api_sources for source in kpi_sources):
        warning_additions.append(
            {
                "code": "daily_kpi_fallback_used",
                "message": "Supplier goods report not found, using API fallback.",
            }
        )
    if DAILY_SOURCE_FALLBACK in kpi_sources:
        warning_additions.append(
            {
                "code": "weak_kpi_source",
                "message": "Daily KPI derived from metrics totals fallback.",
            }
        )
    if bool(safe_daily_kpi.get("quantity_fallback_blocked", False)):
        warning_additions.append(
            {
                "code": "quantity_orders_fallback_blocked",
                "message": "quantity column cannot be used as orders_count fallback",
            }
        )
    if (
        (
            data_sources["orders_count"] == SOURCE_UNKNOWN
            or data_sources["buyouts_count"] == SOURCE_UNKNOWN
        )
        and sales_activity_qty_hint > 0
    ):
        warning_additions.append(
            {
                "code": "totals_orders_buys_not_confirmed",
                "message": (
                    "totals orders/buys not confirmed; keeping totals.orders/totals.buys at 0 "
                    f"while sales_activity_qty={sales_activity_qty_hint}"
                ),
            }
        )

    orders_unknown_reason = str(safe_daily_kpi.get("orders_count_unknown_reason") or "").strip()
    buyouts_unknown_reason = str(safe_daily_kpi.get("buyouts_count_unknown_reason") or "").strip()
    if data_sources["orders_count"] == SOURCE_UNKNOWN:
        warning_additions.append(
            {
                "code": "daily_orders_count_unknown",
                "message": (
                    f"daily_orders_count is unknown: {orders_unknown_reason}"
                    if orders_unknown_reason
                    else "daily_orders_count is unknown: no confirmed source"
                ),
            }
        )
    if data_sources["buyouts_count"] == SOURCE_UNKNOWN:
        warning_additions.append(
            {
                "code": "daily_buyouts_count_unknown",
                "message": (
                    f"daily_buyouts_count is unknown: {buyouts_unknown_reason}"
                    if buyouts_unknown_reason
                    else "daily_buyouts_count is unknown: no confirmed source"
                ),
            }
        )
    if data_sources["orders_count"] == SOURCE_UNKNOWN and data_sources["buyouts_count"] == SOURCE_UNKNOWN:
        warning_additions.append(
            {
                "code": "daily_kpi_unknown",
                "message": "daily orders/buyouts counts remain unknown because no confirmed source is available",
            }
        )

    return {
        "daily_kpi": safe_daily_kpi,
        "totals": safe_totals,
        "source_policy": source_policy if isinstance(source_policy, dict) else {},
        "source_map": source_map,
        "source_flags": source_flags,
        "data_sources": data_sources,
        "commerce_activity": commerce_activity,
        "commerce_kpi": commerce_kpi,
        "warning_additions": warning_additions,
        "derived": {
            "orders_count_confirmed": bool(orders_count_confirmed),
            "buyouts_count_confirmed": bool(buyouts_count_confirmed),
            "confirmed_orders_total": int(confirmed_orders_total),
            "confirmed_buyouts_total": int(confirmed_buyouts_total),
            "item_qty_hint": int(item_qty_hint),
            "sales_activity_qty_hint": int(sales_activity_qty_hint),
            "sku_activity_count": int(sku_activity_count),
        },
    }
