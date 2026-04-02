"""Profit step."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from modules.profit.module import run as run_profit_module


def run_profit(seller: str) -> dict[str, Any]:
    """Run profit module for seller and write analytics/sku_profit.json."""
    seller_root = Path("runtime") / "cabinets" / seller
    return run_profit_module(seller_root)

