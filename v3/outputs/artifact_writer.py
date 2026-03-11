from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from ..storage import write_json
from .artifacts_writer import (
    write_daily_ai_artifacts,
    write_daily_metrics_artifacts,
    write_facts_and_warnings,
    write_job,
    write_report_meta,
    write_weekly_facts_and_warnings,
)

__all__ = [
    "write_daily_metrics_artifacts",
    "write_daily_ai_artifacts",
    "write_facts_and_warnings",
    "write_report_meta",
    "write_job",
    "write_weekly_facts_and_warnings",
    "write_batch_summary",
    "persist_result_job_if_possible",
]


def write_batch_summary(repo_root: str, summary: Dict[str, Any]) -> str:
    cabinets_dir = Path(repo_root) / "cabinets"
    batch_path = cabinets_dir / "_batch" / "batch_run_summary.json"
    write_json(str(batch_path), summary)
    return str(batch_path)


def persist_result_job_if_possible(result: Dict[str, Any]) -> None:
    if not isinstance(result, dict):
        return
    artifacts_dir = str(result.get("artifacts_dir") or "").strip()
    if not artifacts_dir:
        return
    write_job(out_dir=artifacts_dir, job=result)
