from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .sku_attention_score import calculate_attention_score


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct_change(current: float | None, baseline: float | None) -> float | None:
    if current is None or baseline is None:
        return None
    if abs(float(baseline)) <= 1e-9:
        if abs(float(current)) <= 1e-9:
            return 0.0
        return None
    return round((float(current) - float(baseline)) / abs(float(baseline)) * 100.0, 2)


def _metric_snapshot(item: Dict[str, Any], metric: str) -> Dict[str, float | None]:
    current = _safe_float(item.get(metric))
    vs_previous = item.get("vs_previous_day", {})
    if not isinstance(vs_previous, dict):
        vs_previous = {}
    vs_7d = item.get("vs_7d_avg", {})
    if not isinstance(vs_7d, dict):
        vs_7d = {}

    prev_payload = vs_previous.get(metric, {})
    if not isinstance(prev_payload, dict):
        prev_payload = {}
    avg_payload = vs_7d.get(metric, {})
    if not isinstance(avg_payload, dict):
        avg_payload = {}

    previous = _safe_float(prev_payload.get("previous"))
    avg_7d = _safe_float(avg_payload.get("avg_7d"))
    delta_prev_pct = _safe_float(prev_payload.get("delta_pct"))
    delta_7d_pct = _safe_float(avg_payload.get("delta_pct"))
    if delta_prev_pct is None:
        delta_prev_pct = _pct_change(current, previous)
    if delta_7d_pct is None:
        delta_7d_pct = _pct_change(current, avg_7d)

    return {
        "current": current,
        "previous": previous,
        "avg_7d": avg_7d,
        "delta_prev_pct": delta_prev_pct,
        "delta_7d_pct": delta_7d_pct,
    }


def _drop_status(delta_prev_pct: float | None, delta_7d_pct: float | None, warning_threshold: float, critical_threshold: float) -> str:
    deltas = [value for value in (delta_prev_pct, delta_7d_pct) if value is not None]
    if not deltas:
        return "unknown"
    strongest_drop = min(float(value) for value in deltas)
    if strongest_drop <= critical_threshold:
        return "critical"
    if strongest_drop <= warning_threshold:
        return "warning"
    return "ok"


def _build_single_metric_drop_alert(
    *,
    alert_type: str,
    metric: str,
    item: Dict[str, Any],
    warning_threshold: float,
    critical_threshold: float,
    label: str,
) -> Dict[str, Any]:
    snapshot = _metric_snapshot(item, metric)
    status = _drop_status(
        snapshot.get("delta_prev_pct"),
        snapshot.get("delta_7d_pct"),
        warning_threshold=warning_threshold,
        critical_threshold=critical_threshold,
    )
    if status == "unknown":
        reason = f"Недостаточно данных по {label} для сравнения."
    elif status == "critical":
        reason = f"Резкое падение {label} относительно предыдущего дня/7d."
    elif status == "warning":
        reason = f"Снижение {label} относительно предыдущего дня/7d."
    else:
        reason = f"{label} без критичного снижения."

    return {
        "type": alert_type,
        "status": status,
        "reason": reason,
        "current_value": snapshot.get("current"),
        "previous_day": snapshot.get("previous"),
        "rolling_7d_avg": snapshot.get("avg_7d"),
        "delta_vs_prev_pct": snapshot.get("delta_prev_pct"),
        "delta_vs_7d_pct": snapshot.get("delta_7d_pct"),
    }


def _build_traffic_drop_alert(item: Dict[str, Any]) -> Dict[str, Any]:
    impressions = _metric_snapshot(item, "impressions")
    clicks = _metric_snapshot(item, "clicks")
    delta_prev_candidates = [
        value
        for value in (impressions.get("delta_prev_pct"), clicks.get("delta_prev_pct"))
        if value is not None
    ]
    delta_7d_candidates = [
        value
        for value in (impressions.get("delta_7d_pct"), clicks.get("delta_7d_pct"))
        if value is not None
    ]
    delta_prev_pct = min(delta_prev_candidates) if delta_prev_candidates else None
    delta_7d_pct = min(delta_7d_candidates) if delta_7d_candidates else None
    status = _drop_status(
        delta_prev_pct,
        delta_7d_pct,
        warning_threshold=-30.0,
        critical_threshold=-60.0,
    )
    if status == "unknown":
        reason = "Нет достаточных данных по трафику (показы/клики)."
    elif status == "critical":
        reason = "Критичное падение трафика по SKU."
    elif status == "warning":
        reason = "Наблюдается снижение трафика по SKU."
    else:
        reason = "Снижение трафика не обнаружено."

    return {
        "type": "traffic_drop",
        "status": status,
        "reason": reason,
        "current_value": {
            "impressions": impressions.get("current"),
            "clicks": clicks.get("current"),
        },
        "previous_day": {
            "impressions": impressions.get("previous"),
            "clicks": clicks.get("previous"),
        },
        "rolling_7d_avg": {
            "impressions": impressions.get("avg_7d"),
            "clicks": clicks.get("avg_7d"),
        },
        "delta_vs_prev_pct": delta_prev_pct,
        "delta_vs_7d_pct": delta_7d_pct,
    }


