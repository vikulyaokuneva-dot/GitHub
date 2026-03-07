from __future__ import annotations

from typing import Any, Dict, Iterable, List


_ABC_WEIGHTS: Dict[str, float] = {
    "A": 1.2,
    "B": 1.0,
    "C": 0.7,
}

_HEALTH_WEIGHTS: Dict[str, float] = {
    "SCALE": 1.3,
    "FIX": 0.9,
    "WATCH": 0.8,
    "LIQUIDATE": 0.3,
}

_MIN_ORDERS = 2.0
_TOP_IDS = 5


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def _extract_metric_rows(metrics: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    if not isinstance(metrics, dict):
        return []
    for key in ("sku_metrics", "items", "skus"):
        rows = metrics.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _abc_by_sku(abc_rows: List[Dict[str, Any]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not isinstance(abc_rows, list):
        return out
    for row in abc_rows:
        if not isinstance(row, dict):
            continue
        sku = str(row.get("sku") or "").strip()
        if not sku:
            continue
        cls = str(row.get("abc_class") or "").strip().upper()
        out[sku] = cls
    return out


def _health_by_sku(health_payload: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not isinstance(health_payload, dict):
        return out

    for key in ("items", "skus"):
        rows = health_payload.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            sku = str(row.get("sku") or "").strip()
            if not sku:
                continue
            status = str(row.get("status") or row.get("health_status") or "").strip().upper()
            if status:
                out[sku] = status
    return out


def compute_opportunity_scores(
    metrics: Dict[str, Any],
    abc_rows: List[Dict[str, Any]],
    health_payload: Dict[str, Any],
) -> Dict[str, Any]:
    abc_map = _abc_by_sku(abc_rows)
    health_map = _health_by_sku(health_payload)

    opportunities: List[Dict[str, Any]] = []
    for row in _extract_metric_rows(metrics):
        sku = str(row.get("sku") or "").strip()
        if not sku:
            continue

        orders = _safe_float(row.get("orders"))
        if orders < _MIN_ORDERS:
            continue

        revenue = _safe_float(row.get("revenue"))
        profit = _safe_float(row.get("profit"))
        buys = _safe_float(row.get("buys"))

        margin_pct = (profit / revenue) if revenue > 0 else 0.0
        if margin_pct <= 0:
            continue

        buyout_rate = (buys / orders) if orders > 0 else 0.0

        abc_class = abc_map.get(sku, "B")
        abc_weight = _ABC_WEIGHTS.get(abc_class, 1.0)

        health_status = health_map.get(sku, "WATCH")
        health_weight = _HEALTH_WEIGHTS.get(health_status, 1.0)

        score = margin_pct * buyout_rate * abc_weight * health_weight

        opportunities.append(
            {
                "sku": sku,
                "score": round(score, 6),
                "profit": round(profit, 2),
                "margin_pct": round(margin_pct, 6),
                "abc_class": abc_class,
                "health_status": health_status,
            }
        )

    opportunities.sort(key=lambda item: (-_safe_float(item.get("score")), str(item.get("sku") or "")))
    top_opportunities = [
        str(row.get("sku")) for row in opportunities[:_TOP_IDS] if str(row.get("sku") or "").strip()
    ]

    return {
        "opportunities": opportunities,
        "top_opportunities": top_opportunities,
    }
