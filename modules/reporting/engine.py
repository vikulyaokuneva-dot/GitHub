"""Minimal reporting engine."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from shared.io.json_io import read_json, write_json


def build_report(seller_path: Path, mode: str, report_date: date) -> dict:
    """
    Build report JSON from already prepared analytics JSON.

    Reporting does not recalculate metrics.
    """
    finance_summary_path = seller_path / "analytics" / "finance_summary.json"
    finance_summary = read_json(finance_summary_path)
    if not isinstance(finance_summary, dict):
        finance_summary = {}

    report = {
        "seller": seller_path.name,
        "mode": mode,
        "report_date": report_date.isoformat(),
        "finance_summary": finance_summary,
    }
    write_json(seller_path / "outputs" / "report.json", report)
    return report

