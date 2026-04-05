"""Loader for single-file Ozon express audit."""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any

import pandas as pd


HEADER_CANDIDATES = (0, 1, 2, 3, 4, 5)

SIGNAL_WEIGHTS: dict[str, tuple[int, tuple[str, ...]]] = {
    "sku": (3, ("sku", "артикул", "offer id", "ozon sku", "id товара", "товар")),
    "orders": (3, ("заказ", "заказано", "orders", "sales", "продажи", "товаров заказано", "quantity ordered")),
    "revenue": (3, ("выручка", "сумма", "на сумму", "revenue")),
    "stock": (2, ("остаток", "stock", "на складе")),
    "spend": (2, ("расход", "затраты", "спенд", "spend", "реклам", "promotion cost")),
    "impressions": (1, ("показы", "impressions")),
    "visitors": (1, ("посетител", "visitors", "уникальные посетители")),
    "add_to_cart": (1, ("в корзину", "добавили в корзину", "add to cart")),
    "buyouts": (1, ("выкуп", "доставлено", "purchased")),
    "cancellations": (1, ("отмен", "canceled", "отменено")),
    "price_index": (1, ("индекс цен", "price index")),
    "drr": (1, ("дрр",)),
    "reviews": (1, ("отзыв", "reviews")),
    "promotion_days": (1, ("дней продвижения", "дни продвижения", "продвиж")),
    "promo_days": (1, ("дней в акциях", "дни в акциях", "акци")),
}


def normalize_column_name(value: Any) -> str:
    text = str(value or "")
    text = text.replace("\xa0", " ").replace("\n", " ").replace("\r", " ").strip().lower()
    text = re.sub(r"\s+", " ", text)
    if not text or text in {"nan", "none"}:
        return ""
    if re.match(r"^unnamed:\s*\d+", text):
        return ""
    return text


def _dedupe_columns(columns: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    output: list[str] = []
    for idx, column in enumerate(columns):
        base = column or f"col_{idx + 1}"
        counts[base] = counts.get(base, 0) + 1
        output.append(base if counts[base] == 1 else f"{base}_{counts[base]}")
    return output


def _is_effectively_empty(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except Exception:
        pass
    return isinstance(value, str) and not value.strip()


def _clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame()
    work = df.copy()
    work.columns = _dedupe_columns([normalize_column_name(col) for col in list(work.columns)])

    if work.empty:
        return pd.DataFrame()

    keep_columns = [
        col for col in work.columns if any(not _is_effectively_empty(v) for v in work[col].tolist())
    ]
    if not keep_columns:
        return pd.DataFrame()
    work = work[keep_columns]

    keep_rows = [
        idx for idx, row in work.iterrows() if any(not _is_effectively_empty(v) for v in row.tolist())
    ]
    if not keep_rows:
        return pd.DataFrame()

    return work.loc[keep_rows].reset_index(drop=True)


def _match_signals(columns: list[str]) -> dict[str, str]:
    matched: dict[str, str] = {}
    normalized = [normalize_column_name(c) for c in columns]

    for signal_name, (_, keywords) in SIGNAL_WEIGHTS.items():
        for idx, col_norm in enumerate(normalized):
            if not col_norm:
                continue
            if any(normalize_column_name(kw) in col_norm for kw in keywords if normalize_column_name(kw)):
                matched[signal_name] = columns[idx]
                break

    return matched


def _candidate_score(columns: list[str], row_count: int) -> tuple[int, dict[str, str], int]:
    matched = _match_signals(columns)
    score = 0
    for signal_name, (weight, _) in SIGNAL_WEIGHTS.items():
        if signal_name in matched:
            score += int(weight)
    if row_count > 20:
        score += 1
    meaningful_columns = len([c for c in columns if c and not c.startswith("col_")])
    if meaningful_columns >= 3:
        score += 1
    return score, matched, meaningful_columns


def _parse_ymd_dates(text: str) -> list[dt.date]:
    values: list[dt.date] = []
    for m in re.finditer(r"(?<!\d)(20\d{2})[-_.](\d{1,2})[-_.](\d{1,2})(?!\d)", text or ""):
        try:
            values.append(dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except Exception:
            continue
    return values


def _parse_dmy_dates(text: str) -> list[dt.date]:
    values: list[dt.date] = []
    for m in re.finditer(r"(?<!\d)(\d{1,2})[.-](\d{1,2})[.-](20\d{2})(?!\d)", text or ""):
        try:
            values.append(dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))))
        except Exception:
            continue
    return values


def _parse_same_month_range(text: str) -> list[dt.date]:
    values: list[dt.date] = []
    # Format example: 23-29.03.2026
    pattern = r"(?<!\d)(\d{1,2})\s*[-–—]\s*(\d{1,2})[.](\d{1,2})[.](20\d{2})(?!\d)"
    for m in re.finditer(pattern, text or ""):
        try:
            year = int(m.group(4))
            month = int(m.group(3))
            day_from = int(m.group(1))
            day_to = int(m.group(2))
            values.append(dt.date(year, month, day_from))
            values.append(dt.date(year, month, day_to))
        except Exception:
            continue
    return values


def _extract_dates_from_text(text: str) -> list[dt.date]:
    dates = _parse_same_month_range(text) + _parse_ymd_dates(text) + _parse_dmy_dates(text)
    return sorted(set(dates))


def _head_text_from_raw_sheet(raw_df: pd.DataFrame, max_rows: int = 8, max_cols: int = 12) -> str:
    if raw_df is None or raw_df.empty:
        return ""
    lines: list[str] = []
    for row_idx in range(min(max_rows, len(raw_df.index))):
        row = raw_df.iloc[row_idx]
        tokens: list[str] = []
        for col_idx in range(min(max_cols, len(row))):
            value = row.iloc[col_idx]
            if _is_effectively_empty(value):
                continue
            token = str(value).strip()
            if token:
                tokens.append(token)
        if tokens:
            lines.append(" | ".join(tokens))
    return "\n".join(lines)


