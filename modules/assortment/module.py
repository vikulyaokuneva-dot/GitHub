"""Assortment module entrypoint."""

from __future__ import annotations

from pathlib import Path

from modules.assortment.engine import run_assortment


def run(seller_path: str | Path) -> dict:
    """Run assortment processing for a seller."""
    return run_assortment(Path(seller_path))

