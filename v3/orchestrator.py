from __future__ import annotations
from typing import Any, Dict, List, Optional
import os
from datetime import datetime, date

from .job_runner import run_job

def list_sellers(repo_root: str) -> List[str]:
    cabinets_dir = os.path.join(repo_root, "cabinets")
    if not os.path.isdir(cabinets_dir):
        return []
    out = []
    for name in os.listdir(cabinets_dir):
        if name.startswith("_"):
            continue
        cfg = os.path.join(cabinets_dir, name, "config.yaml")
        if os.path.isfile(cfg):
            out.append(name)
    return sorted(out)

def run_daily(repo_root: str, seller_id: Optional[str], run_date: str) -> List[Dict[str, Any]]:
    sellers = [seller_id] if seller_id else list_sellers(repo_root)
    results = []
    for s in sellers:
        results.append(run_job(repo_root, s, run_date, mode="daily"))
    return results

def run_audit(repo_root: str, seller_id: str, run_date: str, audit_input: str) -> List[Dict[str, Any]]:
    return [run_job(repo_root, seller_id, run_date, mode="audit", audit_input=audit_input)]
