"""Audit entry wrapper.

Input: run payload from CLI/invoker.
Output: IngestionResult from input stage.
Does not compute metrics/facts.
"""

from __future__ import annotations

from typing import Any

from ..core.contracts import IngestionResult
from ..pipeline.runners.cli import run_audit


def run(payload: dict[str, Any] | None = None) -> IngestionResult:
    data = dict(payload or {})
    seller_id = str(data.get("seller_id") or "").strip()
    if not seller_id:
        raise ValueError("seller_id is required")

    return run_audit(
        seller_id=seller_id,
        run_date=data.get("run_date") or data.get("date"),
        cabinet_name=data.get("cabinet_name"),
        timezone=str(data.get("timezone") or "Europe/Moscow"),
        dry_run=bool(data.get("dry_run", False)),
    )
