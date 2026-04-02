"""Decision module entrypoint."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from modules.decisions.decision_engine import build_sku_decisions
from shared.io.json_io import read_json, write_json


def run(seller_path: str | Path) -> dict[str, Any]:
    """Run SKU decisions and write analytics/sku_decisions.json."""
    seller_root = Path(seller_path)
    analytics = seller_root / "analytics"

    abc_path = analytics / "abc_analysis.json"
    profit_path = analytics / "sku_profit.json"
    search_path = analytics / "search_insights.json"
    out_path = analytics / "sku_decisions.json"

    abc_payload = read_json(abc_path) or {}
    profit_payload = read_json(profit_path) or {}
    search_payload = read_json(search_path) or {}

    payload = build_sku_decisions(
        abc_payload=abc_payload if isinstance(abc_payload, dict) else {},
        sku_profit_payload=profit_payload if isinstance(profit_payload, dict) else {},
        search_insights_payload=search_payload if isinstance(search_payload, dict) else {},
    )
    payload["input"] = {
        "abc_path": str(abc_path),
        "sku_profit_path": str(profit_path),
        "search_insights_path": str(search_path),
    }
    write_json(out_path, payload)

    return {
        "status": str(payload.get("status", "ok")),
        "path": str(out_path),
        "items_count": len(payload.get("items") or []),
    }

