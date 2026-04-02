"""Search insights step built on top of search_queries analytics artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from modules.search_queries.insights import build_search_insights
from shared.io.json_io import read_json, write_json


def run_search_insights(seller: str) -> dict[str, Any]:
    """Build and persist search insights for seller."""
    seller_root = Path("runtime") / "cabinets" / seller
    analytics_dir = seller_root / "analytics"
    summary_path = analytics_dir / "search_queries_summary.json"
    by_sku_path = analytics_dir / "search_queries_by_sku.json"
    out_path = analytics_dir / "search_insights.json"

    summary = read_json(summary_path) or {}
    by_sku = read_json(by_sku_path) or {}
    insights = build_search_insights(summary, by_sku)
    if not isinstance(insights, dict):
        insights = {
            "status": "ok",
            "profitable_queries": [],
            "wasted_traffic": [],
            "low_visibility_high_demand": [],
            "generated_at": "",
            "source": "search_queries",
        }
    write_json(out_path, insights)
    return {
        "status": str(insights.get("status", "ok")),
        "path": str(out_path),
    }