def _build_cart_conversion_drop_alert(item: Dict[str, Any]) -> Dict[str, Any]:
    cart_count = _safe_float(item.get("cart_count"))
    if cart_count is None:
        status = "unknown"
        reason = "Cart-данные недоступны в текущем слое."
    else:
        status = "not_applicable"
        reason = "Расчет cart conversion пока не реализован для текущего источника."
    return {
        "type": "cart_conversion_drop",
        "status": status,
        "reason": reason,
        "current_value": cart_count,
        "previous_day": None,
        "rolling_7d_avg": None,
        "delta_vs_prev_pct": None,
        "delta_vs_7d_pct": None,
    }


def _build_ad_inefficiency_alert(item: Dict[str, Any]) -> Dict[str, Any]:
    ads_spend = _safe_float(item.get("ads_spend"))
    net_profit = _safe_float(item.get("net_profit"))
    revenue = _safe_float(item.get("revenue"))
    orders = _safe_float(item.get("orders"))
    ctr = _safe_float(item.get("ctr"))
    ads_snapshot = _metric_snapshot(item, "ads_spend")
    orders_snapshot = _metric_snapshot(item, "orders")

    status = "unknown"
    reasons: List[str] = []
    if ads_spend is None:
        reasons.append("ads_spend отсутствует")
        status = "unknown"
    elif ads_spend <= 0:
        status = "not_applicable"
        reasons.append("рекламные расходы отсутствуют")
    else:
        critical_flags = 0
        warning_flags = 0
        if net_profit is not None and net_profit < 0:
            critical_flags += 1
            reasons.append("расходы на рекламу при отрицательной прибыли")
        if revenue is not None and revenue <= 0:
            critical_flags += 1
            reasons.append("расходы на рекламу при нулевой выручке")
        if orders is not None and orders <= 0:
            warning_flags += 1
            reasons.append("реклама без заказов")
        if ctr is not None and ctr < 1.0:
            warning_flags += 1
            reasons.append("низкий CTR")
        ads_growth = _safe_float(ads_snapshot.get("delta_prev_pct"))
        orders_drop = _safe_float(orders_snapshot.get("delta_prev_pct"))
        if ads_growth is not None and orders_drop is not None and ads_growth > 30 and orders_drop < -30:
            warning_flags += 1
            reasons.append("рост ads_spend на фоне падения заказов")

        if critical_flags > 0:
            status = "critical"
        elif warning_flags > 0:
            status = "warning"
        else:
            status = "ok"
            reasons.append("признаков неэффективности не обнаружено")

    return {
        "type": "ad_inefficiency",
        "status": status,
        "reason": "; ".join(reasons),
        "current_value": ads_spend,
        "previous_day": ads_snapshot.get("previous"),
        "rolling_7d_avg": ads_snapshot.get("avg_7d"),
        "delta_vs_prev_pct": ads_snapshot.get("delta_prev_pct"),
        "delta_vs_7d_pct": ads_snapshot.get("delta_7d_pct"),
    }


def _build_dead_stock_alert(item: Dict[str, Any]) -> Dict[str, Any]:
    stock = _safe_float(item.get("stock"))
    orders = _safe_float(item.get("orders"))
    buyouts = _safe_float(item.get("buyouts"))
    if stock is None:
        status = "unknown"
        reason = "Stock-данные отсутствуют."
    elif stock <= 0:
        status = "not_applicable"
        reason = "Положительных остатков нет."
    elif (orders or 0.0) <= 0 and (buyouts or 0.0) <= 0:
        status = "critical" if stock >= 20 else "warning"
        reason = "Есть остатки при нулевых заказах и выкупах."
    else:
        status = "ok"
        reason = "Остатки не выглядят зависшими."
    return {
        "type": "dead_stock",
        "status": status,
        "reason": reason,
        "current_value": stock,
        "previous_day": None,
        "rolling_7d_avg": None,
        "delta_vs_prev_pct": None,
        "delta_vs_7d_pct": None,
    }


