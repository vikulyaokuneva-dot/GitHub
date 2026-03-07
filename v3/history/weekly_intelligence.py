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


def _trend(delta: float) -> str:
    if delta > 0:
        return "up"
    if delta < 0:
        return "down"
    return "flat"


def _build_kpi_trend(start: float, current: float) -> Dict[str, Any]:
    delta = round(current - start, 4)
    delta_pct = round((delta / start) * 100.0, 4) if start > 0 else None
    return {
        "current": round(current, 4),
        "start": round(start, 4),
        "delta": delta,
        "delta_pct": delta_pct,
        "trend": _trend(delta),
    }


def load_last_n_snapshots(history_dir: Path, n: int = 7) -> List[Dict[str, Any]]:
    index_payload = load_history_index(history_dir)
    snapshots = index_payload.get("snapshots", [])
    if not isinstance(snapshots, list):
        return []
    cleaned = [x for x in snapshots if isinstance(x, dict) and str(x.get("date") or "").strip()]
    cleaned.sort(key=lambda x: str(x.get("date") or ""))
    return cleaned[-max(1, int(n)) :]


def _metrics_profit_map(snapshot: Dict[str, Any], history_dir: Path) -> Dict[str, float]:
    rel_path = str(snapshot.get("path") or "").strip()
    if not rel_path:
        return {}
    metrics_path = Path(history_dir) / rel_path / "metrics.json"
    payload = _read_json(metrics_path)
    rows = payload.get("sku_metrics", [])
    if not isinstance(rows, list):
        return {}

    out: Dict[str, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        sku = str(row.get("sku") or "").strip()
        if not sku or not is_valid_sku(sku):
            continue
        out[sku] = _safe_float(row.get("profit", 0.0))
    return out


def build_weekly_intelligence(seller_id: str, history_dir: Path, run_date: str) -> Dict[str, Any]:
    run_dt = _to_date(run_date)
    all_last_7 = load_last_n_snapshots(history_dir, n=7)
    eligible: List[Dict[str, Any]] = []
    for snap in all_last_7:
        snap_dt = _to_date(snap.get("date"))
        if run_dt is None or snap_dt is None or snap_dt <= run_dt:
            eligible.append(snap)

    if run_dt is not None and len(eligible) > 7:
        eligible = eligible[-7:]

    snapshots_used = len(eligible)
    snapshots_available = snapshots_used
    enough_for_weekly = snapshots_used >= 7

    start_snapshot = eligible[0] if eligible else {}
    current_snapshot = eligible[-1] if eligible else {}
    start_kpi = start_snapshot.get("kpi", {}) if isinstance(start_snapshot, dict) else {}
    current_kpi = current_snapshot.get("kpi", {}) if isinstance(current_snapshot, dict) else {}
    if not isinstance(start_kpi, dict):
        start_kpi = {}
    if not isinstance(current_kpi, dict):
        current_kpi = {}

    kpi_trends = {
        "revenue": _build_kpi_trend(_safe_float(start_kpi.get("revenue", 0.0)), _safe_float(current_kpi.get("revenue", 0.0))),
        "profit": _build_kpi_trend(_safe_float(start_kpi.get("profit", 0.0)), _safe_float(current_kpi.get("profit", 0.0))),
        "ads_spend": _build_kpi_trend(_safe_float(start_kpi.get("ads_spend", 0.0)), _safe_float(current_kpi.get("ads_spend", 0.0))),
        "buyouts": _build_kpi_trend(_safe_float(start_kpi.get("buyouts", 0.0)), _safe_float(current_kpi.get("buyouts", 0.0))),
        "sku_count": _build_kpi_trend(_safe_float(start_kpi.get("sku_count", 0.0)), _safe_float(current_kpi.get("sku_count", 0.0))),
    }

    start_profit_map = _metrics_profit_map(start_snapshot, history_dir) if snapshots_used >= 1 else {}
    current_profit_map = _metrics_profit_map(current_snapshot, history_dir) if snapshots_used >= 1 else {}
    sku_union = sorted(set(start_profit_map) | set(current_profit_map))

    growing: List[Dict[str, Any]] = []
    declining: List[Dict[str, Any]] = []
    stable: List[Dict[str, Any]] = []
    for sku in sku_union:
        start_profit = _safe_float(start_profit_map.get(sku, 0.0))
        current_profit = _safe_float(current_profit_map.get(sku, 0.0))
        delta = round(current_profit - start_profit, 4)
        item = {
            "sku": sku,
            "profit_start": round(start_profit, 4),
            "profit_current": round(current_profit, 4),
            "profit_delta": delta,
            "trend": _trend(delta),
        }
        if delta > 0:
            growing.append(item)
        elif delta < 0:
            declining.append(item)
        else:
            stable.append(item)

    growing.sort(key=lambda x: x["profit_delta"], reverse=True)
    declining.sort(key=lambda x: x["profit_delta"])
    stable.sort(key=lambda x: x["sku"])

    insights: List[str] = []
    rev = kpi_trends["revenue"]
    prof = kpi_trends["profit"]
    ads = kpi_trends["ads_spend"]
    buys = kpi_trends["buyouts"]

    if snapshots_used < 2:
        insights.append(f"Истории недостаточно: доступно только {snapshots_used} snapshot для сравнения.")
    else:
        if rev["delta_pct"] is not None:
            direction = "выросла" if rev["delta"] > 0 else ("снизилась" if rev["delta"] < 0 else "не изменилась")
            insights.append(f"Выручка за период {direction} на {abs(float(rev['delta_pct'])):.2f}%.")
        else:
            insights.append(f"Базовая выручка равна 0; изменение выручки: {rev['delta']:.2f}.")

        if prof["delta_pct"] is not None:
            direction = "выросла" if prof["delta"] > 0 else ("снизилась" if prof["delta"] < 0 else "не изменилась")
            insights.append(f"Прибыль за период {direction} на {abs(float(prof['delta_pct'])):.2f}%.")
        else:
            insights.append(f"Базовая прибыль равна 0; изменение прибыли: {prof['delta']:.2f}.")

        if ads["delta_pct"] is not None and prof["delta_pct"] is not None and ads["delta_pct"] > prof["delta_pct"]:
            insights.append("Рекламные расходы росли быстрее прибыли.")
        if buys["delta_pct"] is not None:
            direction = "выросли" if buys["delta"] > 0 else ("снизились" if buys["delta"] < 0 else "не изменились")
            insights.append(f"Выкупы за период {direction} на {abs(float(buys['delta_pct'])):.2f}%.")

    insights.append(f"SKU с ростом прибыли: {len(growing)}; со снижением: {len(declining)}; стабильные: {len(stable)}.")
    if not enough_for_weekly:
        insights.append(f"Истории пока недостаточно для полного 7-дневного анализа: доступно {snapshots_available} snapshot.")

    return {
        "seller_id": seller_id,
        "run_date": run_date,
        "window_days": 7,
        "snapshots_used": snapshots_used,
        "kpi_trends": kpi_trends,
        "sku_trends": {
            "growing": growing,
            "declining": declining,
            "stable": stable,
        },
        "insights": insights[:6],
        "data_quality": {
            "snapshots_available": snapshots_available,
            "enough_for_weekly": enough_for_weekly,
        },
    }


def save_weekly_intelligence(seller_id: str, artifacts_dir: Path, data: Dict[str, Any]) -> Path:
    artifacts_root = Path(artifacts_dir)
    artifacts_root.mkdir(parents=True, exist_ok=True)
    out_path = artifacts_root / "weekly_intelligence.json"
    payload = dict(data)
    payload["seller_id"] = seller_id
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path
