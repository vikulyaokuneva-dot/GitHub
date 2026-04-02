"""Finance module entrypoint."""

from __future__ import annotations

from pathlib import Path

from modules.finance.engine import run_finance


def run(seller_path: str | Path) -> dict:
    """Run finance calculations for a seller."""
    return run_finance(Path(seller_path))

