"""File-based Ozon input detection and parsing for audit MVP."""

from __future__ import annotations

import io
import os
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".csv", ".zip"}
OZON_FILE_TYPES = ("ozon_products_report", "cogs")


OZON_FILENAME_HINTS: dict[str, tuple[str, ...]] = {
    "ozon_products_report": (
        "ozon",
        "товар",
        "products",
        "product",
        "analytics",
        "аналит",
        "продаж",
        "orders",
        "report",
    ),
    "cogs": ("cogs", "себестоим", "cost", "закуп", "cost_price"),
}


OZON_SHEET_HINTS: dict[str, tuple[str, ...]] = {
    "ozon_products_report": ("товар", "products", "analytics", "продаж"),
    "cogs": ("cogs", "себестоим", "cost"),
}


OZON_COLUMN_HINTS: dict[str, tuple[str, ...]] = {
    "ozon_products_report": (
        "товар",
        "наименование",
        "offer id",
        "артикул",
        "sku",
        "заказ",
        "выручк",
        "просмотр",
        "конвер",
        "цена",
    ),
    "cogs": (
        "cogs",
        "себестоимость",
        "cost_price",
        "закуп",
        "артикул",
        "sku",
        "offer",
    ),
}


PRODUCT_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "sku": ("sku", "sku id", "sku_id", "артикул wb", "sku ozon"),
    "offer_id": (
        "offer id",
        "offer_id",
        "offerid",
        "артикул",
        "артикул продавца",
        "seller code",
        "seller_code",
        "vendor code",
        "vendor_code",
    ),
    "name": ("товар", "наименование", "название", "product", "item name", "name"),
    "orders": ("заказы", "заказов", "orders", "ordered units", "количество заказов", "продажи, шт"),
    "revenue": ("выручка", "revenue", "sales", "продажи, руб", "sum", "сумма продаж"),
    "price": ("цена", "price", "средняя цена", "avg price"),
    "views": ("просмотры", "views", "показы", "impressions", "visits"),
    "conversion": ("конверсия", "conversion", "cr", "конверсия в заказ"),
}


COGS_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "id": (
        "sku",
        "артикул",
        "offer id",
        "offer_id",
        "seller code",
        "seller_code",
        "vendor_code",
        "артикул продавца",
    ),
    "cogs": ("cogs", "себестоимость", "cost_price", "cost", "закупка"),
}


def _norm(value: Any) -> str:
    s = "" if value is None else str(value)
    s = s.replace("\xa0", " ").replace("\n", " ").replace("\r", " ")
    s = s.strip().lower().replace("ё", "е")
    s = " ".join(s.split())
    return s


def _clean_id(value: Any) -> str:
    text = _norm(value)
    if not text:
        return ""
    text = text.replace(" ", "")
    return text


def _to_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        if isinstance(value, str):
            value = value.strip().replace(" ", "").replace(",", ".")
        return int(float(value))
    except Exception:
        return None


def _to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        if isinstance(value, str):
            value = value.strip().replace(" ", "").replace(",", ".")
        return float(value)
    except Exception:
        return None


def _read_csv_bytes(data: bytes, header: int | None = 0) -> pd.DataFrame:
    for enc in ("utf-8-sig", "cp1251", "utf-16"):
        try:
            return pd.read_csv(io.BytesIO(data), encoding=enc, header=header)
        except Exception:
            continue
    return pd.read_csv(io.BytesIO(data), encoding_errors="ignore", header=header)


def _read_raw_table(path: Path, sheet_name: str | int = 0, header: int | None = None) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path, sheet_name=sheet_name, header=header)
    if suffix == ".csv":
        return pd.read_csv(path, header=header)
    if suffix == ".zip":
        with zipfile.ZipFile(path, "r") as zf:
            names = [n for n in zf.namelist() if Path(n).suffix.lower() in {".xlsx", ".xls", ".csv"}]
            if not names:
                return pd.DataFrame()
            data = zf.read(names[0])
            inner_suffix = Path(names[0]).suffix.lower()
            if inner_suffix in {".xlsx", ".xls"}:
                return pd.read_excel(io.BytesIO(data), header=header)
            return _read_csv_bytes(data, header=header)
    return pd.DataFrame()


