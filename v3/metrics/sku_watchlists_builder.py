from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int:
    parsed = _safe_float(value)
    if parsed is None:
        return 0
    return int(round(parsed))


def _as_items(payload: Any, key: str = "items") -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get(key, [])
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _alert_map(alerts_payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    rows = _as_items(alerts_payload, "items")
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        sku = str(row.get("sku") or "").strip()
        if not sku:
            continue
        out[sku] = row
    return out


def _dynamics_map(dynamics_payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    rows = _as_items(dynamics_payload, "items")
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        sku = str(row.get("sku") or "").strip()
        if not sku:
            continue
        out[sku] = row
    return out


def _logistics_map(logistics_payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    rows = _as_items(logistics_payload, "skus")
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        sku = str(row.get("sku") or "").strip()
        if not sku:
            continue
        out[sku] = row
    return out


def _find_alert(alert_item: Dict[str, Any], alert_type: str) -> Dict[str, Any]:
    rows = alert_item.get("alerts", [])
    if not isinstance(rows, list):
        return {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("type") or "").strip() == alert_type:
            return row
    return {}


def _is_alert_active(alert_item: Dict[str, Any], alert_type: str) -> bool:
    status = str(_find_alert(alert_item, alert_type).get("status") or "").strip()
    return status in {"warning", "critical"}


def _delta_7d(item: Dict[str, Any], metric: str) -> float | None:
    vs_7d = item.get("vs_7d_avg", {})
    if not isinstance(vs_7d, dict):
        return None
    payload = vs_7d.get(metric, {})
    if not isinstance(payload, dict):
        return None
    return _safe_float(payload.get("delta_pct"))


def _delta_prev(item: Dict[str, Any], metric: str) -> float | None:
    vs_prev = item.get("vs_previous_day", {})
    if not isinstance(vs_prev, dict):
        return None
    payload = vs_prev.get(metric, {})
    if not isinstance(payload, dict):
        return None
    return _safe_float(payload.get("delta_pct"))


def _watch_record(
    *,
    sku: str,
    dynamics_item: Dict[str, Any],
    alert_item: Dict[str, Any],
    reason: str,
) -> Dict[str, Any]:
    orders = _safe_float(dynamics_item.get("orders"))
    buyouts = _safe_float(dynamics_item.get("buyouts"))
    revenue = _safe_float(dynamics_item.get("revenue"))
    net_profit = _safe_float(dynamics_item.get("net_profit"))
    stock = _safe_float(dynamics_item.get("stock"))
    attention = _safe_int(alert_item.get("attention_score"))
    return {
        "sku": sku,
        "attention_score": attention,
        "reason": reason,
        "metrics": {
            "orders": orders,
            "buyouts": buyouts,
            "revenue": revenue,
            "net_profit": net_profit,
            "stock": stock,
        },
        "deltas": {
            "orders_vs_prev_pct": _delta_prev(dynamics_item, "orders"),
            "orders_vs_7d_pct": _delta_7d(dynamics_item, "orders"),
            "buyouts_vs_prev_pct": _delta_prev(dynamics_item, "buyouts"),
            "buyouts_vs_7d_pct": _delta_7d(dynamics_item, "buyouts"),
            "revenue_vs_7d_pct": _delta_7d(dynamics_item, "revenue"),
            "net_profit_vs_7d_pct": _delta_7d(dynamics_item, "net_profit"),
        },
    }


def _top_n(rows: Iterable[Dict[str, Any]], *, n: int = 5, sort_key=None) -> List[Dict[str, Any]]:
    clean = [row for row in rows if isinstance(row, dict)]
    if sort_key is None:
        sort_key = lambda x: (
            -int(x.get("attention_score", 0) or 0),
            str(x.get("sku") or ""),
        )
    clean.sort(key=sort_key)
    return clean[: max(0, int(n))]


def _build_top_growth(
    dynamics_by_sku: Dict[str, Dict[str, Any]],
    alerts_by_sku: Dict[str, Dict[str, Any]],
    *,
    limit: int,
) -> List[Dict[str, Any]]:
    candidates: List[Tuple[float, Dict[str, Any]]] = []
    for sku, dynamics_item in dynamics_by_sku.items():
        if not isinstance(dynamics_item, dict):
            continue
        alert_item = alerts_by_sku.get(sku, {})
        if not isinstance(alert_item, dict):
            alert_item = {}
        deltas = [
            _delta_7d(dynamics_item, "orders"),
            _delta_7d(dynamics_item, "buyouts"),
            _delta_7d(dynamics_item, "revenue"),
            _delta_7d(dynamics_item, "net_profit"),
        ]
        valid_deltas = [float(value) for value in deltas if value is not None and value > 0]
        if not valid_deltas:
            continue
        growth_score = sum(valid_deltas)
        attention = _safe_int(alert_item.get("attention_score"))
        # Growth list should prefer strong positive deltas and lower risk.
        ranking_score = growth_score - float(attention) * 0.25
        reason = "Рост относительно 7d baseline"
        record = _watch_record(
            sku=sku,
            dynamics_item=dynamics_item,
            alert_item=alert_item,
            reason=reason,
        )
        record["growth_score"] = round(growth_score, 2)
        candidates.append((ranking_score, record))

    candidates.sort(key=lambda item: (-item[0], str((item[1] or {}).get("sku") or "")))
    out = [row for _, row in candidates[: max(0, int(limit))]]
    for row in out:
        row.pop("growth_score", None)
    return out


def _build_top_risk(
    dynamics_by_sku: Dict[str, Dict[str, Any]],
    alerts_by_sku: Dict[str, Dict[str, Any]],
    *,
    limit: int,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for sku, alert_item in alerts_by_sku.items():
        attention = _safe_int(alert_item.get("attention_score"))
        if attention <= 0:
            continue
        dynamics_item = dynamics_by_sku.get(sku, {})
        reason = "Высокий attention_score по совокупности сигналов"
        rows.append(
            _watch_record(
                sku=sku,
                dynamics_item=dynamics_item if isinstance(dynamics_item, dict) else {},
                alert_item=alert_item,
                reason=reason,
            )
        )
    return _top_n(rows, n=limit)


def _build_alert_type_watchlist(
    *,
    dynamics_by_sku: Dict[str, Dict[str, Any]],
    alerts_by_sku: Dict[str, Dict[str, Any]],
    alert_types: Tuple[str, ...],
    reason: str,
    limit: int,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for sku, alert_item in alerts_by_sku.items():
        if not isinstance(alert_item, dict):
            continue
        if not any(_is_alert_active(alert_item, alert_type) for alert_type in alert_types):
            continue
        dynamics_item = dynamics_by_sku.get(sku, {})
        rows.append(
            _watch_record(
                sku=sku,
                dynamics_item=dynamics_item if isinstance(dynamics_item, dict) else {},
                alert_item=alert_item,
                reason=reason,
            )
        )
    return _top_n(rows, n=limit)


def _build_logistics_risk(
    *,
    dynamics_by_sku: Dict[str, Dict[str, Any]],
    alerts_by_sku: Dict[str, Dict[str, Any]],
    logistics_by_sku: Dict[str, Dict[str, Any]],
    limit: int,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    pool = set(logistics_by_sku.keys()) | set(alerts_by_sku.keys())
    for sku in pool:
        logistics_item = logistics_by_sku.get(sku, {})
        alert_item = alerts_by_sku.get(sku, {})
        status = str(logistics_item.get("logistics_efficiency_status") or "").strip().lower()
        ktr = _safe_float(logistics_item.get("ktr"))
        has_logistics_risk = status in {"critical", "inefficient"} or (ktr is not None and ktr >= 1.25)
        has_alert_risk = _is_alert_active(alert_item, "critical_ktr")
        if not has_logistics_risk and not has_alert_risk:
            continue
        dynamics_item = dynamics_by_sku.get(sku, {})
        reason = "Риск по KTR/логистике"
        record = _watch_record(
            sku=sku,
            dynamics_item=dynamics_item if isinstance(dynamics_item, dict) else {},
            alert_item=alert_item if isinstance(alert_item, dict) else {},
            reason=reason,
        )
        if ktr is not None:
            record["ktr"] = round(float(ktr), 3)
        rows.append(record)
    return _top_n(rows, n=limit)


def build_sku_watchlists(
    *,
    run_date: str,
    sku_daily_dynamics: Dict[str, Any],
    sku_alerts: Dict[str, Any],
    logistics_ktr: Dict[str, Any] | None = None,
    limit_per_group: int = 5,
) -> Dict[str, Any]:
    limit = max(1, int(limit_per_group))
    dynamics_by_sku = _dynamics_map(sku_daily_dynamics if isinstance(sku_daily_dynamics, dict) else {})
    alerts_by_sku = _alert_map(sku_alerts if isinstance(sku_alerts, dict) else {})
    logistics_by_sku = _logistics_map(logistics_ktr if isinstance(logistics_ktr, dict) else {})

    watchlists = {
        "top_growth": _build_top_growth(
            dynamics_by_sku=dynamics_by_sku,
            alerts_by_sku=alerts_by_sku,
            limit=limit,
        ),
        "top_risk": _build_top_risk(
            dynamics_by_sku=dynamics_by_sku,
            alerts_by_sku=alerts_by_sku,
            limit=limit,
        ),
        "dead_stock": _build_alert_type_watchlist(
            dynamics_by_sku=dynamics_by_sku,
            alerts_by_sku=alerts_by_sku,
            alert_types=("dead_stock", "zero_sales_with_stock"),
            reason="Риск зависших остатков",
            limit=limit,
        ),
        "ad_inefficiency": _build_alert_type_watchlist(
            dynamics_by_sku=dynamics_by_sku,
            alerts_by_sku=alerts_by_sku,
            alert_types=("ad_inefficiency",),
            reason="Риск неэффективной рекламы",
            limit=limit,
        ),
        "conversion_drop": _build_alert_type_watchlist(
            dynamics_by_sku=dynamics_by_sku,
            alerts_by_sku=alerts_by_sku,
            alert_types=("orders_drop", "buyout_drop", "ctr_drop", "cart_conversion_drop"),
            reason="Падение конверсии/продажной воронки",
            limit=limit,
        ),
        "logistics_risk": _build_logistics_risk(
            dynamics_by_sku=dynamics_by_sku,
            alerts_by_sku=alerts_by_sku,
            logistics_by_sku=logistics_by_sku,
            limit=limit,
        ),
    }
    return {
        "date": str(run_date or ""),
        "watchlists": watchlists,
    }

