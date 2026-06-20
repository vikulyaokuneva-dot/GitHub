from __future__ import annotations

from typing import Any, Dict, List

SOURCE_RULES = {
    "cabinet_commerce_daily": "sales_funnel_api",
    "funnel_daily": "sales_funnel_api",
    "finance_final_daily": "finance_detailed_api",
    "live_operational.orders": "orders_api",
    "live_operational.sales": "sales_api",
    "live_operational.stocks": "stocks_api",
}


def _safe_total(rows: List[Dict[str, Any]], field: str) -> float:
    total = 0.0
    for row in rows:
        try:
            total += float(row.get(field, 0.0) or 0.0)
        except Exception:
            continue
    return round(total, 2)


def _safe_total_if(rows: List[Dict[str, Any]], field: str, include_flag: str) -> float:
    total = 0.0
    for row in rows:
        if not bool(row.get(include_flag, False)):
            continue
        try:
            total += float(row.get(field, 0.0) or 0.0)
        except Exception:
            continue
    return round(total, 2)


def _safe_total_if_present(rows: List[Dict[str, Any]], field: str, include_flag: str) -> float | None:
    total = 0.0
    seen = False
    for row in rows:
        if not bool(row.get(include_flag, False)):
            continue
        value = row.get(field)
        if value is None:
            continue
        try:
            total += float(value)
            seen = True
        except Exception:
            continue
    return round(total, 2) if seen else None


def _filter_rows_by_day(rows: List[Dict[str, Any]], target_date: str) -> List[Dict[str, Any]]:
    return [row for row in rows if isinstance(row, dict) and str(row.get("date") or "") == target_date]


def _orders_row_sort_key(row: Dict[str, Any]) -> tuple[str, int]:
    last_change = str(row.get("last_change_date") or "").strip()
    try:
        raw_index = int(row.get("_raw_row_index", -1) or -1)
    except Exception:
        raw_index = -1
    return last_change, raw_index


def _dedupe_orders_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    selected: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        order_id = str(row.get("order_id") or "").strip()
        key = f"order:{order_id}" if order_id else f"raw:{row.get('_raw_row_index')}"
        current = selected.get(key)
        if current is None or _orders_row_sort_key(row) >= _orders_row_sort_key(current):
            selected[key] = row
    return sorted(
        selected.values(),
        key=lambda row: int(row.get("_raw_row_index", 0) or 0),
    )


def _select_finance_rows(rows: List[Dict[str, Any]], target_date: str) -> tuple[List[Dict[str, Any]], str | None, bool | None]:
    exact_rows = _filter_rows_by_day(rows, target_date)
    if exact_rows:
        return exact_rows, target_date, True
    dates = sorted({str(row.get("date") or "") for row in rows if str(row.get("date") or "")})
    if not dates:
        return [], None, None
    actual_date = dates[-1]
    selected = [row for row in rows if str(row.get("date") or "") == actual_date]
    return selected, actual_date, False


def _select_stock_rows(rows: List[Dict[str, Any]], target_date: str) -> tuple[List[Dict[str, Any]], str]:
    stock_dates = sorted({str(row.get("date") or "") for row in rows if isinstance(row, dict) and str(row.get("date") or "")})
    if stock_dates:
        actual_date = stock_dates[-1]
    else:
        actual_date = str(target_date or "")
    selected_rows: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        if actual_date:
            item["date"] = actual_date
        selected_rows.append(item)
    return selected_rows, actual_date


def _warning(code: str, message: str) -> Dict[str, str]:
    return {"code": code, "message": message}


def _calculate_funnel_rate(numerator: float | None, denominator: float | None) -> float | None:
    """Calculate percentage rate for funnel conversion (e.g., cart/open, order/cart)."""
    if denominator and denominator > 0 and numerator is not None:
        return round((numerator / denominator) * 100, 2)
    return None