def _sheet_names(path: Path) -> list[str]:
    try:
        if path.suffix.lower() in {".xlsx", ".xls"}:
            return list(pd.ExcelFile(path).sheet_names)
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path, "r") as zf:
                names = [n for n in zf.namelist() if Path(n).suffix.lower() in {".xlsx", ".xls"}]
                if not names:
                    return []
                return list(pd.ExcelFile(io.BytesIO(zf.read(names[0]))).sheet_names)
    except Exception:
        return []
    return []


def _sample_columns(path: Path, sheet_name: str | int = 0) -> list[str]:
    try:
        df = _read_raw_table(path, sheet_name=sheet_name, header=None)
    except Exception:
        return []
    if df is None or df.empty:
        return []
    return [str(x) for x in list(df.iloc[0].tolist())[:80]]


def _score_hints(values: list[str], hints: tuple[str, ...], per_hit: int, cap: int) -> int:
    score = 0
    text = " | ".join(_norm(v) for v in values)
    for hint in hints:
        h = _norm(hint)
        if h and h in text:
            score += per_hit
            if score >= cap:
                return cap
    return score


@dataclass
class OzonDetectedFile:
    path: str
    file_type: str
    score: int
    detected_by: list[str]
    sheets: list[str]
    sample_columns: list[str]


def detect_ozon_file_type(path: str) -> OzonDetectedFile:
    p = Path(path)
    parent_name = _norm(p.parent.name)
    file_name = _norm(p.name)
    sheets = _sheet_names(p)
    sample_columns = _sample_columns(p)

    scores = {k: 0 for k in OZON_FILE_TYPES}
    reasons: dict[str, list[str]] = {k: [] for k in OZON_FILE_TYPES}

    for file_type in OZON_FILE_TYPES:
        if file_type == "ozon_products_report" and parent_name in {"products", "ozon", "product"}:
            scores[file_type] += 8
            reasons[file_type].append(f"folder:{parent_name}")
        if file_type == "cogs" and parent_name in {"cogs", "costs", "cost"}:
            scores[file_type] += 8
            reasons[file_type].append(f"folder:{parent_name}")

        fn_score = _score_hints([file_name], OZON_FILENAME_HINTS.get(file_type, ()), per_hit=2, cap=10)
        if fn_score:
            scores[file_type] += fn_score
            reasons[file_type].append("filename")

        sh_score = _score_hints(sheets, OZON_SHEET_HINTS.get(file_type, ()), per_hit=2, cap=8)
        if sh_score:
            scores[file_type] += sh_score
            reasons[file_type].append("sheets")

        col_score = _score_hints(sample_columns, OZON_COLUMN_HINTS.get(file_type, ()), per_hit=2, cap=12)
        if col_score:
            scores[file_type] += col_score
            reasons[file_type].append("columns")

    best_type = max(scores, key=lambda k: scores[k])
    best_score = int(scores.get(best_type, 0))
    if best_score <= 0:
        best_type = "unknown"
    return OzonDetectedFile(
        path=str(p),
        file_type=best_type,
        score=best_score,
        detected_by=reasons.get(best_type, []),
        sheets=sheets,
        sample_columns=sample_columns[:20],
    )


def scan_ozon_input_files(input_dir: str) -> list[OzonDetectedFile]:
    base = Path(input_dir)
    if not base.exists() or not base.is_dir():
        return []
    out: list[OzonDetectedFile] = []
    for file in base.rglob("*"):
        if not file.is_file():
            continue
        if file.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        out.append(detect_ozon_file_type(str(file)))
    return out


def select_best_ozon_files(detected_files: list[OzonDetectedFile]) -> dict[str, OzonDetectedFile]:
    best: dict[str, OzonDetectedFile] = {}
    for item in detected_files:
        if item.file_type not in OZON_FILE_TYPES:
            continue
        cur = best.get(item.file_type)
        if cur is None or item.score > cur.score:
            best[item.file_type] = item
    return best


def _detect_header_row(df_raw: pd.DataFrame, aliases: dict[str, tuple[str, ...]], max_scan: int = 20) -> int:
    if df_raw is None or df_raw.empty:
        return 0
    max_rows = min(max_scan, len(df_raw))
    best_idx = 0
    best_score = -1

    for idx in range(max_rows):
        values = [_norm(v) for v in list(df_raw.iloc[idx].tolist()) if _norm(v)]
        if not values:
            continue
        score = 0
        for field_aliases in aliases.values():
            found = False
            for alias in field_aliases:
                a = _norm(alias)
                if any(a in cell for cell in values):
                    found = True
                    break
            if found:
                score += 1
        if score > best_score:
            best_score = score
            best_idx = idx
    return best_idx


