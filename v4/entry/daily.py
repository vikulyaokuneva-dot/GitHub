"""Daily entry wrapper.

Input: run payload from CLI/invoker.
Output: end-to-end daily pipeline result.
Does not implement business logic.
"""

from __future__ import annotations

from typing import Any

from ..pipeline.runners.daily_runner import run_daily_pipeline


def run(payload: dict[str, Any] | None = None) -> dict:
    data = dict(payload or {})
    seller_id = str(data.get("seller_id") or "").strip()
    if not seller_id:
        raise ValueError("seller_id is required")

    run_context = {
        "seller_id": seller_id,
        "run_date": data.get("run_date") or data.get("date"),
        "cabinet_name": data.get("cabinet_name"),
        "timezone": str(data.get("timezone") or "Europe/Moscow"),
        "dry_run": bool(data.get("dry_run", False)),
    }
    return run_daily_pipeline(
        run_context=run_context,
        output_dir=data.get("output_dir"),
    )
