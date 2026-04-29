from __future__ import annotations

import argparse
import ast
import difflib
import json
import os
import re
import sys
from pathlib import Path, PureWindowsPath
from typing import Any

try:
    from . import config
    from .apply_engine import apply_plan, build_apply_plan, build_unified_diff_text, parse_auto_apply_json_response
    from .config import DEFAULT_CHECKS, PROMPTS_DIR, load_env_config
    from .executor import run_checks
    from .file_guard import validate_changed_files
    from .logger import log_event
    from .llm_client import generate_fix_prompt
    from .project_context import collect_project_context
    from .reporter import build_run_summary, create_run_dir, write_json, write_text
    from .task_manager import get_next_task, increment_iteration, load_tasks, save_tasks, update_task_status
except ImportError:
    import config
    from apply_engine import apply_plan, build_apply_plan, build_unified_diff_text, parse_auto_apply_json_response
    from config import DEFAULT_CHECKS, PROMPTS_DIR, load_env_config
    from executor import run_checks
    from file_guard import validate_changed_files
    from logger import log_event
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
DEFAULT_OPENROUTER_MODEL = getattr(config, "DEFAULT_AI_DIRECTOR_MODEL", "openai/gpt-oss-120b:free")
DEFAULT_OPENROUTER_FALLBACK_MODELS = list(
    getattr(
        config,
        "DEFAULT_AI_DIRECTOR_MODEL_FALLBACKS",
        (
            "qwen/qwen3-next-80b-a3b-instruct:free",
            "mistralai/mistral-7b-instruct",
        ),
    )
)
MODE_PLANNER_ONLY = "planner_only"
MODE_CODER_DRAFT = "coder_draft"
MODE_REVIEWER_DRAFT = "reviewer_draft"
MODE_AUTO_APPLY_DRAFT = "auto_apply_draft"
REVIEW_VERDICTS = {"PASS", "NEEDS_CHANGES", "BLOCKED"}
FORBIDDEN_AUTO_APPLY_PATHS = (
    ".git",
    ".env",
    "credentials",
    "secrets",
)


