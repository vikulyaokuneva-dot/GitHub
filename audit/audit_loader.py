"""Offline audit input discovery, detection and parsing."""

from __future__ import annotations

import io
import os
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".csv", ".zip"}
FILE_TYPES = ("finance", "funnel", "stocks", "ads", "search", "cogs")


TYPE_FILENAME_HINTS: dict[str, tuple[str, ...]] = {
    "finance": ("finance", "финанс", "реализац", "детализирован", "отчет"),
    "funnel": ("funnel", "воронк", "sales funnel", "товары"),
    "stocks": ("stock", "остатк", "склад", "warehouse"),
    "ads": ("ads", "advert", "реклам", "статистика"),
    "search": ("search", "поиск", "запрос", "keyword", "ключ"),
    "cogs": ("cogs", "себестоим", "cost", "cost price"),
}

TYPE_SHEET_HINTS: dict[str, tuple[str, ...]] = {
    "finance": ("финанс", "realization", "detail", "sheet1"),
    "funnel": ("товар", "воронк", "funnel"),
    "stocks": ("stock", "остатк", "sheet1"),
    "ads": ("статист", "ads", "campaign"),
    "search": ("поиск", "search", "query", "запрос"),
    "cogs": ("cogs", "себестоим", "cost"),
}

PREFERRED_SHEET_SUBSTR: dict[str, tuple[str, ...]] = {
    "finance": ("detail", "sheet1", "детал", "реализа"),
    "funnel": ("товар", "products"),
    "stocks": ("sheet1", "остатк", "stock"),
    "ads": ("статист", "statistics", "campaign"),
    "search": ("поиск", "search", "query"),
    "cogs": ("cogs", "себестоим", "cost"),
}

TYPE_COLUMN_HINTS: dict[str, tuple[str, ...]] = {
    "finance": (
        "тип документа",
        "обоснование для оплаты",
        "код номенклатуры",
        "кол-во",
        "к перечислению продавцу",
    ),
    "funnel": (
        "переходы в карточку",
        "положили в корзину",
        "заказали",
        "выкупили",
    ),
    "stocks": (
        "всего находится на складах",
        "в пути до получателей",
        "в пути возвраты на склад wb",
    ),
    "ads": (
        "затраты",
        "показы",
        "клики",
        "заказов на сумму",
    ),
    "search": (
        "поисковый запрос",
        "запрос",
        "показы",
        "клики",
    ),
    "cogs": (
        "себестоимость",
        "артикул продавца",
        "sku продавца",
    ),
}


def _norm(text: Any) -> str:
    s = "" if text is None else str(text)
    s = s.replace("\xa0", " ").replace("\n", " ").replace("\r", " ")
    s = s.strip().lower().replace("ё", "е")
    s = " ".join(s.split())
    return s


def _to_float(x: Any) -> float:
    try:
        if x is None or x == "":
            return 0.0
        if isinstance(x, str):
            x = x.strip().replace(" ", "").replace(",", ".")
        return float(x)
    except Exception:
        return 0.0


def _to_int(x: Any) -> int:
    try:
        if x is None or x == "":
            return 0
        return int(round(float(str(x).replace(" ", "").replace(",", "."))))
    except Exception:
        return 0


