from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

from ..cleaning.sku_normalizer import is_valid_sku
from .history_store import load_history_index


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _pct_delta(start: float, current: float) -> float | None:
    if start <= 0:
        return None
    return round(((current - start) / start) * 100.0, 4)


def _severity_rank(value: str) -> int:
    mapping = {"high": 0, "medium": 1, "low": 2}
    return mapping.get(str(value or "").lower(), 3)


def _metric_delta_row(metric: str, start: float, current: float) -> Dict[str, Any]:
    delta = round(current - start, 4)
    delta_pct = _pct_delta(start, current)
    direction = "up" if delta > 0 else ("down" if delta < 0 else "flat")
    return {
        "metric": metric,
        "start": round(start, 4),
        "current": round(current, 4),
        "delta": delta,
        "delta_pct": delta_pct,
        "direction": direction,
    }


def _sku_metrics_map(metrics_payload: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
    rows = metrics_payload.get("sku_metrics", []) if isinstance(metrics_payload, dict) else []
    if not isinstance(rows, list):
        return {}

    out: Dict[str, Dict[str, float]] = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        sku = str(item.get("sku") or "").strip()
        if not sku or not is_valid_sku(sku):
            continue
        buys = item.get("buys")
        if buys is None:
            buys = item.get("sales_count")
        out[sku] = {
            "profit": _safe_float(item.get("profit", 0.0)),
            "revenue": _safe_float(item.get("revenue", 0.0)),
            "ads_spend": _safe_float(item.get("ads_spend", 0.0)),
            "margin_pct": _safe_float(item.get("margin_pct", 0.0)),
            "buys": _safe_float(buys or 0.0),
        }
    return out


def load_recent_history(history_dir: Path, days: int = 7) -> List[Dict[str, Any]]:
    history_root = Path(history_dir)
    index_payload = load_history_index(history_root)
    snapshots = index_payload.get("snapshots", [])
    if not isinstance(snapshots, list):
        return []

    cleaned = [x for x in snapshots if isinstance(x, dict) and str(x.get("date") or "").strip()]
    cleaned.sort(key=lambda x: str(x.get("date") or ""))
    selected = cleaned[-max(1, int(days)) :]

    enriched: List[Dict[str, Any]] = []
    for snapshot in selected:
        row = dict(snapshot)
        rel_path = str(row.get("path") or "").strip()
        metrics_payload: Dict[str, Any] = {}
        facts_payload: Dict[str, Any] = {}
        if rel_path:
            metrics_payload = _read_json(history_root / rel_path / "metrics.json")
            facts_payload = _read_json(history_root / rel_path / "facts.json")
        row["metrics_payload"] = metrics_payload
        row["facts_payload"] = facts_payload
        enriched.append(row)
    return enriched


def detect_kpi_anomalies(history_snapshots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if len(history_snapshots) < 2:
        return []

    start_snapshot = history_snapshots[0]
    current_snapshot = history_snapshots[-1]
    start_kpi = start_snapshot.get("kpi", {}) if isinstance(start_snapshot, dict) else {}
    current_kpi = current_snapshot.get("kpi", {}) if isinstance(current_snapshot, dict) else {}
    if not isinstance(start_kpi, dict):
        start_kpi = {}
    if not isinstance(current_kpi, dict):
        current_kpi = {}

    profit_row = _metric_delta_row("profit", _safe_float(start_kpi.get("profit", 0.0)), _safe_float(current_kpi.get("profit", 0.0)))
    revenue_row = _metric_delta_row("revenue", _safe_float(start_kpi.get("revenue", 0.0)), _safe_float(current_kpi.get("revenue", 0.0)))
    buyouts_row = _metric_delta_row("buyouts", _safe_float(start_kpi.get("buyouts", 0.0)), _safe_float(current_kpi.get("buyouts", 0.0)))
    ads_row = _metric_delta_row("ads_spend", _safe_float(start_kpi.get("ads_spend", 0.0)), _safe_float(current_kpi.get("ads_spend", 0.0)))
    sku_row = _metric_delta_row("sku_count", _safe_float(start_kpi.get("sku_count", 0.0)), _safe_float(current_kpi.get("sku_count", 0.0)))

    anomalies: List[Dict[str, Any]] = []

    if profit_row["delta_pct"] is not None and float(profit_row["delta_pct"]) <= -20.0:
        anomalies.append(
            {
                **profit_row,
                "severity": "high",
                "type": "profit_down_high",
                "message": "Прибыль снизилась более чем на 20%",
            }
        )

    if revenue_row["delta_pct"] is not None and float(revenue_row["delta_pct"]) <= -15.0:
        anomalies.append(
            {
                **revenue_row,
                "severity": "medium",
                "type": "revenue_down_medium",
                "message": "Выручка снизилась более чем на 15%",
            }
        )

    profit_non_growing = False
    if profit_row["delta_pct"] is not None:
        profit_non_growing = float(profit_row["delta_pct"]) <= 0.0
    else:
        profit_non_growing = float(profit_row["delta"]) <= 0.0
    if ads_row["delta_pct"] is not None and float(ads_row["delta_pct"]) >= 15.0 and profit_non_growing:
        anomalies.append(
            {
                **ads_row,
                "severity": "medium",
                "type": "ads_spend_up_without_profit",
                "message": "Рекламные расходы выросли, а прибыль не растет",
            }
        )

    if buyouts_row["delta_pct"] is not None and float(buyouts_row["delta_pct"]) <= -15.0:
        anomalies.append(
            {
                **buyouts_row,
                "severity": "medium",
                "type": "buyouts_drop",
                "message": "Выкупы снизились более чем на 15%",
            }
        )

    if float(sku_row["current"]) < float(sku_row["start"]):
        anomalies.append(
            {
                **sku_row,
                "severity": "low",
                "type": "sku_count_drop",
                "message": "Количество активных SKU сократилось",
            }
        )

    anomalies.sort(key=lambda x: (_severity_rank(str(x.get("severity") or "")), str(x.get("metric") or "")))
    return anomalies


def detect_sku_anomalies(history_snapshots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if len(history_snapshots) < 2:
        return []

    start_payload = history_snapshots[0].get("metrics_payload", {})
    current_payload = history_snapshots[-1].get("metrics_payload", {})
    if not isinstance(start_payload, dict):
        start_payload = {}
    if not isinstance(current_payload, dict):
        current_payload = {}

    start_map = _sku_metrics_map(start_payload)
    current_map = _sku_metrics_map(current_payload)
    sku_union = sorted(set(start_map) | set(current_map))

    anomalies: List[Dict[str, Any]] = []
    for sku in sku_union:
        start = start_map.get(sku, {})
        current = current_map.get(sku, {})

        profit_start = _safe_float(start.get("profit", 0.0))
        profit_current = _safe_float(current.get("profit", 0.0))
        revenue_start = _safe_float(start.get("revenue", 0.0))
        revenue_current = _safe_float(current.get("revenue", 0.0))
        ads_start = _safe_float(start.get("ads_spend", 0.0))
        ads_current = _safe_float(current.get("ads_spend", 0.0))
        margin_start = _safe_float(start.get("margin_pct", 0.0))
        margin_current = _safe_float(current.get("margin_pct", 0.0))
        buys_start = _safe_float(start.get("buys", 0.0))
        buys_current = _safe_float(current.get("buys", 0.0))

        profit_delta_pct = _pct_delta(profit_start, profit_current)
        revenue_delta_pct = _pct_delta(revenue_start, revenue_current)
        ads_delta_pct = _pct_delta(ads_start, ads_current)

        if profit_delta_pct is not None and float(profit_delta_pct) <= -25.0:
            anomalies.append(
                {
                    "sku": sku,
                    "severity": "high",
                    "type": "profit_drop_high",
                    "profit_start": round(profit_start, 4),
                    "profit_current": round(profit_current, 4),
                    "profit_delta": round(profit_current - profit_start, 4),
                    "profit_delta_pct": profit_delta_pct,
                    "message": "Резкое падение прибыли по SKU",
                }
            )

        if revenue_delta_pct is not None and float(revenue_delta_pct) <= -20.0:
            anomalies.append(
                {
                    "sku": sku,
                    "severity": "medium",
                    "type": "revenue_drop_medium",
                    "revenue_start": round(revenue_start, 4),
                    "revenue_current": round(revenue_current, 4),
                    "revenue_delta": round(revenue_current - revenue_start, 4),
                    "revenue_delta_pct": revenue_delta_pct,
                    "message": "Снижение выручки по SKU более чем на 20%",
                }
            )

        profit_flat = False
        if profit_delta_pct is not None:
            profit_flat = float(profit_delta_pct) <= 5.0
        else:
            profit_flat = round(profit_current - profit_start, 4) <= 0.0
        if ads_delta_pct is not None and float(ads_delta_pct) >= 20.0 and profit_flat:
            anomalies.append(
                {
                    "sku": sku,
                    "severity": "medium",
                    "type": "ads_up_profit_flat",
                    "profit_start": round(profit_start, 4),
                    "profit_current": round(profit_current, 4),
                    "ads_start": round(ads_start, 4),
                    "ads_current": round(ads_current, 4),
                    "ads_delta_pct": ads_delta_pct,
                    "message": "Рекламные расходы растут быстрее прибыли",
                }
            )

        if ads_current > 0 and profit_current <= 0:
            anomalies.append(
                {
                    "sku": sku,
                    "severity": "high",
                    "type": "zero_profit_with_spend",
                    "profit_current": round(profit_current, 4),
                    "ads_current": round(ads_current, 4),
                    "message": "Есть рекламные расходы при нулевой или отрицательной прибыли",
                }
            )

        if margin_current < (margin_start - 10.0):
            anomalies.append(
                {
                    "sku": sku,
                    "severity": "medium",
                    "type": "margin_drop",
                    "margin_pct_start": round(margin_start, 4),
                    "margin_pct_current": round(margin_current, 4),
                    "message": "Маржинальность снизилась более чем на 10 п.п.",
                }
            )

        if buys_current == 0 and buys_start > 0:
            anomalies.append(
                {
                    "sku": sku,
                    "severity": "medium",
                    "type": "new_zero_sales_sku",
                    "buys_start": round(buys_start, 4),
                    "buys_current": round(buys_current, 4),
                    "message": "SKU перешел в нулевые продажи",
                }
            )

    anomalies.sort(key=lambda x: (_severity_rank(str(x.get("severity") or "")), str(x.get("sku") or ""), str(x.get("type") or "")))
    return anomalies


def _build_insights(kpi_anomalies: List[Dict[str, Any]], sku_anomalies: List[Dict[str, Any]], snapshots_used: int) -> List[str]:
    insights: List[str] = []
    all_anomalies = list(kpi_anomalies) + list(sku_anomalies)
    high_count = len([x for x in all_anomalies if str(x.get("severity") or "").lower() == "high"])
    medium_count = len([x for x in all_anomalies if str(x.get("severity") or "").lower() == "medium"])

    if snapshots_used < 3:
        insights.append(f"Истории пока недостаточно для надежного поиска аномалий: доступно {snapshots_used} snapshot.")
    if high_count > 0:
        insights.append(f"Обнаружено {high_count} аномалий высокого приоритета.")
    if medium_count > 0:
        insights.append(f"Обнаружено {medium_count} аномалий среднего приоритета.")

    profit_drop = next((x for x in kpi_anomalies if str(x.get("type") or "") == "profit_down_high"), None)
    if isinstance(profit_drop, dict):
        pct = profit_drop.get("delta_pct")
        if pct is not None:
            insights.append(f"Прибыль кабинета снизилась на {abs(float(pct)):.1f}%.")

    sku_risk = next((x for x in sku_anomalies if str(x.get("type") or "") == "ads_up_profit_flat"), None)
    if isinstance(sku_risk, dict):
        insights.append(f"SKU {sku_risk.get('sku', 'n/a')} показывает рост рекламы без роста прибыли.")

    if not all_anomalies:
        insights.append("Значимых аномалий не обнаружено.")

    return insights[:6]


def build_trend_anomalies(seller_id: str, run_date: str, history_dir: Path) -> Dict[str, Any]:
    run_dt = _to_date(run_date)
    snapshots = load_recent_history(history_dir, days=7)
    eligible: List[Dict[str, Any]] = []
    for snapshot in snapshots:
        snapshot_dt = _to_date(snapshot.get("date"))
        if run_dt is None or snapshot_dt is None or snapshot_dt <= run_dt:
            eligible.append(snapshot)
    eligible.sort(key=lambda x: str(x.get("date") or ""))
    if len(eligible) > 7:
        eligible = eligible[-7:]

    snapshots_used = len(eligible)
    kpi_anomalies = detect_kpi_anomalies(eligible)
    sku_anomalies = detect_sku_anomalies(eligible)

    all_anomalies = list(kpi_anomalies) + list(sku_anomalies)
    high_count = len([x for x in all_anomalies if str(x.get("severity") or "").lower() == "high"])
    medium_count = len([x for x in all_anomalies if str(x.get("severity") or "").lower() == "medium"])
    low_count = len([x for x in all_anomalies if str(x.get("severity") or "").lower() == "low"])

    return {
        "seller_id": seller_id,
        "run_date": run_date,
        "window_days": 7,
        "snapshots_used": snapshots_used,
        "kpi_anomalies": kpi_anomalies,
        "sku_anomalies": sku_anomalies,
        "summary": {
            "total_anomalies": len(all_anomalies),
            "high": high_count,
            "medium": medium_count,
            "low": low_count,
        },
        "insights": _build_insights(kpi_anomalies, sku_anomalies, snapshots_used),
        "data_quality": {
            "snapshots_available": snapshots_used,
            "enough_for_detection": snapshots_used >= 3,
        },
    }


def save_trend_anomalies(artifacts_dir: Path, data: Dict[str, Any]) -> Path:
    artifacts_root = Path(artifacts_dir)
    artifacts_root.mkdir(parents=True, exist_ok=True)
    out_path = artifacts_root / "trend_anomalies.json"
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path
