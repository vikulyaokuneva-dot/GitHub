from __future__ import annotations

from typing import Any, Dict, Iterable, List


_TRAFFIC_INCREASE_PCTS: tuple[int, int, int] = (10, 20, 30)


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def _extract_sku_rows(metrics: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    if not isinstance(metrics, dict):
        return []
    for key in ("sku_metrics", "items", "skus"):
        rows = metrics.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def simulate_growth(metrics: Dict[str, Any]) -> Dict[str, Any]:
    skus: List[Dict[str, Any]] = []
    growth_rank: List[Dict[str, Any]] = []

    for row in _extract_sku_rows(metrics):
        sku = str(row.get("sku") or "").strip()
        if not sku:
            continue

        orders = _safe_float(row.get("orders"))
        buys = _safe_float(row.get("buys"))
        revenue = _safe_float(row.get("revenue"))
        profit = _safe_float(row.get("profit"))
        _ads_spend = _safe_float(row.get("ads_spend"))
        _ = revenue, _ads_spend

        if orders < 3:
            continue
        if profit <= 0:
            continue

        buyout_rate = (buys / orders) if orders > 0 else 0.0
        profit_per_buy = (profit / buys) if buys > 0 else 0.0

        simulations: List[Dict[str, Any]] = []
        best_delta = float("-inf")

        for traffic_increase_pct in _TRAFFIC_INCREASE_PCTS:
            traffic_multiplier = traffic_increase_pct / 100.0
            new_orders = orders * (1.0 + traffic_multiplier)
            new_buys = new_orders * buyout_rate
            expected_profit = new_buys * profit_per_buy
            profit_delta = expected_profit - profit

            simulations.append(
                {
                    "traffic_increase_pct": traffic_increase_pct,
                    "expected_orders": int(round(new_orders)),
                    "expected_buys": int(round(new_buys)),
                    "expected_profit": round(expected_profit, 2),
                    "profit_delta": round(profit_delta, 2),
                }
            )
            best_delta = max(best_delta, profit_delta)

        skus.append(
            {
                "sku": sku,
                "base_profit": round(profit, 2),
                "simulations": simulations,
            }
        )
        growth_rank.append({"sku": sku, "best_profit_delta": best_delta})

    growth_rank.sort(key=lambda row: (-_safe_float(row.get("best_profit_delta")), str(row.get("sku") or "")))
    top_growth_skus = [str(row.get("sku")) for row in growth_rank[:5] if str(row.get("sku") or "").strip()]

    return {"skus": skus, "top_growth_skus": top_growth_skus}
