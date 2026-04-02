"""Ingest step placeholder."""

from __future__ import annotations

from datetime import date
from pathlib import Path


def run(paths: dict[str, Path], mode: str, report_date: date) -> None:
    """Temporary stub: v2 should run here."""
    _ = (paths, mode, report_date)
    print("run v2 here")

