from __future__ import annotations
from typing import Any, Dict, List, Tuple
from datetime import datetime

from ..ctx import SellerContext
from ..storage import write_json, ensure_dir
from ..quality_gate import compute_data_confidence

def run(ctx: SellerContext, raw_bundle: Dict[str, Any], warnings: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]:
    """Data phase: превращаем raw_bundle в facts/metrics.
    Сейчас это скелет (нулевые метрики), но формат фиксируем.
    """
    run_paths = ctx.paths.for_date(ctx.run_date)
    ensure_dir(run_paths.reports_dir)
    ensure_dir(run_paths.raw_dir)
    ensure_dir(run_paths.staging_dir)

    facts: Dict[str, Any] = {
        "seller_id": ctx.seller_id,
        "seller_name": ctx.seller_name,
        "run_date": ctx.run_date,
        "timezone": ctx.timezone,
        "mode": ctx.mode,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "kpi": {
            "revenue": 0.0,
            "profit": 0.0,
            "orders": 0,
            "buyouts": 0,
        },
        "raw_meta": {
            "has_wb_token": bool(ctx.get_wb_token()),
        },
    }

    metrics: Dict[str, Any] = {
        "financial": {},
        "funnel": {},
        "ads": {},
        "stock": {},
    }

    confidence = compute_data_confidence(warnings)
    facts["data_confidence"] = confidence

    write_json(f"{run_paths.reports_dir}/facts.json", facts)
    write_json(f"{run_paths.reports_dir}/metrics.json", metrics)
    write_json(f"{run_paths.reports_dir}/warnings.json", warnings)

    return facts, metrics, warnings
