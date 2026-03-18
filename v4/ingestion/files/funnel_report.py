"""Funnel local report parser for audit mode.

Input: file path.
Output: raw funnel rows compatible with normalization layer.
Does not compute KPI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...core.contracts import SourceKind, SourceStatus, SourceStatusCode
from .registry import read_tabular_rows


def _pick(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in row and row.get(key) not in (None, ""):
            return row.get(key)
    return None


def parse(path: str) -> tuple[dict[str, Any], SourceStatus]:
    file_path = Path(path)
    warnings: list[str] = []
    try:
        raw_rows = read_tabular_rows(file_path)
    except Exception as exc:
        status = SourceStatus(
            source_name="funnel_report",
            kind=SourceKind.FILE,
            status=SourceStatusCode.ERROR,
            is_required=False,
            rows_loaded=None,
            error_code="funnel_report_parse_failed",
            error_message=str(exc),
            warnings=["funnel report parse failed"],
            debug={"path": str(file_path)},
        )
        return {"rows": []}, status

    rows: list[dict[str, Any]] = []
    for row in raw_rows:
        rows.append(
            {
                "nmId": _pick(row, ("Артикул WB", "nmId", "nm_id", "entity_id", "id")),
                "views": _pick(row, ("Показы", "views", "impressions")),
                "openCount": _pick(row, ("Открыли карточку", "openCount", "opens")),
                "add_to_cart": _pick(row, ("Положили в корзину", "add_to_cart", "cart_adds")),
                "orders": _pick(row, ("Заказали, шт", "orders", "orderCount")),
                "buys": _pick(row, ("Выкупили, шт", "buys", "buyoutCount")),
                "date": _pick(row, ("Дата", "date", "day")),
            }
        )

    status_code = SourceStatusCode.OK if rows else SourceStatusCode.MISSING
    if rows and all(record.get("views") in (None, "") for record in rows):
        warnings.append("funnel report parsed without views column values")

    status = SourceStatus(
        source_name="funnel_report",
        kind=SourceKind.FILE,
        status=status_code,
        is_required=False,
        rows_loaded=len(rows) if rows else None,
        warnings=warnings,
        debug={"path": str(file_path), "rows_total": len(rows)},
    )
    return {"rows": rows}, status
