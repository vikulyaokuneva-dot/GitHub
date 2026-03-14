from __future__ import annotations

from typing import Any, Dict, List

from .profit_attribution import compute_profit_from_ads, safe_div, safe_float


def _classify_query(*, profit: float, orders: float, spend: float, confidence: str) -> str:
    if confidence == "low" and orders <= 0 and spend <= 0:
        return "insufficient_data"
    if orders <= 0 and spend > 0:
        return "unprofitable"
    if profit > 1.0:
        return "profitable"
    if profit < -1.0:
        return "unprofitable"
    if confidence == "low":
        return "insufficient_data"
    return "neutral"


def build_query_ads_performance(
    *,
    ads_by_query: List[Dict[str, Any]],
    sku_performance: List[Dict[str, Any]],
    min_clicks_for_confidence: int = 5,
) -> List[Dict[str, Any]]:
    sku_index = {
        str(row.get("sku") or "").strip(): row
        for row in sku_performance
        if isinstance(row, dict) and str(row.get("sku") or "").strip()
    }

    out: List[Dict[str, Any]] = []
    for row in ads_by_query:
        if not isinstance(row, dict):
            continue

        query = str(row.get("query") or "").strip()
        if not query:
            continue

        sku = str(row.get("sku") or "").strip()
        sku_ctx = sku_index.get(sku, {})

        impressions = max(0.0, safe_float(row.get("impressions")))
        clicks = max(0.0, safe_float(row.get("clicks")))
        orders = max(0.0, safe_float(row.get("orders")))
        spend = max(0.0, safe_float(row.get("ad_spend")))

        buyouts_raw_available = bool(row.get("buyouts_raw_available", False))
        buyouts_raw = max(0.0, safe_float(row.get("buyouts_raw")))

        revenue_raw_available = bool(row.get("revenue_raw_available", False))
        revenue_raw = max(0.0, safe_float(row.get("revenue_raw")))

        sku_order_to_buyout = sku_ctx.get("order_to_buyout_rate")
        if buyouts_raw_available:
            buyouts = buyouts_raw
        else:
            if sku_order_to_buyout is None:
                buyouts = None
            else:
                buyouts = max(0.0, orders * max(0.0, min(1.0, safe_float(sku_order_to_buyout))))

        revenue_per_order = None
        sku_orders = safe_float(sku_ctx.get("orders_from_ads"))
        if sku_orders > 0:
            revenue_per_order = safe_float(sku_ctx.get("revenue_from_ads")) / sku_orders

        if revenue_raw_available and revenue_raw > 0:
            revenue = revenue_raw
        elif revenue_per_order is not None and orders > 0:
            revenue = max(0.0, revenue_per_order * orders)
        else:
            revenue = 0.0

        cost_ratio = None
        sku_revenue = safe_float(sku_ctx.get("revenue_from_ads"))
        if sku_revenue > 0 and bool(sku_ctx.get("cost_price_available", False)):
            sku_profit = safe_float(sku_ctx.get("profit_from_ads"))
            sku_spend = safe_float(sku_ctx.get("ad_spend"))
            sku_cost = max(0.0, sku_revenue - sku_spend - sku_profit)
            cost_ratio = max(0.0, min(1.0, sku_cost / sku_revenue))

        cost_of_goods = None if cost_ratio is None else max(0.0, revenue * cost_ratio)
        profit = compute_profit_from_ads(
            revenue_from_ads=revenue,
            ad_spend=spend,
            cost_of_goods=cost_of_goods,
        )

        ctr = safe_div(clicks, impressions)
        order_rate = safe_div(orders, impressions)
        conversion_rate = safe_div(orders, clicks)
        buyout_rate = None if buyouts is None else safe_div(buyouts, orders)
        romi = safe_div(profit * 100.0, spend)
        cpo = safe_div(spend, orders)

        if clicks >= max(1, int(min_clicks_for_confidence)) and orders > 0:
            confidence = "high"
        elif clicks > 0 or spend > 0:
            confidence = "medium"
        else:
            confidence = "low"

        classification = _classify_query(
            profit=profit,
            orders=orders,
            spend=spend,
            confidence=confidence,
        )

        out.append(
            {
                "query": query,
                "sku": sku or None,
                "impressions": int(round(impressions)),
                "clicks": int(round(clicks)),
                "CTR": round((ctr or 0.0) * 100.0, 4) if ctr is not None else None,
                "ad_spend": round(spend, 2),
                "orders": round(orders, 4),
                "buyouts": (round(float(buyouts), 4) if buyouts is not None else None),
                "revenue": round(revenue, 2),
                "profit": round(profit, 2),
                "ROMI": round((romi or 0.0), 4) if romi is not None else None,
                "CPO": round((cpo or 0.0), 4) if cpo is not None else None,
                "order_rate": round((order_rate or 0.0) * 100.0, 4) if order_rate is not None else None,
                "conversion_rate": round((conversion_rate or 0.0) * 100.0, 4) if conversion_rate is not None else None,
                "buyout_rate": round((buyout_rate or 0.0) * 100.0, 4) if buyout_rate is not None else None,
                "classification": classification,
                "confidence": confidence,
                "source": str(row.get("source") or "ads_rows"),
            }
        )

    out.sort(
        key=lambda item: (
            safe_float(item.get("profit")),
            safe_float(item.get("revenue")),
            str(item.get("query") or ""),
        ),
        reverse=True,
    )
    return out
