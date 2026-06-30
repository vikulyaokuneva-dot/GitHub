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
      {"sku": "...", "revenue": number, "profit": number, ...}
    Classification priority: profit > revenue > buyouts+orders.
    """
    normalized: List[Dict[str, Any]] = []
    for item in metrics:
        sku = str(item.get("sku") or "").strip()
        if not sku:
            continue
        revenue = _as_float(item.get("revenue"))
        profit = _as_float(item.get("profit"))
        buys = _as_float(item.get("buys") or item.get("sales_count") or item.get("buyouts_qty"))
        orders = _as_float(item.get("orders"))
        normalized.append({"sku": sku, "revenue": revenue, "profit": profit, "buys": buys, "orders": orders})

    if not normalized:
        return []

    total_profit = sum(row["profit"] for row in normalized)
    total_revenue = sum(row["revenue"] for row in normalized)
    total_buys = sum(max(row["buys"], 0.0) for row in normalized)
    total_orders = sum(max(row["orders"], 0.0) for row in normalized)

    if total_profit > 0:
        basis = "profit"
        metric_total = total_profit
        normalized.sort(key=lambda row: row["profit"], reverse=True)
    elif total_revenue > 0:
        basis = "revenue"
        metric_total = total_revenue
        normalized.sort(key=lambda row: row["revenue"], reverse=True)
    elif total_buys > 0:
        basis = "buys"
        metric_total = total_buys
        normalized.sort(key=lambda row: row["buys"], reverse=True)
    elif total_orders > 0:
        basis = "orders"
        metric_total = total_orders
        normalized.sort(key=lambda row: row["orders"], reverse=True)
    else:
        basis = "none"
        metric_total = 0.0

    result: List[Dict[str, Any]] = []
    cumulative = 0.0
    for row in normalized:
        if basis == "profit":
            value = row["profit"]
        elif basis == "revenue":
            value = row["revenue"]
        elif basis == "buys":
            value = max(row["buys"], 0.0)
        else:
            value = max(row["orders"], 0.0)

        if metric_total > 0:
            share = value / metric_total
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
                "basis": basis,
            }
        )

    return result
