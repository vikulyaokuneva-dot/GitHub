from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from .config import TASKS_FILE
except ImportError:
    from config import TASKS_FILE


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create an AI Director task.")
    parser.add_argument("--title", required=True, help="Task title.")
    parser.add_argument("--prompt", required=True, help="Task prompt/description.")
    parser.add_argument("--mode", default="planner_only", help="Task mode. Default: planner_only.")
    parser.add_argument(
        "--include",
        action="append",
        dest="include_paths",
        default=[],
        help="Relative file path to include in planner context. Can be used multiple times.",
    )
    parser.add_argument("--tasks-file", default=str(TASKS_FILE), help="Path to tasks.json.")
    args = parser.parse_args(argv)

    try:
        task = create_task(
            title=args.title,
            prompt=args.prompt,
            mode=args.mode,
            include_paths=args.include_paths,
            tasks_file=Path(args.tasks_file),
        )
    except TaskFileError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(task, ensure_ascii=False, indent=2))
    return 0


class TaskFileError(Exception):
    pass


def create_task(
    *,
    title: str,
    prompt: str,
    mode: str = "planner_only",
    include_paths: list[str] | None = None,
    tasks_file: str | Path = TASKS_FILE,
) -> dict[str, Any]:
    target = Path(tasks_file)
    payload = _load_tasks(target)
    tasks = payload.setdefault("tasks", [])
    task = _build_task(
        title=title,
        prompt=prompt,
        mode=mode,
        include_paths=include_paths,
        existing_tasks=tasks,
    )
    tasks.append(task)
    _save_tasks(target, payload)
    return task


def _load_tasks(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"tasks": []}

    try:
        with path.open("r", encoding="utf-8-sig") as file:
            payload = json.load(file)
    except json.JSONDecodeError as exc:
        raise TaskFileError(f"Cannot parse {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise TaskFileError(f"Tasks root must be a JSON object: {path}")

    tasks = payload.get("tasks")
    if tasks is None:
        payload["tasks"] = []
    elif not isinstance(tasks, list):
        raise TaskFileError(f"'tasks' must be a list in {path}")

    return payload


def _save_tasks(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")


def _build_task(
    *,
    title: str,
    prompt: str,
    mode: str,
    include_paths: list[str] | None,
    existing_tasks: list[Any],
) -> dict[str, Any]:
    created_at = datetime.now().isoformat(timespec="seconds")
    task_id = _unique_task_id(title, existing_tasks)
    task = {
        "id": task_id,
        "title": title,
        "description": prompt,
        "status": "NEW",
        "mode": mode,
        "priority": "low",
        "created_at": created_at,
        "acceptance_criteria": [
            "LLM вызывается через OpenRouter",
            "llm_result.json сохраняется",
            "apply_plan.json сохраняется",
            "apply_result.json сохраняется",
            "код проекта не меняется",
        ],
        "max_iterations": 3,
        "iterations": 0,
    }
    clean_include_paths = _clean_include_paths(include_paths)
    if clean_include_paths:
        task["include_paths"] = clean_include_paths
    return task


def _unique_task_id(title: str, existing_tasks: list[Any]) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_id = f"{_slugify(title)}_{timestamp}"
    existing_ids = {
        str(task.get("id"))
        for task in existing_tasks
        if isinstance(task, dict) and task.get("id") is not None
    }
    if base_id not in existing_ids:
        return base_id

    suffix = 2
    while f"{base_id}_{suffix}" in existing_ids:
        suffix += 1
    return f"{base_id}_{suffix}"


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    return slug or "task"


def _clean_include_paths(include_paths: list[str] | None) -> list[str]:
    if not include_paths:
        return []
    return [
        str(path).strip().replace("\\", "/")
        for path in include_paths
        if str(path).strip()
    ]


if __name__ == "__main__":
    raise SystemExit(main())
