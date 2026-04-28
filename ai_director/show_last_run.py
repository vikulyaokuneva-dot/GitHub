from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    from .config import RUNS_DIR
except ImportError:
    from config import RUNS_DIR


def main(argv: list[str] | None = None) -> int:
    _configure_output()

    parser = argparse.ArgumentParser(description="Show the latest AI Director run.")
    parser.add_argument("--full", action="store_true", help="Print the full LLM response.")
    args = parser.parse_args(argv)

    run_dir = _find_latest_run(Path(RUNS_DIR))
    if run_dir is None:
        print(f"No AI Director runs found in {Path(RUNS_DIR)}")
        return 0

    task = _read_json(run_dir / "task.json")
    llm_result = _read_json(run_dir / "llm_result.json")
    apply_plan = _read_json(run_dir / "apply_plan.json")
    apply_result = _read_json(run_dir / "apply_result.json")

    llm_meta = _as_dict(apply_plan.get("llm")) if isinstance(apply_plan, dict) else {}
    llm_text = _string_value(llm_result.get("text")) if isinstance(llm_result, dict) else ""
    plan_text = _string_value(apply_plan.get("plan")) if isinstance(apply_plan, dict) else ""
    plan_text = plan_text or llm_text

    print("AI Director last run")
    print(f"run_dir: {run_dir}")
    print(f"task_id: {_task_id(run_dir, task)}")
    print(f"task_status: {_task_status(run_dir)}")
    print(f"provider: {_first_value(llm_result, llm_meta, key='provider')}")
    print(f"selected_model: {_first_value(llm_result, llm_meta, key='selected_model')}")
    print(f"status: {_first_value(llm_result, llm_meta, key='status')}")
    print(f"final_status: {_first_value(llm_result, llm_meta, key='final_status')}")
    print(f"context_included: {_first_value(llm_result, key='context_included')}")
    print(f"context_chars: {_first_value(llm_result, key='context_chars')}")
    _print_path_list("include_paths", llm_result.get("include_paths") if isinstance(llm_result, dict) else [])
    _print_path_list("included_files", llm_result.get("included_files") if isinstance(llm_result, dict) else [])
    _print_path_list("missing_files", llm_result.get("missing_files") if isinstance(llm_result, dict) else [])
    print("attempted_models:")
    for model in _attempted_models(llm_result, llm_meta):
        print(f"- {model}")

    skipped = _first_value(apply_result, apply_plan, key="skipped")
    reason = _first_value(apply_result, apply_plan, key="reason")
    print(f"apply_skipped: {skipped}")
    print(f"apply_reason: {reason}")
    print("plan:")
    print(_format_plan(llm_text if args.full else plan_text, full=args.full))
    return 0


def _configure_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _find_latest_run(runs_dir: Path) -> Path | None:
    if not runs_dir.is_dir():
        return None

    run_dirs = [path for path in runs_dir.iterdir() if path.is_dir()]
    if not run_dirs:
        return None

    return max(run_dirs, key=lambda path: path.stat().st_mtime)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}

    try:
        with path.open("r", encoding="utf-8-sig") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        return {"_error": f"Cannot read {path.name}: {exc}"}

    return payload if isinstance(payload, dict) else {"_error": f"{path.name} is not a JSON object"}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _task_id(run_dir: Path, task: dict[str, Any]) -> str:
    if task.get("id"):
        return str(task["id"])

    match = re.match(r"^\d{8}_\d{6}_(.+)$", run_dir.name)
    if match:
        return match.group(1)
    return "(unknown)"


def _task_status(run_dir: Path) -> str:
    final_report = run_dir / "final_report.md"
    if not final_report.is_file():
        return "(unknown)"

    try:
        for line in final_report.read_text(encoding="utf-8-sig").splitlines():
            if line.startswith("Status:"):
                return line.split(":", 1)[1].strip() or "(unknown)"
    except OSError:
        return "(unknown)"

    return "(unknown)"


def _first_value(*sources: dict[str, Any], key: str) -> str:
    for source in sources:
        if not isinstance(source, dict):
            continue
        value = source.get(key)
        if value not in (None, ""):
            return str(value)
    return "(missing)"


def _attempted_models(*sources: dict[str, Any]) -> list[str]:
    for source in sources:
        if not isinstance(source, dict):
            continue
        models = source.get("attempted_models")
        if isinstance(models, list) and models:
            return [str(model) for model in models]
    return ["(missing)"]


def _print_path_list(label: str, value: Any) -> None:
    print(f"{label}:")
    entries = _list_value(value)
    if not entries:
        print("- (none)")
        return
    for entry in entries:
        print(f"- {_format_path_entry(entry)}")


def _list_value(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        return [value]
    return []


def _format_path_entry(entry: Any) -> str:
    if not isinstance(entry, dict):
        return str(entry)

    path = str(entry.get("path") or "(missing)")
    details = []
    reason = entry.get("reason")
    if reason:
        details.append(str(reason))
    chars = entry.get("chars")
    original_chars = entry.get("original_chars")
    if chars is not None and original_chars is not None:
        details.append(f"{chars}/{original_chars} chars")
    elif chars is not None:
        details.append(f"{chars} chars")
    if "truncated" in entry:
        details.append(f"truncated={str(bool(entry.get('truncated'))).lower()}")
    return f"{path} ({', '.join(details)})" if details else path


def _string_value(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _format_plan(text: str, *, full: bool) -> str:
    cleaned = text.strip()
    if not cleaned:
        return "(missing)"
    if full:
        return cleaned

    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    brief = "\n".join(lines[:10])
    if len(brief) > 1200:
        return brief[:1197].rstrip() + "..."
    if len(lines) > 10:
        return brief.rstrip() + "\n..."
    return brief


if __name__ == "__main__":
    raise SystemExit(main())
