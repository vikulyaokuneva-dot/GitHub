from __future__ import annotations

from typing import Any, Dict, List


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
    buyout_rate = _pct(float(buyouts) if buyouts is not None else None, float(orders) if orders is not None else None)

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

    orders_value = _to_int_or_none(safe_commerce_kpi.get("daily_orders_count"))
    buyouts_value = _to_int_or_none(safe_commerce_kpi.get("daily_buyouts_count"))
    orders = orders_value if orders_confirmed else None
    buyouts = buyouts_value if buyouts_confirmed else None

    views = _to_int_or_none(
        _first_present(
            safe_commerce_kpi.get("views"),
            safe_daily_kpi.get("views"),
            safe_totals.get("views"),
            safe_totals.get("card_views"),
            selected_totals.get("ads_impressions"),
            safe_totals.get("ads_impressions"),
        )
    )
    add_to_cart = _to_int_or_none(
        _first_present(
            safe_commerce_kpi.get("add_to_cart"),
            safe_daily_kpi.get("add_to_cart"),
            safe_totals.get("add_to_cart"),
            safe_totals.get("cart_count"),
        )
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

    cabinet_metrics = calculate_funnel_metrics(
        views=views,
        add_to_cart=add_to_cart,
        orders=orders,
        buyouts=buyouts,
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
        "views": (
            "totals.views"
            if safe_totals.get("views") is not None
            else ("totals.ads_impressions_proxy" if views is not None else "unknown")
        ),
        "add_to_cart": "totals.add_to_cart" if add_to_cart is not None else "unknown",
        "orders": str(safe_data_sources.get("orders_count") or safe_daily_kpi.get("data_source_orders_count") or "unknown"),
        "buyouts": str(safe_data_sources.get("buyouts_count") or safe_daily_kpi.get("data_source_buyouts_count") or "unknown"),
        "ads_spend": str(safe_data_sources.get("ads_spend") or "unknown"),
        "cpo": "derived",
    }
    status = _build_status(views=views, add_to_cart=add_to_cart, orders=orders, buyouts=buyouts)

    funnel_payload = {
        "views": cabinet_metrics["views"],
        "add_to_cart": cabinet_metrics["add_to_cart"],
        "orders": cabinet_metrics["orders"],
        "buyouts": cabinet_metrics["buyouts"],
        "view_to_order_conversion": cabinet_metrics["view_to_order_conversion"],
        "cart_rate": cabinet_metrics["cart_rate"],
        "cart_to_order": cabinet_metrics["cart_to_order"],
        "buyout_rate": cabinet_metrics["buyout_rate"],
        "ads_spend": cabinet_metrics["ads_spend"],
        "cpo": cabinet_metrics["cpo"],
        # Backward-compatible aliases for existing report/email blocks.
        "impressions": impressions if impressions is not None else views,
        "clicks": clicks,
        "ctr": ctr,
        "cart_count": cabinet_metrics["add_to_cart"],
        "cart_conversion_pct": cabinet_metrics["cart_rate"],
        "click_to_order_conversion_pct": _pct(
            float(cabinet_metrics["orders"]) if cabinet_metrics["orders"] is not None else None,
            float(clicks) if clicks is not None else None,
        ),
        "order_to_buyout_conversion_pct": cabinet_metrics["buyout_rate"],
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
