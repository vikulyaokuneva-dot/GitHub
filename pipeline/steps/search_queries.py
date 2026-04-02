"""Search queries step."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from modules.search_queries.module import run as run_search_queries_module


def run(paths: dict[str, Path], mode: str, report_date: date) -> dict:
    """Run search queries module for seller path."""
    _ = (mode, report_date)
    return run_search_queries_module(paths["seller_path"])