def _read_with_header(path: Path, header_row: int, sheet_name: str | int = 0) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path, sheet_name=sheet_name, header=header_row)
    if suffix == ".csv":
        return pd.read_csv(path, header=header_row)
    if suffix == ".zip":
        with zipfile.ZipFile(path, "r") as zf:
            names = [n for n in zf.namelist() if Path(n).suffix.lower() in {".xlsx", ".xls", ".csv"}]
            if not names:
                return pd.DataFrame()
            data = zf.read(names[0])
            inner_suffix = Path(names[0]).suffix.lower()
            if inner_suffix in {".xlsx", ".xls"}:
                return pd.read_excel(io.BytesIO(data), header=header_row)
            return _read_csv_bytes(data, header=header_row)
    return pd.DataFrame()


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    renamed = {}
    for col in df.columns:
        c = _norm(col)
        if not c or c.startswith("unnamed"):
            continue
        renamed[col] = c
    return df.rename(columns=renamed)


def _find_column(columns: list[str], aliases: tuple[str, ...]) -> str | None:
    norm_cols = [_norm(c) for c in columns]
    for alias in aliases:
        a = _norm(alias)
        for col in norm_cols:
            if a and a in col:
                return col
    return None


def _resolve_sheet(path: Path, file_type: str) -> str | int:
    sheets = _sheet_names(path)
    if not sheets:
        return 0
    hints = OZON_SHEET_HINTS.get(file_type, ())
    best = sheets[0]
    best_score = -1
    for sheet in sheets:
        score = _score_hints([sheet], hints, per_hit=2, cap=10)
        if file_type == "ozon_products_report" and "товар" in _norm(sheet):
            score += 4
        if score > best_score:
            best_score = score
            best = sheet
    return best


