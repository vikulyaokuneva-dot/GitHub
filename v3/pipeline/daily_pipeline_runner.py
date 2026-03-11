from __future__ import annotations

from typing import Any, Dict

from .daily_ai_stage import run_daily_ai_stage
from .daily_input_stage import run_daily_input_stage
from .daily_metrics_stage import run_daily_metrics_stage
from .daily_output_stage import run_daily_output_stage


def _run_daily_for_seller(repo_root: str, seller_id: str, run_date: str) -> Dict[str, Any]:
    context = run_daily_input_stage(repo_root=repo_root, seller_id=seller_id, run_date=run_date)
    context = run_daily_metrics_stage(context)
    context = run_daily_ai_stage(context)
    return run_daily_output_stage(context)


def run_daily_pipeline_for_seller(repo_root: str, seller_id: str, run_date: str) -> Dict[str, Any]:
    return _run_daily_for_seller(repo_root=repo_root, seller_id=seller_id, run_date=run_date)
