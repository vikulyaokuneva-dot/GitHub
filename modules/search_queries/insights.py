"""Business insights for search queries analytics."""

from __future__ import annotations

from datetime import datetime, timezone
from statistics import median
from typing import Any


def _to_int(value: Any) -> int:
    try:
        if value is None:
            return 0
        return int(round(float(value)))
    except Exception:
        return 0


def _to_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def _iter_query_rows(summary: dict[str, Any], by_sku: dict[str, Any]) -> list[dict[str, Any]]:
    """Build merged query-level rows from summary and by_sku artifacts."""
    merged: dict[str, dict[str, Any]] = {}

    def touch(query: str) -> dict[str, Any]:
        return merged.setdefault(
            query,
            {
                "query": query,
                "query_count": 0,
                "card_clicks": 0,
                "add_to_cart": 0,
                "orders_count": 0,
                "visibility_pct_avg": 0.0,
                "rows_count": 0,
                "_visibility_weighted_sum": 0.0,
            },
        )

    summary_lists = (
        summary.get("top_queries_by_query_count") or [],
        summary.get("top_queries_by_clicks") or [],
        summary.get("top_queries_by_add_to_cart") or [],
        summary.get("top_queries_with_no_orders") or [],
        summary.get("top_queries_low_visibility") or [],
    )

    for rows in summary_lists:
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            query = str(row.get("query", "")).strip()
            if not query:
                continue
            target = touch(query)
            target["query_count"] = max(target["query_count"], _to_int(row.get("query_count")))
            target["card_clicks"] = max(target["card_clicks"], _to_int(row.get("card_clicks")))
            target["add_to_cart"] = max(target["add_to_cart"], _to_int(row.get("add_to_cart")))
            target["orders_count"] = max(target["orders_count"], _to_int(row.get("orders_count")))

            v = _to_float(row.get("visibility_pct_avg", row.get("visibility_pct")))
            if v > 0:
                target["visibility_pct_avg"] = max(target["visibility_pct_avg"], v)
                target["_visibility_weighted_sum"] = max(target["_visibility_weighted_sum"], v)
                target["rows_count"] = max(target["rows_count"], _to_int(row.get("rows_count")) or 1)

    # Fallback enrichment from by_sku when a query was not present in summary top blocks.
    items = by_sku.get("items") or []
    if isinstance(items, list):
        for sku_item in items:
            if not isinstance(sku_item, dict):
                continue
            top_queries = sku_item.get("top_queries") or []
            if not isinstance(top_queries, list):
                continue
            for row in top_queries:
                if not isinstance(row, dict):
                    continue
                query = str(row.get("query", "")).strip()
                if not query:
                    continue
                target = touch(query)
                # For by_sku values we sum to recover query-level signal as close as possible.
                target["query_count"] += _to_int(row.get("query_count"))
                target["card_clicks"] += _to_int(row.get("card_clicks"))
                target["add_to_cart"] += _to_int(row.get("add_to_cart"))
                target["orders_count"] += _to_int(row.get("orders_count"))
                row_weight = _to_int(row.get("rows_count")) or 1
                target["_visibility_weighted_sum"] += _to_float(row.get("visibility_pct_avg")) * row_weight
                target["rows_count"] += row_weight

    result: list[dict[str, Any]] = []
    for row in merged.values():
        rows_count = _to_int(row.get("rows_count"))
        if rows_count > 0:
            weighted = _to_float(row.get("_visibility_weighted_sum"))
            # Preserve the stronger signal from summary tops if it exists.
            candidate = weighted / rows_count if weighted > 0 else 0.0
            row["visibility_pct_avg"] = round(max(_to_float(row.get("visibility_pct_avg")), candidate), 4)
        row.pop("_visibility_weighted_sum", None)
        result.append(row)
    return result


def _build_profitable_queries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matched = [
        row
        for row in rows
        if _to_int(row.get("card_clicks")) > 0
        and _to_int(row.get("add_to_cart")) > 0
        and _to_int(row.get("orders_count")) == 0
    ]
    matched.sort(key=lambda x: (_to_int(x.get("add_to_cart")), _to_int(x.get("card_clicks"))), reverse=True)
    out: list[dict[str, Any]] = []
    for row in matched[:10]:
        out.append(
            {
                "query": str(row.get("query", "")).strip(),
                "clicks": _to_int(row.get("card_clicks")),
                "add_to_cart": _to_int(row.get("add_to_cart")),
                "orders": _to_int(row.get("orders_count")),
                "visibility": round(_to_float(row.get("visibility_pct_avg")), 4),
                "recommendation": "Высокий интерес, нет заказов — проверить карточку (цена, фото, отзывы)",
            }
        )
    return out


def _build_wasted_traffic(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matched = [
        row
        for row in rows
        if _to_int(row.get("card_clicks")) > 0
        and _to_int(row.get("add_to_cart")) == 0
        and _to_int(row.get("orders_count")) == 0
    ]
    matched.sort(key=lambda x: _to_int(x.get("card_clicks")), reverse=True)
    out: list[dict[str, Any]] = []
    for row in matched[:10]:
        out.append(
            {
                "query": str(row.get("query", "")).strip(),
                "clicks": _to_int(row.get("card_clicks")),
                "visibility": round(_to_float(row.get("visibility_pct_avg")), 4),
                "recommendation": "Есть клики, но нет интереса — возможно нерелевантный запрос или плохой CTR карточки",
            }
        )
    return out


def _percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    idx = int(round((len(ordered) - 1) * fraction))
    idx = max(0, min(idx, len(ordered) - 1))
    return ordered[idx]


def _build_low_visibility_high_demand(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    query_counts = [_to_int(row.get("query_count")) for row in rows if _to_int(row.get("query_count")) > 0]
    if not query_counts:
        return []
    median_threshold = int(median(query_counts))
    p70_threshold = _percentile(query_counts, 0.7)
    high_demand_threshold = max(median_threshold, p70_threshold)

    matched = [
        row
        for row in rows
        if _to_int(row.get("query_count")) >= high_demand_threshold
        and _to_float(row.get("visibility_pct_avg")) < 30.0
    ]
    matched.sort(key=lambda x: _to_int(x.get("query_count")), reverse=True)
    out: list[dict[str, Any]] = []
    for row in matched[:10]:
        out.append(
            {
                "query": str(row.get("query", "")).strip(),
                "query_count": _to_int(row.get("query_count")),
                "visibility": round(_to_float(row.get("visibility_pct_avg")), 4),
                "recommendation": "Высокий спрос, но низкая видимость — нужно усиливать SEO или рекламу",
            }
        )
    return out


def build_search_insights(summary: dict[str, Any], by_sku: dict[str, Any]) -> dict[str, Any]:
    """Build business insights from prepared search queries artifacts."""
    try:
        rows = _iter_query_rows(summary if isinstance(summary, dict) else {}, by_sku if isinstance(by_sku, dict) else {})
        result = {
            "status": "ok",
            "profitable_queries": _build_profitable_queries(rows),
            "wasted_traffic": _build_wasted_traffic(rows),
            "low_visibility_high_demand": _build_low_visibility_high_demand(rows),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "search_queries",
        }
        return result
    except Exception as exc:  # pragma: no cover
        return {
            "status": "ok",
            "profitable_queries": [],
            "wasted_traffic": [],
            "low_visibility_high_demand": [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "search_queries",
            "message": f"safe_mode_fallback: {exc}",
        }