def _lookup(row: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    normalized = {_norm(k): v for k, v in row.items()}
    for alias in aliases:
        key = _norm(alias)
        if key in normalized:
            return normalized.get(key)
    return None


def _score_hints(values: list[str], hints: tuple[str, ...], per_hit: int, cap: int) -> int:
    score = 0
    joined = " | ".join(values)
    for hint in hints:
        h = _norm(hint)
        if h and h in joined:
            score += per_hit
            if score >= cap:
                return cap
    return score


def _read_csv_bytes(data: bytes, header: int | None = 0) -> pd.DataFrame:
    for enc in ("utf-8-sig", "cp1251", "utf-16"):
        try:
            return pd.read_csv(io.BytesIO(data), encoding=enc, header=header)
        except Exception:
            continue
    return pd.read_csv(io.BytesIO(data), encoding_errors="ignore", header=header)


def _read_raw_table(path: Path, header_row: int | None = None, sheet_name: str | int = 0) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        if header_row is None:
            return pd.read_excel(path, sheet_name=sheet_name, header=None)
        return pd.read_excel(path, sheet_name=sheet_name, header=header_row)
    if suffix == ".csv":
        if header_row is None:
            return pd.read_csv(path, header=None)
        return pd.read_csv(path, header=header_row)
    if suffix == ".zip":
        with zipfile.ZipFile(path, "r") as zf:
            names = [n for n in zf.namelist() if Path(n).suffix.lower() in {".xlsx", ".xls", ".csv"}]
            if not names:
                return pd.DataFrame()
            inner = names[0]
            data = zf.read(inner)
            inner_suffix = Path(inner).suffix.lower()
            if inner_suffix in {".xlsx", ".xls"}:
                bio = io.BytesIO(data)
                if header_row is None:
                    return pd.read_excel(bio, sheet_name=sheet_name, header=None)
                return pd.read_excel(bio, sheet_name=sheet_name, header=header_row)
            df = _read_csv_bytes(data)
            if header_row is None:
                df = _read_csv_bytes(data, header=None)
                return df
            try:
                return pd.read_csv(io.BytesIO(data), header=header_row)
            except Exception:
                # Fallback: emulate header row manually.
                if df.empty or header_row >= len(df):
                    return df
                header_values = [str(x) for x in list(df.iloc[header_row].tolist())]
                body = df.iloc[header_row + 1 :].copy()
                body.columns = header_values
                return body.reset_index(drop=True)
    return pd.DataFrame()


def _excel_sheet_names(path: Path) -> list[str]:
    try:
        if path.suffix.lower() in {".xlsx", ".xls"}:
            return list(pd.ExcelFile(path).sheet_names)
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path, "r") as zf:
                excel_names = [n for n in zf.namelist() if Path(n).suffix.lower() in {".xlsx", ".xls"}]
                if not excel_names:
                    return []
                data = zf.read(excel_names[0])
                return list(pd.ExcelFile(io.BytesIO(data)).sheet_names)
    except Exception:
        return []
    return []


def _sample_columns(path: Path, sheet_name: str | int = 0) -> list[str]:
    try:
        df = _read_raw_table(path, header_row=None, sheet_name=sheet_name)
        if df is None or df.empty:
            return []
        row0 = [str(x) for x in list(df.iloc[0].tolist())[:80]]
        cols_raw = list(df.columns)[:80]
        cols = [str(c) for c in cols_raw]
        numeric_cols = sum(1 for c in cols_raw if isinstance(c, (int, float)))
        if cols_raw and numeric_cols / float(len(cols_raw)) > 0.6:
            return row0
        # For files with technical headers "Unnamed: N", row0 carries real hints.
        unnamed_ratio = 0.0
        if cols:
            unnamed = sum(1 for c in cols if "unnamed" in _norm(c))
            unnamed_ratio = unnamed / float(len(cols))
        return row0 if unnamed_ratio > 0.5 else cols
    except Exception:
        return []


def _find_best_sheet(path: Path, file_type: str) -> str | int:
    sheets = _excel_sheet_names(path)
    if not sheets:
        return 0
    preferred = tuple(_norm(x) for x in PREFERRED_SHEET_SUBSTR.get(file_type, ()))
    for sheet in sheets:
        sheet_n = _norm(sheet)
        if preferred and any(p and p in sheet_n for p in preferred):
            return sheet
    hints = TYPE_SHEET_HINTS.get(file_type, ())
    best = sheets[0]
    best_score = -1
    for sheet in sheets:
        score = _score_hints([_norm(sheet)], hints, per_hit=3, cap=9)
        sample_cols = _sample_columns(path, sheet_name=sheet)
        score += _score_hints([_norm(c) for c in sample_cols], TYPE_COLUMN_HINTS.get(file_type, ()), per_hit=1, cap=8)
        if score > best_score:
            best_score = score
            best = sheet
    return best


