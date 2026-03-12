from __future__ import annotations

from typing import Any, Dict, Iterable, Tuple


ALERT_WEIGHTS: Dict[str, int] = {
    "traffic_drop": 8,
    "ctr_drop": 8,
    "cart_conversion_drop": 6,
    "orders_drop": 20,
    "buyout_drop": 16,
    "profit_drop": 22,
    "ad_inefficiency": 12,
    "dead_stock": 18,
    "zero_sales_with_stock": 18,
    "critical_ktr": 15,
    "health_score_drop": 12,
}

STATUS_MULTIPLIER: Dict[str, float] = {
    "critical": 1.6,
    "warning": 1.0,
    "ok": 0.0,
    "unknown": 0.0,
    "not_applicable": 0.0,
}


def calculate_attention_score(alerts: Iterable[Dict[str, Any]]) -> Tuple[int, Dict[str, Any]]:
    raw_score = 0.0
    triggered: list[Dict[str, Any]] = []
    for alert in alerts:
        if not isinstance(alert, dict):
            continue
        alert_type = str(alert.get("type") or "").strip()
        status = str(alert.get("status") or "").strip()
        weight = int(ALERT_WEIGHTS.get(alert_type, 0))
        multiplier = float(STATUS_MULTIPLIER.get(status, 0.0))
        if weight <= 0 or multiplier <= 0:
            continue
        points = weight * multiplier
        raw_score += points
        triggered.append(
            {
                "type": alert_type,
                "status": status,
                "weight": weight,
                "multiplier": multiplier,
                "points": round(points, 2),
            }
        )
    attention_score = int(round(max(0.0, raw_score)))
    return attention_score, {"raw_score": round(raw_score, 2), "triggered": triggered}
