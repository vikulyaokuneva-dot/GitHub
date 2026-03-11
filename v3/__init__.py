from __future__ import annotations

from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None  # type: ignore[assignment]


def _load_project_dotenv() -> None:
    project_root = Path(__file__).resolve().parents[1]
    dotenv_path = project_root / ".env"
    if load_dotenv is None:
        if dotenv_path.is_file():
            print("[warn] python-dotenv is not installed; .env was not loaded")
        return
    # .env is optional: load if present, do not override already exported env.
    load_dotenv(dotenv_path=dotenv_path, override=False)


_load_project_dotenv()
