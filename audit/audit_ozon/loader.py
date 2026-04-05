"""Loader for single-file Ozon express audit."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def _normalize_column_name(value: Any) -> str:
    text = str(value or "")
    text = text.replace("\xa0", " ").strip().lower()
    return " ".join(text.split())


def _dedupe_columns(columns: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    out: list[str] = []
    for col in columns:
        base = col or "unnamed"
        idx = counts.get(base, 0)
        counts[base] = idx + 1
        if idx == 0:
            out.append(base)
        else:
            out.append(f"{base}_{idx + 1}")
    return out


def _to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in df.to_dict(orient="records"):
        row: dict[str, Any] = {}
        for k, v in item.items():
            row[str(k)] = None if pd.isna(v) else v
        rows.append(row)
    return rows


def load_ozon_excel(path: str) -> dict[str, Any]:
    """Load Ozon Excel file and normalize columns.

    Returns:
        {
          "columns": [...],
          "rows": [...],
          "row_count": int,
        }
    """
    target = Path(path)
    if not target.exists() or not target.is_file():
        return {"columns": [], "rows": [], "row_count": 0, "error": f"file_not_found: {path}"}

    try:
        workbook = pd.ExcelFile(target)
        sheet_name = workbook.sheet_names[0] if workbook.sheet_names else 0
        df = pd.read_excel(workbook, sheet_name=sheet_name)
    except Exception as exc:
        return {"columns": [], "rows": [], "row_count": 0, "error": f"excel_read_failed: {exc}"}

    if df is None or df.empty:
        return {"columns": [], "rows": [], "row_count": 0}

    normalized_columns = [_normalize_column_name(col) for col in list(df.columns)]
    normalized_columns = _dedupe_columns(normalized_columns)
    df.columns = normalized_columns

    rows = _to_records(df)
    return {
        "columns": normalized_columns,
        "rows": rows,
        "row_count": int(len(rows)),
    }

