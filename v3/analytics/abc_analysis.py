from __future__ import annotations

from typing import Any, Dict, List


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _abc_class(cumulative_share: float) -> str:
    if cumulative_share <= 0.80:
        return "A"
    if cumulative_share <= 0.95:
        return "B"
    return "C"


def compute_abc(metrics: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Build ABC analysis from SKU metrics list.
    Input item format:
      {"sku": "...", "revenue": number, "profit": number}
    """
    normalized: List[Dict[str, Any]] = []
    for item in metrics:
        sku = str(item.get("sku") or "").strip()
        if not sku:
            continue
        revenue = _as_float(item.get("revenue"))
        profit = _as_float(item.get("profit"))
        normalized.append({"sku": sku, "revenue": revenue, "profit": profit})

    normalized.sort(key=lambda row: row["profit"], reverse=True)
    total_profit = sum(row["profit"] for row in normalized)

    result: List[Dict[str, Any]] = []
    cumulative = 0.0
    for row in normalized:
        if total_profit > 0:
            share = row["profit"] / total_profit
            cumulative += share
            cumulative_share = cumulative
            abc_class = _abc_class(cumulative_share)
        else:
            share = 0.0
            cumulative_share = 0.0
            abc_class = "C"

        result.append(
            {
                "sku": row["sku"],
                "revenue": round(row["revenue"], 2),
                "profit": round(row["profit"], 2),
                "share": round(share, 6),
                "cumulative_share": round(cumulative_share, 6),
                "abc_class": abc_class,
            }
        )

    return result
