from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping

from ..paths import artifacts_dir


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _as_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _as_int(value: Any, default: int = 0) -> int:
    numeric = _as_float_or_none(value)
    if numeric is None:
        return default
    return int(round(numeric))


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    return payload if isinstance(payload, dict) else {}


def _save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def _extract_rows(payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get("skus")
    if not isinstance(rows, list):
        rows = payload.get("items")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _dominant_warehouses_from_share(share_by_warehouse: Mapping[str, Any], threshold: float = 0.2) -> List[str]:
    rows: List[tuple[str, float]] = []
    for warehouse, value in share_by_warehouse.items():
        share = _as_float_or_none(value)
        if share is None or share <= threshold:
            continue
        rows.append((str(warehouse), share))
    rows.sort(key=lambda item: (-item[1], item[0]))
    return [warehouse for warehouse, _ in rows]


def _locality_score(demand_share: Mapping[str, Any], stock_share: Mapping[str, Any], ktr: float | None) -> float | None:
    if ktr is None:
        return None
    if not demand_share or not stock_share:
        return None
    warehouses = set(demand_share.keys()) | set(stock_share.keys())
    if not warehouses:
        return None
    score = 0.0
    for warehouse in warehouses:
        demand = _as_float_or_none(demand_share.get(warehouse)) or 0.0
        stock = _as_float_or_none(stock_share.get(warehouse)) or 0.0
        score += min(max(demand, 0.0), max(stock, 0.0))
    score = max(0.0, min(1.0, score))
    return round(score, 3)


def _efficiency_status(ktr: float | None) -> str:
    if ktr is None:
        return "insufficient_data"
    if ktr <= 1.10:
        return "efficient"
    if ktr <= 1.25:
        return "acceptable"
    if ktr <= 1.50:
        return "inefficient"
    return "critical"


def _priority_for_relocation(status: str, confidence: str) -> str:
    if status == "insufficient_data":
        return "none"
    conf = confidence.strip().lower()
    if conf == "low" and status in {"critical", "inefficient"}:
        return "watch"
    if status == "critical" and conf in {"medium", "high"}:
        return "high"
    if status == "inefficient" and conf in {"medium", "high"}:
        return "medium"
    if status == "acceptable":
        return "low"
    if status == "efficient":
        return "none"
    return "none"


def _explanation(status: str, priority: str) -> str:
    if status == "insufficient_data":
        return "Insufficient data for logistics assessment."
    if status == "critical":
        return "Strong mismatch between demand geography and stock geography."
    if status == "inefficient":
        if priority in {"high", "medium", "watch"}:
            return "Stock is poorly aligned with actual warehouse demand. Relocation review is recommended."
        return "Distribution shows mismatch with demand geography and needs attention."
    if status == "acceptable":
        return "Distribution is mostly aligned with demand. Monitor for further changes."
    return "Stock distribution is well aligned with demand geography."


def _build_sku_row(row: Dict[str, Any]) -> Dict[str, Any]:
    demand_share_raw = row.get("demand_share_by_warehouse")
    stock_share_raw = row.get("stock_share_by_warehouse")
    demand_share = demand_share_raw if isinstance(demand_share_raw, dict) else {}
    stock_share = stock_share_raw if isinstance(stock_share_raw, dict) else {}

    ktr = _as_float_or_none(row.get("ktr"))
    gap = _as_float_or_none(row.get("distribution_gap"))
    confidence = str(row.get("confidence") or "low").strip().lower() or "low"
    locality = _locality_score(demand_share, stock_share, ktr)
    efficiency_status = _efficiency_status(ktr)
    priority = _priority_for_relocation(efficiency_status, confidence)

    demand_dominant = row.get("dominant_demand_warehouses")
    stock_dominant = row.get("dominant_stock_warehouses")
    if not isinstance(demand_dominant, list):
        demand_dominant = _dominant_warehouses_from_share(demand_share)
    if not isinstance(stock_dominant, list):
        stock_dominant = _dominant_warehouses_from_share(stock_share)

    return {
        "sku": str(row.get("sku") or "").strip(),
        "total_buys": _as_int(row.get("total_buys"), 0),
        "total_stock": _as_int(row.get("total_stock"), 0),
        "ktr": round(ktr, 3) if ktr is not None else None,
        "distribution_gap": round(gap, 3) if gap is not None else None,
        "confidence": confidence,
        "low_sample_warning": bool(row.get("low_sample_warning", confidence == "low")),
        "locality_score": locality,
        "logistics_efficiency_status": efficiency_status,
        "priority_for_relocation": priority,
        "dominant_demand_warehouses": [str(x) for x in demand_dominant if str(x).strip()],
        "dominant_stock_warehouses": [str(x) for x in stock_dominant if str(x).strip()],
        "explanation": _explanation(efficiency_status, priority),
    }


def _build_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    sku_total = len(rows)
    sku_with_ktr = sum(1 for row in rows if _as_float_or_none(row.get("ktr")) is not None)
    efficient_count = sum(1 for row in rows if row.get("logistics_efficiency_status") == "efficient")
    acceptable_count = sum(1 for row in rows if row.get("logistics_efficiency_status") == "acceptable")
    inefficient_count = sum(1 for row in rows if row.get("logistics_efficiency_status") == "inefficient")
    critical_count = sum(1 for row in rows if row.get("logistics_efficiency_status") == "critical")
    low_confidence_count = sum(1 for row in rows if str(row.get("confidence") or "").strip().lower() == "low")

    ktr_values = [_as_float_or_none(row.get("ktr")) for row in rows]
    ktr_values = [float(value) for value in ktr_values if value is not None]
    locality_values = [_as_float_or_none(row.get("locality_score")) for row in rows]
    locality_values = [float(value) for value in locality_values if value is not None]

    avg_ktr = round(sum(ktr_values) / len(ktr_values), 3) if ktr_values else 0.0
    avg_locality_score = round(sum(locality_values) / len(locality_values), 3) if locality_values else 0.0

    relocation_rows = [
        row
        for row in rows
        if row.get("logistics_efficiency_status") in {"critical", "inefficient"}
        and _as_float_or_none(row.get("ktr")) is not None
    ]
    relocation_rows.sort(
        key=lambda row: (
            -float(_as_float_or_none(row.get("ktr")) or 0.0),
            str(row.get("sku") or ""),
        )
    )
    top_critical_skus = [str(row.get("sku") or "") for row in relocation_rows[:5] if str(row.get("sku") or "").strip()]

    return {
        "sku_total": sku_total,
        "sku_with_ktr": sku_with_ktr,
        "efficient_count": efficient_count,
        "acceptable_count": acceptable_count,
        "inefficient_count": inefficient_count,
        "critical_count": critical_count,
        "low_confidence_count": low_confidence_count,
        "avg_ktr": avg_ktr,
        "avg_locality_score": avg_locality_score,
        "top_critical_skus": top_critical_skus,
    }


def build_logistics_ktr(seller_id: str, run_date: str, repo_root: str | None = None) -> Dict[str, Any]:
    resolved_repo_root = str(Path(repo_root)) if repo_root else str(_repo_root())
    out_dir = Path(artifacts_dir(resolved_repo_root, seller_id, create=True))
    territorial_path = out_dir / "territorial_distribution.json"
    territorial = _load_json(territorial_path)
    territorial_meta = territorial.get("metadata", {}) if isinstance(territorial, dict) else {}
    if not isinstance(territorial_meta, dict):
        territorial_meta = {}

    resolved_seller_id = str(seller_id or territorial_meta.get("seller_id") or "").strip()
    resolved_run_date = str(run_date or territorial_meta.get("run_date") or "").strip()
    sku_rows = [_build_sku_row(row) for row in _extract_rows(territorial)]

    payload = {
        "metadata": {
            "engine": "logistics_ktr_engine",
            "version": "1.0",
            "seller_id": resolved_seller_id,
            "run_date": resolved_run_date,
            "generated_at": _utc_now_iso(),
            "source_artifacts": ["territorial_distribution.json"],
        },
        "summary": _build_summary(sku_rows),
        "skus": sku_rows,
    }
    _save_json(out_dir / "logistics_ktr.json", payload)
    return payload
