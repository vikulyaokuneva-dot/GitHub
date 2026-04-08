"""Offline audit input discovery, detection and parsing."""

from __future__ import annotations

import io
import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".csv", ".zip"}
FILE_TYPES = ("finance", "funnel", "stocks", "ads", "search", "orders", "cogs")


TYPE_FILENAME_HINTS: dict[str, tuple[str, ...]] = {
    "finance": ("finance", "финанс", "реализац", "детализирован", "отчет"),
    "funnel": ("funnel", "воронк", "sales funnel", "товары"),
    "stocks": ("stock", "остатк", "склад", "warehouse"),
    "ads": ("ads", "advert", "реклам", "статистика"),
    "search": ("search", "поиск", "запрос", "keyword", "ключ"),
    "orders": ("orders", "заказы", "лента заказов", "order feed", "заказ"),
    "cogs": ("cogs", "себестоим", "cost", "cost price"),
}

TYPE_SHEET_HINTS: dict[str, tuple[str, ...]] = {
    "finance": ("финанс", "realization", "detail", "sheet1"),
    "funnel": ("товар", "воронк", "funnel"),
    "stocks": ("stock", "остатк", "sheet1"),
    "ads": ("статист", "ads", "campaign"),
    "search": ("поиск", "search", "query", "запрос"),
    "orders": ("заказ", "orders", "лента", "all orders"),
    "cogs": ("cogs", "себестоим", "cost"),
}

PREFERRED_SHEET_SUBSTR: dict[str, tuple[str, ...]] = {
    "finance": ("detail", "sheet1", "детал", "реализа"),
    "funnel": ("товар", "products"),
    "stocks": ("sheet1", "остатк", "stock"),
    "ads": ("статист", "statistics", "campaign"),
    "search": ("поиск", "search", "query"),
    "orders": ("все заказы", "all orders", "orders", "заказ"),
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
    "orders": (
        "артикул wb",
        "артикул продавца",
        "дата оформления заказа",
        "регион прибытия",
        "регион доставки",
        "id заказа",
    ),
    "cogs": (
        "себестоимость",
        "артикул продавца",
        "sku продавца",
    ),
}

STORAGE_COLUMN_ALIASES: tuple[str, ...] = (
    "Хранение, руб",
    "Хранение (руб)",
    "Хранение руб",
    "Стоимость хранения",
    "Услуги по хранению",
    "Услуги по хранению, руб",
    "Хранение товара",
    "Хранение",
    "storage_fee",
    "storage fee",
    "storagefee",
    "storage_cost",
    "storage cost",
    "storage",
)


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


def _to_float_or_none(x: Any) -> float | None:
    try:
        if x is None or x == "":
            return None
        if isinstance(x, str):
            x = x.strip().replace(" ", "").replace(",", ".")
            if x == "":
                return None
        return float(x)
    except Exception:
        return None


def _to_int(x: Any) -> int:
    try:
        if x is None or x == "":
            return 0
        return int(round(float(str(x).replace(" ", "").replace(",", "."))))
    except Exception:
        return 0


def _to_sku_token(x: Any) -> str:
    if x is None:
        return ""
    text = str(x).strip()
    if not text:
        return ""
    normalized = text.replace("\xa0", " ").replace(",", ".").strip()
    try:
        if re.match(r"^\d+(\.0+)?$", normalized):
            return str(int(float(normalized)))
    except Exception:
        pass
    return normalized


def _to_seller_token(x: Any) -> str:
    text = str(x or "").strip()
    if not text:
        return ""
    return " ".join(text.replace("\xa0", " ").split()).lower()


