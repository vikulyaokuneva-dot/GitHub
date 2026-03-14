from __future__ import annotations

from typing import Any, Dict


def safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def safe_div(numerator: Any, denominator: Any) -> float | None:
    den = safe_float(denominator)
    if den <= 0:
        return None
    return safe_float(numerator) / den


def estimate_revenue_from_orders(
    *,
    total_revenue: float,
    total_orders: float,
    attributed_orders: float,
) -> float:
    if total_revenue <= 0 or total_orders <= 0 or attributed_orders <= 0:
        return 0.0
    ratio = min(1.0, max(0.0, attributed_orders / total_orders))
    return max(0.0, total_revenue * ratio)


def estimate_cost_from_orders(
    *,
    total_cost: float,
    total_orders: float,
    attributed_orders: float,
) -> float:
    if total_cost <= 0 or total_orders <= 0 or attributed_orders <= 0:
        return 0.0
    ratio = min(1.0, max(0.0, attributed_orders / total_orders))
    return max(0.0, total_cost * ratio)


def compute_profit_from_ads(
    *,
    revenue_from_ads: float,
    ad_spend: float,
    cost_of_goods: float | None,
) -> float:
    if cost_of_goods is None:
        return revenue_from_ads - ad_spend
    return revenue_from_ads - ad_spend - max(0.0, cost_of_goods)


def build_order_buyout_bridge(
    *,
    total_orders: float,
    total_buyouts: float,
    attributed_orders: float,
    revenue_from_ads: float,
    cost_from_ads: float | None,
    ad_spend: float,
) -> Dict[str, Any]:
    order_to_buyout_rate = safe_div(total_buyouts, total_orders)
    if order_to_buyout_rate is None:
        estimated_buyouts = None
        estimated_buyout_revenue = None
        estimated_buyout_cost = None
        estimated_buyout_profit = None
    else:
        rate = max(0.0, min(1.0, order_to_buyout_rate))
        estimated_buyouts = max(0.0, attributed_orders * rate)
        estimated_buyout_revenue = max(0.0, revenue_from_ads * rate)
        estimated_buyout_cost = None if cost_from_ads is None else max(0.0, cost_from_ads * rate)
        estimated_buyout_profit = compute_profit_from_ads(
            revenue_from_ads=float(estimated_buyout_revenue),
            ad_spend=float(ad_spend),
            cost_of_goods=estimated_buyout_cost,
        )

    return {
        "order_to_buyout_rate": order_to_buyout_rate,
        "estimated_buyouts_from_ads": estimated_buyouts,
        "estimated_buyout_revenue_from_ads": estimated_buyout_revenue,
        "estimated_buyout_cost_from_ads": estimated_buyout_cost,
        "estimated_buyout_profit_from_ads": estimated_buyout_profit,
    }
