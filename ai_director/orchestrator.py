from __future__ import annotations
from ai_director.config import load_env_config

import json
import os
import re
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
    from .project_context import collect_project_context
    from .reporter import build_run_summary, create_run_dir, write_json, write_text
    from .task_manager import get_next_task, increment_iteration, load_tasks, save_tasks, update_task_status
except ImportError:
    import config
    from apply_engine import apply_plan, build_apply_plan
    from config import DEFAULT_CHECKS, PROMPTS_DIR
    from executor import run_checks
    from file_guard import validate_changed_files
    from llm_client import generate_fix_prompt
    from project_context import collect_project_context
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
MODE_PLANNER_ONLY = "planner_only"
MODE_CODER_DRAFT = "coder_draft"
MODE_REVIEWER_DRAFT = "reviewer_draft"
REVIEW_VERDICTS = {"PASS", "NEEDS_CHANGES", "BLOCKED"}


def main(task_id: str | None = None) -> int:
    tasks_payload = load_tasks()
    task = _get_task_to_run(tasks_payload, task_id=task_id)
    if task is None:
        if task_id:
            print(f"AI Director: no runnable NEW task with id {task_id}.")
        else:
            print("AI Director: no tasks with status NEW.")
        return 0

    task_id = str(task.get("id") or "task")
    task["iterations"] = int(task.get("iterations") or 0)
    run_dir = create_run_dir(task_id)
    write_json(run_dir / "task.json", task)

    update_task_status(tasks_payload, task_id, "IN_PROGRESS")
    save_tasks(tasks_payload)

    draft_context = (
        collect_project_context(
            include_paths=_task_include_paths(task),
            exclude_run_dir=run_dir,
        )
        if _uses_project_context(task)
        else None
    )
    if _is_reviewer_draft(task):
        developer_prompt = _build_reviewer_draft_prompt(task, project_context=draft_context)
    elif _is_coder_draft(task):
        developer_prompt = _build_coder_draft_prompt(task, project_context=draft_context)
    elif _is_planner_only(task):
        developer_prompt = _build_planner_prompt(task, project_context=draft_context)
    else:
        developer_prompt = _build_developer_prompt(task)
    write_text(run_dir / "prompt_for_developer.md", developer_prompt)

    if _is_planner_only(task):
        return _run_planner_only_task(
            task=task,
            tasks_payload=tasks_payload,
            task_id=task_id,
            run_dir=run_dir,
            planner_prompt=developer_prompt,
            planner_context=draft_context,
        )

    if _is_coder_draft(task):
        return _run_coder_draft_task(
            task=task,
            tasks_payload=tasks_payload,
            task_id=task_id,
            run_dir=run_dir,
            coder_prompt=developer_prompt,
            coder_context=draft_context,
        )

    if _is_reviewer_draft(task):
        return _run_reviewer_draft_task(
            task=task,
            tasks_payload=tasks_payload,
            task_id=task_id,
            run_dir=run_dir,
            reviewer_prompt=developer_prompt,
            reviewer_context=draft_context,
        )

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