def _is_missing_cell(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    try:
        return bool(pd.isna(value))
    except Exception:
        return False


def _lookup(row: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    normalized = {_norm(k): v for k, v in row.items()}
    first_found = None
    has_first = False
    for alias in aliases:
        key = _norm(alias)
        if key in normalized:
            value = normalized.get(key)
            if not has_first:
                first_found = value
                has_first = True
            if not _is_missing_cell(value):
                return value
    if has_first:
        return first_found
    return None


def _has_any(row: dict[str, Any], aliases: tuple[str, ...]) -> bool:
    return _lookup(row, aliases) not in (None, "", [])


def _resolve_storage_column(columns: list[Any]) -> str | None:
    normalized_to_original: dict[str, str] = {}
    ordered_pairs: list[tuple[str, str]] = []
    for raw_name in columns:
        original = str(raw_name)
        normalized = _norm(original)
        if not normalized:
            continue
        normalized_to_original.setdefault(normalized, original)
        ordered_pairs.append((normalized, original))

    for alias in STORAGE_COLUMN_ALIASES:
        key = _norm(alias)
        if key in normalized_to_original:
            return normalized_to_original.get(key)

    for normalized, original in ordered_pairs:
        if ("хран" in normalized or "storage" in normalized) and not any(
            token in normalized for token in ("срок", "дней", "day", "days")
        ):
            return original
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
    rows, _ = parse_finance_file_with_diagnostics(path)
    return rows


def parse_finance_file_with_diagnostics(path: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path:
        return [], {"status": "file_not_provided", "path": ""}
    df = _read_typed_table(Path(path), "finance")
    if df.empty:
        return [], {"status": "empty_after_parse", "path": path}

    available_columns = [str(col) for col in list(df.columns)]
    storage_source_column = _resolve_storage_column(list(df.columns))
    storage_total = 0.0
    storage_rows_nonzero = 0

    rows: list[dict[str, Any]] = []
    skipped_rows = 0
    for _, r in df.iterrows():
        row = dict(r)
        doc_type = str(_lookup(row, ("Тип документа", "Обоснование для оплаты", "doc_type_name", "supplier_oper_name")) or "").strip()
        storage_value_raw = row.get(storage_source_column) if storage_source_column else _lookup(row, STORAGE_COLUMN_ALIASES)
        storage_fee = _to_float(storage_value_raw)
        if abs(storage_fee) > 1e-9:
            storage_rows_nonzero += 1
            storage_total += abs(storage_fee)
        payload = {
            "doc_type_name": doc_type,
            "supplier_oper_name": doc_type,
            "date": str(
                _lookup(
                    row,
                    (
                        "\u0414\u0430\u0442\u0430",
                        "\u0414\u0430\u0442\u0430 \u043e\u043f\u0435\u0440\u0430\u0446\u0438\u0438",
                        "\u0414\u0430\u0442\u0430 \u043f\u0440\u043e\u0434\u0430\u0436\u0438",
                        "\u0414\u0430\u0442\u0430 \u0437\u0430\u043a\u0430\u0437\u0430",
                        "sale_dt",
                        "rr_dt",
                        "order_date",
                        "date",
                    ),
                )
                or ""
            ).strip(),
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
            "wb_reward_before_agent": _to_float(
                _lookup(
                    row,
                    (
                        "Вознаграждение с продаж до вычета услуг поверенного, без НДС",
                        "Вознаграждение с продаж до вычета услуг поверенного без НДС",
                        "wb_reward_before_agent",
                    ),
                )
            ),
            "pvz_compensation": _to_float(
                _lookup(
                    row,
                    (
                        "Возмещение за выдачу и возврат товаров на ПВЗ",
                        "Возмещение за выдачу и возврат товаров на ПВЗ, без НДС",
                        "pvz_compensation",
                    ),
                )
            ),
            "payment_services_compensation": _to_float(
                _lookup(
                    row,
                    (
                        "Компенсация платёжных услуг/Комиссия за интеграцию",
                        "Компенсация платежных услуг/Комиссия за интеграцию",
                        "Компенсация платёжных услуг/Комиссия за интеграцию платёжных сервисов",
                        "Компенсация платежных услуг/Комиссия за интеграцию платежных сервисов",
                        "payment_services_compensation",
                    ),
                )
            ),
            "payment_services_compensation_amount": _to_float(
                _lookup(
                    row,
                    (
                        "Размер компенсации платёжных услуг/Комиссии за интеграцию",
                        "Размер компенсации платежных услуг/Комиссии за интеграцию",
                        "Размер компенсации платёжных услуг/Комиссии за интеграцию платёжных сервисов, %",
                        "Размер компенсации платежных услуг/Комиссии за интеграцию платежных сервисов, %",
                        "payment_services_compensation_amount",
                    ),
                )
            ),
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
            "storage_fee": storage_fee,
            "penalty": _to_float(_lookup(row, ("Общая сумма штрафов", "penalty", "fine"))),
            "_supplier_article": str(_lookup(row, ("Артикул поставщика", "Артикул продавца", "supplierArticle")) or ""),
            "_name": str(_lookup(row, ("Название", "name")) or ""),
            "_storage_source_column": storage_source_column or "",
            "region": str(
                _lookup(
                    row,
                    (
                        "Регион",
                        "Регион доставки",
                        "Область",
                        "Федеральный округ",
                        "region",
                        "delivery_region",
                        "destinationRegion",
                    ),
                )
                or ""
            ).strip(),
            "city": str(_lookup(row, ("Город", "Город доставки", "city", "delivery_city")) or "").strip(),
            "warehouse": str(_lookup(row, ("Склад", "Склад WB", "warehouse", "warehouseName")) or "").strip(),
        }

        marker = " ".join(
            [
                _norm(payload.get("_name")),
                _norm(payload.get("supplier_oper_name")),
                _norm(payload.get("_supplier_article")),
            ]
        )
        is_total = any(x in marker for x in ("итого", "всего", "total"))
        has_financial_amount = any(
            abs(_to_float(payload.get(key))) > 1e-9
            for key in (
                "retail_amount",
                "ppvz_sales_commission",
                "wb_reward_before_agent",
                "pvz_compensation",
                "payment_services_compensation",
                "payment_services_compensation_amount",
                "ppvz_for_pay",
                "delivery_rub",
                "storage_fee",
                "penalty",
            )
        )
        looks_empty = (
            payload["nm_id"] == 0
            and payload["quantity"] == 0
            and not has_financial_amount
            and not payload["_name"]
            and not payload["supplier_oper_name"]
        )
        if is_total or looks_empty:
            skipped_rows += 1
            continue
        rows.append(payload)
    return rows, {
        "status": "ok" if rows else "empty_after_parse",
        "path": path,
        "rows_total": int(len(df)),
        "rows_parsed": int(len(rows)),
        "rows_skipped": int(skipped_rows),
        "storage_column_found": bool(storage_source_column),
        "storage_source_column": storage_source_column,
        "storage_rows_nonzero": int(storage_rows_nonzero),
        "storage_total": round(float(storage_total), 2),
        "available_columns": available_columns,
    }


def parse_funnel_file(path: str) -> list[dict[str, Any]]:
    if not path:
        return []
    df = _read_typed_table(Path(path), "funnel")
    if df.empty:
        return []
    rows: list[dict[str, Any]] = []
    for _, r in df.iterrows():
        row = dict(r)
        clicks_aliases = ("Переходы в карточку", "Клики", "openCardCount", "clicks")
        impressions_aliases = (
            "Просмотры",
            "Показы",
            "Показы, шт",
            "impressions",
            "views",
            "showCount",
            "shows",
        )
        clicks_col = _lookup_col_name(row, clicks_aliases)
        impressions_col = _lookup_col_name(row, impressions_aliases)
        clicks = _to_int(_lookup(row, clicks_aliases))
        impressions = _to_int(_lookup(row, impressions_aliases))
        clicks_inferred_from_impressions = False
        if clicks <= 0 and impressions > 0 and not clicks_col and impressions_col:
            # Legacy fallback: some files used one column for card transitions.
            clicks = int(impressions)
            clicks_inferred_from_impressions = True

        payload = {
            "date": str(
                _lookup(
                    row,
                    (
                        "\u0414\u0430\u0442\u0430",
                        "\u0414\u0430\u0442\u0430 \u0437\u0430\u043a\u0430\u0437\u0430",
                        "\u041f\u0435\u0440\u0438\u043e\u0434",
                        "period",
                        "date",
                        "order_date",
                    ),
                )
                or ""
            ).strip(),
            "nmId": _to_int(_lookup(row, ("Артикул WB", "Код номенклатуры", "Номенклатура", "nmId"))),
            "openCardCount": int(clicks),
            "clicks": int(clicks),
            "impressions": int(max(impressions, 0)),
            "clicks_inferred_from_impressions": bool(clicks_inferred_from_impressions),
            "addToCartCount": _to_int(_lookup(row, ("Положили в корзину", "Добавлений в корзину", "addToCartCount"))),
            "orderCount": _to_int(_lookup(row, ("Заказали, шт", "Заказы", "orderCount"))),
            "buyoutCount": _to_int(_lookup(row, ("Выкупили, шт", "Выкупы", "buyoutCount"))),
            "orderSum": _to_float(_lookup(row, ("Заказали на сумму, ₽", "Заказали на сумму", "orderSum"))),
            "buyoutSum": _to_float(_lookup(row, ("Выкупили на сумму, ₽", "Выкупили на сумму", "buyoutSum"))),
            "name": str(_lookup(row, ("Название", "name")) or ""),
            "region": str(
                _lookup(
                    row,
                    (
                        "Регион",
                        "Регион доставки",
                        "Область",
                        "Федеральный округ",
                        "region",
                        "delivery_region",
                        "destinationRegion",
                    ),
                )
                or ""
            ).strip(),
            "city": str(_lookup(row, ("Город", "Город доставки", "city", "delivery_city")) or "").strip(),
            "warehouse": str(_lookup(row, ("Склад", "Склад WB", "warehouse", "warehouseName")) or "").strip(),
        }
        is_empty_row = (
            payload["nmId"] == 0
            and payload["impressions"] == 0
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


def _pick_orders_sheet(path: Path) -> str | int:
    sheets = _excel_sheet_names(path)
    if not sheets:
        return 0
    for sheet in sheets:
        sn = _norm(sheet)
        if "все заказы" in sn or "all orders" in sn:
            return sheet
    for sheet in sheets:
        sn = _norm(sheet)
        if "заказ" in sn or "orders" in sn:
            return sheet
    return _find_best_sheet(path, "orders")


def _lookup_col_name(row: dict[str, Any], aliases: tuple[str, ...]) -> str | None:
    normalized = {_norm(k): str(k) for k in row.keys()}
    for alias in aliases:
        key = _norm(alias)
        if key in normalized:
            return normalized.get(key)
    return None


def _value_by_col_offset(row: dict[str, Any], col_name: str | None, offset: int = 1) -> Any:
    if not col_name:
        return None
    keys = list(row.keys())
    try:
        idx = keys.index(col_name)
    except Exception:
        return None
    target_idx = idx + int(offset)
    if target_idx < 0 or target_idx >= len(keys):
        return None
    return row.get(keys[target_idx])


def parse_orders_file(path: str) -> list[dict[str, Any]]:
    rows, _ = parse_orders_file_with_diagnostics(path)
    return rows


def parse_orders_file_with_diagnostics(path: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path:
        return [], {"status": "file_not_provided", "path": ""}

    p = Path(path)
    sheet = _pick_orders_sheet(p)
    header = _find_header_row(p, "orders", sheet_name=sheet)
    df = _read_raw_table(p, header_row=header, sheet_name=sheet)
    if df is None:
        return [], {"status": "parse_failed", "path": path, "sheet": str(sheet), "header_row": int(header)}

    df = df.dropna(axis=1, how="all").fillna("")
    if df.empty:
        return [], {"status": "empty_after_parse", "path": path, "sheet": str(sheet), "header_row": int(header)}

    sku_aliases = ("Артикул WB", "Код номенклатуры", "nmId", "nm_id", "sku")
    seller_aliases = ("Артикул продавца", "Артикул поставщика", "supplierArticle", "seller sku")
    date_aliases = (
        "Дата оформления заказа",
        "Дата заказа",
        "Дата",
        "date",
        "order_date",
    )
    region_aliases = (
        "Регион прибытия",
        "Регион доставки",
        "Регион",
        "Область",
        "region",
        "delivery_region",
    )
    city_aliases = (
        "Город прибытия",
        "Город доставки",
        "Город",
        "city",
        "delivery_city",
    )
    qty_aliases = ("Количество заказов", "Заказы", "Кол-во", "Количество", "orders", "quantity")

    first_row = dict(df.iloc[0].to_dict()) if len(df) > 0 else {}
    sku_col = _lookup_col_name(first_row, sku_aliases)
    seller_col = _lookup_col_name(first_row, seller_aliases)
    date_col = _lookup_col_name(first_row, date_aliases)
    region_col = _lookup_col_name(first_row, region_aliases)
    city_col = _lookup_col_name(first_row, city_aliases)
    qty_col = _lookup_col_name(first_row, qty_aliases)

    missing_columns: list[str] = []
    if not sku_col and not seller_col:
        missing_columns.append("sku_or_seller_article")
    if not date_col:
        missing_columns.append("date")
    if not region_col and not city_col:
        missing_columns.append("region_or_city")

    rows: list[dict[str, Any]] = []
    parsed_rows = 0
    skipped_rows = 0
    geo_rows = 0
    for _, r in df.iterrows():
        parsed_rows += 1
        row = dict(r)

        sku = _to_int(_lookup(row, sku_aliases))
        seller_article = str(_lookup(row, seller_aliases) or "").strip()
        if sku <= 0 and not seller_article:
            skipped_rows += 1
            continue

        date_raw = str(_lookup(row, date_aliases) or "").strip()
        region = str(_lookup(row, region_aliases) or "").strip()
        city = str(_lookup(row, city_aliases) or "").strip()
        if not city and region_col:
            city = str(_value_by_col_offset(row, region_col, offset=1) or "").strip()
            if _norm(city).startswith("unnamed"):
                city = ""

        if not region and not city:
            skipped_rows += 1
            continue

        if region or city:
            geo_rows += 1

        qty_raw = _lookup(row, qty_aliases)
        qty = _to_int(qty_raw)
        if qty <= 0:
            qty = 1

        rows.append(
            {
                "date": date_raw,
                "nmId": int(sku),
                "seller_article": seller_article,
                "region": region,
                "city": city,
                "orders": int(max(qty, 1)),
                "quantity": int(max(qty, 1)),
            }
        )

    status = "ok" if rows else "empty_after_parse"
    if missing_columns and not rows:
        status = "unsupported_format"
    return rows, {
        "status": status,
        "path": path,
        "sheet": str(sheet),
        "header_row": int(header),
        "rows_scanned": int(parsed_rows),
        "rows_parsed": int(len(rows)),
        "rows_with_geo": int(geo_rows),
        "rows_skipped": int(skipped_rows),
        "recognized_columns": {
            "sku": sku_col,
            "seller_article": seller_col,
            "date": date_col,
            "region": region_col,
            "city": city_col,
            "orders": qty_col,
        },
        "missing_columns": missing_columns,
    }


def parse_stocks_file(path: str) -> list[dict[str, Any]]:
    rows, _ = parse_stocks_file_with_diagnostics(path)
    return rows


def _pick_stocks_sheet(path: Path) -> str | int:
    sheets = _excel_sheet_names(path)
    if not sheets:
        return 0
    for sheet in sheets:
        sn = _norm(sheet)
        if "деталь" in sn:
            return sheet
    for sheet in sheets:
        sn = _norm(sheet)
        if "остатк" in sn:
            return sheet
    return sheets[0]


def _extract_date_stock_value(row: dict[str, Any]) -> tuple[int, str | None]:
    # Choose latest date-like column value as current stock; fallback to max.
    date_like_cols = []
    for key in row.keys():
        k = _norm(key)
        if "." in k and any(ch.isdigit() for ch in k):
            date_like_cols.append(key)
    values = []
    for col in date_like_cols:
        values.append((col, _to_int(row.get(col))))
    if not values:
        return 0, None
    # keep order from dataframe: last date is usually latest day in period
    last_col, last_val = values[-1]
    max_val = max(v for _, v in values)
    return (last_val if last_val > 0 else max_val), str(last_col)


def _value_by_index(row: dict[str, Any], idx: int) -> Any:
    if idx < 0:
        return None
    values = list(row.values())
    if idx >= len(values):
        return None
    return values[idx]


def _extract_volume_liters_from_stocks_row(row: dict[str, Any]) -> tuple[float | None, str]:
    direct_volume = _to_float_or_none(
        _lookup(
            row,
            (
                "Объем, л",
                "Объём, л",
                "Объем товара, л",
                "Объём товара, л",
                "Объем л",
                "Объём л",
                "volume_liters",
                "volume_l",
                "volume",
            ),
        )
    )
    if direct_volume is not None and direct_volume > 0:
        return float(direct_volume), "stocks"

    length_cm = _to_float_or_none(
        _lookup(row, ("Длина, см", "Длина см", "length_cm", "length"))
    )
    width_cm = _to_float_or_none(
        _lookup(row, ("Ширина, см", "Ширина см", "width_cm", "width"))
    )
    height_cm = _to_float_or_none(
        _lookup(row, ("Высота, см", "Высота см", "height_cm", "height"))
    )
    if (
        length_cm is not None
        and width_cm is not None
        and height_cm is not None
        and length_cm > 0
        and width_cm > 0
        and height_cm > 0
    ):
        return float((length_cm * width_cm * height_cm) / 1000.0), "calculated"
    return None, "missing"


def _parse_stocks_df_rows(df_local: pd.DataFrame) -> tuple[list[dict[str, Any]], int, int, str | None, int, int]:
    rows_local: list[dict[str, Any]] = []
    mapped_rows_local = 0
    parsed_rows_local = 0
    date_stock_column_local = None
    id_mapped_rows_local = 0
    qty_positive_rows_local = 0

    for _, r in df_local.iterrows():
        row = dict(r)
        parsed_rows_local += 1

        qty = _to_int(_lookup(row, ("quantityFull", "quantity", "qty", "stock")))
        if qty <= 0:
            qty = _to_int(_value_by_index(row, 16))
        if qty <= 0:
            qty_by_day, day_col = _extract_date_stock_value(row)
            if qty_by_day > 0:
                qty = qty_by_day
                if day_col:
                    date_stock_column_local = day_col

        nmid = _to_int(_lookup(row, ("nmId", "nm_id", "sku")))
        if nmid == 0:
            nmid = _to_int(_value_by_index(row, 2))

        supplier_article = str(_lookup(row, ("supplierArticle", "vendorCode", "seller_sku")) or "").strip()
        if not supplier_article:
            supplier_article = str(_value_by_index(row, 0) or "").strip()

        name = str(_lookup(row, ("name", "title")) or "").strip()
        if not name:
            name = str(_value_by_index(row, 1) or "").strip()

        in_way_to_client = _to_int(_lookup(row, ("inWayToClient",)))
        if in_way_to_client == 0:
            in_way_to_client = _to_int(_value_by_index(row, 21))

        in_way_from_client = _to_int(_lookup(row, ("inWayFromClient",)))
        if in_way_from_client == 0:
            in_way_from_client = _to_int(_value_by_index(row, 22))
        volume_liters, volume_source = _extract_volume_liters_from_stocks_row(row)

        payload = {
            "nmId": nmid,
            "quantityFull": int(qty),
            "inWayToClient": in_way_to_client,
            "inWayFromClient": in_way_from_client,
            "volume_liters": round(float(volume_liters), 6) if volume_liters is not None and volume_liters > 0 else None,
            "volume_source": str(volume_source or "missing"),
            "supplierArticle": supplier_article,
            "_name": name,
            "region": str(
                _lookup(
                    row,
                    (
                        "Регион",
                        "Регион склада",
                        "Область",
                        "Федеральный округ",
                        "region",
                        "warehouse_region",
                    ),
                )
                or ""
            ).strip(),
            "city": str(_lookup(row, ("Город", "Город склада", "city", "warehouse_city")) or "").strip(),
            "warehouse": str(
                _lookup(
                    row,
                    (
                        "Склад",
                        "Склад WB",
                        "Склад продавца",
                        "warehouse",
                        "warehouseName",
                    ),
                )
                or ""
            ).strip(),
        }

        marker = " ".join([_norm(payload.get("_name")), _norm(payload.get("supplierArticle"))])
        if any(x in marker for x in ("?????", "?????", "total")):
            continue

        if payload["nmId"] > 0:
            id_mapped_rows_local += 1
        if payload["quantityFull"] > 0:
            qty_positive_rows_local += 1

        if payload["nmId"] or payload["supplierArticle"] or payload["quantityFull"] > 0:
            mapped_rows_local += 1
            rows_local.append(payload)

    return (
        rows_local,
        parsed_rows_local,
        mapped_rows_local,
        date_stock_column_local,
        id_mapped_rows_local,
        qty_positive_rows_local,
    )


def parse_stocks_file_with_diagnostics(path: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path:
        return [], {"status": "file_not_provided", "path": ""}

    p = Path(path)
    sheet = _pick_stocks_sheet(p)
    header_guess = _find_header_row(p, "stocks", sheet_name=sheet)

    header_candidates: list[int] = []
    for candidate in [header_guess, header_guess + 1, 1, 0, 2, 3]:
        if candidate >= 0 and candidate not in header_candidates:
            header_candidates.append(candidate)

    best_rows: list[dict[str, Any]] = []
    best_parsed_rows = 0
    best_mapped_rows = 0
    best_id_mapped_rows = 0
    best_qty_positive_rows = 0
    best_date_col = None
    best_header = header_guess
    tried: list[dict[str, Any]] = []

    for header in header_candidates:
        df = _read_raw_table(p, header_row=header, sheet_name=sheet)
        if df is None:
            tried.append({"header_row": int(header), "status": "parse_failed"})
            continue

        df = df.dropna(axis=1, how="all").fillna("")
        if df.empty:
            tried.append({"header_row": int(header), "status": "empty_after_parse"})
            continue

        (
            rows,
            parsed_rows,
            mapped_rows,
            date_stock_column,
            id_mapped_rows,
            qty_positive_rows,
        ) = _parse_stocks_df_rows(df)
        tried.append(
            {
                "header_row": int(header),
                "status": "ok" if rows else "empty_after_parse",
                "parsed_rows": int(parsed_rows),
                "mapped_rows": int(mapped_rows),
                "id_mapped_rows": int(id_mapped_rows),
                "qty_positive_rows": int(qty_positive_rows),
            }
        )

        candidate_score = (
            int(id_mapped_rows),
            int(qty_positive_rows),
            -abs(int(header) - 1),
            int(mapped_rows),
        )
        best_score = (
            int(best_id_mapped_rows),
            int(best_qty_positive_rows),
            -abs(int(best_header) - 1),
            int(best_mapped_rows),
        )
        if candidate_score > best_score:
            best_rows = rows
            best_parsed_rows = parsed_rows
            best_mapped_rows = mapped_rows
            best_id_mapped_rows = id_mapped_rows
            best_qty_positive_rows = qty_positive_rows
            best_date_col = date_stock_column
            best_header = header

    rows = best_rows
    parsed_rows = best_parsed_rows
    mapped_rows = best_mapped_rows
    date_stock_column = best_date_col

    status = "ok" if rows else "empty_after_parse"
    if parsed_rows > 0 and mapped_rows == 0:
        status = "aggregation_unmapped"

    return rows, {
        "status": status,
        "path": path,
        "sheet": str(sheet),
        "header_row": int(best_header),
        "header_row_guess": int(header_guess),
        "header_candidates_tried": tried,
        "parsed_rows": int(parsed_rows),
        "mapped_rows": int(mapped_rows),
        "id_mapped_rows": int(best_id_mapped_rows),
        "qty_positive_rows": int(best_qty_positive_rows),
        "date_stock_column": date_stock_column,
    }

def parse_ads_file(path: str) -> list[dict[str, Any]]:
    rows, _ = parse_ads_file_with_diagnostics(path)
    return rows


def parse_ads_file_with_diagnostics(path: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path:
        return [], {"status": "file_not_provided", "path": ""}
    df = _read_typed_table(Path(path), "ads")
    if df.empty:
        return [], {"status": "empty_after_parse", "path": path}
    rows: list[dict[str, Any]] = []
    skipped = 0
    for _, r in df.iterrows():
        row = dict(r)
        name = str(_lookup(row, ("Название", "name")) or "")
        query = str(
            _lookup(
                row,
                (
                    "Поисковый запрос",
                    "Поисковая фраза",
                    "Ключевая фраза",
                    "Фраза",
                    "Запрос",
                    "keyword",
                    "query",
                ),
            )
            or ""
        ).strip()
        if _norm(name).startswith("всего по кампании"):
            skipped += 1
            continue
        payload = {
            "nmId": _to_int(_lookup(row, ("Номенклатура", "nmId", "Код номенклатуры"))),
            "spend": _to_float(_lookup(row, ("Затраты, RUB", "Затраты", "Расход", "spend"))),
            "impressions": _to_int(_lookup(row, ("Показы", "Показы, шт", "impressions", "views"))),
            "clicks": _to_int(_lookup(row, ("Клики", "clicks"))),
            "revenueAttr": _to_float(_lookup(row, ("Заказов на сумму, RUB", "Заказов на сумму", "revenueAttr", "orderSum"))),
            "views": _to_int(_lookup(row, ("Показы", "Показы, шт", "impressions", "views"))),
            "name": name,
            "query": query,
        }
        if payload["nmId"] == 0 and payload["spend"] == 0 and payload["impressions"] == 0 and payload["clicks"] == 0:
            skipped += 1
            continue
        rows.append(payload)
    return rows, {
        "status": "ok" if rows else "empty_after_parse",
        "path": path,
        "rows_total": int(len(df)),
        "rows_parsed": int(len(rows)),
        "rows_skipped": int(skipped),
    }


def parse_search_file(path: str) -> list[dict[str, Any]]:
    rows, _ = parse_search_file_with_diagnostics(path)
    return rows


def _pick_search_sheet(path: Path) -> str | int:
    sheets = _excel_sheet_names(path)
    if not sheets:
        return 0
    for sheet in sheets:
        sn = _norm(sheet)
        if "деталь" in sn:
            return sheet
    for sheet in sheets:
        sn = _norm(sheet)
        if "поиск" in sn or "query" in sn:
            return sheet
    return _find_best_sheet(path, "search")


def parse_search_file_with_diagnostics(path: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path:
        return [], {"status": "file_not_provided", "path": ""}
    p = Path(path)
    sheet = _pick_search_sheet(p)
    header = _find_header_row(p, "search", sheet_name=sheet)
    df = _read_raw_table(p, header_row=header, sheet_name=sheet)
    if df is None:
        return [], {"status": "parse_failed", "path": path, "sheet": str(sheet), "header_row": int(header)}
    df = df.dropna(axis=1, how="all").fillna("")
    if df.empty:
        return [], {"status": "empty_after_parse", "path": path, "sheet": str(sheet), "header_row": int(header)}

    normalized_cols = [_norm(c) for c in list(df.columns)]
    recognized = {
        "query": _find_best_sheet,  # placeholder to keep structure assignment explicit below
    }
    query_aliases = ("Поисковый запрос", "Запрос", "Query", "search_query", "phrase")
    impressions_aliases = ("Показы", "Количество запросов", "impressions")
    clicks_aliases = ("Клики", "Переходы в карточку", "clicks")
    add_to_cart_aliases = ("Положили в корзину", "Добавили в корзину", "add_to_cart")
    orders_aliases = ("Заказали, шт", "Заказы", "orderCount", "orders")
    revenue_aliases = ("Выкупили на сумму, ₽", "Заказали на сумму, ₽", "Выручка", "revenue", "orderSum")
    sku_aliases = ("Артикул WB", "Код номенклатуры", "nmId")
    seller_aliases = ("Артикул продавца", "Артикул поставщика", "supplierArticle")

    def _resolve_col(aliases: tuple[str, ...]) -> str | None:
        return _lookup({c: c for c in normalized_cols}, aliases)

    query_col = _resolve_col(query_aliases)
    impressions_col = _resolve_col(impressions_aliases)
    clicks_col = _resolve_col(clicks_aliases)
    add_to_cart_col = _resolve_col(add_to_cart_aliases)
    orders_col = _resolve_col(orders_aliases)
    revenue_col = _resolve_col(revenue_aliases)
    sku_col = _resolve_col(sku_aliases)
    seller_col = _resolve_col(seller_aliases)

    missing_columns = []
    if not query_col:
        missing_columns.append("query")
    if not impressions_col:
        missing_columns.append("impressions")

    rows: list[dict[str, Any]] = []
    parsed_rows = 0
    skipped_rows = 0
    for _, r in df.iterrows():
        parsed_rows += 1
        row = dict(r)
        query = str(_lookup(row, query_aliases) or "").strip()
        if not query:
            skipped_rows += 1
            continue
        if any(x in _norm(query) for x in ("итого", "всего", "total")):
            skipped_rows += 1
            continue
        rows.append(
            {
                "query": query,
                "impressions": _to_int(_lookup(row, impressions_aliases)),
                "clicks": _to_int(_lookup(row, clicks_aliases)),
                "add_to_cart": _to_int(_lookup(row, add_to_cart_aliases)),
                "orders": _to_int(_lookup(row, orders_aliases)),
                "buyouts": _to_int(_lookup(row, ("Выкупы", "buyoutCount", "buyouts"))),
                "spend": _to_float(_lookup(row, ("Расход", "Затраты", "spend"))),
                "revenue": _to_float(_lookup(row, revenue_aliases)),
                "nmId": _to_int(_lookup(row, sku_aliases)),
                "seller_article": str(_lookup(row, seller_aliases) or ""),
            }
        )
    status = "ok" if rows else "empty_after_parse"
    if missing_columns and not rows:
        status = "unsupported_format"
    return rows, {
        "status": status,
        "path": path,
        "sheet": str(sheet),
        "header_row": int(header),
        "parsed_rows": int(parsed_rows),
        "rows_parsed": int(len(rows)),
        "rows_skipped": int(skipped_rows),
        "recognized_columns": {
            "query": query_col,
            "impressions": impressions_col,
            "clicks": clicks_col,
            "add_to_cart": add_to_cart_col,
            "orders": orders_col,
            "revenue": revenue_col,
            "nmId": sku_col,
            "seller_article": seller_col,
        },
        "missing_columns": missing_columns,
    }


def parse_cogs_file(path: str) -> list[dict[str, Any]]:
    rows, _ = parse_cogs_file_with_diagnostics(path)
    return rows


def parse_cogs_file_with_diagnostics(path: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path:
        return [], {"status": "file_not_provided", "path": ""}
    p = Path(path)
    sheet = _find_best_sheet(p, "cogs")
    header = _find_header_row(p, "cogs", sheet_name=sheet)
    df = _read_raw_table(p, header_row=header, sheet_name=sheet)
    if df is None:
        return [], {"status": "parse_failed", "path": path, "sheet": str(sheet), "header_row": int(header)}
    df = df.dropna(axis=1, how="all").fillna("")
    if df.empty:
        return [], {"status": "empty_after_parse", "path": path, "sheet": str(sheet), "header_row": int(header)}

    sku_aliases = ("Артикул WB", "Код номенклатуры", "SKU", "sku", "nmId", "nm_id")
    seller_aliases = ("Артикул продавца", "Артикул поставщика", "seller_sku", "supplierArticle")
    cogs_aliases = ("Себестоимость", "Себестоимость товара", "cogs", "cost", "cost_price")

    source_columns = [str(c) for c in list(df.columns)]
    col_probe = {str(c): str(c) for c in source_columns}
    recognized_columns = {
        "sku": _lookup(col_probe, sku_aliases),
        "seller_sku": _lookup(col_probe, seller_aliases),
        "cogs": _lookup(col_probe, cogs_aliases),
    }
    missing_columns: list[str] = []
    if not recognized_columns.get("cogs"):
        missing_columns.append("cogs")
    if not recognized_columns.get("sku") and not recognized_columns.get("seller_sku"):
        missing_columns.append("sku_or_seller_sku")

    rows: list[dict[str, Any]] = []
    parsed_rows = 0
    skipped_rows = 0
    for _, r in df.iterrows():
        parsed_rows += 1
        row = dict(r)
        cogs = _to_float(_lookup(row, cogs_aliases))
        if cogs <= 0:
            skipped_rows += 1
            continue
        sku_raw = _lookup(row, sku_aliases)
        seller_raw = _lookup(row, seller_aliases)
        sku_token = _to_sku_token(sku_raw)
        seller_token = _to_seller_token(seller_raw)
        if not sku_token and not seller_token:
            skipped_rows += 1
            continue
        rows.append(
            {
                "sku": _to_int(sku_token) if sku_token else 0,
                "sku_token": sku_token,
                "seller_sku": str(seller_raw or "").strip(),
                "seller_sku_token": seller_token,
                "cogs": float(cogs),
            }
        )

    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row.get("sku_token") or ""), str(row.get("seller_sku_token") or ""))
        if key not in deduped:
            deduped[key] = row
            continue
        # Keep latest non-zero value.
        deduped[key]["cogs"] = float(row.get("cogs") or deduped[key].get("cogs") or 0.0)

    rows_out = list(deduped.values())
    status = "ok" if rows_out else "empty_after_parse"
    if missing_columns and not rows_out:
        status = "unsupported_format"
    return rows_out, {
        "status": status,
        "path": path,
        "sheet": str(sheet),
        "header_row": int(header),
        "source_columns": source_columns,
        "recognized_columns": recognized_columns,
        "missing_columns": missing_columns,
        "rows_scanned": int(parsed_rows),
        "rows_loaded": int(len(rows_out)),
        "rows_skipped": int(skipped_rows),
        "unique_sku_tokens": int(len({str(x.get('sku_token') or '') for x in rows_out if str(x.get('sku_token') or '')})),
        "unique_seller_tokens": int(len({str(x.get('seller_sku_token') or '') for x in rows_out if str(x.get('seller_sku_token') or '')})),
    }


def select_best_detected_files(detected_files: list[DetectedFile]) -> dict[str, DetectedFile]:
    best: dict[str, DetectedFile] = {}
    for item in detected_files:
        if item.file_type not in FILE_TYPES:
            continue
        cur = best.get(item.file_type)
        if cur is None or item.score > cur.score:
            best[item.file_type] = item
    return best


def group_detected_files(detected_files: list[DetectedFile]) -> dict[str, list[DetectedFile]]:
    grouped: dict[str, list[DetectedFile]] = {k: [] for k in FILE_TYPES}
    for item in detected_files:
        if item.file_type not in FILE_TYPES:
            continue
        grouped[item.file_type].append(item)
    for key in grouped:
        grouped[key] = sorted(grouped[key], key=lambda x: (-int(x.score), str(x.path)))
    return grouped


# Compatibility wrappers used by previous audit mode.
def load_ads_xlsx(path: str) -> list[dict[str, Any]]:
    return parse_ads_file(path)


def load_finance_xlsx(path: str) -> list[dict[str, Any]]:
    return parse_finance_file(path)


def load_funnel_xlsx(path: str) -> list[dict[str, Any]]:
    return parse_funnel_file(path)


def load_stocks_xlsx(path: str) -> list[dict[str, Any]]:
    return parse_stocks_file(path)


def load_orders_xlsx(path: str) -> list[dict[str, Any]]:
    return parse_orders_file(path)
