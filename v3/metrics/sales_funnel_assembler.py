from __future__ import annotations

from typing import Any, Dict, List, Tuple


def _to_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _pct(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None:
        return None
    if denominator <= 0:
        return None
    return round(numerator / denominator * 100.0, 2)


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        return value
    return None


def _source_is_known(value: Any) -> bool:
    return not _is_unknown_source(value)


def _sanitize_count(value: Any, *, source: Any) -> int | None:
    normalized = _to_int_or_none(value)
    if normalized is None:
        return None
    if normalized == 0 and not _source_is_known(source):
        return None
    return normalized


def _extract_funnel_xlsx_payload(metrics: Dict[str, Any], explicit: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if isinstance(explicit, dict) and isinstance(explicit.get("cabinet_totals"), dict):
        return explicit

    candidates: List[Any] = []
    if isinstance(metrics, dict):
        candidates.extend(
            [
                metrics.get("funnel_xlsx"),
                metrics.get("funnel_report_xlsx"),
                metrics.get("funnel_report"),
                metrics.get("local_funnel"),
                metrics.get("wb_funnel_xlsx"),
            ]
        )
        input_debug = metrics.get("input_debug", {})
        if isinstance(input_debug, dict):
            candidates.extend(
                [
                    input_debug.get("funnel_xlsx"),
                    input_debug.get("funnel_report"),
                    input_debug.get("local_funnel"),
                ]
            )

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if isinstance(candidate.get("cabinet_totals"), dict):
            return candidate
        if any(key in candidate for key in ("views", "add_to_cart", "orders", "buyouts")):
            return {
                "cabinet_totals": {
                    "views": candidate.get("views"),
                    "add_to_cart": candidate.get("add_to_cart"),
                    "orders": candidate.get("orders"),
                    "buyouts": candidate.get("buyouts"),
                    "orders_amount": candidate.get("orders_amount"),
                    "buyouts_amount": candidate.get("buyouts_amount"),
                },
                "sku_rows": candidate.get("sku_rows") if isinstance(candidate.get("sku_rows"), list) else [],
            }
    return {}


def _pick_priority_metric(*, xlsx_value: Any, api_value: Any, api_source: str) -> Tuple[int | None, str]:
    xlsx_count = _to_int_or_none(xlsx_value)
    if xlsx_count is not None:
        return xlsx_count, "funnel_xlsx"
    api_count = _sanitize_count(api_value, source=api_source)
    if api_count is not None:
        return api_count, "api"
    return None, "unknown"


def _pick_priority_float(*, xlsx_value: Any, api_value: Any, api_source: str) -> Tuple[float | None, str]:
    xlsx_number = _to_float_or_none(xlsx_value)
    if xlsx_number is not None:
        return xlsx_number, "funnel_xlsx"
    api_number = _to_float_or_none(api_value)
    if api_number is None:
        return None, "unknown"
    if abs(api_number) <= 1e-12 and not _source_is_known(api_source):
        return None, "unknown"
    return api_number, "api"


def _is_unknown_source(value: Any) -> bool:
    token = str(value or "").strip().lower()
    return token in {"", "unknown", "not_confirmed", "missing", "unavailable"}


def _build_status(*, views: int | None, add_to_cart: int | None, orders: int | None, buyouts: int | None) -> Dict[str, str]:
    if views is not None and add_to_cart is not None:
        traffic = "confirmed"
    elif views is not None or add_to_cart is not None:
        traffic = "partial"
    else:
        traffic = "unknown"

    if views is not None and orders is not None:
        conversion = "confirmed"
    elif orders is not None:
        conversion = "partial"
    else:
        conversion = "unknown"

    if orders is not None and buyouts is not None:
        buyout_stage = "confirmed"
    elif orders is not None or buyouts is not None:
        buyout_stage = "partial"
    else:
        buyout_stage = "unknown"

    return {
        "traffic": traffic,
        "conversion": conversion,
        "buyout_stage": buyout_stage,
    }


def calculate_funnel_metrics(
    *,
    views: int | None,
    add_to_cart: int | None,
    orders: int | None,
    buyouts: int | None,
    ads_spend: float | None,
    revenue: float | None = None,
    commission: float | None = None,
    logistics: float | None = None,
    tax: float | None = None,
    cogs: float | None = None,
    profit: float | None = None,
) -> Dict[str, Any]:
    view_to_order_conversion = _pct(float(orders) if orders is not None else None, float(views) if views is not None else None)
    cart_rate = _pct(float(add_to_cart) if add_to_cart is not None else None, float(views) if views is not None else None)
    cart_to_order = _pct(float(orders) if orders is not None else None, float(add_to_cart) if add_to_cart is not None else None)
    raw_buyout_rate = _pct(float(buyouts) if buyouts is not None else None, float(orders) if orders is not None else None)
    buyout_rate_over_100 = bool(raw_buyout_rate is not None and raw_buyout_rate > 100.0)
    buyout_rate_note = (
        "order_to_buyout_conversion_gt_100: possible date shift between orders and buyouts"
        if buyout_rate_over_100
        else ""
    )
    buyout_rate = None if buyout_rate_over_100 else raw_buyout_rate

    cpo: float | None = None
    if ads_spend is not None and orders is not None and orders > 0:
        cpo = round(float(ads_spend) / float(orders), 2)

    marketing_layer = {
        "basis": "orders",
        "orders": orders,
        "ads_spend": round(float(ads_spend), 2) if ads_spend is not None else None,
        "cpo": cpo,
    }
    financial_layer = {
        "basis": "buyouts",
        "buyouts": buyouts,
        "revenue": round(float(revenue), 2) if revenue is not None else None,
        "commission": round(float(commission), 2) if commission is not None else None,
        "logistics": round(float(logistics), 2) if logistics is not None else None,
        "tax": round(float(tax), 2) if tax is not None else None,
        "cogs": round(float(cogs), 2) if cogs is not None else None,
        "profit": round(float(profit), 2) if profit is not None else None,
    }

    return {
        "views": views,
        "add_to_cart": add_to_cart,
        "orders": orders,
        "buyouts": buyouts,
        "view_to_order_conversion": view_to_order_conversion,
        "cart_rate": cart_rate,
        "cart_to_order": cart_to_order,
        "buyout_rate": buyout_rate,
        "buyout_rate_over_100": buyout_rate_over_100,
        "buyout_rate_note": buyout_rate_note,
        "ads_spend": round(float(ads_spend), 2) if ads_spend is not None else None,
        "cpo": cpo,
        "marketing_layer": marketing_layer,
        "financial_layer": financial_layer,
    }


def assemble_sales_funnel(
    *,
    run_date: str,
    metrics: Dict[str, Any],
    ads_diagnostics: Dict[str, Any],
    funnel_xlsx_payload: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    safe_metrics = metrics if isinstance(metrics, dict) else {}
    safe_totals = safe_metrics.get("totals", {})
    if not isinstance(safe_totals, dict):
        safe_totals = {}
    safe_commerce_kpi = safe_metrics.get("commerce_kpi", {})
    if not isinstance(safe_commerce_kpi, dict):
        safe_commerce_kpi = {}
    safe_daily_kpi = safe_metrics.get("daily_kpi", {})
    if not isinstance(safe_daily_kpi, dict):
        safe_daily_kpi = {}
    safe_financial_kpi = safe_metrics.get("financial_kpi", {})
    if not isinstance(safe_financial_kpi, dict):
        safe_financial_kpi = {}
    safe_data_sources = safe_metrics.get("data_sources", {})
    if not isinstance(safe_data_sources, dict):
        safe_data_sources = {}
    safe_ads_diag = ads_diagnostics if isinstance(ads_diagnostics, dict) else {}
    selected_totals = safe_ads_diag.get("selected_totals", {})
    if not isinstance(selected_totals, dict):
        selected_totals = {}
    safe_funnel_xlsx = _extract_funnel_xlsx_payload(safe_metrics, funnel_xlsx_payload)
    funnel_xlsx_totals = safe_funnel_xlsx.get("cabinet_totals", {})
    if not isinstance(funnel_xlsx_totals, dict):
        funnel_xlsx_totals = {}

    orders_confirmed = bool(
        safe_commerce_kpi.get(
            "orders_count_confirmed",
            safe_daily_kpi.get("orders_count_confirmed", False),
        )
    )
    buyouts_confirmed = bool(
        safe_commerce_kpi.get(
            "buyouts_count_confirmed",
            safe_daily_kpi.get("buyouts_count_confirmed", False),
        )
    )

    orders_value = _to_int_or_none(
        _first_present(
            safe_commerce_kpi.get("daily_orders_count"),
            safe_daily_kpi.get("daily_orders_count"),
        )
    )
    buyouts_value = _to_int_or_none(
        _first_present(
            safe_commerce_kpi.get("daily_buyouts_count"),
            safe_daily_kpi.get("daily_buyouts_count"),
        )
    )
    orders = orders_value if orders_confirmed else None
    buyouts = buyouts_value if buyouts_confirmed else None

    orders_source = _first_present(
        safe_data_sources.get("orders_count"),
        safe_daily_kpi.get("data_source_orders_count"),
        safe_daily_kpi.get("source_count"),
    )
    buyouts_source = _first_present(
        safe_data_sources.get("buyouts_count"),
        safe_daily_kpi.get("data_source_buyouts_count"),
        safe_daily_kpi.get("source_count"),
    )
    traffic_source = _first_present(
        safe_data_sources.get("views"),
        safe_data_sources.get("orders_count"),
        safe_daily_kpi.get("data_source_orders_count"),
    )
    add_to_cart_source = _first_present(
        safe_data_sources.get("add_to_cart"),
        safe_data_sources.get("orders_count"),
        safe_daily_kpi.get("data_source_orders_count"),
    )

    # Keep conversion metrics available when counts are present in known sources,
    # even if confirmation flags are not final yet.
    orders_for_calc = orders
    if orders_for_calc is None:
        orders_totals_value = _to_int_or_none(safe_totals.get("orders"))
        if orders_totals_value is not None and (orders_totals_value > 0 or not _is_unknown_source(orders_source)):
            orders_for_calc = orders_totals_value
    buyouts_for_calc = buyouts
    if buyouts_for_calc is None:
        buyouts_totals_value = _to_int_or_none(safe_totals.get("buys"))
        if buyouts_totals_value is not None and (buyouts_totals_value > 0 or not _is_unknown_source(buyouts_source)):
            buyouts_for_calc = buyouts_totals_value
    orders_for_calc, orders_source_final = _pick_priority_metric(
        xlsx_value=funnel_xlsx_totals.get("orders"),
        api_value=orders_for_calc,
        api_source=str(orders_source or "unknown"),
    )
    buyouts_for_calc, buyouts_source_final = _pick_priority_metric(
        xlsx_value=funnel_xlsx_totals.get("buyouts"),
        api_value=buyouts_for_calc,
        api_source=str(buyouts_source or "unknown"),
    )

    api_views = _to_int_or_none(
        _first_present(
            safe_commerce_kpi.get("views"),
            safe_daily_kpi.get("views"),
            safe_totals.get("views"),
            safe_totals.get("card_views"),
            selected_totals.get("ads_impressions"),
            safe_totals.get("ads_impressions"),
        )
    )
    views, views_source_final = _pick_priority_metric(
        xlsx_value=funnel_xlsx_totals.get("views"),
        api_value=api_views,
        api_source=str(traffic_source or "unknown"),
    )

    api_add_to_cart = _to_int_or_none(
        _first_present(
            safe_commerce_kpi.get("add_to_cart"),
            safe_daily_kpi.get("add_to_cart"),
            safe_totals.get("add_to_cart"),
            safe_totals.get("cart_count"),
        )
    )
    add_to_cart, add_to_cart_source_final = _pick_priority_metric(
        xlsx_value=funnel_xlsx_totals.get("add_to_cart"),
        api_value=api_add_to_cart,
        api_source=str(add_to_cart_source or "unknown"),
    )
    clicks = _to_int_or_none(_first_present(selected_totals.get("ads_clicks"), safe_totals.get("ads_clicks")))
    impressions = _to_int_or_none(
        _first_present(selected_totals.get("ads_impressions"), safe_totals.get("ads_impressions"))
    )
    ctr = _pct(float(clicks) if clicks is not None else None, float(impressions) if impressions is not None else None)

    ads_spend = _to_float_or_none(
        _first_present(
            safe_financial_kpi.get("ads_spend"),
            safe_totals.get("ads_spend_total"),
            safe_totals.get("ads_spend"),
            selected_totals.get("ads_spend"),
        )
    )
    if str(safe_data_sources.get("ads_spend") or "").strip().lower() == "unknown":
        ads_spend = None
    revenue = _to_float_or_none(
        _first_present(
            safe_financial_kpi.get("revenue"),
            safe_totals.get("total_revenue"),
            safe_totals.get("revenue"),
        )
    )
    commission = _to_float_or_none(_first_present(safe_financial_kpi.get("wb_commission"), safe_totals.get("wb_commission")))
    logistics = _to_float_or_none(_first_present(safe_financial_kpi.get("logistics"), safe_totals.get("logistics")))
    tax = _to_float_or_none(_first_present(safe_financial_kpi.get("tax"), safe_totals.get("tax")))
    cogs = _to_float_or_none(_first_present(safe_financial_kpi.get("cost_price"), safe_totals.get("cost_price")))
    profit = _to_float_or_none(_first_present(safe_financial_kpi.get("net_profit"), safe_totals.get("net_profit"), safe_totals.get("profit")))

    orders_amount, orders_amount_source = _pick_priority_float(
        xlsx_value=funnel_xlsx_totals.get("orders_amount"),
        api_value=None,
        api_source="unknown",
    )
    buyouts_amount, buyouts_amount_source = _pick_priority_float(
        xlsx_value=funnel_xlsx_totals.get("buyouts_amount"),
        api_value=None,
        api_source="unknown",
    )

    cabinet_metrics = calculate_funnel_metrics(
        views=views,
        add_to_cart=add_to_cart,
        orders=orders_for_calc,
        buyouts=buyouts_for_calc,
        ads_spend=ads_spend,
        revenue=revenue,
        commission=commission,
        logistics=logistics,
        tax=tax,
        cogs=cogs,
        profit=profit,
    )

    sku_funnel: List[Dict[str, Any]] = []
    for row in safe_metrics.get("sku_metrics", []):
        if not isinstance(row, dict):
            continue
        sku_orders = _to_int_or_none(row.get("orders"))
        sku_buyouts = _to_int_or_none(_first_present(row.get("buyouts"), row.get("buys")))
        sku_views = _to_int_or_none(
            _first_present(
                row.get("views"),
                row.get("card_views"),
                row.get("impressions"),
            )
        )
        if sku_views is not None and sku_views <= 0:
            if _to_float_or_none(row.get("ads_spend")) is None and _to_int_or_none(row.get("clicks")) is None:
                sku_views = None
        sku_add_to_cart = _to_int_or_none(_first_present(row.get("add_to_cart"), row.get("cart_count")))
        sku_ads_spend = _to_float_or_none(row.get("ads_spend"))
        sku_revenue = _to_float_or_none(row.get("revenue"))
        sku_commission = _to_float_or_none(_first_present(row.get("commission"), row.get("wb_commission")))
        sku_logistics = _to_float_or_none(row.get("logistics"))
        sku_tax = _to_float_or_none(row.get("tax"))
        sku_cogs = _to_float_or_none(_first_present(row.get("cogs"), row.get("cost_price")))
        sku_profit = _to_float_or_none(row.get("profit"))
        sku_metrics = calculate_funnel_metrics(
            views=sku_views,
            add_to_cart=sku_add_to_cart,
            orders=sku_orders,
            buyouts=sku_buyouts,
            ads_spend=sku_ads_spend,
            revenue=sku_revenue,
            commission=sku_commission,
            logistics=sku_logistics,
            tax=sku_tax,
            cogs=sku_cogs,
            profit=sku_profit,
        )
        sku_metrics["sku"] = str(row.get("sku") or "")
        sku_funnel.append(sku_metrics)

    data_sources = {
        "views": views_source_final,
        "add_to_cart": add_to_cart_source_final,
        "orders": orders_source_final,
        "buyouts": buyouts_source_final,
        "orders_amount": orders_amount_source,
        "buyouts_amount": buyouts_amount_source,
        "ads_spend": str(safe_data_sources.get("ads_spend") or "unknown"),
        "cpo": "derived",
    }
    status = _build_status(views=views, add_to_cart=add_to_cart, orders=orders, buyouts=buyouts)

    order_to_buyout_over_100 = bool(cabinet_metrics.get("buyout_rate_over_100", False))
    order_to_buyout_note = str(cabinet_metrics.get("buyout_rate_note") or "")
    if order_to_buyout_over_100 and isinstance(status, dict):
        status["buyout_stage"] = "partial"

    funnel_payload = {
        "views": cabinet_metrics["views"],
        "add_to_cart": cabinet_metrics["add_to_cart"],
        "orders": cabinet_metrics["orders"],
        "buyouts": cabinet_metrics["buyouts"],
        "view_to_order_conversion": cabinet_metrics["view_to_order_conversion"],
        "view_to_order": cabinet_metrics["view_to_order_conversion"],
        "cart_rate": cabinet_metrics["cart_rate"],
        "cart_to_order": cabinet_metrics["cart_to_order"],
        "buyout_rate": cabinet_metrics["buyout_rate"],
        "order_to_buyout": cabinet_metrics["buyout_rate"],
        "order_to_buyout_over_100": order_to_buyout_over_100,
        "order_to_buyout_note": order_to_buyout_note,
        "orders_amount": round(orders_amount, 2) if orders_amount is not None else None,
        "buyouts_amount": round(buyouts_amount, 2) if buyouts_amount is not None else None,
        "ads_spend": cabinet_metrics["ads_spend"],
        "cpo": cabinet_metrics["cpo"],
        # Backward-compatible aliases for existing report/email blocks.
        "impressions": impressions if impressions is not None else views,
        "clicks": clicks,
        "ctr": ctr,
        "cart_count": cabinet_metrics["add_to_cart"],
        "cart_conversion_pct": cabinet_metrics["cart_to_order"],
        "cart_rate_pct": cabinet_metrics["cart_rate"],
        "click_to_order_conversion_pct": _pct(
            float(cabinet_metrics["orders"]) if cabinet_metrics["orders"] is not None else None,
            float(clicks) if clicks is not None else None,
        ),
        "order_to_buyout_conversion_pct": cabinet_metrics["buyout_rate"],
        "conversion_rates": {
            "view_to_order": cabinet_metrics["view_to_order_conversion"],
            "cart_to_order": cabinet_metrics["cart_to_order"],
            "order_to_buyout": cabinet_metrics["buyout_rate"],
            "order_to_buyout_over_100": order_to_buyout_over_100,
            "order_to_buyout_note": order_to_buyout_note,
        },
        "marketing_layer": cabinet_metrics["marketing_layer"],
        "financial_layer": cabinet_metrics["financial_layer"],
    }

    return {
        "date": str(run_date or ""),
        "funnel": funnel_payload,
        "data_sources": data_sources,
        "status": status,
        "marketing_layer": cabinet_metrics["marketing_layer"],
        "financial_layer": cabinet_metrics["financial_layer"],
        "sku_funnel": sku_funnel,
    }





