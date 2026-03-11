from __future__ import annotations

from typing import Any, Dict, List

DAILY_SOURCE_SUPPLIER_GOODS = "supplier_goods"
DAILY_SOURCE_ORDERS_API = "orders_api"
DAILY_SOURCE_SALES_API = "sales_api"
DAILY_SOURCE_REALIZATION_API = "realization_api"
DAILY_SOURCE_FALLBACK = "metrics_totals_fallback"


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _row_price_fallback(row: Dict[str, Any]) -> float:
    if not isinstance(row, dict):
        return 0.0
    return _safe_float(
        row.get("price", row.get("revenue", row.get("totalPrice", row.get("priceWithDisc", row.get("finishedPrice", 0.0)))))
    )


def _rows_count(rows: List[Dict[str, Any]]) -> int:
    return len([row for row in rows if isinstance(row, dict)])


def _rows_price_sum(rows: List[Dict[str, Any]]) -> float:
    return round(sum(_row_price_fallback(row) for row in rows if isinstance(row, dict)), 2)


def resolve_daily_kpi(
    totals: Dict[str, Any],
    supplier_goods_daily: Dict[str, Any],
    api_orders_rows: List[Dict[str, Any]],
    api_sales_rows: List[Dict[str, Any]],
    api_realization_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    fallback_orders_count = int(round(_safe_float(totals.get("orders", 0))))
    fallback_orders_amount = 0.0
    fallback_buyouts_count = int(round(_safe_float(totals.get("buys", 0))))
    fallback_buyouts_amount = 0.0

    payload = {
        "daily_orders_count": fallback_orders_count,
        "daily_orders_amount": round(fallback_orders_amount, 2),
        "daily_buyouts_count": fallback_buyouts_count,
        "daily_buyouts_amount": round(fallback_buyouts_amount, 2),
        "data_source_orders": DAILY_SOURCE_FALLBACK,
        "data_source_buyouts": DAILY_SOURCE_FALLBACK,
        "data_source_orders_count": DAILY_SOURCE_FALLBACK,
        "data_source_orders_amount": DAILY_SOURCE_FALLBACK,
        "data_source_buyouts_count": DAILY_SOURCE_FALLBACK,
        "data_source_buyouts_amount": DAILY_SOURCE_FALLBACK,
        "orders_amount_confirmed": False,
        "buyouts_amount_confirmed": False,
        "supplier_goods_source_file": "",
    }

    if isinstance(supplier_goods_daily, dict) and bool(supplier_goods_daily.get("found")):
        source_file = str(supplier_goods_daily.get("source_file") or "")
        payload.update(
            {
                "daily_orders_count": int(supplier_goods_daily.get("orders_count", fallback_orders_count) or 0),
                "daily_orders_amount": round(
                    _safe_float(supplier_goods_daily.get("orders_amount", fallback_orders_amount)),
                    2,
                ),
                "daily_buyouts_count": int(supplier_goods_daily.get("buyouts_count", fallback_buyouts_count) or 0),
                "daily_buyouts_amount": round(
                    _safe_float(supplier_goods_daily.get("buyouts_amount", fallback_buyouts_amount)),
                    2,
                ),
                "data_source_orders": DAILY_SOURCE_SUPPLIER_GOODS,
                "data_source_buyouts": DAILY_SOURCE_SUPPLIER_GOODS,
                "data_source_orders_count": DAILY_SOURCE_SUPPLIER_GOODS,
                "data_source_orders_amount": DAILY_SOURCE_SUPPLIER_GOODS,
                "data_source_buyouts_count": DAILY_SOURCE_SUPPLIER_GOODS,
                "data_source_buyouts_amount": DAILY_SOURCE_SUPPLIER_GOODS,
                "orders_amount_confirmed": True,
                "buyouts_amount_confirmed": True,
                "supplier_goods_source_file": source_file,
            }
        )
        return payload

    orders_rows_count = _rows_count(api_orders_rows)
    sales_rows_count = _rows_count(api_sales_rows)
    realization_rows_count = _rows_count(api_realization_rows)

    # orders_count: supplier_goods_report -> orders_api -> sales_api -> fallback
    if orders_rows_count > 0:
        payload["daily_orders_count"] = orders_rows_count
        payload["data_source_orders_count"] = DAILY_SOURCE_ORDERS_API
    elif sales_rows_count > 0:
        payload["daily_orders_count"] = sales_rows_count
        payload["data_source_orders_count"] = DAILY_SOURCE_SALES_API

    # orders_amount: supplier_goods_report -> sales_api -> fallback (orders_api excluded)
    if sales_rows_count > 0:
        payload["daily_orders_amount"] = _rows_price_sum(api_sales_rows)
        payload["data_source_orders_amount"] = DAILY_SOURCE_SALES_API
        payload["orders_amount_confirmed"] = True

    # buyouts_count/amount: supplier_goods_report -> sales_api -> realization_api -> fallback
    if sales_rows_count > 0:
        payload["daily_buyouts_count"] = sales_rows_count
        payload["daily_buyouts_amount"] = _rows_price_sum(api_sales_rows)
        payload["data_source_buyouts_count"] = DAILY_SOURCE_SALES_API
        payload["data_source_buyouts_amount"] = DAILY_SOURCE_SALES_API
        payload["buyouts_amount_confirmed"] = True
    elif realization_rows_count > 0:
        payload["daily_buyouts_count"] = realization_rows_count
        payload["daily_buyouts_amount"] = _rows_price_sum(api_realization_rows)
        payload["data_source_buyouts_count"] = DAILY_SOURCE_REALIZATION_API
        payload["data_source_buyouts_amount"] = DAILY_SOURCE_REALIZATION_API
        payload["buyouts_amount_confirmed"] = True

    payload["data_source_orders"] = str(payload.get("data_source_orders_count") or DAILY_SOURCE_FALLBACK)
    payload["data_source_buyouts"] = str(payload.get("data_source_buyouts_count") or DAILY_SOURCE_FALLBACK)

    return payload