def _find_header_row(path: Path, file_type: str, sheet_name: str | int = 0) -> int:
    try:
        raw = _read_raw_table(path, header_row=None, sheet_name=sheet_name)
    except Exception:
        return 0
    if raw is None or raw.empty:
        return 0

    hints = tuple(_norm(x) for x in TYPE_COLUMN_HINTS.get(file_type, ()))
    max_scan = min(len(raw), 25)
    best_idx = 0
    best_score = -1
    for idx in range(max_scan):
        values = [_norm(x) for x in list(raw.iloc[idx].tolist()) if _norm(x)]
        if not values:
            continue
        score = 0
        for hint in hints:
            if any(hint in v for v in values):
                score += 1
        if score > best_score:
            best_score = score
            best_idx = idx
    return best_idx


def _read_typed_table(path: Path, file_type: str) -> pd.DataFrame:
    sheet = _find_best_sheet(path, file_type)
    header = _find_header_row(path, file_type, sheet_name=sheet)
    df = _read_raw_table(path, header_row=header, sheet_name=sheet)
    if df is None:
        return pd.DataFrame()
    df = df.dropna(axis=1, how="all")
    return df.fillna("")


@dataclass
class DetectedFile:
    path: str
    file_type: str
    score: int
    detected_by: list[str]
    sheets: list[str]
    sample_columns: list[str]


def detect_file_type(path: str) -> DetectedFile:
    p = Path(path)
    parent_name = _norm(p.parent.name)
    file_name = _norm(p.name)
    sheets = _excel_sheet_names(p)
    sample_cols = _sample_columns(p)

    scores = {k: 0 for k in FILE_TYPES}
    reasons: dict[str, list[str]] = {k: [] for k in FILE_TYPES}

    for file_type in FILE_TYPES:
        if parent_name == file_type:
            scores[file_type] += 7
            reasons[file_type].append(f"folder:{parent_name}")

        fn_score = _score_hints([file_name], TYPE_FILENAME_HINTS.get(file_type, ()), per_hit=2, cap=8)
        if fn_score:
            scores[file_type] += fn_score
            reasons[file_type].append("filename")

        sh_score = _score_hints([_norm(s) for s in sheets], TYPE_SHEET_HINTS.get(file_type, ()), per_hit=2, cap=8)
        if sh_score:
            scores[file_type] += sh_score
            reasons[file_type].append("sheets")

        col_score = _score_hints([_norm(c) for c in sample_cols], TYPE_COLUMN_HINTS.get(file_type, ()), per_hit=2, cap=10)
        if col_score:
            scores[file_type] += col_score
            reasons[file_type].append("columns")

    best_type = max(scores, key=lambda k: scores[k])
    best_score = int(scores.get(best_type, 0))
    if best_score <= 0:
        best_type = "unknown"

    return DetectedFile(
        path=str(p),
        file_type=best_type,
        score=best_score,
        detected_by=reasons.get(best_type, []),
        sheets=sheets,
        sample_columns=sample_cols[:20],
    )


def scan_input_files(input_dir: str) -> list[DetectedFile]:
    base = Path(input_dir)
    if not base.exists() or not base.is_dir():
        return []
    out: list[DetectedFile] = []
    for file in base.rglob("*"):
        if not file.is_file():
            continue
        if file.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        out.append(detect_file_type(str(file)))
    return out


def pick_first_file(dir_path: str) -> str | None:
    if not dir_path or not os.path.isdir(dir_path):
        return None
    for name in os.listdir(dir_path):
        suffix = Path(name).suffix.lower()
        if suffix in SUPPORTED_EXTENSIONS:
            return os.path.join(dir_path, name)
    return None