def parse_ozon_products_file(path: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path:
        return [], {"status": "missing_input"}
    p = Path(path)
    sheet = _resolve_sheet(p, "ozon_products_report")
    df_raw = _read_raw_table(p, sheet_name=sheet, header=None)
    if df_raw is None or df_raw.empty:
        return [], {"status": "empty_file", "sheet": str(sheet)}

    header_row = _detect_header_row(df_raw, PRODUCT_FIELD_ALIASES, max_scan=20)
    df = _read_with_header(p, header_row=header_row, sheet_name=sheet)
    df = _normalize_columns(df).fillna("")
    if df.empty:
        return [], {"status": "empty_after_header", "sheet": str(sheet), "header_row": header_row}

    cols = [_norm(c) for c in list(df.columns)]
    recognized: dict[str, str] = {}
    for field, aliases in PRODUCT_FIELD_ALIASES.items():
        col = _find_column(cols, aliases)
        if col:
            recognized[field] = col

    missing_columns = [k for k in ("sku", "offer_id", "name", "orders", "revenue") if k not in recognized]

    rows: list[dict[str, Any]] = []
    rows_before = len(df)

    for _, raw in df.iterrows():
        row = {_norm(k): v for k, v in dict(raw).items()}

        name_val = str(row.get(recognized.get("name", ""), "")).strip() if "name" in recognized else ""
        sku_val = str(row.get(recognized.get("sku", ""), "")).strip() if "sku" in recognized else ""
        offer_val = str(row.get(recognized.get("offer_id", ""), "")).strip() if "offer_id" in recognized else ""

        marker = " ".join([_norm(name_val), _norm(sku_val), _norm(offer_val)])
        if any(x in marker for x in ("итого", "всего", "total")):
            continue
        if not name_val and not sku_val and not offer_val:
            continue

        orders = _to_int(row.get(recognized.get("orders", ""), None)) if "orders" in recognized else None
        revenue = _to_float(row.get(recognized.get("revenue", ""), None)) if "revenue" in recognized else None
        price = _to_float(row.get(recognized.get("price", ""), None)) if "price" in recognized else None
        views = _to_int(row.get(recognized.get("views", ""), None)) if "views" in recognized else None
        conversion = _to_float(row.get(recognized.get("conversion", ""), None)) if "conversion" in recognized else None

        rows.append(
            {
                "sku": sku_val or None,
                "offer_id": offer_val or None,
                "name": name_val or None,
                "orders": orders,
                "revenue": revenue,
                "price": price,
                "views": views,
                "conversion": conversion,
            }
        )

    diagnostics = {
        "status": "ok",
        "source_file": str(p),
        "sheet": str(sheet),
        "header_row": int(header_row),
        "rows_before_filter": int(rows_before),
        "rows_after_filter": int(len(rows)),
        "recognized_columns": recognized,
        "missing_columns": missing_columns,
    }
    return rows, diagnostics


def parse_ozon_cogs_file(path: str) -> tuple[dict[str, float], dict[str, Any]]:
    if not path:
        return {}, {"status": "missing_input"}
    p = Path(path)
    sheet = _resolve_sheet(p, "cogs")
    df_raw = _read_raw_table(p, sheet_name=sheet, header=None)
    if df_raw is None or df_raw.empty:
        return {}, {"status": "empty_file", "sheet": str(sheet)}

    header_row = _detect_header_row(df_raw, COGS_FIELD_ALIASES, max_scan=20)
    df = _read_with_header(p, header_row=header_row, sheet_name=sheet)
    df = _normalize_columns(df).fillna("")
    if df.empty:
        return {}, {"status": "empty_after_header", "sheet": str(sheet), "header_row": header_row}

    cols = [_norm(c) for c in list(df.columns)]
    id_col = _find_column(cols, COGS_FIELD_ALIASES["id"])
    cogs_col = _find_column(cols, COGS_FIELD_ALIASES["cogs"])
    if not id_col or not cogs_col:
        return {}, {
            "status": "required_columns_missing",
            "sheet": str(sheet),
            "header_row": int(header_row),
            "recognized_columns": {"id": id_col, "cogs": cogs_col},
        }

    cogs_map: dict[str, float] = {}
    skipped = 0
    for _, raw in df.iterrows():
        row = {_norm(k): v for k, v in dict(raw).items()}
        id_raw = row.get(id_col, "")
        cogs_raw = row.get(cogs_col, None)
        key = str(id_raw or "").strip()
        if not key:
            continue
        cogs = _to_float(cogs_raw)
        if cogs is None:
            skipped += 1
            continue
        cogs_map[key] = float(cogs)

    diagnostics = {
        "status": "ok",
        "source_file": str(p),
        "sheet": str(sheet),
        "header_row": int(header_row),
        "rows_total": int(len(df)),
        "rows_loaded": int(len(cogs_map)),
        "rows_skipped": int(skipped),
        "recognized_columns": {"id": id_col, "cogs": cogs_col},
    }
    return cogs_map, diagnostics


def build_cogs_match_index(cogs_map: dict[str, float]) -> dict[str, dict[str, float]]:
    exact: dict[str, float] = {}
    cleaned: dict[str, float] = {}
    for raw_key, value in (cogs_map or {}).items():
        key = str(raw_key).strip()
        if not key:
            continue
        exact[key] = float(value)
        ck = _clean_id(key)
        if ck and ck not in cleaned:
            cleaned[ck] = float(value)
    return {"exact": exact, "cleaned": cleaned}


def match_cogs_for_sku(
    *,
    sku: Any,
    offer_id: Any,
    seller_code: Any,
    cogs_index: dict[str, dict[str, float]],
) -> tuple[float | None, str]:
    exact = (cogs_index or {}).get("exact") or {}
    cleaned = (cogs_index or {}).get("cleaned") or {}

    candidates = []
    for candidate in (sku, offer_id, seller_code):
        if candidate is None:
            continue
        text = str(candidate).strip()
        if text:
            candidates.append(text)

    for candidate in candidates:
        if candidate in exact:
            return float(exact[candidate]), "exact"

    for candidate in candidates:
        ck = _clean_id(candidate)
        if ck and ck in cleaned:
            return float(cleaned[ck]), "cleaned"

    return None, "not_found"


def pick_first_file(dir_path: str) -> str | None:
    if not dir_path or not os.path.isdir(dir_path):
        return None
    for name in os.listdir(dir_path):
        if Path(name).suffix.lower() in SUPPORTED_EXTENSIONS:
            return os.path.join(dir_path, name)
    return None

