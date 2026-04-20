"""Audit stock parser for WB history xlsx.

Primary source: sheet "Остатки по дням" (SKU + warehouse + date columns).
Optional control source: sheet "Детальная информация" (current day stock).
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any

import pandas as pd


STOCK_SKU_COLUMN_PRIORITY: tuple[str, ...] = (
    "Артикул WB",
    "Артикул",
    "nmId",
    "SKU",
)

STOCK_SKU_COLUMN_ALIASES: tuple[str, ...] = STOCK_SKU_COLUMN_PRIORITY + (
    "nm_id",
    "nmid",
)

STOCK_TOTAL_COLUMN_PRIORITY: tuple[str, ...] = (
    "Всего находится на складах",
    "Остаток",
    "Количество",
    "Остатки, шт",
)

STOCK_TOTAL_COLUMN_ALIASES: tuple[str, ...] = STOCK_TOTAL_COLUMN_PRIORITY + (
    "Остатки на текущий день, шт",
    "Остатки на текущий день",
    "quantityFull",
    "quantity",
    "qty",
    "stock",
)


def _norm(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\xa0", " ").replace("\n", " ").replace("\r", " ")
    text = text.strip().lower().replace("ё", "е")
    return " ".join(text.split())


def _to_int_non_negative(value: Any) -> int:
    try:
        if value is None:
            return 0
        if isinstance(value, str):
            cleaned = value.strip().replace(" ", "").replace(",", ".")
            if cleaned == "":
                return 0
            num = float(cleaned)
        elif isinstance(value, (int, float)):
            if pd.isna(value):
                return 0
            num = float(value)
        else:
            num = float(value)
        if num <= 0:
            return 0
        return int(round(num))
    except Exception:
        return 0


def _parse_date(value: Any) -> dt.date | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    text = str(value).strip()
    if not text:
        return None

    for pattern in (
        r"(?<!\d)(\d{1,2})\.(\d{1,2})\.(20\d{2})(?!\d)",
        r"(?<!\d)(20\d{2})[-_/](\d{1,2})[-_/](\d{1,2})(?!\d)",
    ):
        match = re.search(pattern, text)
        if not match:
            continue
        try:
            if pattern.startswith("(?<!\\d)(\\d{1,2})\\."):
                day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
            else:
                year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
            return dt.date(year, month, day)
        except Exception:
            continue
    return None


def _find_sheet_name(sheet_names: list[str], hints: tuple[str, ...]) -> str | None:
    normalized_hints = tuple(_norm(x) for x in hints if _norm(x))
    for sheet in sheet_names:
        sheet_norm = _norm(sheet)
        if any(h in sheet_norm for h in normalized_hints):
            return sheet
    return None


def _build_table_with_header(raw_df: pd.DataFrame, header_row: int) -> pd.DataFrame:
    header_values = list(raw_df.iloc[header_row].tolist())
    headers: list[str] = []
    seen: dict[str, int] = {}
    for idx, value in enumerate(header_values):
        base = str(value).strip() if value is not None and str(value).strip() else f"col_{idx}"
        count = seen.get(base, 0)
        seen[base] = count + 1
        headers.append(base if count == 0 else f"{base}_{count}")

    body = raw_df.iloc[header_row + 1 :].copy()
    body.columns = headers
    body = body.dropna(axis=0, how="all")
    body = body.dropna(axis=1, how="all")
    return body.reset_index(drop=True).fillna("")


def _find_header_row_with_dates(raw_df: pd.DataFrame, *, require_detail_qty: bool = False) -> int | None:
    max_scan = min(len(raw_df), 20)
    best_row = None
    best_score = -1
    total_stock_hints = tuple(_norm(x) for x in STOCK_TOTAL_COLUMN_ALIASES if _norm(x))
    for idx in range(max_scan):
        values = [str(v).strip() for v in list(raw_df.iloc[idx].tolist())]
        normalized_values = [_norm(v) for v in values if _norm(v)]
        if not normalized_values:
            continue

        has_sku = any(
            ("артикул wb" in v)
            or ("артикул" == v)
            or ("nmid" in v)
            or ("nm_id" in v)
            or ("sku" == v)
            for v in normalized_values
        )
        has_warehouse = any("склад" in v or "warehouse" in v for v in normalized_values)
        has_total_stock = any(v in total_stock_hints for v in normalized_values)
        has_detail_qty = any(
            ("остатки на текущий день" in v and "шт" in v) or "quantityfull" in v
            for v in normalized_values
        ) or has_total_stock
        date_cols = sum(1 for v in values if _parse_date(v) is not None)

        if require_detail_qty:
            if not (has_sku and has_warehouse and has_detail_qty):
                continue
            score = date_cols + 5 + (2 if has_total_stock else 0)
        else:
            if not (has_sku and has_warehouse and (date_cols > 0 or has_total_stock)):
                continue
            score = date_cols + (3 if has_total_stock else 0)

        if score > best_score:
            best_score = score
            best_row = idx
    return best_row


def _resolve_column(columns: list[str], aliases: tuple[str, ...]) -> str | None:
    normalized_to_original: dict[str, str] = {}
    for col in columns:
        normalized_to_original.setdefault(_norm(col), col)
    for alias in aliases:
        key = _norm(alias)
        if key in normalized_to_original:
            return normalized_to_original[key]
    return None


def _detect_date_columns(columns: list[str]) -> list[tuple[str, dt.date]]:
    out: list[tuple[str, dt.date]] = []
    for col in columns:
        parsed = _parse_date(col)
        if parsed is not None:
            out.append((col, parsed))
    return out


def _pick_date_column(
    date_columns: list[tuple[str, dt.date]],
    preferred_date: str | None = None,
) -> tuple[str | None, dt.date | None, str]:
    if not date_columns:
        return None, None, "no_date_columns"

    preferred = None
    if preferred_date:
        preferred = _parse_date(preferred_date)
        if preferred is None:
            try:
                preferred = dt.date.fromisoformat(str(preferred_date).strip())
            except Exception:
                preferred = None
    if preferred is not None:
        for col_name, col_date in date_columns:
            if col_date == preferred:
                return col_name, col_date, "preferred_date"

    col_name, col_date = sorted(date_columns, key=lambda item: item[1])[-1]
    return col_name, col_date, "latest_available"


def _parse_detail_control_sheet(path: Path, sheet_name: str | None) -> dict[str, Any]:
    if not sheet_name:
        return {
            "status": "detail_sheet_not_found",
            "detail_total_stock": None,
            "region_by_sku_warehouse": {},
            "detail_rows_parsed": 0,
        }

    try:
        raw = pd.read_excel(path, sheet_name=sheet_name, header=None)
    except Exception as exc:
        return {
            "status": "detail_sheet_read_failed",
            "detail_total_stock": None,
            "region_by_sku_warehouse": {},
            "detail_rows_parsed": 0,
            "error": str(exc),
        }

    if raw.empty:
        return {
            "status": "detail_sheet_empty",
            "detail_total_stock": None,
            "region_by_sku_warehouse": {},
            "detail_rows_parsed": 0,
        }

    header_row = _find_header_row_with_dates(raw, require_detail_qty=True)
    if header_row is None:
        return {
            "status": "detail_header_not_found",
            "detail_total_stock": None,
            "region_by_sku_warehouse": {},
            "detail_rows_parsed": 0,
        }

    df = _build_table_with_header(raw, header_row)
    columns = [str(c) for c in list(df.columns)]

    sku_col = _resolve_column(columns, STOCK_SKU_COLUMN_ALIASES)
    warehouse_col = _resolve_column(columns, ("Склад", "Склад WB", "warehouse", "warehouseName"))
    region_col = _resolve_column(columns, ("Регион", "region", "Регион склада"))
    qty_col = _resolve_column(columns, STOCK_TOTAL_COLUMN_ALIASES)
    if not sku_col or not warehouse_col or not qty_col:
        return {
            "status": "detail_required_columns_missing",
            "detail_total_stock": None,
            "region_by_sku_warehouse": {},
            "detail_rows_parsed": 0,
            "columns": columns,
        }

    total_stock = 0
    parsed_rows = 0
    region_by_sku_warehouse: dict[tuple[int, str], str] = {}
    for _, rec in df.iterrows():
        row = dict(rec)
        sku = _to_int_non_negative(row.get(sku_col))
        warehouse = str(row.get(warehouse_col) or "").strip()
        if sku <= 0 or not warehouse:
            continue
        qty = _to_int_non_negative(row.get(qty_col))
        total_stock += qty
        parsed_rows += 1
        region = str(row.get(region_col) or "").strip() if region_col else ""
        if region:
            region_by_sku_warehouse[(int(sku), warehouse)] = region

    return {
        "status": "ok",
        "detail_total_stock": int(total_stock),
        "region_by_sku_warehouse": region_by_sku_warehouse,
        "detail_rows_parsed": int(parsed_rows),
        "sheet": sheet_name,
    }


def parse_audit_stock_history_with_diagnostics(
    path: str,
    *,
    preferred_date: str | None = None,
) -> dict[str, Any]:
    if not path:
        return {
            "status": "file_not_provided",
            "path": "",
            "rows": [],
            "sku_total_stocks": {},
            "sku_stocks_by_warehouse": {},
            "warnings": [],
        }

    stock_path = Path(path)
    if not stock_path.exists():
        return {
            "status": "file_not_found",
            "path": path,
            "rows": [],
            "sku_total_stocks": {},
            "sku_stocks_by_warehouse": {},
            "warnings": [f"Stock file not found: {path}"],
        }

    try:
        xls = pd.ExcelFile(stock_path)
        sheet_names = list(xls.sheet_names)
    except Exception as exc:
        return {
            "status": "excel_open_failed",
            "path": path,
            "rows": [],
            "sku_total_stocks": {},
            "sku_stocks_by_warehouse": {},
            "warnings": [f"Failed to open stock xlsx: {exc}"],
        }

    history_sheet = _find_sheet_name(sheet_names, ("Остатки по дням", "stock by day", "history"))
    detail_sheet = _find_sheet_name(sheet_names, ("Детальная информация", "detail"))
    warnings: list[str] = []

    if not history_sheet:
        return {
            "status": "history_sheet_not_found",
            "path": path,
            "rows": [],
            "sku_total_stocks": {},
            "sku_stocks_by_warehouse": {},
            "source": "xlsx_history",
            "source_sheet": None,
            "source_date": None,
            "available_dates": [],
            "warnings": ["Sheet 'Остатки по дням' not found in stock file"],
            "detail_sheet": detail_sheet,
        }

    try:
        raw_history = pd.read_excel(stock_path, sheet_name=history_sheet, header=None)
    except Exception as exc:
        return {
            "status": "history_sheet_read_failed",
            "path": path,
            "rows": [],
            "sku_total_stocks": {},
            "sku_stocks_by_warehouse": {},
            "source": "xlsx_history",
            "source_sheet": history_sheet,
            "source_date": None,
            "available_dates": [],
            "warnings": [f"Failed to read history sheet: {exc}"],
            "detail_sheet": detail_sheet,
        }

    if raw_history.empty:
        return {
            "status": "history_sheet_empty",
            "path": path,
            "rows": [],
            "sku_total_stocks": {},
            "sku_stocks_by_warehouse": {},
            "source": "xlsx_history",
            "source_sheet": history_sheet,
            "source_date": None,
            "available_dates": [],
            "warnings": ["History sheet is empty"],
            "detail_sheet": detail_sheet,
        }

    header_row = _find_header_row_with_dates(raw_history, require_detail_qty=False)
    if header_row is None:
        return {
            "status": "history_header_not_found",
            "path": path,
            "rows": [],
            "sku_total_stocks": {},
            "sku_stocks_by_warehouse": {},
            "source": "xlsx_history",
            "source_sheet": history_sheet,
            "source_date": None,
            "available_dates": [],
            "warnings": ["Unable to detect header in history sheet"],
            "detail_sheet": detail_sheet,
        }

    history_df = _build_table_with_header(raw_history, header_row)
    columns = [str(c) for c in list(history_df.columns)]

    sku_col = _resolve_column(columns, STOCK_SKU_COLUMN_ALIASES)
    warehouse_col = _resolve_column(columns, ("Склад", "Склад WB", "warehouse", "warehouseName"))
    seller_col = _resolve_column(columns, ("Артикул продавца", "supplierArticle", "seller_article"))
    name_col = _resolve_column(columns, ("Название", "name", "Наименование"))
    region_col = _resolve_column(columns, ("Регион", "Регион склада", "region"))
    total_stock_col = _resolve_column(columns, STOCK_TOTAL_COLUMN_ALIASES)

    if not sku_col or not warehouse_col:
        return {
            "status": "history_required_columns_missing",
            "path": path,
            "rows": [],
            "sku_total_stocks": {},
            "sku_stocks_by_warehouse": {},
            "source": "xlsx_history",
            "source_sheet": history_sheet,
            "source_date": None,
            "available_dates": [],
            "warnings": ["Missing required columns in history sheet: sku/warehouse"],
            "detail_sheet": detail_sheet,
            "columns": columns,
        }

    date_columns = _detect_date_columns(columns)
    chosen_date_col, chosen_date, date_pick_reason = _pick_date_column(date_columns, preferred_date=preferred_date)
    available_dates = sorted({date.isoformat() for _, date in date_columns})
    qty_column = total_stock_col or chosen_date_col
    qty_column_pick = "total_stock_column" if total_stock_col else date_pick_reason
    source_date = chosen_date.isoformat() if isinstance(chosen_date, dt.date) else None
    if not qty_column:
        return {
            "status": "history_date_columns_missing",
            "path": path,
            "rows": [],
            "sku_total_stocks": {},
            "sku_stocks_by_warehouse": {},
            "source": "xlsx_history",
            "source_sheet": history_sheet,
            "source_date": None,
            "available_dates": available_dates,
            "warnings": ["No date columns found in history sheet"],
            "detail_sheet": detail_sheet,
            "columns": columns,
        }

    detail_control = _parse_detail_control_sheet(stock_path, detail_sheet)
    region_by_sku_warehouse = detail_control.get("region_by_sku_warehouse") or {}

    sku_totals: dict[int, int] = {}
    sku_warehouses: dict[int, dict[str, int]] = {}
    rows: list[dict[str, Any]] = []
    parsed_rows = 0

    for _, rec in history_df.iterrows():
        row = dict(rec)
        sku = _to_int_non_negative(row.get(sku_col))
        warehouse = str(row.get(warehouse_col) or "").strip()
        if sku <= 0 or not warehouse:
            continue

        qty = _to_int_non_negative(row.get(qty_column))
        seller_article = str(row.get(seller_col) or "").strip() if seller_col else ""
        name = str(row.get(name_col) or "").strip() if name_col else ""
        region = str(row.get(region_col) or "").strip() if region_col else ""
        if not region:
            region = str(region_by_sku_warehouse.get((int(sku), warehouse)) or "").strip()

        sku_totals[int(sku)] = sku_totals.get(int(sku), 0) + int(qty)
        sku_warehouses.setdefault(int(sku), {})
        sku_warehouses[int(sku)][warehouse] = sku_warehouses[int(sku)].get(warehouse, 0) + int(qty)
        rows.append(
            {
                "nmId": int(sku),
                "quantityFull": int(qty),
                "quantity": int(qty),
                "warehouse": warehouse,
                "region": region,
                "supplierArticle": seller_article,
                "_name": name,
                "source_date": source_date,
            }
        )
        parsed_rows += 1

    sku_total_stocks = {str(sku): int(total) for sku, total in sorted(sku_totals.items(), key=lambda item: item[0])}
    sku_stocks_by_warehouse: dict[str, list[dict[str, Any]]] = {}
    for sku, warehouse_map in sku_warehouses.items():
        ordered = sorted(
            (
                {"warehouse": str(warehouse), "qty": int(max(qty, 0))}
                for warehouse, qty in warehouse_map.items()
            ),
            key=lambda item: item["qty"],
            reverse=True,
        )
        sku_stocks_by_warehouse[str(sku)] = ordered

    history_total = int(sum(sku_total_stocks.values()))
    detail_total = detail_control.get("detail_total_stock")
    totals_match = None
    total_diff = None
    if isinstance(detail_total, int):
        total_diff = int(history_total - int(detail_total))
        totals_match = abs(total_diff) <= 1
        if not totals_match:
            warnings.append(
                "Stock totals mismatch between sheets: "
                f"history_total={history_total}, detail_total={int(detail_total)}, diff={total_diff}"
            )

    status = "ok" if rows else "empty_after_parse"
    return {
        "status": status,
        "path": path,
        "rows": rows,
        "rows_parsed": int(parsed_rows),
        "source": "xlsx_history",
        "source_sheet": history_sheet,
        "source_date": source_date,
        "source_date_column": str(chosen_date_col) if chosen_date_col else None,
        "source_stock_column": str(total_stock_col) if total_stock_col else None,
        "source_date_pick": qty_column_pick,
        "available_dates": available_dates,
        "sku_total_stocks": sku_total_stocks,
        "sku_stocks_by_warehouse": sku_stocks_by_warehouse,
        "detail_sheet": detail_sheet,
        "detail_status": detail_control.get("status"),
        "detail_rows_parsed": int(detail_control.get("detail_rows_parsed") or 0),
        "control_total_history": int(history_total),
        "control_total_detail": int(detail_total) if isinstance(detail_total, int) else None,
        "control_total_diff": int(total_diff) if isinstance(total_diff, int) else None,
        "control_totals_match": totals_match,
        "warnings": warnings,
        "columns": columns,
    }