def _detect_period(path: Path, sheet_names: list[str], head_texts: list[str]) -> dict[str, Any]:
    candidates: list[dt.date] = []
    candidates.extend(_extract_dates_from_text(path.name))
    for sheet_name in sheet_names:
        candidates.extend(_extract_dates_from_text(str(sheet_name)))
    for snippet in head_texts:
        candidates.extend(_extract_dates_from_text(snippet))

    unique = sorted(set(candidates))
    if len(unique) >= 2:
        date_from = unique[0]
        date_to = unique[-1]
        return {
            "status": "ok",
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "label_ru": f"с {date_from.strftime('%d.%m.%Y')} по {date_to.strftime('%d.%m.%Y')}",
            "fallback_used": False,
            "message": "Период распознан автоматически.",
        }

    if len(unique) == 1:
        one = unique[0]
        return {
            "status": "single_date",
            "date_from": one.isoformat(),
            "date_to": one.isoformat(),
            "label_ru": f"с {one.strftime('%d.%m.%Y')} по {one.strftime('%d.%m.%Y')}",
            "fallback_used": False,
            "message": "Найдена только одна дата в выгрузке; период принят как один день.",
        }

    file_date = dt.datetime.fromtimestamp(path.stat().st_mtime).date()
    return {
        "status": "fallback_file_date",
        "date_from": file_date.isoformat(),
        "date_to": file_date.isoformat(),
        "label_ru": f"с {file_date.strftime('%d.%m.%Y')} по {file_date.strftime('%d.%m.%Y')}",
        "fallback_used": True,
        "message": "Период не найден, используется дата выгрузки файла.",
    }


def _to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in df.to_dict(orient="records"):
        record: dict[str, Any] = {}
        for k, v in item.items():
            record[str(k)] = None if _is_effectively_empty(v) else v
        rows.append(record)
    return rows


def load_ozon_excel(path: str) -> dict[str, Any]:
    """Load Ozon Excel file and choose best sheet/header candidate."""
    target = Path(path)
    if not target.exists() or not target.is_file():
        return {"columns": [], "rows": [], "row_count": 0, "error": f"file_not_found: {path}"}

    try:
        workbook = pd.ExcelFile(target)
    except Exception as exc:
        return {"columns": [], "rows": [], "row_count": 0, "error": f"excel_read_failed: {exc}"}

    parse_candidates: list[dict[str, Any]] = []
    best_df: pd.DataFrame | None = None
    best_info: dict[str, Any] | None = None
    head_texts: list[str] = []

    for sheet_name in workbook.sheet_names:
        try:
            raw_preview = pd.read_excel(workbook, sheet_name=sheet_name, header=None, dtype=object)
            preview_text = _head_text_from_raw_sheet(raw_preview)
            if preview_text:
                head_texts.append(preview_text)
        except Exception:
            pass

        for header_row in HEADER_CANDIDATES:
            try:
                raw_df = pd.read_excel(workbook, sheet_name=sheet_name, header=header_row, dtype=object)
            except Exception:
                continue

            normalized_df = _clean_dataframe(raw_df)
            columns = [str(c) for c in list(normalized_df.columns)] if not normalized_df.empty else []
            row_count = int(len(normalized_df.index)) if not normalized_df.empty else 0
            score, matched_signals, meaningful_columns = _candidate_score(columns, row_count)

            candidate = {
                "sheet": str(sheet_name),
                "header_row": int(header_row),
                "score": int(score),
                "row_count": int(row_count),
                "matched_signals": matched_signals,
                "columns_sample": columns[:20],
                "meaningful_columns": int(meaningful_columns),
            }
            parse_candidates.append(candidate)

            current_key = (score, row_count, len(matched_signals), meaningful_columns)
            best_key = (-1, -1, -1, -1)
            if best_info is not None:
                best_key = (
                    int(best_info.get("score") or 0),
                    int(best_info.get("row_count") or 0),
                    len(best_info.get("matched_signals") or {}),
                    int(best_info.get("meaningful_columns") or 0),
                )
            if current_key > best_key:
                best_info = candidate
                best_df = normalized_df

    period_hint = _detect_period(target, list(workbook.sheet_names), head_texts)
    sorted_candidates = sorted(
        parse_candidates,
        key=lambda x: (int(x.get("score") or 0), int(x.get("row_count") or 0), len(x.get("matched_signals") or {})),
        reverse=True,
    )

    if best_df is None or best_info is None or best_df.empty:
        return {
            "columns": [],
            "rows": [],
            "row_count": 0,
            "diagnostics": {
                "chosen_sheet": workbook.sheet_names[0] if workbook.sheet_names else "",
                "chosen_header_row": 0,
                "chosen_score": 0,
                "matched_signals": {},
                "parse_candidates": sorted_candidates,
                "row_count_after_normalization": 0,
                "sheet_names": list(workbook.sheet_names),
                "period_hint": period_hint,
            },
        }

    rows = _to_records(best_df)
    return {
        "columns": [str(c) for c in list(best_df.columns)],
        "rows": rows,
        "row_count": int(len(rows)),
        "diagnostics": {
            "chosen_sheet": best_info.get("sheet"),
            "chosen_header_row": int(best_info.get("header_row") or 0),
            "chosen_score": int(best_info.get("score") or 0),
            "matched_signals": best_info.get("matched_signals") or {},
            "parse_candidates": sorted_candidates,
            "row_count_after_normalization": int(len(rows)),
            "sheet_names": list(workbook.sheet_names),
            "period_hint": period_hint,
        },
    }
