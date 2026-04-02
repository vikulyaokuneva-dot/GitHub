"""ABC step."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from modules.abc.module import run as run_abc_module


def run_abc(seller: str) -> dict[str, Any]:
    """Run ABC module for seller and write analytics/abc_analysis.json."""
    seller_root = Path("runtime") / "cabinets" / seller
    return run_abc_module(seller_root)

