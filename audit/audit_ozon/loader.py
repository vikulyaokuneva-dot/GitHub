"""Loader for single-file Ozon express audit."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd


HEADER_CANDIDATES = (0, 1, 2, 3, 4, 5)

SIGNAL_WEIGHTS: dict[str, tuple[int, tuple[str, ...]]] = {
    "sku": (
        3,
        (
            "sku",
            "\u0430\u0440\u0442\u0438\u043a\u0443\u043b",
            "offer id",
            "ozon sku",
            "id \u0442\u043e\u0432\u0430\u0440\u0430",
            "\u0442\u043e\u0432\u0430\u0440",
        ),
    ),
    "orders": (
        3,
        (
            "\u0437\u0430\u043a\u0430\u0437",
            "\u0437\u0430\u043a\u0430\u0437\u0430\u043d\u043e",
            "orders",
            "sales",
            "\u043f\u0440\u043e\u0434\u0430\u0436\u0438",
            "\u0442\u043e\u0432\u0430\u0440\u043e\u0432 \u0437\u0430\u043a\u0430\u0437\u0430\u043d\u043e",
            "quantity ordered",
        ),
    ),
    "revenue": (
        3,
        (
            "\u0432\u044b\u0440\u0443\u0447\u043a\u0430",
            "\u0441\u0443\u043c\u043c\u0430",
            "\u043d\u0430 \u0441\u0443\u043c\u043c\u0443",
            "revenue",
        ),
    ),
    "stock": (2, ("\u043e\u0441\u0442\u0430\u0442\u043e\u043a", "stock", "\u043d\u0430 \u0441\u043a\u043b\u0430\u0434\u0435")),
    "impressions": (1, ("\u043f\u043e\u043a\u0430\u0437\u044b", "impressions")),
    "visitors": (1, ("\u043f\u043e\u0441\u0435\u0442\u0438\u0442\u0435\u043b", "visitors", "\u0443\u043d\u0438\u043a\u0430\u043b\u044c\u043d\u044b\u0435 \u043f\u043e\u0441\u0435\u0442\u0438\u0442\u0435\u043b\u0438")),
    "add_to_cart": (1, ("\u0432 \u043a\u043e\u0440\u0437\u0438\u043d\u0443", "\u0434\u043e\u0431\u0430\u0432\u0438\u043b\u0438 \u0432 \u043a\u043e\u0440\u0437\u0438\u043d\u0443", "add to cart")),
    "buyouts": (1, ("\u0432\u044b\u043a\u0443\u043f", "\u0434\u043e\u0441\u0442\u0430\u0432\u043b\u0435\u043d\u043e", "purchased")),
    "cancellations": (1, ("\u043e\u0442\u043c\u0435\u043d", "canceled", "\u043e\u0442\u043c\u0435\u043d\u0435\u043d\u043e")),
    "price_index": (1, ("\u0438\u043d\u0434\u0435\u043a\u0441 \u0446\u0435\u043d", "price index")),
    "drr": (1, ("\u0434\u0440\u0440",)),
    "reviews": (1, ("\u043e\u0442\u0437\u044b\u0432", "reviews")),
    "promotion_days": (1, ("\u0434\u043d\u0435\u0439 \u043f\u0440\u043e\u0434\u0432\u0438\u0436\u0435\u043d\u0438\u044f", "\u0434\u043d\u0438 \u043f\u0440\u043e\u0434\u0432\u0438\u0436\u0435\u043d\u0438\u044f", "\u043f\u0440\u043e\u0434\u0432\u0438\u0436")),
    "promo_days": (1, ("\u0434\u043d\u0435\u0439 \u0432 \u0430\u043a\u0446\u0438\u044f\u0445", "\u0434\u043d\u0438 \u0432 \u0430\u043a\u0446\u0438\u044f\u0445", "\u0430\u043a\u0446\u0438")),
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
    out: list[str] = []
    for idx, col in enumerate(columns):
        base = col or f"col_{idx + 1}"
        seen = counts.get(base, 0) + 1
        counts[base] = seen
        if seen == 1:
            out.append(base)
        else:
            out.append(f"{base}_{seen}")
    return out


def _is_effectively_empty(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except Exception:
        pass
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame()
    work = df.copy()
    normalized_columns = [normalize_column_name(col) for col in list(work.columns)]
    normalized_columns = _dedupe_columns(normalized_columns)
    work.columns = normalized_columns

    keep_columns: list[str] = []
    for col in work.columns:
        series = work[col]
        has_data = any(not _is_effectively_empty(v) for v in series.tolist())
        if has_data:
            keep_columns.append(col)
    work = work[keep_columns] if keep_columns else pd.DataFrame()

    if work.empty:
        return pd.DataFrame()

    mask = []
    for _, row in work.iterrows():
        mask.append(any(not _is_effectively_empty(v) for v in row.tolist()))
    work = work[mask]
    work = work.reset_index(drop=True)
    return work


def _match_signals(columns: list[str]) -> dict[str, str]:
    matched: dict[str, str] = {}
    for signal_name, (_, keywords) in SIGNAL_WEIGHTS.items():
        for col in columns:
            col_norm = normalize_column_name(col)
            if not col_norm:
                continue
            for kw in keywords:
                token = normalize_column_name(kw)
                if token and token in col_norm:
                    matched[signal_name] = col
                    break
            if signal_name in matched:
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
    meaningful = len([c for c in columns if c and not c.startswith("col_")])
    if meaningful >= 3:
        score += 1
    return score, matched, meaningful


def _extract_dates_from_text(text: str) -> list[str]:
    values: list[str] = []
    if not text:
        return values
    for m in re.finditer(r"(?<!\d)(20\d{2})[-_.](\d{1,2})[-_.](\d{1,2})(?!\d)", text):
        values.append(f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}")
    for m in re.finditer(r"(?<!\d)(\d{1,2})[.](\d{1,2})[.](20\d{2})(?!\d)", text):
        values.append(f"{int(m.group(3)):04d}-{int(m.group(2)):02d}-{int(m.group(1)):02d}")
    return values


def _period_hint(path: Path, sheet_names: list[str]) -> dict[str, Any]:
    candidate_dates: list[str] = []
    candidate_dates.extend(_extract_dates_from_text(path.name))
    for sheet in sheet_names:
        candidate_dates.extend(_extract_dates_from_text(str(sheet)))
    unique = sorted(set(candidate_dates))
    if len(unique) >= 2:
        date_from, date_to = unique[0], unique[-1]
        return {
            "status": "ok",
            "date_from": date_from,
            "date_to": date_to,
            "label": f"\u0441 {date_from} \u043f\u043e {date_to}",
        }
    return {"status": "unknown", "label": "\u043f\u0435\u0440\u0438\u043e\u0434 \u043d\u0435 \u0440\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u043d \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438"}


def _to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in df.to_dict(orient="records"):
        row: dict[str, Any] = {}
        for k, v in item.items():
            row[str(k)] = None if _is_effectively_empty(v) else v
        rows.append(row)
    return rows


def load_ozon_excel(path: str) -> dict[str, Any]:
    """Load Ozon Excel and choose the best sheet/header candidate."""
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

    for sheet in workbook.sheet_names:
        for header_row in HEADER_CANDIDATES:
            try:
                raw_df = pd.read_excel(workbook, sheet_name=sheet, header=header_row)
            except Exception:
                continue

            normalized_df = _clean_dataframe(raw_df)
            columns = [str(c) for c in list(normalized_df.columns)] if not normalized_df.empty else []
            row_count = int(len(normalized_df.index)) if not normalized_df.empty else 0
            score, matched, meaningful = _candidate_score(columns, row_count)

            candidate = {
                "sheet": str(sheet),
                "header_row": int(header_row),
                "score": int(score),
                "row_count": int(row_count),
                "matched_signals": matched,
                "columns_sample": columns[:20],
                "meaningful_columns": int(meaningful),
            }
            parse_candidates.append(candidate)

            candidate_key = (int(score), int(row_count), len(matched), int(meaningful))
            best_key = (
                (
                    int(best_info.get("score") or -1),
                    int(best_info.get("row_count") or -1),
                    len(best_info.get("matched_signals") or {}),
                    int(best_info.get("meaningful_columns") or 0),
                )
                if best_info is not None
                else (-1, -1, -1, -1)
            )
            if candidate_key > best_key:
                best_info = candidate
                best_df = normalized_df

    if best_df is None or best_info is None or best_df.empty:
        return {
            "columns": [],
            "rows": [],
            "row_count": 0,
            "diagnostics": {
                "chosen_sheet": workbook.sheet_names[0] if workbook.sheet_names else "",
                "chosen_header_row": 0,
                "parse_candidates": parse_candidates,
                "row_count_after_normalization": 0,
                "period_hint": _period_hint(target, workbook.sheet_names),
            },
        }

    rows = _to_records(best_df)
    parse_candidates = sorted(parse_candidates, key=lambda x: (x.get("score", 0), x.get("row_count", 0)), reverse=True)
    return {
        "columns": [str(c) for c in list(best_df.columns)],
        "rows": rows,
        "row_count": int(len(rows)),
        "diagnostics": {
            "chosen_sheet": best_info.get("sheet"),
            "chosen_header_row": int(best_info.get("header_row") or 0),
            "chosen_score": int(best_info.get("score") or 0),
            "matched_signals": best_info.get("matched_signals") or {},
            "parse_candidates": parse_candidates,
            "row_count_after_normalization": int(len(rows)),
            "sheet_names": list(workbook.sheet_names),
            "period_hint": _period_hint(target, workbook.sheet_names),
        },
    }
