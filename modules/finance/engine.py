"""Minimal finance engine based on JSON files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from shared.io.json_io import read_json, write_json


def _to_float(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def run_finance(seller_path: Path) -> dict:
    """
    Read realization JSON, compute revenue/tax, save finance_summary.json.

    Input:
      runtime/cabinets/<seller>/raw/realization.json
      runtime/cabinets/<seller>/config/cogs.json
    Output:
      runtime/cabinets/<seller>/analytics/finance_summary.json
    """
    realization_path = seller_path / "raw" / "realization.json"
    cogs_path = seller_path / "config" / "cogs.json"
    output_path = seller_path / "analytics" / "finance_summary.json"

    realization_payload = read_json(realization_path)
    rows = realization_payload if isinstance(realization_payload, list) else []
    revenue = sum(_to_float(row.get("sale_amount")) for row in rows if isinstance(row, dict))

    cogs_payload = read_json(cogs_path)
    settings = cogs_payload.get("settings", {}) if isinstance(cogs_payload, dict) else {}
    tax_rate = _to_float(settings.get("tax_rate")) or 0.06
    tax = revenue * tax_rate

    summary = {
        "rows_count": len(rows),
        "revenue": round(revenue, 2),
        "tax_rate": round(tax_rate, 6),
        "tax": round(tax, 2),
    }
    write_json(output_path, summary)
    return summary

