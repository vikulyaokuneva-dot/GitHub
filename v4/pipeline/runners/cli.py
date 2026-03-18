"""CLI runner skeleton.

Input: parsed CLI parameters.
Output: process exit code.
Does not implement production pipeline execution in stage 1.
"""

from __future__ import annotations

from .seller_orchestrator import run_for_seller


def run_daily(*, seller_id: str, run_date: str) -> int:
    run_for_seller(seller_id=seller_id, mode="daily_api_mode", run_date=run_date)
    return 0


def run_audit(*, seller_id: str, run_date: str) -> int:
    run_for_seller(seller_id=seller_id, mode="audit_file_mode", run_date=run_date)
    return 0
