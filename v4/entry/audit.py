"""Audit entry wrapper.

Input: run payload from CLI/invoker.
Output: end-to-end audit pipeline result.
Does not implement business logic.
"""

from __future__ import annotations

from typing import Any

from ..pipeline.runners.audit_runner import run_audit_pipeline


def run(payload: dict[str, Any] | None = None) -> dict:
    data = dict(payload or {})
    input_path = str(data.get("input_path") or "").strip()
    if not input_path:
        raise ValueError("input_path is required for audit mode")

    run_context = {
        "seller_id": str(data.get("seller_id") or "seller_001").strip() or "seller_001",
        "run_date": data.get("run_date") or data.get("date"),
        "cabinet_name": data.get("cabinet_name"),
        "timezone": str(data.get("timezone") or "Europe/Moscow"),
        "dry_run": bool(data.get("dry_run", False)),
    }
    return run_audit_pipeline(
        input_path=input_path,
        run_context=run_context,
        output_dir=data.get("output_dir"),
    )
