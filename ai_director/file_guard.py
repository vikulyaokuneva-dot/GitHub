from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

try:
    from .config import ALLOWED_WRITE_PATHS, FORBIDDEN_WRITE_PATHS, PROJECT_ROOT
except ImportError:
    from config import ALLOWED_WRITE_PATHS, FORBIDDEN_WRITE_PATHS, PROJECT_ROOT


def is_path_allowed(path: str | Path) -> bool:
    target = _resolve_project_path(path)
    if _is_inside_any(target, FORBIDDEN_WRITE_PATHS):
        return False
    return _is_inside_any(target, ALLOWED_WRITE_PATHS)


def get_git_changed_files() -> list[str]:
    completed = subprocess.run(
        "git status --porcelain",
        shell=True,
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        timeout=300,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "git status failed")

    changed: list[str] = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        path_text = line[3:].strip()
        if " -> " in path_text:
            path_text = path_text.split(" -> ", 1)[1].strip()
        if path_text:
            changed.append(path_text)
    return changed


def validate_changed_files(files: list[str] | None = None) -> dict[str, Any]:
    changed_files = files if files is not None else get_git_changed_files()
    violations = [path for path in changed_files if not is_path_allowed(path)]
    return {
        "ok": not violations,
        "changed_files": changed_files,
        "violations": violations,
        "allowed_roots": [str(path) for path in ALLOWED_WRITE_PATHS],
        "forbidden_roots": [str(path) for path in FORBIDDEN_WRITE_PATHS],
    }


def _resolve_project_path(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def _is_inside_any(path: Path, roots: tuple[Path, ...]) -> bool:
    for root in roots:
        resolved_root = root.resolve()
        if path == resolved_root:
            return True
        try:
            path.relative_to(resolved_root)
            return True
        except ValueError:
            continue
    return False
