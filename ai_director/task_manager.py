from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from .config import MAX_ITERATIONS_DEFAULT, TASKS_FILE
except ImportError:
    from config import MAX_ITERATIONS_DEFAULT, TASKS_FILE


def load_tasks(path: str | Path = TASKS_FILE) -> dict[str, Any]:
    target = Path(path)
    if not target.is_file():
        return {"tasks": []}
    with target.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError(f"Tasks root must be an object: {target}")
    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        payload["tasks"] = []
    return payload


def save_tasks(tasks_payload: dict[str, Any], path: str | Path = TASKS_FILE) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as file:
        json.dump(tasks_payload, file, ensure_ascii=False, indent=2)
        file.write("\n")


def get_next_task(tasks_payload: dict[str, Any]) -> dict[str, Any] | None:
    tasks = tasks_payload.get("tasks", [])
    if not isinstance(tasks, list):
        return None
    for task in tasks:
        if not isinstance(task, dict):
            continue
        status = str(task.get("status") or "NEW").strip().upper()
        iterations = int(task.get("iterations") or 0)
        max_iterations = int(task.get("max_iterations") or MAX_ITERATIONS_DEFAULT)
        if status == "NEW" and iterations < max_iterations:
            return task
    return None


def update_task_status(tasks_payload: dict[str, Any], task_id: str, status: str) -> dict[str, Any]:
    task = _find_task(tasks_payload, task_id)
    task["status"] = str(status).strip()
    return task


def increment_iteration(tasks_payload: dict[str, Any], task_id: str) -> int:
    task = _find_task(tasks_payload, task_id)
    next_value = int(task.get("iterations") or 0) + 1
    task["iterations"] = next_value
    return next_value


def _find_task(tasks_payload: dict[str, Any], task_id: str) -> dict[str, Any]:
    tasks = tasks_payload.get("tasks", [])
    if not isinstance(tasks, list):
        raise ValueError("tasks must be a list")
    for task in tasks:
        if isinstance(task, dict) and str(task.get("id") or "") == str(task_id):
            return task
    raise KeyError(f"Task not found: {task_id}")
