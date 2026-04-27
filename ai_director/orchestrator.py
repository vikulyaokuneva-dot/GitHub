from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    from . import config
    from .apply_engine import apply_plan, build_apply_plan
    from .config import DEFAULT_CHECKS, PROMPTS_DIR
    from .executor import run_checks
    from .file_guard import validate_changed_files
    from .llm_client import generate_fix_prompt
    from .reporter import build_run_summary, create_run_dir, write_json, write_text
    from .task_manager import get_next_task, increment_iteration, load_tasks, save_tasks, update_task_status
except ImportError:
    import config
    from apply_engine import apply_plan, build_apply_plan
    from config import DEFAULT_CHECKS, PROMPTS_DIR
    from executor import run_checks
    from file_guard import validate_changed_files
    from llm_client import generate_fix_prompt
    from reporter import build_run_summary, create_run_dir, write_json, write_text
    from task_manager import get_next_task, increment_iteration, load_tasks, save_tasks, update_task_status

try:
    from src.openrouter_client import generate_text_result
except ModuleNotFoundError:
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from src.openrouter_client import generate_text_result


LLM_PROVIDER = getattr(config, "LLM_PROVIDER", "openrouter")
DEFAULT_OPENROUTER_MODEL = getattr(config, "DEFAULT_AI_DIRECTOR_MODEL", "qwen/qwen3-coder:free")


def main() -> int:
    tasks_payload = load_tasks()
    task = get_next_task(tasks_payload)
    if task is None:
        print("AI Director: no tasks with status NEW.")
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
        print("Fixer Agent prompt created")

        llm_result = _call_llm(fix_prompt)
        write_json(run_dir / "llm_result.json", llm_result)
        llm_response = str(llm_result.get("text") or "")
        write_text(run_dir / "fix_response.md", llm_response)

        if not llm_result["ok"]:
            final_status = str(llm_result["status"])
            update_task_status(tasks_payload, task_id, final_status)
            write_json(run_dir / "apply_plan.json", _build_skipped_apply_plan(final_status, llm_result))
            write_json(run_dir / "apply_result.json", _build_skipped_apply_result(final_status))
            print(f"LLM unavailable: {final_status}. Details saved to llm_result.json")
        else:
            apply_plan_data = build_apply_plan(llm_response, config.PROJECT_ROOT)
            write_json(run_dir / "apply_plan.json", apply_plan_data)

            apply_result = apply_plan(apply_plan_data, config.PROJECT_ROOT, dry_run=True)
            write_json(run_dir / "apply_result.json", apply_result)

            print("Apply plan created")
            print("Apply stage completed in dry-run mode")
            print("LLM response saved")

            iterations = int(task.get("iterations") or 0)
            max_iterations = int(task.get("max_iterations") or 3)
            if iterations >= max_iterations:
                final_status = "NEEDS_HUMAN"
                update_task_status(tasks_payload, task_id, final_status)
                print(f"Task {task_id} needs human intervention")
            else:
                final_status = "FAILED"
                update_task_status(tasks_payload, task_id, final_status)
                print(f"Task {task_id} failed checks and can be retried")

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


def _call_llm(prompt: str) -> dict[str, Any]:
    provider = LLM_PROVIDER
    model = os.getenv("AI_DIRECTOR_MODEL", DEFAULT_OPENROUTER_MODEL)
    fallback_models = [
        item.strip()
        for item in os.getenv("AI_DIRECTOR_MODEL_FALLBACKS", "").split(",")
        if item.strip()
    ]
    print(f"LLM provider={provider} model={model} fallbacks={fallback_models}")

    try:
        result = generate_text_result(prompt)
    except Exception as exc:
        return _llm_error_result(
            status="api_error",
            provider=provider,
            model=model,
            text=f"ERROR: {exc}",
            attempted_models=[],
            selected_model="",
            last_error=f"ERROR: {exc}",
        )

    attempted_models = list(result.get("attempted_models") or [])
    selected_model = str(result.get("selected_model") or "")
    final_status = str(result.get("final_status") or result.get("status") or "api_error")
    last_error = str(result.get("last_error") or result.get("error") or "")
    text = str(result.get("text") or "")

    if not isinstance(text, str) or not text.strip():
        return _llm_error_result(
            status="api_error",
            provider=provider,
            model=model,
            text="ERROR: empty OpenRouter response",
            attempted_models=attempted_models,
            selected_model=selected_model,
            last_error="ERROR: empty OpenRouter response",
        )

    if not bool(result.get("ok")):
        return _llm_error_result(
            status=final_status,
            provider=provider,
            model=model,
            text=text,
            attempted_models=attempted_models,
            selected_model=selected_model,
            last_error=last_error or text,
            errors=list(result.get("errors") or []),
        )

    return {
        "ok": True,
        "status": "ok",
        "final_status": "ok",
        "provider": provider,
        "model": selected_model or model,
        "configured_model": model,
        "attempted_models": attempted_models,
        "selected_model": selected_model or model,
        "text": text,
        "error": "",
        "last_error": last_error,
        "errors": list(result.get("errors") or []),
    }


def _llm_error_result(
    *,
    status: str,
    provider: str,
    model: str,
    text: str,
    attempted_models: list[str] | None = None,
    selected_model: str = "",
    last_error: str = "",
    errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "ok": False,
        "status": status,
        "final_status": status,
        "provider": provider,
        "model": model,
        "configured_model": model,
        "attempted_models": attempted_models or [],
        "selected_model": selected_model,
        "text": text,
        "error": last_error or text,
        "last_error": last_error or text,
        "errors": errors or [],
    }


def _build_skipped_apply_plan(status: str, llm_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": False,
        "dry_run": True,
        "skipped": True,
        "reason": status,
        "llm": {
            "provider": llm_result.get("provider"),
            "model": llm_result.get("model"),
            "configured_model": llm_result.get("configured_model"),
            "attempted_models": llm_result.get("attempted_models"),
            "selected_model": llm_result.get("selected_model"),
            "status": llm_result.get("status"),
            "final_status": llm_result.get("final_status"),
            "error": llm_result.get("error"),
            "last_error": llm_result.get("last_error"),
        },
    }


def _build_skipped_apply_result(status: str) -> dict[str, Any]:
    return {
        "ok": False,
        "dry_run": True,
        "applied": False,
        "skipped": True,
        "actions": [],
        "message": f"Apply skipped because LLM status is {status}.",
    }


def _classify_llm_error(text: str) -> str | None:
    normalized = text.strip().lower()
    if not normalized.startswith("error"):
        return None

    if (
        "openrouter_api_key" in normalized
        or "api key" in normalized
        or "401" in normalized
        or "403" in normalized
        or "unauthorized" in normalized
        or "forbidden" in normalized
    ):
        return "no_llm"
    return "api_error"


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
