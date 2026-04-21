from __future__ import annotations

from typing import Any, Dict, List

SOURCE_RULES = {
    "orders_count": "orders_api",
    "orders_amount": "orders_api",
    "buyouts_count": "sales_api",
    "buyouts_amount": "sales_api",
    "financial": "finance_api",
    "stock.total_units": "stocks_api",
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
    orders_debug = (raw_bundle.get("orders") or {}).get("debug", {})
    sales_debug = (raw_bundle.get("sales") or {}).get("debug", {})
    stocks_debug = (raw_bundle.get("stocks") or {}).get("debug", {})
    finance_debug = (raw_bundle.get("realization") or {}).get("debug", {})

    orders_all = list(normalized_bundle.get("orders_rows", []))
    sales_all = list(normalized_bundle.get("sales_rows", []))
    stocks_all = list(normalized_bundle.get("stocks_rows", []))
    finance_all = list(normalized_bundle.get("realization_rows", []))

    orders_rows = _filter_rows_by_day(orders_all, target_date)
    sales_rows = _filter_rows_by_day(sales_all, target_date)
    finance_rows, finance_actual_date, finance_date_aligned = _select_finance_rows(finance_all, target_date)

    orders_available = bool(orders_debug.get("success", False))
    sales_available = bool(sales_debug.get("success", False))
    stocks_available = bool(stocks_debug.get("success", False))
    finance_available = bool(finance_debug.get("success", False))

    warnings: List[Dict[str, str]] = []
    if not orders_available:
        warnings.append(_warning("orders_api_unavailable", str(orders_debug.get("error_text") or "orders API unavailable")))
    if not sales_available:
        warnings.append(_warning("sales_api_unavailable", str(sales_debug.get("error_text") or "sales API unavailable")))
    if not stocks_available:
        warnings.append(_warning("stocks_api_unavailable", str(stocks_debug.get("error_text") or "stocks API unavailable")))
    if not finance_available:
        warnings.append(_warning("finance_api_unavailable", str(finance_debug.get("error_text") or "finance API unavailable")))
    if finance_available and finance_actual_date and finance_actual_date != target_date:
        warnings.append(
            _warning(
                "financial_date_misaligned",
                f"Financial rows selected from {finance_actual_date} instead of {target_date}.",
            )
        )

    orders_count = _safe_total(orders_rows, "quantity") if orders_available else None
    orders_amount = _safe_total(orders_rows, "amount") if orders_available else None
    buyouts_count = _safe_total(sales_rows, "quantity") if sales_available else None
    buyouts_amount = _safe_total(sales_rows, "amount") if sales_available else None
    stock_total_units = _safe_total(stocks_all, "stock") if stocks_available else None

    if finance_available:
        financial = {
            "source": SOURCE_RULES["financial"],
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
            "tax": _safe_total(finance_rows, "tax"),
            "net_profit": None,
            "margin_pct": None,
            "finality": "partial_without_cogs",
            "rows": finance_rows,
        }
    else:
        financial = {
            "source": SOURCE_RULES["financial"],
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
            "tax": None,
            "net_profit": None,
            "margin_pct": None,
            "finality": "missing",
            "rows": [],
        }

    return {
        "source_rules": dict(SOURCE_RULES),
        "warnings": warnings,
        "orders": {
            "source": SOURCE_RULES["orders_count"],
            "available": orders_available,
            "count": orders_count,
            "amount": orders_amount,
            "rows": orders_rows,
        },
        "sales": {
            "source": SOURCE_RULES["buyouts_count"],
            "available": sales_available,
            "count": buyouts_count,
            "amount": buyouts_amount,
            "rows": sales_rows,
        },
        "financial": financial,
        "stock": {
            "source": SOURCE_RULES["stock.total_units"],
            "available": stocks_available,
            "total_units": stock_total_units,
            "rows": stocks_all,
        },
        "counts": {
            "reconciled": {
                "orders": len(orders_rows),
                "sales": len(sales_rows),
                "realization": len(financial.get("rows", [])),
                "stocks": len(stocks_all),
            }
        },
    }
