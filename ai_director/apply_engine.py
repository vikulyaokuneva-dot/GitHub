from __future__ import annotations

from pathlib import Path
from typing import Any


def parse_llm_response(response: str) -> dict[str, Any]:
    """
    Safely parse an LLM response.

    MVP format is intentionally minimal:
    - mock or empty responses produce an empty plan;
    - CODE_CHANGES parsing will be added later.
    """
    if not response or response.startswith("MOCK_RESPONSE"):
        return {
            "ok": False,
            "reason": "No real LLM response to apply",
            "files": [],
        }

    return {
        "ok": False,
        "reason": "Parser not implemented yet",
        "files": [],
    }


def validate_apply_plan(plan: dict[str, Any], project_root: Path) -> dict[str, Any]:
    """
    Validate a future apply plan.

    Current rules:
    - absolute paths are forbidden;
    - parent traversal is forbidden;
    - empty paths are forbidden;
    - paths outside ai_director dry-run infrastructure are forbidden.
    """
    violations: list[dict[str, str]] = []
    ai_director_root = (project_root / "ai_director").resolve()

    for item in plan.get("files", []):
        if not isinstance(item, dict):
            violations.append({"path": "", "reason": "file item must be an object"})
            continue

        raw_path = str(item.get("path", "")).strip()
        if not raw_path:
            violations.append({"path": raw_path, "reason": "empty path"})
            continue

        path = Path(raw_path)

        if path.is_absolute():
            violations.append({"path": raw_path, "reason": "absolute paths are forbidden"})
            continue

        if ".." in path.parts:
            violations.append({"path": raw_path, "reason": "parent traversal is forbidden"})
            continue

        resolved_path = (project_root / path).resolve()
        try:
            resolved_path.relative_to(ai_director_root)
        except ValueError:
            violations.append(
                {
                    "path": raw_path,
                    "reason": "paths outside ai_director dry-run infrastructure are forbidden",
                }
            )

    return {
        "ok": len(violations) == 0,
        "violations": violations,
    }


def build_apply_plan(response: str, project_root: Path) -> dict[str, Any]:
    parsed = parse_llm_response(response)
    validation = validate_apply_plan(parsed, project_root)

    return {
        "ok": bool(parsed.get("ok", False)) and validation["ok"],
        "parsed": parsed,
        "validation": validation,
        "dry_run": True,
    }


def apply_plan(plan: dict[str, Any], project_root: Path, dry_run: bool = True) -> dict[str, Any]:
    """
    Safely apply a plan.

    This stage is always dry-run:
    - real files are not changed;
    - only potential actions are returned.
    """
    _ = project_root, dry_run
    actions: list[dict[str, Any]] = []

    for item in plan.get("parsed", {}).get("files", []):
        if not isinstance(item, dict):
            continue
        actions.append(
            {
                "action": "would_modify",
                "path": item.get("path"),
            }
        )

    return {
        "ok": True,
        "dry_run": True,
        "applied": False,
        "actions": actions,
        "message": "Dry-run only. No files were changed.",
    }
