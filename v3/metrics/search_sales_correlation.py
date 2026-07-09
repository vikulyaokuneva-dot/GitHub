from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def build_search_sales_correlation(
    *,
    search_texts_rows: List[Dict[str, Any]],
    search_orders_rows: List[Dict[str, Any]],
    ads_rows: List[Dict[str, Any]],
    sku_metrics: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build search-to-sales correlation analytics.

    Connects search query positions with real orders and ad spend.
    """
    # Aggregate orders by query
    orders_by_query: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "total_orders": 0,
        "total_amount": 0.0,
        "nm_ids": set(),
        "dates": set(),
        "avg_position": 0.0,
        "position_count": 0,
    })
    for row in search_orders_rows:
        if not isinstance(row, dict):
            continue
        query = str(row.get("query") or "").strip()
        if not query:
            continue
        bucket = orders_by_query[query]
        bucket["total_orders"] += _safe_int(row.get("orders_count"))
        bucket["total_amount"] += _safe_float(row.get("orders_amount"))
        nm_id = _safe_int(row.get("nm_id"))
        if nm_id:
            bucket["nm_ids"].add(nm_id)
        date_str = str(row.get("date") or "").strip()
        if date_str:
            bucket["dates"].add(date_str)
        pos = _safe_float(row.get("position"))
        if pos > 0:
            bucket["avg_position"] += pos
            bucket["position_count"] += 1

    # Aggregate texts by query (frequency, clicks)
    texts_by_query: Dict[str, Dict[str, Any]] = {}
    for row in search_texts_rows:
        if not isinstance(row, dict):
            continue
        query = str(row.get("query") or "").strip()
        if not query:
            continue
        if query not in texts_by_query:
            texts_by_query[query] = {
                "frequency": 0,
                "clicks": 0,
                "cart": 0,
                "nm_ids": set(),
            }
        bucket = texts_by_query[query]
        bucket["frequency"] += _safe_int(row.get("frequency"))
        bucket["clicks"] += _safe_int(row.get("clicks"))
        bucket["cart"] += _safe_int(row.get("cart"))
        nm_id = _safe_int(row.get("nm_id"))
        if nm_id:
            bucket["nm_ids"].add(nm_id)

    # Calculate ad spend by query (from ads_rows if available)
    ads_by_query: Dict[str, float] = defaultdict(float)
    for row in ads_rows:
        if not isinstance(row, dict):
            continue
        query = str(row.get("query") or row.get("keyword") or "").strip()
        if not query:
            continue
        spend = _safe_float(row.get("sum") or row.get("spend") or row.get("cost"))
        ads_by_query[query] += abs(spend)

    # Build correlated results
    correlated: List[Dict[str, Any]] = []
    all_queries = set(list(orders_by_query.keys()) + list(texts_by_query.keys()))

    for query in all_queries:
        order_data = orders_by_query.get(query, {})
        text_data = texts_by_query.get(query, {})
        ad_spend = ads_by_query.get(query, 0.0)

        total_orders = order_data.get("total_orders", 0)
        total_amount = order_data.get("total_amount", 0.0)
        frequency = text_data.get("frequency", 0)
        clicks = text_data.get("clicks", 0)
        cart = text_data.get("cart", 0)
        avg_pos = (
            order_data.get("avg_position", 0) / order_data.get("position_count", 1)
            if order_data.get("position_count", 0) > 0
            else 0.0
        )

        # Conversion metrics
        query_cart_to_order = round(total_orders / cart * 100, 1) if cart > 0 else None
        query_click_to_order = round(total_orders / clicks * 100, 1) if clicks > 0 else None
        query_cpo = round(ad_spend / total_orders, 2) if total_orders > 0 and ad_spend > 0 else None
        query_revenue_per_order = round(total_amount / total_orders, 2) if total_orders > 0 else None
        query_roi = round(total_amount / ad_spend, 2) if ad_spend > 0 and total_amount > 0 else None

        # Classification
        if total_orders > 0 and ad_spend > 0 and (total_amount / ad_spend) >= 3.0:
            efficiency = "profitable"
        elif total_orders > 0 and ad_spend > 0 and (total_amount / ad_spend) < 1.0:
            efficiency = "unprofitable"
        elif total_orders > 0:
            efficiency = "organic"
        elif ad_spend > 0:
            efficiency = "ads_no_orders"
        else:
            efficiency = "low_activity"

        nm_ids_list = sorted(order_data.get("nm_ids", set()) | text_data.get("nm_ids", set()))

        correlated.append({
            "query": query,
            "nm_ids": nm_ids_list,
            "frequency": frequency,
            "clicks": clicks,
            "cart": cart,
            "orders": total_orders,
            "orders_amount": round(total_amount, 2),
            "avg_position": round(avg_pos, 1),
            "ad_spend": round(ad_spend, 2),
            "cart_to_order_pct": query_cart_to_order,
            "click_to_order_pct": query_click_to_order,
            "cpo": query_cpo,
            "revenue_per_order": query_revenue_per_order,
            "roi": query_roi,
            "efficiency": efficiency,
            "dates_count": len(order_data.get("dates", set())),
        })

    # Sort by orders desc, then by amount desc
    correlated.sort(key=lambda x: (-x["orders"], -x["orders_amount"]))

    # Summary stats
    total_queries = len(correlated)
    queries_with_orders = len([q for q in correlated if q["orders"] > 0])
    queries_with_ads = len([q for q in correlated if q["ad_spend"] > 0])
    profitable = len([q for q in correlated if q["efficiency"] == "profitable"])
    unprofitable = len([q for q in correlated if q["efficiency"] == "unprofitable"])
    organic = len([q for q in correlated if q["efficiency"] == "organic"])

    return {
        "queries": correlated,
        "summary": {
            "total_queries": total_queries,
            "queries_with_orders": queries_with_orders,
            "queries_with_ads": queries_with_ads,
            "profitable_queries": profitable,
            "unprofitable_queries": unprofitable,
            "organic_queries": organic,
        },
    }
