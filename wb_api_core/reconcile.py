from __future__ import annotations

from typing import Any, Dict, List

SOURCE_RULES = {
    "cabinet_commerce_daily": "sales_funnel_api",
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


def _warning(code: str, message: str) -> Dict[str, str]:
    return {"code": code, "message": message}


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

    cabinet_rows = _filter_rows_by_day(cabinet_all, target_date)
    finance_rows, finance_actual_date, finance_date_aligned = _select_finance_rows(finance_all, target_date)
    orders_rows_before_dedupe = _filter_rows_by_day(orders_all, target_date)
    orders_rows = _dedupe_orders_rows(orders_rows_before_dedupe)
    sales_rows = _filter_rows_by_day(sales_all, target_date)

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

    if finance_available:
        finance_final_daily = {
            "source": SOURCE_RULES["finance_final_daily"],
            "available": True,
            "target_date": target_date,
            "actual_date": finance_actual_date,
            "date_aligned": finance_date_aligned,
            "gross_revenue": _safe_total(finance_rows, "gross_revenue"),
            "seller_payout": _safe_total(finance_rows, "seller_payout"),
            "wb_commission": _safe_total(finance_rows, "wb_commission"),
            "logistics": _safe_total(finance_rows, "logistics"),
            "storage": _safe_total(finance_rows, "storage"),
            "penalties": _safe_total(finance_rows, "penalties"),
            "deductions": _safe_total(finance_rows, "deductions"),
            "acquiring": _safe_total(finance_rows, "acquiring"),
            "tax": _safe_total(finance_rows, "tax"),
            "rows": finance_rows,
        }
    else:
        finance_final_daily = {
            "source": SOURCE_RULES["finance_final_daily"],
            "available": False,
            "target_date": target_date,
            "actual_date": None,
            "date_aligned": None,
            "gross_revenue": None,
            "seller_payout": None,
            "wb_commission": None,
            "logistics": None,
            "storage": None,
            "penalties": None,
            "deductions": None,
            "acquiring": None,
            "tax": None,
            "rows": [],
        }

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
            "target_date": target_date,
            "total_units": _safe_total(stocks_all, "stock") if stocks_available else None,
            "rows": stocks_all,
        },
    }

    return {
        "source_rules": dict(SOURCE_RULES),
        "warnings": warnings,
        "cabinet_commerce_daily": cabinet_commerce_daily,
        "finance_final_daily": finance_final_daily,
        "live_operational": live_operational,
        "counts": {
            "reconciled": {
                "cabinet_commerce": len(cabinet_rows),
                "finance_final": len(finance_final_daily.get("rows", [])),
                "orders": len(orders_rows),
                "sales": len(sales_rows),
                "stocks": len(stocks_all),
            }
        },
    }
