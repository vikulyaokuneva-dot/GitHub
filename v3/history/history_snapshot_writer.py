from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .history_store import save_daily_history_snapshot
from ..outputs.facts_builder import attach_history_summary_to_facts


def write_daily_history_snapshot_and_build_patches(
    *,
    seller_id: str,
    run_date: str,
    out_dir: str,
    facts: Dict[str, Any],
    warnings: List[Dict[str, Any]],
) -> Dict[str, Any]:
    history_dir = Path(out_dir).parent / "history"

    history_snapshot = save_daily_history_snapshot(
        seller_id=seller_id,
        run_date=run_date,
        artifacts_dir=Path(out_dir),
        history_dir=history_dir,
    )
    history_summary = history_snapshot.get("history_summary", {}) if isinstance(history_snapshot, dict) else {}
    if not isinstance(history_summary, dict):
        history_summary = {}

    facts_with_history = attach_history_summary_to_facts(
        facts if isinstance(facts, dict) else {},
        history_summary,
        run_date,
    )

    warnings_with_history = [item for item in warnings if isinstance(item, dict)] if isinstance(warnings, list) else []
    warnings_with_history.append(
        {
            "code": "history_snapshot_saved",
            "message": f"History snapshot saved for {run_date}",
        }
    )

    history_snapshot_final = save_daily_history_snapshot(
        seller_id=seller_id,
        run_date=run_date,
        artifacts_dir=Path(out_dir),
        history_dir=history_dir,
    )

    return {
        "facts": facts_with_history,
        "warnings": warnings_with_history,
        "history_snapshot_final": history_snapshot_final if isinstance(history_snapshot_final, dict) else {},
        "history_snapshot_patch": {
            "date": run_date,
            "path": str((history_snapshot_final or {}).get("snapshot_path", "")),
            "files": (history_snapshot_final or {}).get("files", []),
        },
    }
