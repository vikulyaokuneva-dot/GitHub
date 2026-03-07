from __future__ import annotations

import json
import os
from typing import Any, Dict, List


def _as_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _extract_sku_metrics(metrics: Any) -> List[Dict[str, Any]]:
    if isinstance(metrics, list):
        return [item for item in metrics if isinstance(item, dict)]
    if isinstance(metrics, dict):
        rows = metrics.get("sku_metrics")
        if isinstance(rows, list):
            return [item for item in rows if isinstance(item, dict)]
    return []


def _profit_class(cumulative_profit_share: float, has_positive_total: bool) -> str:
    if not has_positive_total:
        return "P3"
    if cumulative_profit_share <= 0.80:
        return "P1"
    if cumulative_profit_share <= 0.95:
        return "P2"
    return "P3"


def classify_profit_groups(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = {"p1": [], "p2": [], "p3": []}
    for row in rows:
        label = str(row.get("class") or "").upper()
        if label == "P1":
            groups["p1"].append(row)
        elif label == "P2":
            groups["p2"].append(row)
        else:
            groups["p3"].append(row)
    return groups


def build_profit_contribution(metrics: Dict[str, Any]) -> Dict[str, Any]:
    sku_rows = _extract_sku_metrics(metrics)
    normalized: List[Dict[str, Any]] = []
    for row in sku_rows:
        sku = str(row.get("sku") or "").strip()
        if not sku:
            continue
        normalized.append(
            {
                "sku": sku,
                "profit": round(_as_float(row.get("profit")), 2),
            }
        )

    normalized.sort(key=lambda item: _as_float(item.get("profit")), reverse=True)
    total_profit = sum(_as_float(item.get("profit")) for item in normalized)
    has_positive_total = total_profit > 0

    cumulative = 0.0
    ranked: List[Dict[str, Any]] = []
    for item in normalized:
        profit = _as_float(item.get("profit"))
        if has_positive_total:
            profit_share = profit / total_profit
            cumulative += profit_share
        else:
            profit_share = 0.0
            cumulative = 0.0

        ranked.append(
            {
                "sku": str(item.get("sku") or ""),
                "profit": round(profit, 2),
                "profit_share": round(profit_share, 6),
                "cumulative_profit_share": round(cumulative, 6),
                "class": _profit_class(cumulative, has_positive_total),
            }
        )

    grouped = classify_profit_groups(ranked)
    grouped["top_profit_skus"] = ranked[:5]
    grouped["meta"] = {
        "total_profit": round(total_profit, 2),
        "sku_count": len(ranked),
    }
    return grouped


def save_profit_contribution(output_path: str, data: Dict[str, Any]) -> None:
    directory = os.path.dirname(output_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)

