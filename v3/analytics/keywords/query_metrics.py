from __future__ import annotations

from typing import Any, Dict, List

from .query_utils import safe_div


def build_query_metrics(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue

        impressions = row.get("impressions")
        clicks = row.get("clicks")
        add_to_cart = row.get("add_to_cart")
        orders = row.get("orders")
        buyouts = row.get("buyouts")
        spend = row.get("spend")

        ctr = safe_div(clicks, impressions)
        cart_rate = safe_div(add_to_cart, impressions)
        conversion = safe_div(orders, impressions)
        click_to_order = safe_div(orders, clicks)
        buyout_rate = safe_div(buyouts, orders)
        spend_per_order = safe_div(spend, orders)
        spend_per_buyout = safe_div(spend, buyouts)

        items.append(
            {
                "sku": str(row.get("sku") or "").strip(),
                "query": str(row.get("query") or "").strip(),
                "impressions": impressions,
                "clicks": clicks,
                "add_to_cart": add_to_cart,
                "orders": orders,
                "buyouts": buyouts,
                "spend": spend,
                "avg_position": row.get("avg_position"),
                "date": row.get("date"),
                "period": row.get("period"),
                "ctr": ctr,
                "cart_rate": cart_rate,
                "conversion": conversion,
                "click_to_order": click_to_order,
                "buyout_rate": buyout_rate,
                "spend_per_order": spend_per_order,
                "spend_per_buyout": spend_per_buyout,
            }
        )

    return items
