from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from ..analytics.profit_contribution import save_profit_contribution
from ..analytics.territorial_distribution import save_territorial_distribution
from ..storage import write_json


def write_daily_metrics_artifacts(
    *,
    out_dir: str,
    metrics: Dict[str, Any],
    financial_debug: List[Dict[str, Any]],
    abc_rows: List[Dict[str, Any]],
    profit_contribution: Dict[str, Any],
    territorial_distribution: Dict[str, Any],
) -> None:
    write_json(os.path.join(out_dir, "metrics.json"), metrics)
    write_json(os.path.join(out_dir, "financial_debug.json"), financial_debug)
    write_json(os.path.join(out_dir, "abc_analysis.json"), abc_rows)
    save_profit_contribution(os.path.join(out_dir, "profit_contribution.json"), profit_contribution)
    save_territorial_distribution(Path(out_dir) / "territorial_distribution.json", territorial_distribution)


def write_daily_ai_artifacts(
    *,
    out_dir: str,
    health_payload: Dict[str, Any],
    decisions_payload: Dict[str, Any],
    growth_simulation: Dict[str, Any],
    opportunity_scores: Dict[str, Any],
    director_strategy: Dict[str, Any],
    api_debug: Dict[str, Any],
) -> None:
    write_json(os.path.join(out_dir, "health_score.json"), health_payload)
    write_json(os.path.join(out_dir, "decisions.json"), decisions_payload)
    write_json(os.path.join(out_dir, "growth_simulation.json"), growth_simulation)
    write_json(os.path.join(out_dir, "opportunity_scores.json"), opportunity_scores)
    write_json(os.path.join(out_dir, "director_strategy.json"), director_strategy)
    write_json(os.path.join(out_dir, "api_debug.json"), api_debug if isinstance(api_debug, dict) else {})


def write_facts_and_warnings(*, out_dir: str, facts: Dict[str, Any], warnings: List[Dict[str, Any]]) -> None:
    write_json(os.path.join(out_dir, "facts.json"), facts)
    write_json(os.path.join(out_dir, "warnings.json"), warnings)


def write_report_meta(*, out_dir: str, report_meta: Dict[str, Any]) -> None:
    write_json(os.path.join(out_dir, "report_meta.json"), report_meta)


def write_job(*, out_dir: str, job: Dict[str, Any]) -> None:
    write_json(os.path.join(out_dir, "job.json"), job)


def write_weekly_facts_and_warnings(
    *,
    out_dir: str,
    weekly_facts: Dict[str, Any],
    warnings: List[Dict[str, Any]],
) -> None:
    write_json(os.path.join(out_dir, "weekly_facts.json"), weekly_facts)
    write_json(os.path.join(out_dir, "warnings.json"), warnings)
