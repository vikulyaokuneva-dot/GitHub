from __future__ import annotations

from typing import Any, Dict, List

from .profit_attribution import (
    build_order_buyout_bridge,
    compute_profit_from_ads,
    estimate_cost_from_orders,
    estimate_revenue_from_orders,
    safe_div,
    safe_float,
)


def _pick_metric_float(row: Dict[str, Any], *keys: str) -> float:
    for key in keys:
        if key in row and row.get(key) is not None:
            return safe_float(row.get(key))
    return 0.0


def build_sku_ads_performance(
    *,
    ads_by_sku: List[Dict[str, Any]],
    sku_metrics_index: Dict[str, Dict[str, Any]],
    min_orders_for_confidence: int = 3,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    for row in ads_by_sku:
        if not isinstance(row, dict):
            continue
        sku = str(row.get("sku") or "").strip()
        if not sku:
            continue

        metric_row = sku_metrics_index.get(sku, {}) if isinstance(sku_metrics_index, dict) else {}

        ad_spend = max(0.0, safe_float(row.get("ad_spend")))
        impressions = max(0.0, safe_float(row.get("impressions")))
        clicks = max(0.0, safe_float(row.get("clicks")))
        orders_from_ads = max(0.0, safe_float(row.get("orders_from_ads")))

        total_orders = max(0.0, _pick_metric_float(metric_row, "orders", "orders_count"))
        total_buyouts = max(0.0, _pick_metric_float(metric_row, "buys", "buyouts", "sales_count"))
        total_revenue = max(0.0, _pick_metric_float(metric_row, "revenue", "buyouts_amount", "orders_amount"))

        total_cost_price_raw = metric_row.get("cost_price")
        total_cost_price = None if total_cost_price_raw is None else max(0.0, safe_float(total_cost_price_raw))

        revenue_from_ads_raw_available = bool(row.get("revenue_from_ads_raw_available", False))
        revenue_from_ads_raw = max(0.0, safe_float(row.get("revenue_from_ads_raw")))

        if revenue_from_ads_raw_available and revenue_from_ads_raw > 0:
            revenue_from_ads = revenue_from_ads_raw
        else:
            revenue_from_ads = estimate_revenue_from_orders(
                total_revenue=total_revenue,
                total_orders=total_orders,
                attributed_orders=orders_from_ads,
            )

        if total_cost_price is None:
            cost_of_goods = None
        else:
            cost_of_goods = estimate_cost_from_orders(
                total_cost=total_cost_price,
                total_orders=total_orders,
                attributed_orders=orders_from_ads,
            )

        buyouts_raw_available = bool(row.get("buyouts_from_ads_raw_available", False))
        buyouts_from_ads_raw = max(0.0, safe_float(row.get("buyouts_from_ads_raw")))

        bridge = build_order_buyout_bridge(
            total_orders=total_orders,
            total_buyouts=total_buyouts,
            attributed_orders=orders_from_ads,
            revenue_from_ads=revenue_from_ads,
            cost_from_ads=cost_of_goods,
            ad_spend=ad_spend,
        )

        buyouts_from_ads = buyouts_from_ads_raw if buyouts_raw_available else bridge.get("estimated_buyouts_from_ads")
        profit_from_ads = compute_profit_from_ads(
            revenue_from_ads=revenue_from_ads,
            ad_spend=ad_spend,
            cost_of_goods=cost_of_goods,
        )

        ctr = safe_div(clicks, impressions)
        cpo = safe_div(ad_spend, orders_from_ads)
        drr = safe_div(ad_spend * 100.0, revenue_from_ads)
        romi = safe_div(profit_from_ads * 100.0, ad_spend)

        confidence = "low"
        if orders_from_ads >= max(1, int(min_orders_for_confidence)) and buyouts_from_ads is not None:
            confidence = "high"
        elif orders_from_ads > 0:
            confidence = "medium"

        out.append(
            {
                "sku": sku,
                "ad_spend": round(ad_spend, 2),
                "impressions": int(round(impressions)),
                "clicks": int(round(clicks)),
                "CTR": round((ctr or 0.0) * 100.0, 4) if ctr is not None else None,
                "orders_from_ads": round(orders_from_ads, 4),
                "buyouts_from_ads": (round(float(buyouts_from_ads), 4) if buyouts_from_ads is not None else None),
                "revenue_from_ads": round(revenue_from_ads, 2),
                "profit_from_ads": round(profit_from_ads, 2),
                "ROMI": round((romi or 0.0), 4) if romi is not None else None,
                "DRR": round((drr or 0.0), 4) if drr is not None else None,
                "CPO": round((cpo or 0.0), 4) if cpo is not None else None,
                "order_to_buyout_rate": bridge.get("order_to_buyout_rate"),
                "estimated_buyout_revenue_from_ads": bridge.get("estimated_buyout_revenue_from_ads"),
                "estimated_buyout_profit_from_ads": bridge.get("estimated_buyout_profit_from_ads"),
                "cost_price_available": total_cost_price is not None,
                "confidence": confidence,
                "source": "ads_report",
            }
        )

    out.sort(
        key=lambda item: (
            safe_float(item.get("profit_from_ads")),
            safe_float(item.get("revenue_from_ads")),
            str(item.get("sku") or ""),
        ),
        reverse=True,
    )
    return out
