from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from .config import DEFAULT_CHECKS, PROMPTS_DIR
    from .executor import run_checks
    from .file_guard import validate_changed_files
    from .llm_client import call_llm, generate_fix_prompt
    from .reporter import build_run_summary, create_run_dir, write_json, write_text
    from .task_manager import get_next_task, increment_iteration, load_tasks, save_tasks, update_task_status
except ImportError:
    from config import DEFAULT_CHECKS, PROMPTS_DIR
    from executor import run_checks
    from file_guard import validate_changed_files
    from llm_client import call_llm, generate_fix_prompt
    from reporter import build_run_summary, create_run_dir, write_json, write_text
    from task_manager import get_next_task, increment_iteration, load_tasks, save_tasks, update_task_status


def main() -> int:
    tasks_payload = load_tasks()
    task = get_next_task(tasks_payload)
    if task is None:
        print("AI Director: нет задач со статусом NEW.")
        return 0

    task_id = str(task.get("id") or "task")
    task["iterations"] = int(task.get("iterations") or 0)
    run_dir = create_run_dir(task_id)
    write_json(run_dir / "task.json", task)

    update_task_status(tasks_payload, task_id, "IN_PROGRESS")
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
    check_results = run_checks([str(command) for command in checks])
    _ensure_check_success_flags(check_results)
    write_json(run_dir / "check_results.json", check_results)

    guard_result = validate_changed_files()
    write_json(run_dir / "guard_result.json", guard_result)

    all_checks_passed = all(r["success"] for r in check_results["results"])
    guard_ok = bool(guard_result["ok"])

    if all_checks_passed and guard_ok:
        final_status = "DONE"
        update_task_status(tasks_payload, task_id, final_status)
    else:
        increment_iteration(tasks_payload, task_id)
        failure_snapshot = {
            "checks": check_results,
            "guard": guard_result,
        }
        write_json(run_dir / "failure_snapshot.json", failure_snapshot)

        fix_prompt = generate_fix_prompt(task, failure_snapshot)
        write_text(run_dir / "fix_prompt.md", fix_prompt)
        print("🤖 Fixer Agent prompt создан")

        llm_response = call_llm(fix_prompt)
        write_text(run_dir / "fix_response.md", llm_response)
        print("🤖 Ответ LLM сохранён (mock)")

        iterations = int(task.get("iterations") or 0)
        max_iterations = int(task.get("max_iterations") or 3)
        if iterations >= max_iterations:
            final_status = "NEEDS_HUMAN"
            update_task_status(tasks_payload, task_id, final_status)
            print(f"❌ Задача {task_id} требует вмешательства человека")
        else:
            final_status = "FAILED"
            update_task_status(tasks_payload, task_id, final_status)
            print(f"⚠️ Задача {task_id} не прошла проверки, можно повторить")

    print("Checks passed:", all_checks_passed)
    print("Guard ok:", guard_ok)
    print("Iterations:", task["iterations"])
    save_tasks(tasks_payload)

    final_report = build_run_summary(
        task=task,
        final_status=final_status,
        checks_result=check_results,
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
                "checks_ok": all_checks_passed,
                "file_guard_ok": guard_ok,
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


def _ensure_check_success_flags(check_results: dict[str, Any]) -> None:
    results = check_results.get("results")
    if not isinstance(results, list):
        check_results["results"] = []
        return
    for item in results:
        if not isinstance(item, dict):
            continue
        if "success" not in item:
            item["success"] = item.get("returncode") == 0 and not bool(item.get("timed_out"))


def _read_prompt(filename: str) -> str:
    path = Path(PROMPTS_DIR) / filename
    if not path.is_file():
        return f"<!-- missing prompt: {filename} -->"
    return path.read_text(encoding="utf-8").strip()


if __name__ == "__main__":
    raise SystemExit(main())