def _build_zero_sales_with_stock_alert(item: Dict[str, Any]) -> Dict[str, Any]:
    stock = _safe_float(item.get("stock"))
    orders = _safe_float(item.get("orders"))
    buyouts = _safe_float(item.get("buyouts"))
    revenue = _safe_float(item.get("revenue"))
    if stock is None:
        status = "unknown"
        reason = "Stock-данные отсутствуют."
    elif stock <= 0:
        status = "not_applicable"
        reason = "Положительных остатков нет."
    elif revenue is None:
        status = "unknown"
        reason = "Выручка по SKU не определена."
    elif revenue <= 0 and (orders or 0.0) <= 0 and (buyouts or 0.0) <= 0:
        status = "critical" if stock >= 5 else "warning"
        reason = "Есть остатки, но продажи отсутствуют."
    else:
        status = "ok"
        reason = "Сигнал zero_sales_with_stock не подтвержден."
    return {
        "type": "zero_sales_with_stock",
        "status": status,
        "reason": reason,
        "current_value": stock,
        "previous_day": None,
        "rolling_7d_avg": None,
        "delta_vs_prev_pct": None,
        "delta_vs_7d_pct": None,
    }


def _build_critical_ktr_alert(item: Dict[str, Any], logistics_by_sku: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    sku = str(item.get("sku") or "")
    logistics = logistics_by_sku.get(sku, {})
    if not logistics:
        status = "unknown"
        reason = "KTR по SKU недоступен."
        ktr = None
    else:
        ktr = _safe_float(logistics.get("ktr"))
        efficiency_status = str(logistics.get("logistics_efficiency_status") or "").strip().lower()
        if efficiency_status == "critical" or (ktr is not None and ktr >= 1.5):
            status = "critical"
            reason = "Критичный KTR."
        elif efficiency_status == "inefficient" or (ktr is not None and ktr >= 1.25):
            status = "warning"
            reason = "KTR выше целевого."
        elif efficiency_status == "insufficient_data":
            status = "unknown"
            reason = "Недостаточно данных для KTR."
        else:
            status = "ok"
            reason = "KTR в допустимом диапазоне."
    return {
        "type": "critical_ktr",
        "status": status,
        "reason": reason,
        "current_value": ktr,
        "previous_day": None,
        "rolling_7d_avg": None,
        "delta_vs_prev_pct": None,
        "delta_vs_7d_pct": None,
    }


def _load_health_map(path: Path) -> Dict[str, float]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    items = payload.get("items", []) if isinstance(payload, dict) else []
    if not isinstance(items, list):
        return {}
    out: Dict[str, float] = {}
    for row in items:
        if not isinstance(row, dict):
            continue
        sku = str(row.get("sku") or "").strip()
        score = _safe_float(row.get("health_score"))
        if sku and score is not None:
            out[sku] = float(score)
    return out


def _history_dates(history_root: Path, run_date: str) -> List[str]:
    daily_dir = history_root / "daily"
    if not daily_dir.is_dir():
        return []
    candidates = [item.name for item in daily_dir.iterdir() if item.is_dir()]
    return sorted([item for item in candidates if item < run_date])


def _previous_day(run_date: str) -> str | None:
    try:
        value = date.fromisoformat(run_date)
    except ValueError:
        return None
    return (value - timedelta(days=1)).isoformat()


def _history_health_scores(history_root: Path, run_date: str) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for day in _history_dates(history_root, run_date):
        health_map = _load_health_map(history_root / "daily" / day / "health_score.json")
        if health_map:
            out[day] = health_map
    return out


def _build_health_score_drop_alert(
    *,
    item: Dict[str, Any],
    current_health_by_sku: Dict[str, float],
    history_health: Dict[str, Dict[str, float]],
    run_date: str,
) -> Dict[str, Any]:
    sku = str(item.get("sku") or "")
    current = _safe_float(current_health_by_sku.get(sku))

    prev = None
    previous_day_key = _previous_day(run_date)
    if previous_day_key:
        prev = _safe_float((history_health.get(previous_day_key) or {}).get(sku))

    recent_dates = sorted(history_health.keys())[-7:]
    history_values: List[float] = []
    for day in recent_dates:
        value = _safe_float((history_health.get(day) or {}).get(sku))
        if value is not None:
            history_values.append(float(value))
    avg_7d = round(sum(history_values) / len(history_values), 2) if history_values else None

    delta_vs_prev = _pct_change(current, prev)
    delta_vs_7d = _pct_change(current, avg_7d)
    status = _drop_status(delta_vs_prev, delta_vs_7d, warning_threshold=-15.0, critical_threshold=-35.0)
    if current is None:
        status = "unknown"
        reason = "Текущий health_score отсутствует."
    elif status == "unknown":
        reason = "Недостаточно исторических данных для health_score."
    elif status == "critical":
        reason = "Критичное снижение health_score."
    elif status == "warning":
        reason = "Наблюдается снижение health_score."
    else:
        reason = "Health score без критичного снижения."

    return {
        "type": "health_score_drop",
        "status": status,
        "reason": reason,
        "current_value": current,
        "previous_day": prev,
        "rolling_7d_avg": avg_7d,
        "delta_vs_prev_pct": delta_vs_prev,
        "delta_vs_7d_pct": delta_vs_7d,
    }


def _logistics_by_sku(logistics_ktr: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    rows = logistics_ktr.get("skus", []) if isinstance(logistics_ktr, dict) else []
    if not isinstance(rows, list):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        sku = str(row.get("sku") or "").strip()
        if sku:
            out[sku] = row
    return out


def _current_health_by_sku(health_payload: Dict[str, Any]) -> Dict[str, float]:
    rows = health_payload.get("items", []) if isinstance(health_payload, dict) else []
    if not isinstance(rows, list):
        return {}
    out: Dict[str, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        sku = str(row.get("sku") or "").strip()
        score = _safe_float(row.get("health_score"))
        if sku and score is not None:
            out[sku] = float(score)
    return out


def build_sku_alerts(
    *,
    run_date: str,
    sku_daily_dynamics: Dict[str, Any],
    logistics_ktr: Dict[str, Any] | None = None,
    health_payload: Dict[str, Any] | None = None,
    history_root: str | Path | None = None,
) -> Dict[str, Any]:
    dynamics_items_raw = sku_daily_dynamics.get("items", []) if isinstance(sku_daily_dynamics, dict) else []
    dynamics_items = [item for item in dynamics_items_raw if isinstance(item, dict)] if isinstance(dynamics_items_raw, list) else []
    logistics_map = _logistics_by_sku(logistics_ktr if isinstance(logistics_ktr, dict) else {})
    current_health_map = _current_health_by_sku(health_payload if isinstance(health_payload, dict) else {})
    history_health: Dict[str, Dict[str, float]] = {}
    if history_root:
        history_health = _history_health_scores(Path(history_root), run_date)

    out_items: List[Dict[str, Any]] = []
    for item in dynamics_items:
        sku = str(item.get("sku") or "").strip()
        if not sku:
            continue

        alerts: List[Dict[str, Any]] = []
        alerts.append(_build_traffic_drop_alert(item))
        alerts.append(
            _build_single_metric_drop_alert(
                alert_type="ctr_drop",
                metric="ctr",
                item=item,
                warning_threshold=-20.0,
                critical_threshold=-35.0,
                label="CTR",
            )
        )
        alerts.append(_build_cart_conversion_drop_alert(item))
        alerts.append(
            _build_single_metric_drop_alert(
                alert_type="orders_drop",
                metric="orders",
                item=item,
                warning_threshold=-30.0,
                critical_threshold=-60.0,
                label="заказов",
            )
        )
        alerts.append(
            _build_single_metric_drop_alert(
                alert_type="buyout_drop",
                metric="buyouts",
                item=item,
                warning_threshold=-30.0,
                critical_threshold=-60.0,
                label="выкупов",
            )
        )
        alerts.append(
            _build_single_metric_drop_alert(
                alert_type="profit_drop",
                metric="net_profit",
                item=item,
                warning_threshold=-30.0,
                critical_threshold=-60.0,
                label="чистой прибыли",
            )
        )
        alerts.append(_build_ad_inefficiency_alert(item))
        alerts.append(_build_dead_stock_alert(item))
        alerts.append(_build_zero_sales_with_stock_alert(item))
        alerts.append(_build_critical_ktr_alert(item, logistics_by_sku=logistics_map))
        alerts.append(
            _build_health_score_drop_alert(
                item=item,
                current_health_by_sku=current_health_map,
                history_health=history_health,
                run_date=run_date,
            )
        )

        attention_score, score_debug = calculate_attention_score(alerts)
        out_items.append(
            {
                "sku": sku,
                "attention_score": attention_score,
                "alerts": alerts,
                "score_debug": score_debug,
            }
        )

    out_items.sort(
        key=lambda row: (
            -int(row.get("attention_score", 0) or 0),
            str(row.get("sku") or ""),
        )
    )
    return {
        "date": str(run_date or ""),
        "items": out_items,
    }

