"""Minimal reporting engine."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from shared.io.json_io import read_json, write_json


def _resolve_tax_rate(seller_config: dict[str, Any] | None) -> float:
    try:
        value = float((seller_config or {}).get("tax_rate") or 0.06)
        if value > 0:
            return value
    except (TypeError, ValueError):
        pass
    return 0.06


def build_report(
    seller_path: Path,
    mode: str,
    report_date: date,
    seller_config: dict[str, Any] | None = None,
) -> dict:
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
        "config_snapshot": {
            "seller": seller_path.name,
            "mode": mode,
            "tax_rate": _resolve_tax_rate(seller_config),
        },
    }
    write_json(seller_path / "outputs" / "report.json", report)
    return report