def _determine_funnel_status(
    open_count: float | None,
    cart_count: float | None,
    orders_count: float | None,
    buyouts_count: float | None,
) -> str:
    """Determine overall funnel status based on data availability."""
    has_upper = bool(open_count and open_count > 0) or bool(cart_count and cart_count > 0)
    has_lower = bool(orders_count and orders_count > 0) or bool(buyouts_count and buyouts_count > 0)
    
    if has_upper and has_lower:
        return "ok"
    elif has_upper or has_lower:
        return "partial"
    else:
        return "unavailable"


def reconcile_bundle(
    *,
    raw_bundle: Dict[str, Any],
    normalized_bundle: Dict[str, Any],
    target_date: str,
) -> Dict[str, Any]:
    cabinet_debug = (raw_bundle.get("cabinet_commerce") or {}).get("debug", {})
    finance_debug = (raw_bundle.get("finance_final") or {}).get("debug", {})
    orders_debug = (raw_bundle.get("orders") or {}).get("debug", {})
    sales_debug = (raw_bundle.get("sales") or {}).get("debug", {})
    stocks_debug = (raw_bundle.get("stocks") or {}).get("debug", {})

    cabinet_all = list(normalized_bundle.get("cabinet_commerce_rows", []))
    finance_all = list(normalized_bundle.get("finance_final_rows", []))
    orders_all = list(normalized_bundle.get("orders_rows", []))
    sales_all = list(normalized_bundle.get("sales_rows", []))
    stocks_all = list(normalized_bundle.get("stocks_rows", []))
    ads_all = list(normalized_bundle.get("ads_rows", []))

    cabinet_rows = _filter_rows_by_day(cabinet_all, target_date)
    finance_rows, finance_actual_date, finance_date_aligned = _select_finance_rows(finance_all, target_date)
    orders_rows_before_dedupe = _filter_rows_by_day(orders_all, target_date)
    orders_rows = _dedupe_orders_rows(orders_rows_before_dedupe)
    sales_rows = _filter_rows_by_day(sales_all, target_date)
    stock_rows, stock_actual_date = _select_stock_rows(stocks_all, target_date)
    ads_rows = _filter_rows_by_day(ads_all, target_date)

    cabinet_available = bool(cabinet_debug.get("success", False))
    finance_available = bool(finance_debug.get("success", False))
    orders_available = bool(orders_debug.get("success", False))
    sales_available = bool(sales_debug.get("success", False))
    stocks_available = bool(stocks_debug.get("success", False))

    warnings: List[Dict[str, str]] = []
    if not cabinet_available:
        warnings.append(
            _warning(
                "cabinet_commerce_api_unavailable",
                str(cabinet_debug.get("error_text") or "cabinet commerce API unavailable"),
            )
        )
    if not finance_available:
        warnings.append(
            _warning(
                "finance_final_api_unavailable",
                str(finance_debug.get("error_text") or "finance final API unavailable"),
            )
        )
    if not orders_available:
        warnings.append(_warning("orders_api_unavailable", str(orders_debug.get("error_text") or "orders API unavailable")))
    if not sales_available:
        warnings.append(_warning("sales_api_unavailable", str(sales_debug.get("error_text") or "sales API unavailable")))
    if not stocks_available:
        warnings.append(_warning("stocks_api_unavailable", str(stocks_debug.get("error_text") or "stocks API unavailable")))
    if finance_available and finance_actual_date and finance_actual_date != target_date:
        warnings.append(
            _warning(
                "finance_final_date_misaligned",
                f"Finance rows selected from {finance_actual_date} instead of {target_date}.",
            )
        )
    cabinet_commerce_daily = {
        "source": SOURCE_RULES["cabinet_commerce_daily"],
        "available": cabinet_available,
        "target_date": target_date,
        "orders_count": _safe_total(cabinet_rows, "order_count") if cabinet_available else None,
        "orders_amount": _safe_total(cabinet_rows, "order_sum") if cabinet_available else None,
        "buyouts_count": _safe_total(cabinet_rows, "buyout_count") if cabinet_available else None,
        "buyouts_amount": _safe_total(cabinet_rows, "buyout_sum") if cabinet_available else None,
        "rows": cabinet_rows,
    }

    # Build funnel_daily from same cabinet_rows (without rows field to avoid duplication)
    funnel_open_count = _safe_total(cabinet_rows, "open_count") if cabinet_available else None
    funnel_cart_count = _safe_total(cabinet_rows, "cart_count") if cabinet_available else None
    funnel_orders_count = _safe_total(cabinet_rows, "order_count") if cabinet_available else None
    funnel_orders_amount = _safe_total(cabinet_rows, "order_sum") if cabinet_available else None
    funnel_buyouts_count = _safe_total(cabinet_rows, "buyout_count") if cabinet_available else None
    funnel_buyouts_amount = _safe_total(cabinet_rows, "buyout_sum") if cabinet_available else None

    funnel_daily = {
        "source": SOURCE_RULES["funnel_daily"],
        "owner_block": "funnel_daily",
        "available": cabinet_available,
        "target_date": target_date,
        "open_count": funnel_open_count,
        "cart_count": funnel_cart_count,
        "orders_count": funnel_orders_count,
        "orders_amount": funnel_orders_amount,
        "buyouts_count": funnel_buyouts_count,
        "buyouts_amount": funnel_buyouts_amount,
        "open_to_cart_rate": _calculate_funnel_rate(funnel_cart_count, funnel_open_count),
        "cart_to_order_rate": _calculate_funnel_rate(funnel_orders_count, funnel_cart_count),
        "order_to_buyout_rate": _calculate_funnel_rate(funnel_buyouts_count, funnel_orders_count),
        "upper_funnel_status": "ok" if (funnel_open_count and funnel_open_count > 0) or (funnel_cart_count and funnel_cart_count > 0) else "unavailable",
        "lower_funnel_status": "ok" if (funnel_orders_count and funnel_orders_count > 0) or (funnel_buyouts_count and funnel_buyouts_count > 0) else "unavailable",
        "status": _determine_funnel_status(funnel_open_count, funnel_cart_count, funnel_orders_count, funnel_buyouts_count),
    }


    if finance_available:
        finance_effective_rows = [row for row in finance_rows if bool(row.get("include_in_totals", False))]
        logistics_amount = _safe_total_if_present(finance_rows, "logistics_amount", "include_logistics")
        finance_final_daily = {
            "source": SOURCE_RULES["finance_final_daily"],
            "available": True,
            "target_date": target_date,
            "actual_date": finance_actual_date,
            "date_aligned": finance_date_aligned,
            "gross_revenue": _safe_total_if(finance_rows, "gross_revenue", "include_gross_revenue"),
            "sale_customer_revenue": _safe_total_if_present(
                finance_rows,
                "sale_customer_amount",
                "include_sale_customer_amount",
            ),
            "wb_realized_revenue": _safe_total_if_present(finance_rows, "wb_realized_revenue", "include_gross_revenue"),
            "realized_sales_qty": _safe_total_if_present(finance_rows, "realized_sales_qty", "include_realized_sales"),
            "realized_sales_revenue": _safe_total_if_present(finance_rows, "realized_sales_revenue", "include_realized_sales"),
            "seller_payout": _safe_total_if(finance_rows, "seller_payout", "include_seller_payout"),
            "wb_commission": _safe_total_if(finance_rows, "wb_commission", "include_wb_commission"),
            "deliveries_qty": _safe_total_if_present(finance_rows, "deliveries_qty", "include_deliveries_qty"),
            "returns_qty": _safe_total_if_present(finance_rows, "returns_qty", "include_returns_qty"),
            "logistics": logistics_amount,
            "logistics_amount": logistics_amount,
            "storage": _safe_total_if(finance_rows, "storage", "include_storage"),
            "penalties": _safe_total_if(finance_rows, "penalties", "include_penalties"),
            "deductions": _safe_total_if(finance_rows, "deductions", "include_deductions"),
            "acquiring": _safe_total_if(finance_rows, "acquiring", "include_acquiring"),
            "tax": _safe_total_if(finance_rows, "tax", "include_tax"),
            "rows": finance_rows,
            "diagnostics": {
                "selected_rows_count": len(finance_rows),
                "effective_rows_count": len(finance_effective_rows),
                "technical_zero_rows_count": len([row for row in finance_rows if bool(row.get("is_zero_technical", False))]),
            },
        }
    else:
        finance_final_daily = {
            "source": SOURCE_RULES["finance_final_daily"],
            "available": False,
            "target_date": target_date,
            "actual_date": None,
            "date_aligned": None,
            "gross_revenue": None,
            "sale_customer_revenue": None,
            "wb_realized_revenue": None,
            "realized_sales_qty": None,
            "realized_sales_revenue": None,
            "seller_payout": None,
            "wb_commission": None,
            "deliveries_qty": None,
            "returns_qty": None,
            "logistics": None,
            "logistics_amount": None,
            "storage": None,
            "penalties": None,
            "deductions": None,
            "acquiring": None,
            "tax": None,
            "rows": [],
            "diagnostics": {
                "selected_rows_count": 0,
                "effective_rows_count": 0,
                "technical_zero_rows_count": 0,
            },
        }

    ads_available = bool((raw_bundle.get("ads") or {}).get("debug", {}).get("success", False))

    live_operational = {
        "orders": {
            "source": SOURCE_RULES["live_operational.orders"],
            "available": orders_available,
            "target_date": target_date,
            "count": float(len(orders_rows)) if orders_available else None,
            "amount": _safe_total(orders_rows, "amount") if orders_available else None,
            "rows": orders_rows,
            "diagnostics": {
                "target_day_rows_before_dedupe": len(orders_rows_before_dedupe),
                "target_day_rows_after_dedupe": len(orders_rows),
                "target_day_quantity_sum": _safe_total(orders_rows_before_dedupe, "quantity") if orders_available else None,
                "count_formula": "len(unique order rows by order_id)",
                "amount_formula": "sum(amount) over the same unique order rows",
            },
        },
        "sales": {
            "source": SOURCE_RULES["live_operational.sales"],
            "available": sales_available,
            "target_date": target_date,
            "count": _safe_total(sales_rows, "quantity") if sales_available else None,
            "amount": _safe_total(sales_rows, "amount") if sales_available else None,
            "rows": sales_rows,
        },
        "stocks": {
            "source": SOURCE_RULES["live_operational.stocks"],
            "available": stocks_available,
            "snapshot_kind": "live_snapshot",
            "operational_date_reference": target_date,
            "snapshot_date": stock_actual_date if stocks_available else None,
            "total_units": _safe_total(stock_rows, "stock") if stocks_available else None,
            "rows": stock_rows,
        },
        "ads": {
            "source": "ads_api",
            "available": ads_available,
            "target_date": target_date,
            "count": len(ads_rows),
            "ads_spend_total": _safe_total(ads_rows, "ads_spend") if ads_available else 0.0,
            "rows": ads_rows,
        },
    }

    return {
        "source_rules": dict(SOURCE_RULES),
        "warnings": warnings,
        "cabinet_commerce_daily": cabinet_commerce_daily,
        "funnel_daily": funnel_daily,
        "finance_final_daily": finance_final_daily,
        "live_operational": live_operational,
        "counts": {
            "reconciled": {
                "cabinet_commerce": len(cabinet_rows),
                "finance_final": len(finance_final_daily.get("rows", [])),
                "orders": len(orders_rows),
                "sales": len(sales_rows),
                "stocks": len(stock_rows),
                "ads": len(ads_rows),
            }
        },
    }
