from __future__ import annotations

from typing import Any, Dict, List

DAILY_SOURCE_SUPPLIER_GOODS = "supplier_goods"
DAILY_SOURCE_ORDERS_API = "orders_api"
DAILY_SOURCE_SALES_API = "sales_api"
DAILY_SOURCE_REALIZATION_API = "realization_api"
DAILY_SOURCE_FALLBACK = "metrics_totals_fallback"
DAILY_SOURCE_UNKNOWN = "unknown"


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


def _rows_have_amount_signal(rows: List[Dict[str, Any]]) -> bool:
    amount_keys = (
        "price",
        "revenue",
        "totalPrice",
        "priceWithDisc",
        "finishedPrice",
        "forPay",
        "ppvz_for_pay",
        "order_amount",
        "buyout_amount",
    )
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in amount_keys:
            if key not in row:
                continue
            value = row.get(key)
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            return True
    return False


def resolve_daily_kpi(
    totals: Dict[str, Any],
    supplier_goods_daily: Dict[str, Any],
    api_orders_rows: List[Dict[str, Any]],
    api_sales_rows: List[Dict[str, Any]],
    api_realization_rows: List[Dict[str, Any]],
    *,
    source_mode: str = "",
) -> Dict[str, Any]:
    fallback_orders_count = 0
    fallback_orders_amount = 0.0
    fallback_buyouts_count = 0
    fallback_buyouts_amount = 0.0
    totals_orders_hint = int(
        round(
            _safe_float(
                totals.get(
                    "sales_activity_qty",
                    totals.get("item_qty", totals.get("orders", 0)),
                )
            )
        )
    )
    totals_buyouts_hint = int(
        round(
            _safe_float(
                totals.get(
                    "sales_activity_qty",
                    totals.get("item_qty", totals.get("buys", 0)),
                )
            )
        )
    )

    payload = {
        "daily_orders_count": fallback_orders_count,
        "daily_orders_amount": round(fallback_orders_amount, 2),
        "daily_buyouts_count": fallback_buyouts_count,
        "daily_buyouts_amount": round(fallback_buyouts_amount, 2),
        "data_source_orders": DAILY_SOURCE_UNKNOWN,
        "data_source_buyouts": DAILY_SOURCE_UNKNOWN,
        "data_source_orders_count": DAILY_SOURCE_UNKNOWN,
        "data_source_orders_amount": DAILY_SOURCE_UNKNOWN,
        "data_source_buyouts_count": DAILY_SOURCE_UNKNOWN,
        "data_source_buyouts_amount": DAILY_SOURCE_UNKNOWN,
        "orders_amount_confirmed": False,
        "buyouts_amount_confirmed": False,
        "orders_count_confirmed": False,
        "buyouts_count_confirmed": False,
        "supplier_goods_source_file": "",
        "quantity_fallback_blocked": False,
        "orders_count_unknown_reason": "",
        "buyouts_count_unknown_reason": "",
        "sku_activity_orders_hint": totals_orders_hint,
        "sku_activity_buyouts_hint": totals_buyouts_hint,
        "api_orders_rows_count": 0,
        "api_sales_rows_count": 0,
        "api_realization_rows_count": 0,
        "supplier_orders_count_raw": 0,
        "supplier_buyouts_count_raw": 0,
        "supplier_goods_ignored_in_wb_api": False,
    }

    orders_rows_count = _rows_count(api_orders_rows)
    sales_rows_count = _rows_count(api_sales_rows)
    realization_rows_count = _rows_count(api_realization_rows)
    payload["api_orders_rows_count"] = orders_rows_count
    payload["api_sales_rows_count"] = sales_rows_count
    payload["api_realization_rows_count"] = realization_rows_count

    normalized_source_mode = str(source_mode or "").strip().lower()
    strict_api_mode = normalized_source_mode == "wb_api"
    supplier_found = isinstance(supplier_goods_daily, dict) and bool(supplier_goods_daily.get("found"))
    allow_supplier_in_wb_api = bool(
        isinstance(supplier_goods_daily, dict) and supplier_goods_daily.get("allow_wb_api_daily_kpi_fallback", False)
    )
    supplier_enabled = supplier_found and (not strict_api_mode or allow_supplier_in_wb_api)
    if supplier_found and not supplier_enabled:
        payload["supplier_goods_ignored_in_wb_api"] = True

    supplier_source_file = str(supplier_goods_daily.get("source_file") or "") if supplier_found else ""
    supplier_orders_count_raw = int(_safe_float(supplier_goods_daily.get("orders_count", 0))) if supplier_enabled else 0
    supplier_buyouts_count_raw = int(_safe_float(supplier_goods_daily.get("buyouts_count", 0))) if supplier_enabled else 0
    supplier_orders_amount_raw = round(_safe_float(supplier_goods_daily.get("orders_amount", 0.0)), 2) if supplier_enabled else 0.0
    supplier_buyouts_amount_raw = round(_safe_float(supplier_goods_daily.get("buyouts_amount", 0.0)), 2) if supplier_enabled else 0.0
    supplier_orders_count_confirmed = bool(supplier_goods_daily.get("orders_count_confirmed", False)) if supplier_enabled else False
    supplier_buyouts_count_confirmed = bool(supplier_goods_daily.get("buyouts_count_confirmed", False)) if supplier_enabled else False
    supplier_amounts_confirmed = bool(
        supplier_goods_daily.get("amounts_confirmed", supplier_goods_daily.get("kpi_confirmed", supplier_found))
    ) if supplier_enabled else False
    if supplier_source_file:
        payload["supplier_goods_source_file"] = supplier_source_file
    payload["supplier_orders_count_raw"] = supplier_orders_count_raw
    payload["supplier_buyouts_count_raw"] = supplier_buyouts_count_raw

    # orders_count: supplier_goods_confirmed -> orders_api -> sales_api -> metrics_totals_fallback -> unknown
    if supplier_orders_count_confirmed:
        payload["daily_orders_count"] = supplier_orders_count_raw
        payload["data_source_orders_count"] = DAILY_SOURCE_SUPPLIER_GOODS
        payload["orders_count_confirmed"] = True
    elif orders_rows_count > 0:
        payload["daily_orders_count"] = orders_rows_count
        payload["data_source_orders_count"] = DAILY_SOURCE_ORDERS_API
        payload["orders_count_confirmed"] = True
    elif sales_rows_count > 0:
        payload["daily_orders_count"] = sales_rows_count
        payload["data_source_orders_count"] = DAILY_SOURCE_SALES_API
        payload["orders_count_confirmed"] = True
    elif totals_orders_hint > 0:
        # Use metrics totals as fallback source
        payload["daily_orders_count"] = totals_orders_hint
        payload["data_source_orders_count"] = DAILY_SOURCE_FALLBACK
        payload["orders_count_confirmed"] = True
    else:
        payload["orders_count_unknown_reason"] = "no_confirmed_orders_source: supplier_goods/api.orders/api.sales/metrics_totals"

    # orders_amount policy:
    # - strict wb_api mode: keep semantic alignment with orders_count source
    # - non-api/local modes: preserve legacy fallback behavior
    orders_count_source = str(payload.get("data_source_orders_count") or DAILY_SOURCE_UNKNOWN)
    orders_amount_signal = _rows_have_amount_signal(api_orders_rows)
    sales_amount_signal = _rows_have_amount_signal(api_sales_rows)
    if strict_api_mode:
        if orders_count_source == DAILY_SOURCE_ORDERS_API and orders_rows_count > 0 and orders_amount_signal:
            payload["daily_orders_amount"] = _rows_price_sum(api_orders_rows)
            payload["data_source_orders_amount"] = DAILY_SOURCE_ORDERS_API
            payload["orders_amount_confirmed"] = True
        elif orders_count_source == DAILY_SOURCE_SALES_API and sales_rows_count > 0 and sales_amount_signal:
            payload["daily_orders_amount"] = _rows_price_sum(api_sales_rows)
            payload["data_source_orders_amount"] = DAILY_SOURCE_SALES_API
            payload["orders_amount_confirmed"] = True
        elif orders_count_source == DAILY_SOURCE_SUPPLIER_GOODS and supplier_amounts_confirmed:
            payload["daily_orders_amount"] = supplier_orders_amount_raw
            payload["data_source_orders_amount"] = DAILY_SOURCE_SUPPLIER_GOODS
            payload["orders_amount_confirmed"] = True
    else:
        if sales_rows_count > 0 and sales_amount_signal:
            payload["daily_orders_amount"] = _rows_price_sum(api_sales_rows)
            payload["data_source_orders_amount"] = DAILY_SOURCE_SALES_API
            payload["orders_amount_confirmed"] = True
        elif supplier_amounts_confirmed:
            payload["daily_orders_amount"] = supplier_orders_amount_raw
            payload["data_source_orders_amount"] = DAILY_SOURCE_SUPPLIER_GOODS
            payload["orders_amount_confirmed"] = True

    # buyouts_count: supplier_goods_confirmed -> sales_api -> realization_api -> metrics_totals_fallback -> unknown
    if supplier_buyouts_count_confirmed:
        payload["daily_buyouts_count"] = supplier_buyouts_count_raw
        payload["data_source_buyouts_count"] = DAILY_SOURCE_SUPPLIER_GOODS
        payload["buyouts_count_confirmed"] = True
    elif sales_rows_count > 0:
        payload["daily_buyouts_count"] = sales_rows_count
        payload["data_source_buyouts_count"] = DAILY_SOURCE_SALES_API
        payload["buyouts_count_confirmed"] = True
    elif realization_rows_count > 0:
        payload["daily_buyouts_count"] = realization_rows_count
        payload["data_source_buyouts_count"] = DAILY_SOURCE_REALIZATION_API
        payload["buyouts_count_confirmed"] = True
    elif totals_buyouts_hint > 0:
        # Use metrics totals as fallback source
        payload["daily_buyouts_count"] = totals_buyouts_hint
        payload["data_source_buyouts_count"] = DAILY_SOURCE_FALLBACK
        payload["buyouts_count_confirmed"] = True
    else:
        payload["buyouts_count_unknown_reason"] = "no_confirmed_buyouts_source: supplier_goods/api.sales/api.realization/metrics_totals"

    # buyouts_amount policy:
    # - strict wb_api mode: keep semantic alignment with buyouts_count source
    # - non-api/local modes: preserve legacy fallback behavior
    buyouts_count_source = str(payload.get("data_source_buyouts_count") or DAILY_SOURCE_UNKNOWN)
    realization_amount_signal = _rows_have_amount_signal(api_realization_rows)
    if strict_api_mode:
        if buyouts_count_source == DAILY_SOURCE_SALES_API and sales_rows_count > 0 and sales_amount_signal:
            payload["daily_buyouts_amount"] = _rows_price_sum(api_sales_rows)
            payload["data_source_buyouts_amount"] = DAILY_SOURCE_SALES_API
            payload["buyouts_amount_confirmed"] = True
        elif buyouts_count_source == DAILY_SOURCE_REALIZATION_API and realization_rows_count > 0 and realization_amount_signal:
            payload["daily_buyouts_amount"] = _rows_price_sum(api_realization_rows)
            payload["data_source_buyouts_amount"] = DAILY_SOURCE_REALIZATION_API
            payload["buyouts_amount_confirmed"] = True
        elif buyouts_count_source == DAILY_SOURCE_SUPPLIER_GOODS and supplier_amounts_confirmed:
            payload["daily_buyouts_amount"] = supplier_buyouts_amount_raw
            payload["data_source_buyouts_amount"] = DAILY_SOURCE_SUPPLIER_GOODS
            payload["buyouts_amount_confirmed"] = True
    else:
        if sales_rows_count > 0 and sales_amount_signal:
            payload["daily_buyouts_amount"] = _rows_price_sum(api_sales_rows)
            payload["data_source_buyouts_amount"] = DAILY_SOURCE_SALES_API
            payload["buyouts_amount_confirmed"] = True
        elif realization_rows_count > 0 and realization_amount_signal:
            payload["daily_buyouts_amount"] = _rows_price_sum(api_realization_rows)
            payload["data_source_buyouts_amount"] = DAILY_SOURCE_REALIZATION_API
            payload["buyouts_amount_confirmed"] = True
        elif supplier_amounts_confirmed:
            payload["daily_buyouts_amount"] = supplier_buyouts_amount_raw
            payload["data_source_buyouts_amount"] = DAILY_SOURCE_SUPPLIER_GOODS
            payload["buyouts_amount_confirmed"] = True

    payload["data_source_orders"] = str(payload.get("data_source_orders_count") or DAILY_SOURCE_UNKNOWN)
    payload["data_source_buyouts"] = str(payload.get("data_source_buyouts_count") or DAILY_SOURCE_UNKNOWN)

    # Only block fallback if data is truly unavailable (not even metrics_totals)
    if (
        str(payload.get("data_source_orders_count") or DAILY_SOURCE_UNKNOWN) == DAILY_SOURCE_UNKNOWN
        and totals_orders_hint > 0
    ):
        payload["quantity_fallback_blocked"] = True
        reason = (
            "quantity_hint_blocked_for_orders_count"
            f" (sku_activity_hint={totals_orders_hint})"
        )
        payload["orders_count_unknown_reason"] = (
            f"{payload['orders_count_unknown_reason']}; {reason}"
            if payload.get("orders_count_unknown_reason")
            else reason
        )
    if (
        str(payload.get("data_source_buyouts_count") or DAILY_SOURCE_UNKNOWN) == DAILY_SOURCE_UNKNOWN
        and totals_buyouts_hint > 0
    ):
        payload["quantity_fallback_blocked"] = True
        reason = (
            "quantity_hint_blocked_for_buyouts_count"
            f" (sku_activity_hint={totals_buyouts_hint})"
        )
        payload["buyouts_count_unknown_reason"] = (
            f"{payload['buyouts_count_unknown_reason']}; {reason}"
            if payload.get("buyouts_count_unknown_reason")
            else reason
        )

    if (
        str(payload.get("data_source_orders_count") or DAILY_SOURCE_UNKNOWN) == DAILY_SOURCE_UNKNOWN
        and str(payload.get("data_source_buyouts_count") or DAILY_SOURCE_UNKNOWN) == DAILY_SOURCE_UNKNOWN
        and (totals_orders_hint > 0 or totals_buyouts_hint > 0)
    ):
        payload["quantity_fallback_blocked"] = True

    # Keep legacy behavior to ensure amount flags remain consistent with amounts source.
    if (
        str(payload.get("data_source_orders_amount") or DAILY_SOURCE_UNKNOWN) == DAILY_SOURCE_SUPPLIER_GOODS
        and supplier_source_file
    ):
        payload["supplier_goods_source_file"] = supplier_source_file
    if (
        str(payload.get("data_source_buyouts_amount") or DAILY_SOURCE_UNKNOWN) == DAILY_SOURCE_SUPPLIER_GOODS
        and supplier_source_file
    ):
        payload["supplier_goods_source_file"] = supplier_source_file

    if (
        str(payload.get("data_source_orders_count") or DAILY_SOURCE_UNKNOWN) == DAILY_SOURCE_UNKNOWN
        and str(payload.get("orders_count_unknown_reason") or "").strip() == ""
    ):
        payload["orders_count_unknown_reason"] = "orders_count source unresolved"
    if (
        str(payload.get("data_source_buyouts_count") or DAILY_SOURCE_UNKNOWN) == DAILY_SOURCE_UNKNOWN
        and str(payload.get("buyouts_count_unknown_reason") or "").strip() == ""
    ):
        payload["buyouts_count_unknown_reason"] = "buyouts_count source unresolved"

    return payload
