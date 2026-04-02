"""Reporting step."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from modules.reporting.module import run as run_reporting_module


def run(paths: dict[str, Path], mode: str, report_date: date) -> dict:
    """Run reporting module for seller path."""
    return run_reporting_module(paths["seller_path"], mode=mode, report_date=report_date)

