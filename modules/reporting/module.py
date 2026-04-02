"""Reporting module entrypoint."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from modules.reporting.engine import build_report


def run(seller_path: str | Path, mode: str, report_date: date) -> dict:
    """Run report builder for a seller."""
    return build_report(Path(seller_path), mode=mode, report_date=report_date)

