from __future__ import annotations

from typing import Any, Dict

from ..pipeline.daily_stage_support import sync_from_entry


def run_daily_history_stage(payload: Dict[str, Any]) -> Dict[str, Any]:
    sync_from_entry(globals())

    data: Dict[str, Any] = dict(payload or {})
    seller_id = str(data.get("seller_id") or "")
    run_date = str(data.get("run_date") or "")
    out_dir = str(data.get("out_dir") or "")
    warnings_collector = data.get("warnings_collector")
    if not isinstance(warnings_collector, WarningsCollector):
        warnings_collector = WarningsCollector()
    facts = data.get("facts", {})
    if not isinstance(facts, dict):
        facts = {}
    job = data.get("job", {})
    if not isinstance(job, dict):
        job = {}

    history_bundle = write_daily_history_snapshot_and_build_patches(
        seller_id=seller_id,
        run_date=run_date,
        out_dir=out_dir,
        facts=facts if isinstance(facts, dict) else {},
        warnings=warnings_collector.export_warnings(),
    )
    facts = history_bundle.get("facts", {}) if isinstance(history_bundle, dict) else {}
    if not isinstance(facts, dict):
        facts = {}
    warnings_after_history = history_bundle.get("warnings", []) if isinstance(history_bundle, dict) else []
    if not isinstance(warnings_after_history, list):
        warnings_after_history = warnings_collector.export_warnings()
    write_facts_and_warnings(
        out_dir=out_dir,
        facts=facts if isinstance(facts, dict) else {},
        warnings=warnings_after_history,
    )
    job = attach_daily_job_history(
        job if isinstance(job, dict) else {},
        run_date=run_date,
        history_snapshot_final=(
            history_bundle.get("history_snapshot_final", {})
            if isinstance(history_bundle, dict)
            else {}
        ),
    )
    job = attach_job_warnings(
        job if isinstance(job, dict) else {},
        warnings=warnings_after_history,
    )
    write_job(out_dir=out_dir, job=job)
    return job
