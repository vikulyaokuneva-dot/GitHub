"""Finance step."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from modules.finance.module import run as run_finance_module


def run(paths: dict[str, Path], mode: str, report_date: date) -> dict:
    """Run finance module for seller path."""
    _ = (mode, report_date)
    return run_finance_module(paths["seller_path"])

