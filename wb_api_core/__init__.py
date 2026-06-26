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
        return
    load_dotenv(dotenv_path=dotenv_path, override=False)


_load_project_dotenv()

__all__: list[str] = []