def main(task_id: str | None = None) -> int:
    tasks_payload = load_tasks()
    task = _get_task_to_run(tasks_payload, task_id=task_id)
    if task is None:
        if task_id:
            print(f"AI Director: no runnable NEW task with id {task_id}.")
        else:
            print("AI Director: no tasks with status NEW.")
        log_event("No runnable task found")
        return 0

    task_id = str(task.get("id") or "task")
    log_event(f"Task started: {task_id}")
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
    if _is_auto_apply_draft(task):
        developer_prompt = _build_auto_apply_json_prompt(task)
    elif _is_reviewer_draft(task):
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

    if _is_auto_apply_draft(task):
        return _run_auto_apply_draft_task(
            task=task,
            tasks_payload=tasks_payload,
            task_id=task_id,
            run_dir=run_dir,
            coder_prompt=developer_prompt,
            coder_context=draft_context,
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
    log_event(f"Task finished: {task_id} status={final_status}")
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
    log_event(f"Task finished: {task_id} status={final_status}")
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
    log_event(f"Task finished: {task_id} status={final_status}")
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
    log_event(f"Task finished: {task_id} status={final_status}")
    return 0 if final_status == "DONE" else 1


def _run_auto_apply_draft_task(
    *,
    task: dict[str, Any],
    tasks_payload: dict[str, Any],
    task_id: str,
    run_dir: Path,
    coder_prompt: str,
    coder_context: dict[str, Any] | None,
) -> int:
    print("Auto-apply draft started")
    source_path, source_error = _find_coder_output_source(task, config.PROJECT_ROOT)
    apply_plan_data: dict[str, Any]
    auto_apply_diff = ""
    llm_result: dict[str, Any] | None = None
    raw_response = ""
    source_name = "coder_output.md"
    needs_human = False

    if source_path is None and source_error == "coder_output_not_in_include_paths":
        update_task_status(tasks_payload, task_id, "CODING_DRAFT")
        save_tasks(tasks_payload)

        print("Auto-apply JSON prompt created")
        llm_result = _call_llm(coder_prompt)
        _attach_context_metadata(llm_result, coder_context)
        llm_result["mode"] = MODE_AUTO_APPLY_DRAFT
        raw_response = str(llm_result.get("text") or "")
        write_text(run_dir / "coder_output.md", raw_response)

        if not llm_result["ok"]:
            auto_apply_result = _build_auto_apply_error_result(str(llm_result.get("status") or "llm_error"))
            apply_plan_data = _build_auto_apply_plan([], source=source_name, error=auto_apply_result["violations"][0]["reason"])
        else:
            update_task_status(tasks_payload, task_id, "APPLYING_DRAFT")
            save_tasks(tasks_payload)
            parsed_response = parse_auto_apply_json_response(raw_response)
            if not parsed_response["ok"]:
                needs_human = True
                write_text(run_dir / "llm_raw_response.txt", raw_response)
                auto_apply_result = _build_auto_apply_error_result(str(parsed_response.get("reason") or "invalid_format"))
                apply_plan_data = _build_auto_apply_plan([], source=source_name, error="invalid_format")
                llm_result["ok"] = False
                llm_result["status"] = "invalid_format"
                llm_result["final_status"] = "invalid_format"
                llm_result["error"] = "invalid_format"
                llm_result["last_error"] = "invalid_format"
            else:
                files = list(parsed_response.get("files") or [])
                apply_plan_data = _build_auto_apply_plan(files, source=source_name)
                auto_apply_diff = _build_auto_apply_diff(files, project_root=config.PROJECT_ROOT)
                auto_apply_result = apply_auto_apply_files(
                    files,
                    project_root=config.PROJECT_ROOT,
                    source=source_name,
                )
    elif source_path is None:
        update_task_status(tasks_payload, task_id, "APPLYING_DRAFT")
        save_tasks(tasks_payload)
        auto_apply_result = _build_auto_apply_error_result(source_error or "coder_output.md not found")
        apply_plan_data = _build_auto_apply_plan([], source="coder_output.md", error=source_error)
    else:
        update_task_status(tasks_payload, task_id, "APPLYING_DRAFT")
        save_tasks(tasks_payload)
        source_name = source_path.name
        try:
            raw_response = source_path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            auto_apply_result = _build_auto_apply_error_result(f"cannot read coder_output.md: {exc}")
            apply_plan_data = _build_auto_apply_plan([], source=source_name, error=str(exc))
        else:
            parsed_response = parse_auto_apply_json_response(raw_response)
            if not parsed_response["ok"]:
                needs_human = True
                write_text(run_dir / "llm_raw_response.txt", raw_response)
                auto_apply_result = _build_auto_apply_error_result(str(parsed_response.get("reason") or "invalid_format"))
                apply_plan_data = _build_auto_apply_plan([], source=source_name, error="invalid_format")
            else:
                files = list(parsed_response.get("files") or [])
                apply_plan_data = _build_auto_apply_plan(files, source=source_name)
                auto_apply_diff = _build_auto_apply_diff(files, project_root=config.PROJECT_ROOT)
                auto_apply_result = apply_auto_apply_files(
                    files,
                    project_root=config.PROJECT_ROOT,
                    source=source_name,
                )

    write_json(run_dir / "apply_plan.json", apply_plan_data)
    write_json(run_dir / "auto_apply_result.json", auto_apply_result)
    write_json(run_dir / "apply_result.json", auto_apply_result)
    write_text(run_dir / "auto_apply.diff", auto_apply_diff)
    write_json(run_dir / "llm_result.json", _build_auto_apply_llm_result(task, auto_apply_result, llm_result=llm_result))

    if auto_apply_result.get("ok"):
        update_task_status(tasks_payload, task_id, "CHECKING")
        save_tasks(tasks_payload)
        check_results = run_checks(_auto_apply_check_commands(task, auto_apply_result))
        _ensure_check_success_flags(check_results)
        guard_result = validate_changed_files(list(auto_apply_result.get("applied_files") or []))
    else:
        check_results = _build_skipped_checks_result("auto_apply_failed")
        guard_result = _build_skipped_guard_result("auto_apply_failed")
    write_json(run_dir / "check_results.json", check_results)
    write_json(run_dir / "guard_result.json", guard_result)

    checks_ok = all(r["success"] for r in check_results["results"]) if check_results.get("results") else True
    guard_ok = bool(guard_result.get("ok"))
    final_status = "DONE" if auto_apply_result.get("ok") and checks_ok and guard_ok else "FAILED"
    if needs_human or _has_auto_apply_violation(auto_apply_result, "destructive_update"):
        final_status = "NEEDS_HUMAN"
    update_task_status(tasks_payload, task_id, final_status)
    save_tasks(tasks_payload)

    final_report = build_run_summary(
        task=task,
        final_status=final_status,
        checks_result=check_results,
        guard_result=guard_result,
        run_dir=run_dir,
    )
    write_text(run_dir / "final_report.md", final_report)

    print("Checks skipped: auto_apply_draft" if check_results.get("skipped") else "Checks completed")
    print("Guard skipped: auto_apply_draft" if guard_result.get("skipped") else "Guard completed")
    print("Iterations:", task["iterations"])
    print(
        json.dumps(
            {
                "task_id": task_id,
                "status": final_status,
                "mode": MODE_AUTO_APPLY_DRAFT,
                "run_dir": str(run_dir),
                "auto_apply_result": str(run_dir / "auto_apply_result.json"),
                "applied_files": auto_apply_result.get("applied_files"),
                "violations": auto_apply_result.get("violations"),
                "checks_ok": checks_ok,
                "file_guard_ok": guard_ok,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    log_event(f"Task finished: {task_id} status={final_status}")
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
    raw_fallback_models = env.get("AI_DIRECTOR_MODEL_FALLBACKS")
    if raw_fallback_models is None:
        raw_fallback_models = os.getenv("AI_DIRECTOR_MODEL_FALLBACKS")
    fallback_models = (
        [item.strip() for item in raw_fallback_models.split(",") if item.strip()]
        if raw_fallback_models is not None
        else list(DEFAULT_OPENROUTER_FALLBACK_MODELS)
    )

    api_key = env.get("OPENROUTER_API_KEY") or os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        log_event("LLM error: OPENROUTER_API_KEY not found")
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
    os.environ["AI_DIRECTOR_MODEL_FALLBACKS"] = ",".join(fallback_models)

    print(f"LLM provider={provider} model={model} fallbacks={fallback_models}")
    log_event(f"Calling LLM provider={provider} model={model}")

    try:
        result = generate_text_result(prompt)
        log_event("LLM response received")
    except Exception as exc:
        log_event(f"LLM error: {exc}")
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
        log_event("LLM error: empty OpenRouter response")
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
        log_event(f"LLM error: {last_error or text}")
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


def parse_coder_output(markdown: str) -> list[dict[str, str]]:
    code_section = _extract_markdown_h1_section(markdown, "Code")
    if not code_section:
        return []

    pattern = re.compile(
        r"(?ms)^##\s+(?P<path>.+?)\s*\n+```(?P<language>[A-Za-z0-9_+.-]*)[^\n]*\n(?P<content>.*?)\n```"
    )
    blocks: list[dict[str, str]] = []
    for match in pattern.finditer(code_section):
        path = match.group("path").strip().strip("`")
        language = match.group("language").strip()
        content = match.group("content")
        if not path:
            continue
        blocks.append(
            {
                "path": path,
                "language": language,
                "content": content,
            }
        )
    return blocks


def apply_coder_output(
    markdown: str,
    *,
    project_root: str | Path = config.PROJECT_ROOT,
    source: str = "coder_output.md",
) -> dict[str, Any]:
    blocks = parse_coder_output(markdown)
    if not blocks:
        return {
            "ok": False,
            "applied_files": [],
            "skipped_files": [],
            "violations": [{"path": "", "reason": "no_code_blocks"}],
            "source": source,
        }
    return apply_auto_apply_files(blocks, project_root=project_root, source=source)


def apply_auto_apply_files(
    files: list[dict[str, str]],
    *,
    project_root: str | Path = config.PROJECT_ROOT,
    source: str = "coder_output.md",
) -> dict[str, Any]:
    applied_files: list[str] = []
    skipped_files: list[dict[str, str]] = []
    violations: list[dict[str, str]] = []

    if not files:
        return {
            "ok": False,
            "applied_files": [],
            "skipped_files": [],
            "violations": [{"path": "", "reason": "no_files"}],
            "source": source,
        }

    root = Path(project_root)
    for file_entry in files:
        relative_path = str(file_entry.get("path") or "")
        operation = str(file_entry.get("operation") or "upsert")
        if operation != "upsert":
            entry = {"path": relative_path, "reason": "unsupported_operation"}
            skipped_files.append(entry)
            violations.append(entry)
            continue

        target, reason = _resolve_auto_apply_target(root, relative_path)
        if target is None:
            entry = {"path": relative_path, "reason": reason}
            skipped_files.append(entry)
            violations.append(entry)
            continue

        content = str(file_entry.get("content") or "")
        if target.is_file():
            before = target.read_text(encoding="utf-8")
            if _is_destructive_update(before, content):
                entry = {"path": relative_path, "reason": "destructive_update"}
                skipped_files.append(entry)
                violations.append(entry)
                continue

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        applied_files.append(_display_project_path(root, target))

    return {
        "ok": bool(applied_files) and not violations,
        "applied_files": applied_files,
        "skipped_files": skipped_files,
        "violations": violations,
        "source": source,
    }


def _build_auto_apply_plan(
    blocks: list[dict[str, str]],
    *,
    source: str,
    error: str | None = None,
) -> dict[str, Any]:
    files = []
    violations = []
    for block in blocks:
        path = str(block.get("path") or "")
        target, reason = _resolve_auto_apply_target(config.PROJECT_ROOT, path)
        safe = target is not None
        if safe and target is not None and target.is_file():
            try:
                current_content = target.read_text(encoding="utf-8")
            except OSError:
                current_content = ""
            if _is_destructive_update(current_content, str(block.get("content") or "")):
                safe = False
                reason = "destructive_update"
        if not safe:
            violations.append({"path": path, "reason": reason})
        files.append(
            {
                "path": path,
                "operation": "upsert",
                "language": str(block.get("language") or ""),
                "content_chars": len(str(block.get("content") or "")),
                "safe": safe,
                "reason": reason,
            }
        )

    if error:
        violations.append({"path": "", "reason": error})

    return {
        "ok": bool(files) and not violations,
        "mode": MODE_AUTO_APPLY_DRAFT,
        "source": source,
        "files": files,
        "violations": violations,
        "dry_run": False,
    }


def _auto_apply_check_commands(task: dict[str, Any], auto_apply_result: dict[str, Any]) -> list[str]:
    checks = task.get("checks")
    if isinstance(checks, list) and checks:
        return [str(command) for command in checks]

    applied_files = [str(path).replace("\\", "/") for path in auto_apply_result.get("applied_files") or []]
    test_files = sorted(
        path
        for path in applied_files
        if path.startswith("tests/") and path.endswith(".py")
    )
    if test_files:
        return [f"python -m pytest {' '.join(test_files)} -q"]

    return [str(command) for command in DEFAULT_CHECKS]


def _has_auto_apply_violation(auto_apply_result: dict[str, Any], reason: str) -> bool:
    for item in auto_apply_result.get("violations") or []:
        if isinstance(item, dict) and item.get("reason") == reason:
            return True
    return False


def _is_destructive_update(before: str, after: str) -> bool:
    return _deletes_more_than_half_lines(before, after) or bool(_removed_python_symbols(before, after))


def _deletes_more_than_half_lines(before: str, after: str) -> bool:
    before_lines = before.splitlines()
    if not before_lines:
        return False

    after_lines = after.splitlines()
    deleted_count = 0
    for tag, start_old, end_old, _start_new, _end_new in difflib.SequenceMatcher(
        a=before_lines,
        b=after_lines,
    ).get_opcodes():
        if tag in {"delete", "replace"}:
            deleted_count += end_old - start_old

    return deleted_count / len(before_lines) > 0.5


def _removed_python_symbols(before: str, after: str) -> set[str]:
    before_symbols = _extract_python_symbols(before)
    if not before_symbols:
        return set()
    return before_symbols - _extract_python_symbols(after)


def _extract_python_symbols(source: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return _extract_python_symbols_with_regex(source)

    symbols: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    symbols.add(target.id)
    return symbols


def _extract_python_symbols_with_regex(source: str) -> set[str]:
    symbols: set[str] = set()
    for line in source.splitlines():
        match = re.match(r"\s*(?:async\s+def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)\b", line)
        if match:
            symbols.add(match.group(1))
            continue
        match = re.match(r"\s*([A-Z][A-Z0-9_]*)\s*(?::[^=]+)?=", line)
        if match:
            symbols.add(match.group(1))
    return symbols


def _build_auto_apply_diff(blocks: list[dict[str, str]], *, project_root: str | Path) -> str:
    root = Path(project_root)
    chunks: list[str] = []
    for block in blocks:
        path = str(block.get("path") or "")
        target, reason = _resolve_auto_apply_target(root, path)
        if target is None:
            chunks.append(f"# skipped {path}: {reason}\n")
            continue

        before = target.read_text(encoding="utf-8") if target.is_file() else ""
        after = str(block.get("content") or "")
        diff_text = build_unified_diff_text(
            before,
            after,
            fromfile=f"a/{_display_project_path(root, target)}",
            tofile=f"b/{_display_project_path(root, target)}",
        )
        if diff_text:
            chunks.append(diff_text)
    return "\n".join(chunk.rstrip("\n") for chunk in chunks) + ("\n" if chunks else "")


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


def _build_auto_apply_json_prompt(task: dict[str, Any]) -> str:
    task_payload = {
        "title": str(task.get("title") or ""),
        "prompt": str(task.get("prompt") or task.get("description") or ""),
    }
    shape = {
        "files": [
            {
                "path": "relative/path.py",
                "operation": "upsert",
                "content": "...",
            }
        ]
    }
    parts = [
        "Return only one JSON object.",
        "The first character must be {.",
        "No Markdown.",
        "No comments.",
        "No prose.",
        "Use relative project paths only.",
        "Use operation value upsert only.",
        "The files array must contain at least one file entry.",
        "Include every file required by the task.",
        "Use this exact JSON shape:",
        json.dumps(shape, ensure_ascii=False, indent=2),
        "Task JSON:",
        json.dumps(task_payload, ensure_ascii=False, indent=2),
    ]
    return "\n".join(parts).strip() + "\n"


def _is_planner_only(task: dict[str, Any]) -> bool:
    return _task_mode(task) == MODE_PLANNER_ONLY


def _is_coder_draft(task: dict[str, Any]) -> bool:
    return _task_mode(task) == MODE_CODER_DRAFT


def _is_reviewer_draft(task: dict[str, Any]) -> bool:
    return _task_mode(task) == MODE_REVIEWER_DRAFT


def _is_auto_apply_draft(task: dict[str, Any]) -> bool:
    return _task_mode(task) == MODE_AUTO_APPLY_DRAFT


def _uses_project_context(task: dict[str, Any]) -> bool:
    return _task_mode(task) in {MODE_PLANNER_ONLY, MODE_CODER_DRAFT, MODE_REVIEWER_DRAFT, MODE_AUTO_APPLY_DRAFT}


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


def _extract_markdown_h1_section(markdown: str, heading: str) -> str:
    heading_pattern = re.compile(rf"^#(?!#)\s+{re.escape(heading)}\s*$")
    h1_pattern = re.compile(r"^#(?!#)\s+\S")
    in_section = False
    in_fence = False
    lines: list[str] = []

    for line in markdown.splitlines(keepends=True):
        stripped = line.rstrip("\r\n")
        if not in_section:
            if heading_pattern.match(stripped):
                in_section = True
            continue

        if not in_fence and h1_pattern.match(stripped):
            break

        lines.append(line)
        if stripped.startswith("```"):
            in_fence = not in_fence

    return "".join(lines)


def _find_coder_output_source(task: dict[str, Any], project_root: str | Path) -> tuple[Path | None, str]:
    for include_path in _task_include_paths(task):
        normalized = include_path.replace("\\", "/")
        if Path(normalized).name != "coder_output.md":
            continue
        target, reason = _resolve_auto_apply_target(Path(project_root), normalized, require_existing=True)
        if target is None:
            return None, reason
        if not target.is_file():
            return None, "coder_output_not_file"
        return target, ""
    return None, "coder_output_not_in_include_paths"


def _resolve_auto_apply_target(
    project_root: Path,
    relative_path: str,
    *,
    require_existing: bool = False,
) -> tuple[Path | None, str]:
    normalized = str(relative_path).strip().replace("\\", "/")
    windows_path = PureWindowsPath(relative_path)
    if (
        not normalized
        or Path(relative_path).is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or normalized.startswith("/")
    ):
        return None, "absolute_or_empty_path"

    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        return None, "parent_reference"

    try:
        root_resolved = project_root.resolve()
        target = project_root.joinpath(*parts).resolve(strict=False)
        target.relative_to(root_resolved)
    except (OSError, ValueError):
        return None, "outside_project_root"

    forbidden_reason = _auto_apply_forbidden_reason(root_resolved, target)
    if forbidden_reason:
        return None, forbidden_reason
    if require_existing and not target.exists():
        return None, "missing_source"
    return target, ""


def _auto_apply_forbidden_reason(project_root: Path, target: Path) -> str:
    for relative in FORBIDDEN_AUTO_APPLY_PATHS:
        forbidden = (project_root / relative).resolve(strict=False)
        if target == forbidden:
            return "forbidden_path"
        try:
            target.relative_to(forbidden)
            return "forbidden_path"
        except ValueError:
            continue
    return ""


def _display_project_path(project_root: Path, target: Path) -> str:
    try:
        return target.resolve(strict=False).relative_to(project_root.resolve()).as_posix()
    except (OSError, ValueError):
        return str(target)


def _build_auto_apply_error_result(reason: str) -> dict[str, Any]:
    return {
        "ok": False,
        "applied_files": [],
        "skipped_files": [],
        "violations": [{"path": "", "reason": reason}],
        "source": "coder_output.md",
    }


def _build_auto_apply_llm_result(
    task: dict[str, Any],
    auto_apply_result: dict[str, Any],
    *,
    llm_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if llm_result is None:
        result: dict[str, Any] = {
            "ok": bool(auto_apply_result.get("ok")),
            "status": "ok" if auto_apply_result.get("ok") else "apply_error",
            "final_status": "ok" if auto_apply_result.get("ok") else "apply_error",
            "provider": "none",
            "model": "none",
            "configured_model": "none",
            "attempted_models": [],
            "selected_model": "none",
            "text": "",
            "error": "" if auto_apply_result.get("ok") else "auto_apply_draft failed",
            "last_error": "" if auto_apply_result.get("ok") else "auto_apply_draft failed",
            "errors": [],
        }
    else:
        result = dict(llm_result)

    result["mode"] = MODE_AUTO_APPLY_DRAFT
    if "include_paths" not in result:
        result["include_paths"] = _task_include_paths(task)
    result["applied_files"] = list(auto_apply_result.get("applied_files") or [])
    result["violations"] = list(auto_apply_result.get("violations") or [])
    result["source"] = auto_apply_result.get("source", "coder_output.md")
    result["apply_ok"] = bool(auto_apply_result.get("ok"))
    return result


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


def _main_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run AI Director orchestrator.")
    parser.add_argument("--task-id", default=None, help="Run a specific NEW task id.")
    args = parser.parse_args(argv)
    return main(task_id=args.task_id)


if __name__ == "__main__":
    raise SystemExit(_main_cli())