def parse_finance_file(path: str) -> list[dict[str, Any]]:
    if not path:
        return []
    df = _read_typed_table(Path(path), "finance")
    if df.empty:
        return []
    rows: list[dict[str, Any]] = []
    for _, r in df.iterrows():
        row = dict(r)
        doc_type = str(_lookup(row, ("Тип документа", "Обоснование для оплаты", "doc_type_name", "supplier_oper_name")) or "").strip()
        rows.append(
            {
                "doc_type_name": doc_type,
                "supplier_oper_name": doc_type,
                "nm_id": _to_int(_lookup(row, ("Код номенклатуры", "Артикул WB", "nm_id", "nmId", "Номенклатура"))),
                "quantity": _to_int(_lookup(row, ("Кол-во", "Количество", "quantity", "qty", "count"))),
                "retail_amount": _to_float(
                    _lookup(
                        row,
                        (
                            "Вайлдберриз реализовал Товар (Пр)",
                            "К перечислению Продавцу за реализованный Товар",
                            "retail_amount",
                        ),
                    )
                ),
                "retail_price_withdisc_rub": _to_float(
                    _lookup(row, ("Цена розничная с учетом согласованной скидки", "Цена розничная", "retail_price_withdisc_rub"))
                ),
                "ppvz_sales_commission": _to_float(_lookup(row, ("Вознаграждение Вайлдберриз (ВВ), без НДС", "ppvz_sales_commission"))),
                "ppvz_for_pay": _to_float(_lookup(row, ("К перечислению Продавцу за реализованный Товар", "ppvz_for_pay"))),
                "delivery_rub": _to_float(
                    _lookup(
                        row,
                        (
                            "Услуги по доставке товара покупателю",
                            "Возмещение за выдачу и возврат товаров на ПВЗ",
                            "delivery_rub",
                            "logistics",
                        ),
                    )
                ),
                "storage_fee": _to_float(_lookup(row, ("Хранение", "storage_fee", "storage"))),
                "penalty": _to_float(_lookup(row, ("Общая сумма штрафов", "penalty", "fine"))),
                "_supplier_article": str(_lookup(row, ("Артикул поставщика", "Артикул продавца", "supplierArticle")) or ""),
                "_name": str(_lookup(row, ("Название", "name")) or ""),
            }
        )
    return rows


def parse_funnel_file(path: str) -> list[dict[str, Any]]:
    if not path:
        return []
    df = _read_typed_table(Path(path), "funnel")
    if df.empty:
        return []
    rows: list[dict[str, Any]] = []
    for _, r in df.iterrows():
        row = dict(r)
        payload = {
            "nmId": _to_int(_lookup(row, ("Артикул WB", "Код номенклатуры", "Номенклатура", "nmId"))),
            "openCardCount": _to_int(_lookup(row, ("Переходы в карточку", "Просмотры", "Показы", "openCardCount"))),
            "addToCartCount": _to_int(_lookup(row, ("Положили в корзину", "Добавлений в корзину", "addToCartCount"))),
            "orderCount": _to_int(_lookup(row, ("Заказали, шт", "Заказы", "orderCount"))),
            "buyoutCount": _to_int(_lookup(row, ("Выкупили, шт", "Выкупы", "buyoutCount"))),
            "orderSum": _to_float(_lookup(row, ("Заказали на сумму, ₽", "Заказали на сумму", "orderSum"))),
            "buyoutSum": _to_float(_lookup(row, ("Выкупили на сумму, ₽", "Выкупили на сумму", "buyoutSum"))),
            "name": str(_lookup(row, ("Название", "name")) or ""),
        }
        is_empty_row = (
            payload["nmId"] == 0
            and payload["openCardCount"] == 0
            and payload["addToCartCount"] == 0
            and payload["orderCount"] == 0
            and payload["buyoutCount"] == 0
            and payload["orderSum"] == 0.0
            and payload["buyoutSum"] == 0.0
            and not payload["name"].strip()
        )
        if is_empty_row:
            continue
        rows.append(payload)
    return rows


def parse_stocks_file(path: str) -> list[dict[str, Any]]:
    if not path:
        return []
    df = _read_typed_table(Path(path), "stocks")
    if df.empty:
        return []
    rows: list[dict[str, Any]] = []
    for _, r in df.iterrows():
        row = dict(r)
        rows.append(
            {
                "nmId": _to_int(_lookup(row, ("Артикул WB", "Код номенклатуры", "nmId"))),
                "quantityFull": _to_int(_lookup(row, ("Всего находится на складах", "quantityFull", "quantity"))),
                "inWayToClient": _to_int(_lookup(row, ("В пути до получателей", "inWayToClient"))),
                "inWayFromClient": _to_int(_lookup(row, ("В пути возвраты на склад WB", "inWayFromClient"))),
                "supplierArticle": str(
                    _lookup(row, ("Артикул продавца", "Артикул поставщика", "supplierArticle", "vendorCode")) or ""
                ),
                "_name": str(_lookup(row, ("Название", "name")) or ""),
            }
        )
    return rows


