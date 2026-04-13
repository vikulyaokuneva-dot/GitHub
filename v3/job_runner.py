"""LEGACY v3 skeleton runner (reports/data layout).

Deprecated for active production daily flow.
Active route: `python -m v3.entry daily --seller <seller>`.
Kept only for backward compatibility of legacy modules.
"""

from __future__ import annotations
from typing import Any, Dict, Optional
import os
import traceback
from datetime import datetime

from .ctx import SellerContext
from .storage import ensure_dir, write_json
from .sources.wb_api_source import collect as collect_wb
from .sources.audit_excel_source import collect as collect_audit
from .pipeline.data_phase import run as run_data_phase
from .pipeline.report_phase import run as run_report_phase

def run_job(repo_root: str, seller_id: str, run_date: str, mode: str, audit_input: Optional[str] = None) -> Dict[str, Any]:
    ctx = SellerContext.from_repo(repo_root=repo_root, seller_id=seller_id, run_date=run_date, mode=mode)
    run_paths = ctx.paths.for_date(ctx.run_date)
    ensure_dir(run_paths.reports_dir)

    job_path = os.path.join(run_paths.reports_dir, "job.json")
    job = {
        "seller_id": ctx.seller_id,
        "run_date": ctx.run_date,
        "mode": mode,
        "status": "running",
        "started_at": datetime.utcnow().isoformat() + "Z",
        "finished_at": None,
        "error": None,
        "artifacts": [],
    }
    write_json(job_path, job)

    try:
        if mode == "audit":
            raw_bundle, warnings = collect_audit(ctx, audit_input or "")
        else:
            raw_bundle, warnings = collect_wb(ctx)

        facts, metrics, warnings = run_data_phase(ctx, raw_bundle, warnings)
        pdf_path = run_report_phase(ctx, facts, metrics, warnings)

        job["status"] = "success"
        job["finished_at"] = datetime.utcnow().isoformat() + "Z"
        job["artifacts"] = [
            "facts.json",
            "metrics.json",
            "warnings.json",
            "report.pdf",
            "report_meta.json",
            "job.json",
        ]
        write_json(job_path, job)
        return job

    except Exception as e:
        job["status"] = "failed"
        job["finished_at"] = datetime.utcnow().isoformat() + "Z"
        job["error"] = str(e)
        # write traceback into reports dir for debugging
        tb_path = os.path.join(run_paths.reports_dir, "traceback.txt")
        with open(tb_path, "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())
        job["artifacts"] = ["job.json", "traceback.txt"]
        write_json(job_path, job)
        return job