def _run_planner_only_task(
    *,
    task: dict[str, Any],
    tasks_payload: dict[str, Any],
    task_id: str,
    run_dir: Path,
    planner_prompt: str,
    planner_context: dict[str, Any] | None,
) -> int:
    update_task_status(tasks_payload, task_id, "PLANNING")
    save_tasks(tasks_payload)

    print("Planner-only prompt created")
    llm_result = _call_llm(planner_prompt)
    _attach_context_metadata(llm_result, planner_context)
    write_json(run_dir / "llm_result.json", llm_result)
    llm_response = str(llm_result.get("text") or "")
    write_text(run_dir / "planner_response.md", llm_response)

    check_results = _build_skipped_checks_result("planner_only")
    guard_result = _build_skipped_guard_result("planner_only")
    write_json(run_dir / "check_results.json", check_results)
    write_json(run_dir / "guard_result.json", guard_result)

    if not llm_result["ok"]:
        final_status = str(llm_result["status"])
        update_task_status(tasks_payload, task_id, final_status)
        write_json(run_dir / "apply_plan.json", _build_skipped_apply_plan(final_status, llm_result))
        write_json(run_dir / "apply_result.json", _build_skipped_apply_result(final_status))
        print(f"LLM unavailable: {final_status}. Details saved to llm_result.json")
    else:
        final_status = "DONE"
        update_task_status(tasks_payload, task_id, final_status)
        write_json(run_dir / "apply_plan.json", _build_planner_apply_plan(llm_result))
        write_json(run_dir / "apply_result.json", _build_planner_apply_result())
        print("Planner-only plan saved")
        print("Apply stage skipped by planner_only mode")

    save_tasks(tasks_payload)

    final_report = build_run_summary(
        task=task,
        final_status=final_status,
        checks_result=check_results,
        guard_result=guard_result,
        run_dir=run_dir,
    )
    write_text(run_dir / "final_report.md", final_report)

    print("Checks skipped: planner_only")
    print("Guard skipped: planner_only")
    print("Iterations:", task["iterations"])
    print(
        json.dumps(
            {
                "task_id": task_id,
                "status": final_status,
                "mode": "planner_only",
                "run_dir": str(run_dir),
                "checks_ok": True,
                "file_guard_ok": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if final_status == "DONE" else 1


def _run_coder_draft_task(
    *,
    task: dict[str, Any],
    tasks_payload: dict[str, Any],
    task_id: str,
    run_dir: Path,
    coder_prompt: str,
    coder_context: dict[str, Any] | None,
) -> int:
    update_task_status(tasks_payload, task_id, "CODING_DRAFT")
    save_tasks(tasks_payload)

    print("Coder-draft prompt created")
    llm_result = _call_llm(coder_prompt)
    _attach_context_metadata(llm_result, coder_context)
    _attach_coder_draft_metadata(llm_result)
    write_json(run_dir / "llm_result.json", llm_result)
    coder_output = str(llm_result.get("text") or "")
    write_text(run_dir / "coder_output.md", coder_output)

    check_results = _build_skipped_checks_result(MODE_CODER_DRAFT)
    guard_result = _build_skipped_guard_result(MODE_CODER_DRAFT)
    write_json(run_dir / "check_results.json", check_results)
    write_json(run_dir / "guard_result.json", guard_result)

    if not llm_result["ok"]:
        final_status = str(llm_result["status"])
        update_task_status(tasks_payload, task_id, final_status)
        write_json(run_dir / "apply_plan.json", _build_skipped_apply_plan(final_status, llm_result))
        write_json(run_dir / "apply_result.json", _build_skipped_apply_result(final_status))
        print(f"LLM unavailable: {final_status}. Details saved to llm_result.json")
    else:
        final_status = "DONE"
        update_task_status(tasks_payload, task_id, final_status)
        write_json(run_dir / "apply_plan.json", _build_coder_draft_apply_plan(llm_result))
        write_json(run_dir / "apply_result.json", _build_coder_draft_apply_result())
        print("Coder draft saved")
        print("Apply stage skipped by coder_draft mode")

    save_tasks(tasks_payload)

    final_report = build_run_summary(
        task=task,
        final_status=final_status,
        checks_result=check_results,
        guard_result=guard_result,
        run_dir=run_dir,
    )
    write_text(run_dir / "final_report.md", final_report)

    print("Checks skipped: coder_draft")
    print("Guard skipped: coder_draft")
    print("Iterations:", task["iterations"])
    print(
        json.dumps(
            {
                "task_id": task_id,
                "status": final_status,
                "mode": MODE_CODER_DRAFT,
                "run_dir": str(run_dir),
                "coder_output": str(run_dir / "coder_output.md"),
                "checks_ok": True,
                "file_guard_ok": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if final_status == "DONE" else 1


def _run_reviewer_draft_task(
    *,
    task: dict[str, Any],
    tasks_payload: dict[str, Any],
    task_id: str,
    run_dir: Path,
    reviewer_prompt: str,
    reviewer_context: dict[str, Any] | None,
) -> int:
    update_task_status(tasks_payload, task_id, "REVIEWING_DRAFT")
    save_tasks(tasks_payload)

    print("Reviewer-draft prompt created")
    llm_result = _call_llm(reviewer_prompt)
    _attach_context_metadata(llm_result, reviewer_context)
    _attach_reviewer_draft_metadata(llm_result)
    write_json(run_dir / "llm_result.json", llm_result)
    reviewer_output = str(llm_result.get("text") or "")
    write_text(run_dir / "reviewer_output.md", reviewer_output)

    check_results = _build_skipped_checks_result(MODE_REVIEWER_DRAFT)
    guard_result = _build_skipped_guard_result(MODE_REVIEWER_DRAFT)
    write_json(run_dir / "check_results.json", check_results)
    write_json(run_dir / "guard_result.json", guard_result)

    if not llm_result["ok"]:
        final_status = str(llm_result["status"])
        update_task_status(tasks_payload, task_id, final_status)
        write_json(run_dir / "apply_plan.json", _build_skipped_apply_plan(final_status, llm_result))
        write_json(run_dir / "apply_result.json", _build_skipped_apply_result(final_status))
        print(f"LLM unavailable: {final_status}. Details saved to llm_result.json")
    else:
        final_status = "DONE"
        update_task_status(tasks_payload, task_id, final_status)
        write_json(run_dir / "apply_plan.json", _build_reviewer_draft_apply_plan(llm_result))
        write_json(run_dir / "apply_result.json", _build_reviewer_draft_apply_result())
        print("Reviewer draft saved")
        print("Apply stage skipped by reviewer_draft mode")

    save_tasks(tasks_payload)

    final_report = build_run_summary(
        task=task,
        final_status=final_status,
        checks_result=check_results,
        guard_result=guard_result,
        run_dir=run_dir,
    )
    write_text(run_dir / "final_report.md", final_report)

    print("Checks skipped: reviewer_draft")
    print("Guard skipped: reviewer_draft")
    print("Iterations:", task["iterations"])
    print(
        json.dumps(
            {
                "task_id": task_id,
                "status": final_status,
                "mode": MODE_REVIEWER_DRAFT,
                "run_dir": str(run_dir),
                "reviewer_output": str(run_dir / "reviewer_output.md"),
                "review_verdict": llm_result.get("review_verdict"),
                "checks_ok": True,
                "file_guard_ok": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if final_status == "DONE" else 1


def _get_task_to_run(tasks_payload: dict[str, Any], *, task_id: str | None = None) -> dict[str, Any] | None:
    if task_id is None:
        return get_next_task(tasks_payload)

    tasks = tasks_payload.get("tasks", [])
    if not isinstance(tasks, list):
        return None

    for task in tasks:
        if not isinstance(task, dict):
            continue
        if str(task.get("id") or "") != str(task_id):
            continue
        status = str(task.get("status") or "NEW").strip().upper()
        iterations = int(task.get("iterations") or 0)
        max_iterations = int(task.get("max_iterations") or 3)
        if status == "NEW" and iterations < max_iterations:
            return task
        return None

    return None


def _attach_context_metadata(llm_result: dict[str, Any], planner_context: dict[str, Any] | None) -> None:
    llm_result["context_included"] = bool(planner_context and planner_context.get("included"))
    llm_result["context_chars"] = int(planner_context.get("chars") or 0) if planner_context else 0
    llm_result["include_paths"] = list(planner_context.get("include_paths") or []) if planner_context else []
    llm_result["included_files"] = list(planner_context.get("included_files") or []) if planner_context else []
    llm_result["missing_files"] = list(planner_context.get("missing_files") or []) if planner_context else []


def _attach_coder_draft_metadata(llm_result: dict[str, Any]) -> None:
    llm_response = str(llm_result.get("text") or "")
    llm_result["mode"] = MODE_CODER_DRAFT
    llm_result["files_suggested"] = _extract_files_suggested(llm_response)
    llm_result["has_code"] = _has_code_block(llm_response)


def _attach_reviewer_draft_metadata(llm_result: dict[str, Any]) -> None:
    llm_response = str(llm_result.get("text") or "")
    llm_result["mode"] = MODE_REVIEWER_DRAFT
    llm_result["has_review"] = bool(llm_result.get("ok") and llm_response.strip())
    llm_result["review_verdict"] = _extract_review_verdict(llm_response)


def _call_llm(prompt: str) -> dict[str, Any]:
    provider = LLM_PROVIDER
    env = load_env_config()

    model = (
        env.get("OPENROUTER_MODEL")
        or os.getenv("AI_DIRECTOR_MODEL")
        or DEFAULT_OPENROUTER_MODEL
    )
    fallback_models = [
        item.strip()
        for item in (
            env.get("AI_DIRECTOR_MODEL_FALLBACKS")
            or os.getenv("AI_DIRECTOR_MODEL_FALLBACKS", "")
        ).split(",")
        if item.strip()
    ]

    api_key = env.get("OPENROUTER_API_KEY") or os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return _llm_error_result(
            status="no_llm",
            provider=provider,
            model=model,
            text="ERROR: OPENROUTER_API_KEY not found in .env or environment",
            attempted_models=[],
            selected_model="",
            last_error="ERROR: OPENROUTER_API_KEY not found in .env or environment",
        )

    # generate_text_result reads configuration from process environment.
    os.environ["OPENROUTER_API_KEY"] = api_key
    os.environ["AI_DIRECTOR_MODEL"] = model
    if fallback_models:
        os.environ["AI_DIRECTOR_MODEL_FALLBACKS"] = ",".join(fallback_models)

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
        "reason": status,
        "actions": [],
        "message": f"Apply skipped because LLM status is {status}.",
    }


def _build_planner_apply_plan(llm_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "mode": "planner_only",
        "dry_run": True,
        "skipped": True,
        "reason": "planner_only",
        "plan": str(llm_result.get("text") or ""),
        "actions": [],
        "llm": {
            "provider": llm_result.get("provider"),
            "model": llm_result.get("model"),
            "configured_model": llm_result.get("configured_model"),
            "attempted_models": llm_result.get("attempted_models"),
            "selected_model": llm_result.get("selected_model"),
            "status": llm_result.get("status"),
            "final_status": llm_result.get("final_status"),
            "last_error": llm_result.get("last_error"),
            "context_included": llm_result.get("context_included"),
            "context_chars": llm_result.get("context_chars"),
            "include_paths": llm_result.get("include_paths"),
            "included_files": llm_result.get("included_files"),
            "missing_files": llm_result.get("missing_files"),
        },
    }


def _build_planner_apply_result() -> dict[str, Any]:
    return {
        "ok": True,
        "dry_run": True,
        "applied": False,
        "skipped": True,
        "reason": "planner_only",
        "actions": [],
        "message": "Planner-only mode: plan saved, no code changes applied.",
    }


def _build_coder_draft_apply_plan(llm_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "mode": MODE_CODER_DRAFT,
        "dry_run": True,
        "skipped": True,
        "reason": MODE_CODER_DRAFT,
        "coder_output": "coder_output.md",
        "files_suggested": list(llm_result.get("files_suggested") or []),
        "has_code": bool(llm_result.get("has_code")),
        "actions": [],
        "llm": {
            "provider": llm_result.get("provider"),
            "model": llm_result.get("model"),
            "configured_model": llm_result.get("configured_model"),
            "attempted_models": llm_result.get("attempted_models"),
            "selected_model": llm_result.get("selected_model"),
            "status": llm_result.get("status"),
            "final_status": llm_result.get("final_status"),
            "last_error": llm_result.get("last_error"),
            "context_included": llm_result.get("context_included"),
            "context_chars": llm_result.get("context_chars"),
            "include_paths": llm_result.get("include_paths"),
            "included_files": llm_result.get("included_files"),
            "missing_files": llm_result.get("missing_files"),
            "files_suggested": llm_result.get("files_suggested"),
            "has_code": llm_result.get("has_code"),
        },
    }


def _build_coder_draft_apply_result() -> dict[str, Any]:
    return {
        "ok": True,
        "dry_run": True,
        "applied": False,
        "skipped": True,
        "reason": MODE_CODER_DRAFT,
        "actions": [],
        "message": "Coder-draft mode: code draft saved, no files changed.",
    }


def _build_reviewer_draft_apply_plan(llm_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "mode": MODE_REVIEWER_DRAFT,
        "dry_run": True,
        "skipped": True,
        "reason": MODE_REVIEWER_DRAFT,
        "reviewer_output": "reviewer_output.md",
        "has_review": bool(llm_result.get("has_review")),
        "review_verdict": str(llm_result.get("review_verdict") or "UNKNOWN"),
        "actions": [],
        "llm": {
            "provider": llm_result.get("provider"),
            "model": llm_result.get("model"),
            "configured_model": llm_result.get("configured_model"),
            "attempted_models": llm_result.get("attempted_models"),
            "selected_model": llm_result.get("selected_model"),
            "status": llm_result.get("status"),
            "final_status": llm_result.get("final_status"),
            "last_error": llm_result.get("last_error"),
            "context_included": llm_result.get("context_included"),
            "context_chars": llm_result.get("context_chars"),
            "include_paths": llm_result.get("include_paths"),
            "included_files": llm_result.get("included_files"),
            "missing_files": llm_result.get("missing_files"),
            "has_review": llm_result.get("has_review"),
            "review_verdict": llm_result.get("review_verdict"),
        },
    }


def _build_reviewer_draft_apply_result() -> dict[str, Any]:
    return {
        "ok": True,
        "dry_run": True,
        "applied": False,
        "skipped": True,
        "reason": MODE_REVIEWER_DRAFT,
        "actions": [],
        "message": "Reviewer-draft mode: review saved, no files changed.",
    }


def _build_skipped_checks_result(reason: str) -> dict[str, Any]:
    return {
        "ok": True,
        "skipped": True,
        "reason": reason,
        "results": [],
    }


def _build_skipped_guard_result(reason: str) -> dict[str, Any]:
    return {
        "ok": True,
        "skipped": True,
        "reason": reason,
        "changed_files": [],
        "violations": [],
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


def _build_planner_prompt(task: dict[str, Any], *, project_context: dict[str, Any] | None = None) -> str:
    context_text = ""
    if project_context and project_context.get("included"):
        context_text = str(project_context.get("text") or "").strip()

    parts = [
        "# Prompt for AI Director Planner",
        "",
        "You are the AI Director Planner.",
        "Analyze the task and return a concise plan only.",
        "Do not modify code. Do not propose an apply patch.",
        "Focus on the smallest useful next step.",
        "",
        context_text or "(project context unavailable)",
        "",
        "## Task",
        "```json",
        json.dumps(task, ensure_ascii=False, indent=2),
        "```",
    ]
    return "\n".join(parts).strip() + "\n"


def _build_coder_draft_prompt(task: dict[str, Any], *, project_context: dict[str, Any] | None = None) -> str:
    context_text = ""
    if project_context and project_context.get("included"):
        context_text = str(project_context.get("text") or "").strip()

    parts = [
        "# Prompt for AI Director Coder Draft",
        "",
        "You are a senior Python developer working in safe draft mode.",
        "Generate code for the task, but do not modify files, do not run commands, and do not apply patches.",
        "Use the project structure and the included files as your only source context.",
        "Work only with the requested include_paths for existing-file context.",
        "Do not make assumptions about files outside the provided context.",
        "If the task asks for a new file, provide the full proposed file content.",
        "If the task requires modifying an existing file that was not included, list it but explain the missing context in the summary.",
        "",
        context_text or "(project context unavailable)",
        "",
        "## Task",
        "```json",
        json.dumps(task, ensure_ascii=False, indent=2),
        "```",
        "",
        "Return strictly this Markdown structure and nothing outside it:",
        "",
        "# Summary",
        "...",
        "",
        "# Files to create",
        "- path/to/file.py",
        "",
        "# Files to modify",
        "- path/to/file.py",
        "",
        "# Code",
        "",
        "## path/to/file.py",
        "```python",
        "<full code file content>",
        "```",
        "",
        "# Tests",
        "...",
        "",
        "# Run instructions",
        "...",
        "",
        "# VS Code instructions",
        "...",
    ]
    return "\n".join(parts).strip() + "\n"


def _build_reviewer_draft_prompt(task: dict[str, Any], *, project_context: dict[str, Any] | None = None) -> str:
    context_text = ""
    if project_context and project_context.get("included"):
        context_text = str(project_context.get("text") or "").strip()

    parts = [
        "# Prompt for AI Director Reviewer Draft",
        "",
        "You are a senior Python code reviewer working in safe review mode.",
        "Review the supplied code or text only. Do not modify files, do not run commands, do not apply patches, and do not write code into the project.",
        "Use the project structure and include_paths content as your only source context.",
        "Do not make assumptions about files outside the provided context.",
        "If required code or tests are missing from include_paths, mark related checks as UNKNOWN or BLOCKED.",
        "",
        "Check all of the following:",
        "- whether the code satisfies the task requirements;",
        "- whether business logic is preserved;",
        "- edge cases;",
        "- risks around empty values, wrong fallbacks, or data loss;",
        "- unnecessary complexity;",
        "- whether tests are sufficient;",
        "- which tests should be added;",
        "- whether the code can be applied safely.",
        "",
        context_text or "(project context unavailable)",
        "",
        "## Task",
        "```json",
        json.dumps(task, ensure_ascii=False, indent=2),
        "```",
        "",
        "Return strictly this Markdown structure and nothing outside it:",
        "",
        "# Review verdict",
        "PASS / NEEDS_CHANGES / BLOCKED",
        "",
        "# Summary",
        "Краткая оценка.",
        "",
        "# Requirement check",
        "- requirement: ...",
        "  status: PASS/FAIL/UNKNOWN",
        "  comment: ...",
        "",
        "# Issues",
        "## Critical",
        "- ...",
        "",
        "## Major",
        "- ...",
        "",
        "## Minor",
        "- ...",
        "",
        "# Test recommendations",
        "- ...",
        "",
        "# Suggested fixes",
        "- ...",
        "",
        "# Final recommendation",
        "Применять / не применять / применить после правок.",
    ]
    return "\n".join(parts).strip() + "\n"


def _is_planner_only(task: dict[str, Any]) -> bool:
    return _task_mode(task) == MODE_PLANNER_ONLY


def _is_coder_draft(task: dict[str, Any]) -> bool:
    return _task_mode(task) == MODE_CODER_DRAFT


def _is_reviewer_draft(task: dict[str, Any]) -> bool:
    return _task_mode(task) == MODE_REVIEWER_DRAFT


def _uses_project_context(task: dict[str, Any]) -> bool:
    return _task_mode(task) in {MODE_PLANNER_ONLY, MODE_CODER_DRAFT, MODE_REVIEWER_DRAFT}


def _task_mode(task: dict[str, Any]) -> str:
    return str(task.get("mode") or "").strip().lower()


def _task_include_paths(task: dict[str, Any]) -> list[str]:
    include_paths = task.get("include_paths")
    if isinstance(include_paths, str):
        return [include_paths]
    if not isinstance(include_paths, list):
        return []
    return [str(path) for path in include_paths if str(path).strip()]


def _extract_files_suggested(text: str) -> list[str]:
    files: list[str] = []
    for section in ("Files to create", "Files to modify"):
        files.extend(_extract_section_bullets(text, section))

    for match in re.finditer(r"(?m)^##\s+(.+?)\s*$", text):
        path = match.group(1).strip()
        if path and not path.startswith("#"):
            files.append(path)

    seen = set()
    result: list[str] = []
    for path in files:
        normalized = path.strip().strip("`").replace("\\", "/")
        if _is_empty_file_marker(normalized) or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _extract_section_bullets(text: str, section: str) -> list[str]:
    pattern = rf"(?ms)^#\s+{re.escape(section)}\s*\n(?P<body>.*?)(?=^#\s+|\Z)"
    match = re.search(pattern, text)
    if not match:
        return []

    files = []
    for line in match.group("body").splitlines():
        stripped = line.strip()
        if not stripped.startswith("-"):
            continue
        value = stripped[1:].strip().strip("`")
        if value:
            files.append(value)
    return files


def _has_code_block(text: str) -> bool:
    return bool(re.search(r"```(?:\w+)?\s*\n.+?\n```", text, flags=re.DOTALL))


def _extract_review_verdict(text: str) -> str:
    match = re.search(r"(?ims)^#\s+Review verdict\s*\n(?P<body>.*?)(?=^#\s+|\Z)", text)
    if not match:
        return "UNKNOWN"

    for line in match.group("body").splitlines():
        normalized = line.strip().strip("*_`:- ").upper()
        if not normalized:
            continue
        if "/" in normalized and sum(verdict in normalized for verdict in REVIEW_VERDICTS) > 1:
            continue
        verdict = normalized.split()[0].strip(":")
        if normalized.startswith("NEEDS_CHANGES"):
            verdict = "NEEDS_CHANGES"
        if verdict in REVIEW_VERDICTS:
            return verdict
    return "UNKNOWN"


def _is_empty_file_marker(value: str) -> bool:
    normalized = re.sub(r"^[\s*_`]+|[\s*_`]+$", "", value).strip().lower().rstrip(".")
    return normalized in {"", "(none)", "none", "n/a", "not applicable"} or normalized.startswith("no ")


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
