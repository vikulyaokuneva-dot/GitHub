"""ABC module entrypoint."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from modules.abc.abc_engine import build_abc_analysis
from shared.io.json_io import read_json, write_json


def run(seller_path: str | Path) -> dict[str, Any]:
    """Run ABC analysis based on analytics/sku_profit.json."""
    seller_root = Path(seller_path)
    analytics = seller_root / "analytics"
    in_path = analytics / "sku_profit.json"
    out_path = analytics / "abc_analysis.json"

    sku_profit = read_json(in_path)
    payload = build_abc_analysis(sku_profit if isinstance(sku_profit, dict) else {})
    payload["input"] = {"sku_profit_path": str(in_path)}
    write_json(out_path, payload)

    return {
        "status": str(payload.get("status", "ok")),
        "path": str(out_path),
        "a_count": len(payload.get("A") or []),
        "b_count": len(payload.get("B") or []),
        "c_count": len(payload.get("C") or []),
        "excluded_count": len(payload.get("excluded_items") or []),
    }

