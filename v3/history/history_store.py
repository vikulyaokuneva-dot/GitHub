from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, List


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        if value is None:
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def load_history_index(history_dir: Path) -> Dict[str, Any]:
    history_root = Path(history_dir)
    index_path = history_root / "history_index.json"
    if not index_path.is_file():
        return {"seller_id": history_root.parent.name, "snapshots": []}

    payload = _read_json(index_path)
    snapshots = payload.get("snapshots", [])
    if not isinstance(snapshots, list):
        snapshots = []
    seller_id = str(payload.get("seller_id") or history_root.parent.name)
    return {"seller_id": seller_id, "snapshots": snapshots}


def update_history_index(history_dir: Path, snapshot_meta: Dict[str, Any]) -> None:
    history_root = Path(history_dir)
    history_root.mkdir(parents=True, exist_ok=True)
    index_path = history_root / "history_index.json"

    index_payload = load_history_index(history_root)
    snapshots = index_payload.get("snapshots", [])
    if not isinstance(snapshots, list):
        snapshots = []

    run_date = str(snapshot_meta.get("date") or "")
    replaced = False
    for i, item in enumerate(snapshots):
        if isinstance(item, dict) and str(item.get("date") or "") == run_date:
            snapshots[i] = snapshot_meta
            replaced = True
            break
    if not replaced:
        snapshots.append(snapshot_meta)

    snapshots_sorted = sorted(
        [x for x in snapshots if isinstance(x, dict)],
        key=lambda x: str(x.get("date") or ""),
    )
    out = {
        "seller_id": str(snapshot_meta.get("seller_id") or index_payload.get("seller_id") or history_root.parent.name),
        "snapshots": snapshots_sorted,
    }
    index_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


def save_daily_history_snapshot(seller_id: str, run_date: str, artifacts_dir: Path, history_dir: Path) -> Dict[str, Any]:
    artifacts_root = Path(artifacts_dir)
    history_root = Path(history_dir)
    snapshot_dir = history_root / "daily" / run_date
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    required_files = [
        "metrics.json",
        "event_ledger.json",
        "facts.json",
        "warnings.json",
        "abc_analysis.json",
        "profit_contribution.json",
        "health_score.json",
        "decisions.json",
    ]
    optional_artifacts = [
        "case_similarity.json",
        "sku_daily_dynamics.json",
        "sku_alerts.json",
        "sku_watchlists.json",
        "keyword_monitoring.json",
        "territorial_distribution.json",
        "territorial_distribution_summary.json",
        "territorial_distribution_metrics.json",
        "logistics_ktr.json",
    ]
    copied_files: List[str] = []

    for name in required_files + optional_artifacts:
        source = artifacts_root / name
        if not source.is_file():
            continue
        target = snapshot_dir / name
        shutil.copy2(source, target)
        copied_files.append(name)

    seller_root = history_root.parent
    outcomes_source = seller_root / "memory" / "outcomes" / f"{run_date}_outcomes.json"
    if outcomes_source.is_file():
        target_name = outcomes_source.name
        shutil.copy2(outcomes_source, snapshot_dir / target_name)
        copied_files.append(target_name)

    facts = _read_json(artifacts_root / "facts.json")
    metrics = _read_json(artifacts_root / "metrics.json")

    facts_kpi = facts.get("kpi", {}) if isinstance(facts, dict) else {}
    totals = metrics.get("totals", {}) if isinstance(metrics, dict) else {}
    data_quality = facts.get("data_quality", {}) if isinstance(facts, dict) else {}
    sku_metrics = metrics.get("sku_metrics", []) if isinstance(metrics, dict) else []
    if not isinstance(sku_metrics, list):
        sku_metrics = []

    snapshot_meta = {
        "date": run_date,
        "path": f"daily/{run_date}",
        "files": sorted(copied_files),
        "kpi": {
            "revenue": round(_safe_float(facts_kpi.get("revenue", totals.get("revenue", 0.0))), 4),
            "profit": round(_safe_float(facts_kpi.get("profit", totals.get("profit", 0.0))), 4),
            "buyouts": _safe_int(facts_kpi.get("buyouts", totals.get("buys", 0))),
            "ads_spend": round(_safe_float(totals.get("ads_spend", 0.0)), 4),
            "sku_count": len([x for x in sku_metrics if isinstance(x, dict)]),
            "valid_sku_count": _safe_int(data_quality.get("valid_sku_count", 0)),
            "invalid_sku_rows": _safe_int(data_quality.get("invalid_sku_rows", 0)),
        },
        "seller_id": seller_id,
    }

    update_history_index(history_root, snapshot_meta)
    index_after = load_history_index(history_root)
    snapshots_after = index_after.get("snapshots", [])
    if not isinstance(snapshots_after, list):
        snapshots_after = []
    latest_date = max([str(x.get("date") or "") for x in snapshots_after if isinstance(x, dict)] or [run_date])

    return {
        "seller_id": seller_id,
        "date": run_date,
        "snapshot_path": str(snapshot_dir),
        "files": sorted(copied_files),
        "history_summary": {
            "snapshots_count": len(snapshots_after),
            "latest_snapshot_date": latest_date,
        },
        "snapshot_meta": snapshot_meta,
    }
