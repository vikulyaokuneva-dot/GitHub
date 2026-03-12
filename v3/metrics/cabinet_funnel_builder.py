from __future__ import annotations

from typing import Any, Dict


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        if value is None:
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _pct(numerator: float, denominator: float) -> float | None:
    if denominator < 0:
        return None
    if abs(denominator) <= 1e-9:
        if abs(numerator) <= 1e-9:
            return 0.0
        return None
    return round(numerator / denominator * 100.0, 2)


def build_cabinet_funnel_core(
    *,
    run_date: str,
    metrics: Dict[str, Any],
    ads_diagnostics: Dict[str, Any],
) -> Dict[str, Any]:
    safe_metrics = metrics if isinstance(metrics, dict) else {}
    safe_ads_diag = ads_diagnostics if isinstance(ads_diagnostics, dict) else {}
    commerce_kpi = safe_metrics.get("commerce_kpi", {})
    if not isinstance(commerce_kpi, dict):
        commerce_kpi = {}

    orders_confirmed = bool(commerce_kpi.get("orders_count_confirmed", False))
    buyouts_confirmed = bool(commerce_kpi.get("buyouts_count_confirmed", False))
    orders = _safe_int(commerce_kpi.get("daily_orders_count")) if orders_confirmed else None
    buyouts = _safe_int(commerce_kpi.get("daily_buyouts_count")) if buyouts_confirmed else None

    selected_totals = safe_ads_diag.get("selected_totals", {})
    if not isinstance(selected_totals, dict):
        selected_totals = {}
    ads_rows = _safe_int(safe_ads_diag.get("rows", 0))
    traffic_available = ads_rows > 0
    impressions = _safe_int(selected_totals.get("ads_impressions", 0)) if traffic_available else None
    clicks = _safe_int(selected_totals.get("ads_clicks", 0)) if traffic_available else None
    ctr = _pct(float(clicks), float(impressions)) if (impressions is not None and clicks is not None) else None

    click_to_order_conversion_pct = (
        _pct(float(orders), float(clicks))
        if (orders is not None and clicks is not None)
        else None
    )
    order_to_buyout_conversion_pct = (
        _pct(float(buyouts), float(orders))
        if (orders is not None and buyouts is not None)
        else None
    )

    if impressions is not None and clicks is not None:
        traffic_status = "confirmed"
    elif impressions is not None or clicks is not None:
        traffic_status = "partial"
    else:
        traffic_status = "unknown"

    if click_to_order_conversion_pct is not None:
        conversion_status = "confirmed"
    elif orders is not None:
        conversion_status = "partial"
    else:
        conversion_status = "unknown"

    if order_to_buyout_conversion_pct is not None:
        buyout_stage_status = "confirmed"
    elif orders is not None or buyouts is not None:
        buyout_stage_status = "partial"
    else:
        buyout_stage_status = "unknown"

    data_sources = {
        "impressions": "ads_diagnostics.selected_totals" if impressions is not None else "unknown",
        "clicks": "ads_diagnostics.selected_totals" if clicks is not None else "unknown",
        "orders": "daily_metrics.commerce_kpi" if orders is not None else "unknown",
        "buyouts": "daily_metrics.commerce_kpi" if buyouts is not None else "unknown",
        "ctr": "derived" if ctr is not None else "unknown",
        "click_to_order_conversion_pct": "derived" if click_to_order_conversion_pct is not None else "unknown",
        "order_to_buyout_conversion_pct": "derived" if order_to_buyout_conversion_pct is not None else "unknown",
    }

    return {
        "date": str(run_date or ""),
        "funnel": {
            "impressions": impressions,
            "clicks": clicks,
            "ctr": ctr,
            "cart_count": None,
            "cart_conversion_pct": None,
            "orders": orders,
            "click_to_order_conversion_pct": click_to_order_conversion_pct,
            "buyouts": buyouts,
            "order_to_buyout_conversion_pct": order_to_buyout_conversion_pct,
        },
        "data_sources": data_sources,
        "status": {
            "traffic": traffic_status,
            "conversion": conversion_status,
            "buyout_stage": buyout_stage_status,
        },
    }
