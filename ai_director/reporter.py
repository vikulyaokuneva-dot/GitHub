from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from .config import RUNS_DIR
except ImportError:
    from config import RUNS_DIR


def create_run_dir(task_id: str, base_dir: str | Path = RUNS_DIR) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_task_id = "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in task_id)
    run_dir = Path(base_dir) / f"{timestamp}_{safe_task_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def write_text(path: str | Path, content: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def write_json(path: str | Path, payload: Any) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")
    return target


def build_run_summary(
    *,
    task: dict[str, Any],
    final_status: str,
    checks_result: dict[str, Any],
    guard_result: dict[str, Any],
    run_dir: str | Path,
) -> str:
    checks_ok = bool(checks_result.get("ok"))
    guard_ok = bool(guard_result.get("ok"))
    changed_files = guard_result.get("changed_files") or []
    violations = guard_result.get("violations") or []

    lines = [
        f"# AI Director Run: {task.get('id', 'unknown')}",
        "",
        f"Status: {final_status}",
        f"Title: {task.get('title', '')}",
        f"Run dir: {Path(run_dir)}",
        "",
        "## Checks",
        f"OK: {checks_ok}",
    ]
    for item in checks_result.get("results", []):
        if not isinstance(item, dict):
            continue
        lines.append(f"- `{item.get('command')}` -> {item.get('returncode')}")

    lines.extend(
        [
            "",
            "## File Guard",
            f"OK: {guard_ok}",
            f"Changed files: {len(changed_files)}",
        ]
    )
    for path in changed_files:
        lines.append(f"- {path}")
    if violations:
        lines.append("")
        lines.append("## Violations")
        for path in violations:
            lines.append(f"- {path}")

    return "\n".join(lines).strip() + "\n"