def parse_ads_file(path: str) -> list[dict[str, Any]]:
    if not path:
        return []
    df = _read_typed_table(Path(path), "ads")
    if df.empty:
        return []
    rows: list[dict[str, Any]] = []
    for _, r in df.iterrows():
        row = dict(r)
        rows.append(
            {
                "nmId": _to_int(_lookup(row, ("Номенклатура", "nmId", "Код номенклатуры"))),
                "spend": _to_float(_lookup(row, ("Затраты, RUB", "Затраты", "Расход", "spend"))),
                "impressions": _to_int(_lookup(row, ("Показы", "Показы, шт", "impressions", "views"))),
                "clicks": _to_int(_lookup(row, ("Клики", "clicks"))),
                "revenueAttr": _to_float(_lookup(row, ("Заказов на сумму, RUB", "Заказов на сумму", "revenueAttr", "orderSum"))),
                "views": _to_int(_lookup(row, ("Показы", "Показы, шт", "impressions", "views"))),
                "name": str(_lookup(row, ("Название", "name")) or ""),
            }
        )
    return rows


def parse_search_file(path: str) -> list[dict[str, Any]]:
    if not path:
        return []
    df = _read_typed_table(Path(path), "search")
    if df.empty:
        return []
    rows: list[dict[str, Any]] = []
    for _, r in df.iterrows():
        row = dict(r)
        query = str(_lookup(row, ("Поисковый запрос", "Запрос", "Query", "search_query", "phrase")) or "").strip()
        if not query:
            continue
        rows.append(
            {
                "query": query,
                "impressions": _to_int(_lookup(row, ("Показы", "impressions"))),
                "clicks": _to_int(_lookup(row, ("Клики", "clicks"))),
                "orders": _to_int(_lookup(row, ("Заказы", "orderCount", "orders"))),
                "buyouts": _to_int(_lookup(row, ("Выкупы", "buyoutCount", "buyouts"))),
                "spend": _to_float(_lookup(row, ("Расход", "Затраты", "spend"))),
                "revenue": _to_float(_lookup(row, ("Выручка", "Заказов на сумму", "revenue", "orderSum"))),
            }
        )
    return rows


def parse_cogs_file(path: str) -> list[dict[str, Any]]:
    if not path:
        return []
    df = _read_typed_table(Path(path), "cogs")
    if df.empty:
        return []
    rows: list[dict[str, Any]] = []
    for _, r in df.iterrows():
        row = dict(r)
        cogs = _to_float(_lookup(row, ("Себестоимость", "cogs", "cost", "cost_price")))
        sku_raw = _lookup(row, ("Артикул WB", "Код номенклатуры", "sku", "nmId", "Артикул продавца", "seller_sku"))
        sku_str = str(sku_raw or "").strip()
        if not sku_str:
            continue
        rows.append(
            {
                "sku": _to_int(sku_str),
                "seller_sku": sku_str,
                "cogs": cogs,
            }
        )
    return rows


def select_best_detected_files(detected_files: list[DetectedFile]) -> dict[str, DetectedFile]:
    best: dict[str, DetectedFile] = {}
    for item in detected_files:
        if item.file_type not in FILE_TYPES:
            continue
        cur = best.get(item.file_type)
        if cur is None or item.score > cur.score:
            best[item.file_type] = item
    return best


# Compatibility wrappers used by previous audit mode.
def load_ads_xlsx(path: str) -> list[dict[str, Any]]:
    return parse_ads_file(path)


def load_finance_xlsx(path: str) -> list[dict[str, Any]]:
    return parse_finance_file(path)


def load_funnel_xlsx(path: str) -> list[dict[str, Any]]:
    return parse_funnel_file(path)


def load_stocks_xlsx(path: str) -> list[dict[str, Any]]:
    return parse_stocks_file(path)
