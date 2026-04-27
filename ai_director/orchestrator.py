from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from .config import DEFAULT_CHECKS, PROMPTS_DIR
    from .executor import run_checks
    from .file_guard import validate_changed_files
    from .reporter import build_run_summary, create_run_dir, write_json, write_text
    from .task_manager import get_next_task, increment_iteration, load_tasks, save_tasks, update_task_status
except ImportError:
    from config import DEFAULT_CHECKS, PROMPTS_DIR
    from executor import run_checks
    from file_guard import validate_changed_files
    from reporter import build_run_summary, create_run_dir, write_json, write_text
    from task_manager import get_next_task, increment_iteration, load_tasks, save_tasks, update_task_status


def main() -> int:
    tasks_payload = load_tasks()
    task = get_next_task(tasks_payload)
    if task is None:
        print("AI Director: нет задач со статусом NEW.")
        return 0

    task_id = str(task.get("id") or "task")
    run_dir = create_run_dir(task_id)
    write_json(run_dir / "task.json", task)

    update_task_status(tasks_payload, task_id, "IN_PROGRESS")
    increment_iteration(tasks_payload, task_id)
    save_tasks(tasks_payload)

    developer_prompt = _build_developer_prompt(task)
    write_text(run_dir / "prompt_for_developer.md", developer_prompt)

    update_task_status(tasks_payload, task_id, "READY_TO_CHECK")
    save_tasks(tasks_payload)

    update_task_status(tasks_payload, task_id, "CHECKING")
    save_tasks(tasks_payload)

    checks = task.get("checks")
    if not isinstance(checks, list) or not checks:
        checks = DEFAULT_CHECKS
    checks_result = run_checks([str(command) for command in checks])
    write_json(run_dir / "check_results.json", checks_result)

    guard_result = validate_changed_files()
    write_json(run_dir / "guard_result.json", guard_result)

    final_status = "DONE" if checks_result.get("ok") and guard_result.get("ok") else "FAILED"
    update_task_status(tasks_payload, task_id, final_status)
    save_tasks(tasks_payload)

    final_report = build_run_summary(
        task=task,
        final_status=final_status,
        checks_result=checks_result,
        guard_result=guard_result,
        run_dir=run_dir,
    )
    write_text(run_dir / "final_report.md", final_report)

    print(
        json.dumps(
            {
                "task_id": task_id,
                "status": final_status,
                "run_dir": str(run_dir),
                "checks_ok": bool(checks_result.get("ok")),
                "file_guard_ok": bool(guard_result.get("ok")),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if final_status == "DONE" else 1


def _build_developer_prompt(task: dict[str, Any]) -> str:
    parts = [
        "# Prompt for Developer Agent",
        "",
        _read_prompt("system_rules.md"),
        "",
        _read_prompt("developer_agent.md"),
        "",
        "## Task",
        "```json",
        json.dumps(task, ensure_ascii=False, indent=2),
        "```",
    ]
    return "\n".join(parts).strip() + "\n"


def _read_prompt(filename: str) -> str:
    path = Path(PROMPTS_DIR) / filename
    if not path.is_file():
        return f"<!-- missing prompt: {filename} -->"
    return path.read_text(encoding="utf-8").strip()


if __name__ == "__main__":
    raise SystemExit(main())
