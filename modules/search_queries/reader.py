"""Reader for WB search queries XLSX report."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


SHEET_CANDIDATES: tuple[str, ...] = (
    "Детальные показатели",
    # Safe fallback for already existing WB exports in repo.
    "Статистика по ключевым словам",
)

MAX_HEADER_SCAN_ROWS = 300

# Kept name for backward compatibility with existing imports in this module package.
HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "seller_sku": (
        "артикул продавца",
        "sku продавца",
        "артикул продавца, штрихкод",
        "артикул поставщика",
    ),
    "wb_sku": (
        "артикул wb",
        "номенклатура wb",
        "nm id",
        "nmid",
        "nmid",
        "артикул вайлдберриз",
        "артикул",
    ),
    "query": (
        "поисковый запрос",
        "ключевая фраза",
        "запрос",
    ),
    "query_count": (
        "количество запросов",
        "частотность",
        "просмотры",
        "показы",
    ),
    "visibility_pct": ("видимость", "видимость %", "видимость, %"),
    "avg_position": ("средняя позиция",),
    "median_position": ("медианная позиция",),
    "card_clicks": (
        "переходы в карточку",
        "клики",
        "переходы",
    ),
    "add_to_cart": (
        "положили в корзину",
        "в корзину",
        "добавления в корзину",
    ),
    "cart_conv_pct": (
        "конверсия в корзину",
        "конверсия в корзину %",
        "конверсия в корзину, %",
    ),
    "orders_count": ("заказали", "заказы", "количество заказов", "заказали, шт"),
    "order_conv_pct": (
        "конверсия в заказ",
        "конверсия в заказ %",
        "конверсия в заказ, %",
    ),
    "price_min": ("минимальная цена со скидкой", "минимальная цена"),
    "price_max": ("максимальная цена со скидкой", "максимальная цена"),
    "ctr": ("ctr",),
    "spend": ("затраты", "расход", "сумма затрат"),
}


def normalize_header_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\xa0", " ").replace("\n", " ").replace("\r", " ")
    text = text.strip().lower().replace("ё", "е")
    text = re.sub(r"\s+", " ", text)
    return text


def _match_synonym(cell_norm: str, alias_norm: str) -> bool:
    if not cell_norm or not alias_norm:
        return False
    if cell_norm == alias_norm:
        return True
    if alias_norm in cell_norm:
        return True
    if len(cell_norm) >= 5 and cell_norm in alias_norm:
        return True
    return False


def match_field_by_header(header_text: Any) -> str | None:
    cell_norm = normalize_header_text(header_text)
    if not cell_norm:
        return None

    best_field: str | None = None
    best_score = -1
    for field, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            alias_norm = normalize_header_text(alias)
            if not _match_synonym(cell_norm, alias_norm):
                continue
            if field == "wb_sku" and alias_norm == "артикул" and "продав" in cell_norm:
                # Avoid false positive on "Артикул продавца".
                continue
            score = len(alias_norm)
            if cell_norm == alias_norm:
                score += 100
            if score > best_score:
                best_score = score
                best_field = field
    return best_field


def _pick_sheet_name(sheet_names: list[str]) -> str | None:
    for candidate in SHEET_CANDIDATES:
        if candidate in sheet_names:
            return candidate
    return None


def _score_header(values: list[str]) -> int:
    matched_fields = set()
    for value in values:
        field = match_field_by_header(value)
        if field:
            matched_fields.add(field)

    score = len(matched_fields)
    if "query" in matched_fields:
        score += 2
    for extra in ("query_count", "card_clicks", "orders_count", "visibility_pct"):
        if extra in matched_fields:
            score += 1
    return score


def _detect_recognized_columns(headers: list[str]) -> dict[str, str]:
    recognized: dict[str, str] = {}
    for header in headers:
        field = match_field_by_header(header)
        if field and field not in recognized:
            recognized[field] = header
    return recognized


def _find_header_row(rows: list[list[Any]]) -> tuple[int | None, dict[str, str], int]:
    best_idx = None
    best_columns: dict[str, str] = {}
    best_score = 0
    for idx, row in enumerate(rows):
        stringified = [normalize_header_text(v) for v in row]
        if not any(stringified):
            continue
        recognized = _detect_recognized_columns(stringified)
        score = _score_header(stringified)
        if score > best_score:
            best_score = score
            best_idx = idx
            best_columns = recognized

    if best_idx is None or best_score <= 0:
        return None, {}, best_score

    # Header row must have at least a query-like column and several recognized fields.
    if "query" not in best_columns or len(best_columns) < 3:
        return None, best_columns, best_score
    return best_idx, best_columns, best_score


def read_search_queries_xlsx(path: str | Path) -> dict[str, Any]:
    """
    Read WB search queries XLSX and return raw row dictionaries.

    Returns dict:
      status: ok | no_input | dependency_missing | read_error | sheet_not_found | header_not_found
      rows: list[dict]
      sheet_name: str | None
      message: str
    """
    xlsx_path = Path(path)
    if not xlsx_path.exists():
        return {
            "status": "no_input",
            "rows": [],
            "sheet_name": None,
            "message": f"Input file not found: {xlsx_path}",
        }

    try:
        from openpyxl import load_workbook  # type: ignore
    except Exception as exc:  # pragma: no cover
        return {
            "status": "dependency_missing",
            "rows": [],
            "sheet_name": None,
            "message": f"openpyxl is required to read xlsx ({exc})",
        }

    try:
        # read_only=False is intentionally used here:
        # WB exports may contain broken worksheet dimensions and then read_only mode
        # can skip most rows.
        wb = load_workbook(xlsx_path, read_only=False, data_only=True)
    except Exception as exc:
        return {
            "status": "read_error",
            "rows": [],
            "sheet_name": None,
            "message": f"Failed to read xlsx: {exc}",
        }

    sheet_name = _pick_sheet_name(list(wb.sheetnames))
    if sheet_name is None:
        return {
            "status": "sheet_not_found",
            "rows": [],
            "sheet_name": None,
            "message": (
                "Sheet not found. Expected one of: "
                + ", ".join(SHEET_CANDIDATES)
                + f". Available: {', '.join(wb.sheetnames)}"
            ),
        }

    ws = wb[sheet_name]
    all_rows: list[list[Any]] = [list(r) for r in ws.iter_rows(values_only=True)]
    if not all_rows:
        return {
            "status": "ok",
            "rows": [],
            "sheet_name": sheet_name,
            "message": "Sheet is empty",
        }

    scan_rows = all_rows[:MAX_HEADER_SCAN_ROWS]
    header_idx, recognized_columns_norm, best_score = _find_header_row(scan_rows)
    if header_idx is None:
        return {
            "status": "header_not_found",
            "rows": [],
            "sheet_name": sheet_name,
            "header_row_index": None,
            "recognized_columns": {},
            "has_sku_columns": False,
            "message": (
                f"Header row not found in first {MAX_HEADER_SCAN_ROWS} rows "
                f"(best_score={best_score}, recognized={sorted(recognized_columns_norm.keys())})"
            ),
        }

    headers = [str(v).strip() if v is not None else "" for v in all_rows[header_idx]]
    recognized_columns: dict[str, str] = {}
    for field, normalized_header in recognized_columns_norm.items():
        for header in headers:
            if normalize_header_text(header) == normalized_header:
                recognized_columns[field] = header
                break
        if field not in recognized_columns:
            recognized_columns[field] = normalized_header

    data_rows = all_rows[header_idx + 1 :]
    raw_rows: list[dict[str, Any]] = []
    for row in data_rows:
        if not any(cell is not None and str(cell).strip() != "" for cell in row):
            continue
        item: dict[str, Any] = {}
        max_cols = max(len(headers), len(row))
        for idx in range(max_cols):
            key = headers[idx] if idx < len(headers) else f"col_{idx + 1}"
            if not key:
                key = f"col_{idx + 1}"
            val = row[idx] if idx < len(row) else None
            item[key] = val
        raw_rows.append(item)

    return {
        "status": "ok",
        "rows": raw_rows,
        "sheet_name": sheet_name,
        "header_row_index": header_idx + 1,
        "recognized_columns": recognized_columns,
        "has_sku_columns": bool(recognized_columns.get("seller_sku") or recognized_columns.get("wb_sku")),
        "message": (
            f"Loaded {len(raw_rows)} rows from {sheet_name}; "
            f"header_row={header_idx + 1}; recognized={sorted(recognized_columns.keys())}"
        ),
    }
