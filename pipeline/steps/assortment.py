"""Assortment step."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from modules.assortment.module import run as run_assortment_module


def run(paths: dict[str, Path], mode: str, report_date: date) -> dict:
    """Run assortment module for seller path."""
    _ = (mode, report_date)
    return run_assortment_module(paths["seller_path"])

