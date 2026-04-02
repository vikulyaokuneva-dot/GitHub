"""Finance module entrypoint."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from modules.finance.engine import run_finance


def run(seller_path: str | Path, seller_config: dict[str, Any] | None = None) -> dict:
    """Run finance calculations for a seller."""
    return run_finance(Path(seller_path), seller_config=seller_config)
