"""ABC analysis based on SKU profit layer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


PRELIMINARY_MESSAGE = "ABC рассчитан по предварительным данным (WB финансы не подтверждены)"


def _to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _build_empty(*, status: str, abc_status: str, finance_status: str, profit_status: str, message: str = "") -> dict[str, Any]:
    payload = {
        "status": status,
        "abc_status": abc_status,
        "finance_status": finance_status,
        "profit_status": profit_status,
        "total_skus": 0,
        "total_profit": 0.0,
        "A": [],
        "B": [],
        "C": [],
        "loss_makers": [],
        "low_margin": [],
        "excluded_items": [],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "abc_module",
    }
    if message:
        payload["message"] = message
    return payload


def build_abc_analysis(sku_profit: dict[str, Any]) -> dict[str, Any]:
    """Build ABC analysis strictly from sku_profit items (profit-based)."""
    if not isinstance(sku_profit, dict):
        return _build_empty(
            status="ok",
            abc_status="final",
            finance_status="missing",
            profit_status="preliminary",
            message="sku_profit payload is missing or invalid; safe-mode output",
        )

    finance_status = str(sku_profit.get("finance_status") or "missing")
    profit_status = str(sku_profit.get("profit_status") or "preliminary")
    abc_status = "preliminary" if profit_status == "preliminary" else "final"

    raw_items = _as_list(sku_profit.get("items"))
    excluded_items: list[dict[str, Any]] = []
    valid_rows: list[dict[str, Any]] = []

    for row in raw_items:
        if not isinstance(row, dict):
            continue
        sku = str(row.get("sku") or "").strip()
        cogs_unit = row.get("cogs_unit")
        revenue = _to_float(row.get("revenue_total"))
        profit = _to_float(row.get("profit"))
        margin_pct = _to_float(row.get("margin_pct"))

        if cogs_unit is None:
            excluded_items.append({"sku": sku, "reason": "no_cogs"})
            continue
        if revenue is None or revenue <= 0:
            excluded_items.append({"sku": sku, "reason": "no_revenue"})
            continue
        if profit is None:
            excluded_items.append({"sku": sku, "reason": "profit_null"})
            continue

        valid_rows.append(
            {
                "sku": sku,
                "profit": float(profit),
                "revenue": float(revenue),
                "margin_pct": margin_pct if margin_pct is not None else 0.0,
            }
        )

    if not valid_rows:
        result = _build_empty(
            status="ok",
            abc_status=abc_status,
            finance_status=finance_status,
            profit_status=profit_status,
            message="No eligible SKU rows for ABC",
        )
        result["excluded_items"] = excluded_items
        if abc_status == "preliminary":
            result["abc_message"] = PRELIMINARY_MESSAGE
        return result

    valid_rows.sort(key=lambda r: float(r.get("profit", 0.0)), reverse=True)
    total_profit = round(sum(float(r.get("profit", 0.0)) for r in valid_rows), 2)

    if total_profit <= 0:
        result = _build_empty(
            status="no_positive_profit",
            abc_status=abc_status,
            finance_status=finance_status,
            profit_status=profit_status,
            message="Total profit is <= 0; ABC shares are not calculated",
        )
        result["excluded_items"] = excluded_items
        result["loss_makers"] = [
            {
                "sku": str(r.get("sku", "")),
                "profit": round(float(r.get("profit", 0.0)), 2),
                "revenue": round(float(r.get("revenue", 0.0)), 2),
            }
            for r in valid_rows
            if float(r.get("profit", 0.0)) < 0
        ]
        result["low_margin"] = [
            {
                "sku": str(r.get("sku", "")),
                "profit": round(float(r.get("profit", 0.0)), 2),
                "margin_pct": round(float(r.get("margin_pct", 0.0)), 2),
            }
            for r in valid_rows
            if float(r.get("margin_pct", 0.0)) < 10.0
        ]
        result["total_skus"] = len(valid_rows)
        result["total_profit"] = total_profit
        if abc_status == "preliminary":
            result["abc_message"] = PRELIMINARY_MESSAGE
        return result

    cumulative = 0.0
    A: list[dict[str, Any]] = []
    B: list[dict[str, Any]] = []
    C: list[dict[str, Any]] = []

    for row in valid_rows:
        profit = float(row.get("profit", 0.0))
        revenue = float(row.get("revenue", 0.0))
        share = profit / total_profit
        cumulative += share

        if cumulative <= 0.80:
            category = "A"
        elif cumulative <= 0.95:
            category = "B"
        else:
            category = "C"

        item = {
            "sku": str(row.get("sku", "")),
            "profit": round(profit, 2),
            "revenue": round(revenue, 2),
            "profit_share": round(share, 6),
            "cumulative_share": round(cumulative, 6),
            "category": category,
        }
        if category == "A":
            A.append(item)
        elif category == "B":
            B.append(item)
        else:
            C.append(item)

    loss_makers = [
        {"sku": str(r.get("sku", "")), "profit": round(float(r.get("profit", 0.0)), 2)}
        for r in valid_rows
        if float(r.get("profit", 0.0)) < 0
    ]
    low_margin = [
        {
            "sku": str(r.get("sku", "")),
            "profit": round(float(r.get("profit", 0.0)), 2),
            "margin_pct": round(float(r.get("margin_pct", 0.0)), 2),
        }
        for r in valid_rows
        if float(r.get("margin_pct", 0.0)) < 10.0
    ]

    result = {
        "status": "ok",
        "abc_status": abc_status,
        "finance_status": finance_status,
        "profit_status": profit_status,
        "total_skus": len(valid_rows),
        "total_profit": total_profit,
        "A": A,
        "B": B,
        "C": C,
        "loss_makers": loss_makers,
        "low_margin": low_margin,
        "excluded_items": excluded_items,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "abc_module",
    }
    if abc_status == "preliminary":
        result["abc_message"] = PRELIMINARY_MESSAGE
    return result

