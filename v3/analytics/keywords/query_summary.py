from __future__ import annotations

from typing import Any, Dict, List

from .query_classifier import QUERY_STATUSES


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _top_queries(rows: List[Dict[str, Any]], field: str, limit: int = 5) -> List[Dict[str, Any]]:
    sorted_rows = sorted(
        [row for row in rows if isinstance(row, dict)],
        key=lambda item: (_safe_float(item.get(field)), str(item.get("query") or "")),
        reverse=True,
    )
    out: List[Dict[str, Any]] = []
    for row in sorted_rows[:limit]:
        out.append(
            {
                "query": str(row.get("query") or ""),
                field: row.get(field),
                "query_status": str(row.get("query_status") or "insufficient_data"),
            }
        )
    return out


def _resolve_keyword_health_status(summary: Dict[str, Any]) -> str:
    winners = int(summary.get("winner_queries_count", 0) or 0)
    growth = int(summary.get("growth_queries_count", 0) or 0)
    weak = int(summary.get("weak_queries_count", 0) or 0)
    costly = int(summary.get("costly_queries_count", 0) or 0)
    total = int(summary.get("query_count", 0) or 0)

    if total <= 0:
        return "insufficient_data"
    if costly > 0 or weak > winners:
        return "risk"
    if winners > 0 and growth > 0 and weak == 0:
        return "strong"
    if winners > 0:
        return "healthy"
    return "unstable"


def build_sku_keyword_summaries(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_sku: Dict[str, List[Dict[str, Any]]] = {}
    for row in items:
        if not isinstance(row, dict):
            continue
        sku = str(row.get("sku") or "").strip()
        if not sku:
            continue
        by_sku.setdefault(sku, []).append(row)

    out: List[Dict[str, Any]] = []
    weak_types = {"low_conversion", "low_relevance", "traffic_only", "no_orders"}

    for sku, rows in sorted(by_sku.items(), key=lambda item: str(item[0])):
        status_counts = {status: 0 for status in QUERY_STATUSES}
        for row in rows:
            status = str(row.get("query_status") or "insufficient_data")
            if status not in status_counts:
                status = "insufficient_data"
            status_counts[status] += 1

        sku_summary = {
            "sku": sku,
            "query_count": len(rows),
            "winner_queries_count": int(status_counts.get("winner", 0)),
            "growth_queries_count": int(status_counts.get("growth_opportunity", 0)),
            "weak_queries_count": sum(int(status_counts.get(key, 0)) for key in weak_types),
            "costly_queries_count": int(status_counts.get("costly", 0)),
            "top_queries_by_impressions": _top_queries(rows, "impressions", limit=5),
            "top_queries_by_orders": _top_queries(rows, "orders", limit=5),
            "top_queries_by_spend": _top_queries(rows, "spend", limit=5),
            "top_problem_queries": [
                {
                    "query": str(row.get("query") or ""),
                    "query_status": str(row.get("query_status") or "insufficient_data"),
                }
                for row in rows
                if str(row.get("query_status") or "insufficient_data") in weak_types.union({"costly"})
            ][:5],
            "warnings": [],
        }
        sku_summary["keyword_health_status"] = _resolve_keyword_health_status(sku_summary)
        out.append(sku_summary)

    return out


def build_keyword_global_summary(
    query_items: List[Dict[str, Any]],
    sku_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    status_counts = {status: 0 for status in QUERY_STATUSES}
    for row in query_items:
        if not isinstance(row, dict):
            continue
        status = str(row.get("query_status") or "insufficient_data")
        if status not in status_counts:
            status = "insufficient_data"
        status_counts[status] += 1

    winner_count = int(status_counts.get("winner", 0))
    growth_count = int(status_counts.get("growth_opportunity", 0))
    low_relevance_count = int(status_counts.get("low_relevance", 0))
    no_orders_count = int(status_counts.get("no_orders", 0))
    costly_count = int(status_counts.get("costly", 0))

    return {
        "sku_count_with_keywords": len([row for row in sku_items if isinstance(row, dict)]),
        "total_query_count": len([row for row in query_items if isinstance(row, dict)]),
        "winner_query_count": winner_count,
        "growth_query_count": growth_count,
        "low_relevance_query_count": low_relevance_count,
        "no_orders_query_count": no_orders_count,
        "costly_query_count": costly_count,
        "top_global_queries_by_impressions": _top_queries(query_items, "impressions", limit=10),
        "top_global_queries_by_orders": _top_queries(query_items, "orders", limit=10),
        "top_global_problem_queries": [
            {
                "sku": str(row.get("sku") or ""),
                "query": str(row.get("query") or ""),
                "query_status": str(row.get("query_status") or "insufficient_data"),
            }
            for row in query_items
            if str(row.get("query_status") or "insufficient_data") in {"low_relevance", "low_conversion", "no_orders", "traffic_only", "costly"}
        ][:12],
        "query_status_counts": status_counts,
    }
