"""Decisions step."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from modules.decisions.module import run as run_decisions_module


def run_decisions(seller: str) -> dict[str, Any]:
    """Run decisions module for seller and write analytics/sku_decisions.json."""
    seller_root = Path("runtime") / "cabinets" / seller
    return run_decisions_module(seller_root)

