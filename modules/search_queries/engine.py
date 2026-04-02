"""Engine for search queries analytics aggregates."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _top(items: list[dict[str, Any]], key: str, limit: int = 10, reverse: bool = True) -> list[dict[str, Any]]:
    return sorted(items, key=lambda x: x.get(key, 0), reverse=reverse)[:limit]


def _aggregate_by_query(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        query = row.get("query", "")
        if not query:
            continue
        item = grouped.setdefault(
            query,
            {
                "query": query,
                "query_count": 0,
                "card_clicks": 0,
                "add_to_cart": 0,
                "orders_count": 0,
                "visibility_pct_avg": 0.0,
                "rows_count": 0,
            },
        )
        item["query_count"] += int(row.get("query_count", 0) or 0)
        item["card_clicks"] += int(row.get("card_clicks", 0) or 0)
        item["add_to_cart"] += int(row.get("add_to_cart", 0) or 0)
        item["orders_count"] += int(row.get("orders_count", 0) or 0)
        item["visibility_pct_avg"] += float(row.get("visibility_pct", 0.0) or 0.0)
        item["rows_count"] += 1

    out: list[dict[str, Any]] = []
    for item in grouped.values():
        rows_count = int(item.get("rows_count", 0) or 0)
        if rows_count > 0:
            item["visibility_pct_avg"] = round(float(item["visibility_pct_avg"]) / rows_count, 4)
        out.append(item)
    return out


def build_search_queries_summary(rows: list[dict[str, Any]], has_sku_columns: bool = True) -> dict[str, Any]:
    query_agg = _aggregate_by_query(rows)
    if has_sku_columns:
        sku_keys = {
            (str(r.get("seller_sku", "")).strip(), str(r.get("wb_sku", "")).strip())
            for r in rows
            if str(r.get("seller_sku", "")).strip() or str(r.get("wb_sku", "")).strip()
        }
    else:
        sku_keys = set()
    top_no_orders = _top([x for x in query_agg if int(x.get("orders_count", 0) or 0) <= 0], "query_count", 20)
    top_low_visibility = _top(query_agg, "visibility_pct_avg", 20, reverse=False)

    return {
        "total_rows": len(rows),
        "unique_queries": len({str(r.get("query", "")).strip() for r in rows if str(r.get("query", "")).strip()}),
        "unique_skus": len(sku_keys),
        "top_queries_by_query_count": _top(query_agg, "query_count", 20),
        "top_queries_by_clicks": _top(query_agg, "card_clicks", 20),
        "top_queries_by_add_to_cart": _top(query_agg, "add_to_cart", 20),
        "top_queries_with_no_orders": top_no_orders,
        "top_queries_low_visibility": top_low_visibility,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def build_search_queries_by_sku(rows: list[dict[str, Any]], has_sku_columns: bool = True) -> dict[str, Any]:
    if not has_sku_columns:
        return {
            "total_skus": 0,
            "items": [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (str(row.get("seller_sku", "")).strip(), str(row.get("wb_sku", "")).strip())
        if not key[0] and not key[1]:
            continue
        grouped.setdefault(key, []).append(row)

    sku_rows: list[dict[str, Any]] = []
    for (seller_sku, wb_sku), sku_items in grouped.items():
        query_agg = _aggregate_by_query(sku_items)
        sku_rows.append(
            {
                "seller_sku": seller_sku,
                "wb_sku": wb_sku,
                "rows_count": len(sku_items),
                "query_count_total": sum(int(x.get("query_count", 0) or 0) for x in sku_items),
                "clicks_total": sum(int(x.get("card_clicks", 0) or 0) for x in sku_items),
                "add_to_cart_total": sum(int(x.get("add_to_cart", 0) or 0) for x in sku_items),
                "orders_total": sum(int(x.get("orders_count", 0) or 0) for x in sku_items),
                "top_queries": _top(query_agg, "query_count", 10),
            }
        )

    sku_rows = sorted(sku_rows, key=lambda x: x.get("query_count_total", 0), reverse=True)
    return {
        "total_skus": len(sku_rows),
        "items": sku_rows,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
