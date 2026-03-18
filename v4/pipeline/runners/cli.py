"""CLI runner wrappers.

Input: mode-specific run arguments.
Output: IngestionResult from orchestrator.
Does not execute metrics/facts/outputs stages.
"""

from __future__ import annotations

from ...core.contracts import IngestionResult, RunMode
from .seller_orchestrator import run_for_seller


def run_daily(
    *,
    seller_id: str,
    run_date: object | None,
    cabinet_name: str | None = None,
    timezone: str = "Europe/Moscow",
    dry_run: bool = False,
) -> IngestionResult:
    return run_for_seller(
        seller_id=seller_id,
        mode=RunMode.DAILY_API,
        run_date=run_date,
        cabinet_name=cabinet_name,
        timezone=timezone,
        dry_run=dry_run,
    )


def run_audit(
    *,
    seller_id: str,
    run_date: object | None,
    cabinet_name: str | None = None,
    timezone: str = "Europe/Moscow",
    dry_run: bool = False,
) -> IngestionResult:
    return run_for_seller(
        seller_id=seller_id,
        mode=RunMode.AUDIT_FILE,
        run_date=run_date,
        cabinet_name=cabinet_name,
        timezone=timezone,
        dry_run=dry_run,
    )
