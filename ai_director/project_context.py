from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from .config import PROJECT_ROOT, RUNS_DIR
except ImportError:
    from config import PROJECT_ROOT, RUNS_DIR


KEY_PATHS = (
    "ai_director/orchestrator.py",
    "ai_director/tasks/tasks.json",
    "src/openrouter_client.py",
    "report_v2/",
    "docs/testing.md",
)

SKIP_TOP_LEVEL_ENTRIES = {
    ".env",
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
}


def collect_project_context(
    *,
    max_chars: int = 8000,
    project_root: str | Path = PROJECT_ROOT,
    runs_dir: str | Path = RUNS_DIR,
    exclude_run_dir: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(project_root)
    runs = Path(runs_dir)
    sections = [
        "# Project Context",
        "",
        "## Top-level entries",
        *_top_level_entries(root),
        "",
        "## Key paths",
        *_key_paths(root),
        "",
        "## Last AI Director runs",
        *_last_run_dirs(runs, exclude_run_dir=Path(exclude_run_dir) if exclude_run_dir else None),
        "",
        "## README_AI_DIRECTOR.md excerpt",
        _readme_excerpt(root / "ai_director" / "README_AI_DIRECTOR.md"),
    ]
    text = "\n".join(sections).strip() + "\n"
    text, truncated = _truncate(text, max_chars=max_chars)
    return {
        "included": bool(text.strip()),
        "chars": len(text),
        "max_chars": max_chars,
        "truncated": truncated,
        "text": text,
    }


def _top_level_entries(root: Path) -> list[str]:
    if not root.is_dir():
        return [f"- missing project root: {root}"]

    entries = [
        path
        for path in root.iterdir()
        if path.name not in SKIP_TOP_LEVEL_ENTRIES
    ]
    entries = sorted(entries, key=lambda path: (not path.is_dir(), path.name.lower()))
    lines: list[str] = []
    for path in entries[:80]:
        suffix = "/" if path.is_dir() else ""
        lines.append(f"- {path.name}{suffix}")
    if len(entries) > 80:
        lines.append(f"- ... {len(entries) - 80} more")
    return lines or ["- (empty)"]


def _key_paths(root: Path) -> list[str]:
    lines = []
    for relative in KEY_PATHS:
        target = root / relative.rstrip("/")
        kind = "dir" if relative.endswith("/") else "file"
        status = "present" if target.exists() else "missing"
        lines.append(f"- {relative}: {status} ({kind})")
    return lines


def _last_run_dirs(runs_dir: Path, *, exclude_run_dir: Path | None = None) -> list[str]:
    if not runs_dir.is_dir():
        return [f"- no runs directory: {runs_dir}"]

    excluded = exclude_run_dir.resolve() if exclude_run_dir else None
    run_dirs = []
    for path in runs_dir.iterdir():
        if not path.is_dir():
            continue
        if excluded and path.resolve() == excluded:
            continue
        run_dirs.append(path)

    latest = sorted(run_dirs, key=lambda path: path.stat().st_mtime, reverse=True)[:3]
    return [f"- {path.name}" for path in latest] or ["- (none)"]


def _readme_excerpt(path: Path, max_chars: int = 3500) -> str:
    if not path.is_file():
        return "(missing)"

    text = path.read_text(encoding="utf-8-sig").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 16].rstrip() + "\n...[truncated]"


def _truncate(text: str, *, max_chars: int) -> tuple[str, bool]:
    if max_chars <= 0:
        return "", bool(text)
    if len(text) <= max_chars:
        return text, False
    suffix = "\n...[context truncated]\n"
    keep = max(0, max_chars - len(suffix))
    return text[:keep].rstrip() + suffix, True
