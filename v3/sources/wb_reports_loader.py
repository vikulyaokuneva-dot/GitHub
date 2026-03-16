from __future__ import annotations

import csv
import os
import re
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Tuple
from xml.etree import ElementTree as ET

try:
    import pandas as pd  # type: ignore
except Exception:
    pd = None

from ..cleaning.sku_normalizer import split_assigned_vs_unassigned_rows
from ..validation.data_integrity import (
    evaluate_financial_integrity,
    evaluate_sku_attribution,
    resolve_report_reliability_level,
)

ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}

REPORT_NAME_KEYWORDS = {
    "sales": ["воронка", "продаж", "реализац", "детализирован", "еженедель", "sales", "sale", "realization", "статистик"],
    "ads": ["реклам", "кампан", "продвиж", "ads", "advert", "campaign", "promo"],
    "stocks": ["остат", "склад", "stock", "inventory"],
}

ADS_FILE_NAME_KEYWORDS = ("статистика", "реклама", "advert", "ads")
ADS_SHEET_KEYWORDS = ("статистика", "statistics")
EXCEL_EXTENSIONS = {".xlsx", ".xls"}
ADS_REPORT_NAME_KEYWORDS = ("статистика", "ads", "реклама")
ADS_REQUIRED_COLUMN_HINT = "затраты_rub"

SUPPLIER_GOODS_NAME_KEYWORDS = ("ежедневный", "детализированный", "supplier", "goods", "report")
SUPPLIER_GOODS_REQUIRED_COLUMN_HINTS = (
    "номенклатура",
    "заказано",
    "выкупили",
    "сумма заказов",
    "к перечислению",
)
SUPPLIER_GOODS_FINANCIAL_COLUMN_HINTS = (
    "код номенклатуры",
    "к перечислению продавцу за реализованный товар",
    "вознаграждение вайлдберриз",
    "услуги по доставке товара покупателю",
    "хранение",
    "удержания",
    "количество возврата",
)

_SUPPLIER_GOODS_DAILY_FIELD_SYNONYMS = {
    "orders_count": (
        "шт",
        "заказанные_товары_шт",
        "заказано",
        "заказано_шт",
        "кол_во_заказов",
        "колво_заказов",
        "количество_заказов",
    ),
    "orders_amount": (
        "сумма_заказов",
        "сумма_заказов_минус_комиссия_wb_руб",
        "сумма_заказов_руб",
        "заказов_на_сумму_rub",
        "заказов_на_сумму",
    ),
    "buyouts_count": (
        "выкупили",
        "выкупили_шт",
        "выкупы_шт",
        "количество_выкупов",
        "кол_во_выкупов",
        "продажи_шт",
    ),
    "buyouts_amount": (
        "к_перечислению_руб",
        "к_перечислению_за_товар_руб",
        "к_перечислению_продавцу_за_товар_руб",
        "к_перечислению_продавцу_за_реализованный_товар",
        "к_перечислению",
    ),
}

_SUPPLIER_GOODS_CONFIRMED_ORDERS_COUNT_HINTS = (
    "orders_count",
    "order_count",
    "кол_во_заказов",
    "количество_заказов",
    "колво_заказов",
)

_SUPPLIER_GOODS_CONFIRMED_BUYOUTS_COUNT_HINTS = (
    "buyouts_count",
    "кол_во_выкупов",
    "количество_выкупов",
    "колво_выкупов",
)

_SUPPLIER_GOODS_FILE_TOKENS = (
    "товар",
    "goods",
    "supplier",
    "ежеднев",
    "детализирован",
    "report",
    "daily",
    "воронка",
)

FIELD_SYNONYMS = {
    "sku": ["sku", "nm_id", "nmid", "артикул", "артикул_wb", "артикул_продавца", "номенклатура", "код_товара", "код_номенклатуры", "наименование", "товар", "предмет"],
    "seller_sku": ["seller_sku", "supplier_sku", "артикул_поставщика", "артикул_продавца", "артикул", "vendor_code"],
    "warehouse": ["warehouse", "склад", "склад_продажи", "склад_отгрузки", "warehouse_name", "наименование_склада", "наименование_офиса_доставки", "офис_доставки", "office"],
    "revenue": [
        "revenue",
        "выручка",
        "заказов_на_сумму_rub",
        "заказов_на_сумму_руб",
        "заказов_на_сумму",
        "к_перечислению",
        "кперечислению",
        "к_перечислению_продавцу",
        "к_перечислению_продавцу_за_реализованный_товар",
        "итого_к_перечислению",
        "sum_to_pay",
        "сумма_продаж",
        "сумма_реализации",
        "ваилдберриз_реализовал_товар_пр",
    ],
    "gross_revenue": [
        "gross_revenue",
        "retail_price",
        "retail_revenue",
        "цена_розничная",
        "сумма_розничной_цены",
    ],
    "wb_realized_revenue": [
        "wb_realized_revenue",
        "realized_revenue",
        "ваилдберриз_реализовал_товар_пр",
        "вайлдберриз_реализовал_товар_пр",
    ],
    "seller_payout": [
        "seller_payout",
        "sum_to_pay",
        "к_перечислению",
        "кперечислению",
        "к_перечислению_продавцу",
        "к_перечислению_продавцу_за_реализованный_товар",
        "итого_к_перечислению",
    ],
    "profit": ["profit", "прибыль", "доход", "валовая_прибыль", "net_profit"],
    "orders": [
        "orders",
        "order_count",
        "orders_count",
        "заказы",
        "заказы_шт",
        "колво_заказов",
        "колво_заказов_шт",
        "кол_во_заказов",
        "кол_заказов",
        "количество_заказов",
        "количество_заказов_шт",
        "заказанные_товары",
        "заказанные_товары_шт",
        "заказано_шт",
        "заказов_на_сумму",
        "ordered_units",
        "ordered_qty",
        "ordered_quantity",
    ],
    "buys": ["buys", "выкупы", "продажи", "колво_выкупов", "количество_выкупов", "выкупили", "кол_во", "количество", "кол-во"],
    "sales_count": ["sales_count", "продаж", "колво_продаж", "количество_продаж", "реализовано", "кол_во", "количество", "кол-во"],
    "stock": [
        "stock",
        "остаток",
        "остатки",
        "склад_остаток",
        "stocks",
        "на_складе",
        "всего_находится_на_складах",
        "в_пути_до_получателей",
    ],
    "ads_spend": ["ads_spend", "расходы_на_рекламу", "затраты", "затраты_на_рекламу", "затраты_rub", "расходы", "spend", "cost"],
    "roi": ["roi", "romi", "окупаемость", "рентабельность_рекламы"],
    "ddr": ["ddr", "ддр", "доля_рекламных_расходов", "доля_расходов"],
    "cpo": ["cpo", "стоимость_заказа", "cost_per_order"],
    "impressions": ["impressions", "показы", "показы_всего", "просмотры", "views"],
    "clicks": ["clicks", "клики", "переходы", "click"],
    "ctr": ["ctr", "ctr_%", "ctr(%)", "кликабельность"],
    "cpc": ["cpc", "цена_клика", "стоимость_клика"],
    "acos": ["acos", "acos_%", "ддр", "доля_рекламных_расходов"],
    "romi": ["romi", "roi", "окупаемость_рекламы", "рентабельность_рекламы"],
    "conversion_type": ["conversion_type", "тип_конверсии", "конверсия"],
    "query": [
        "query",
        "keyword",
        "search_query",
        "search_term",
        "phrase",
        "search_phrase",
        "query_text",
        "ключевой_запрос",
        "поисковый_запрос",
        "поисковая_фраза",
        "ключевая_фраза",
        "запрос",
    ],
    "add_to_cart": ["add_to_cart", "cart_adds", "cart_add", "carts", "добавления_в_корзину", "корзина"],
    "buyouts": ["buyouts", "buyout_units", "sales_units", "выкупы", "выкупили"],
    "avg_position": ["avg_position", "average_position", "position_avg", "средняя_позиция", "позиция_средняя"],
    "margin": ["margin", "маржа", "маржинальность"],
    "margin_pct": ["margin_pct", "маржа_pct", "маржа_процент", "margin_percent"],
    "cost_price": [
        "cost_price",
        "cogs",
        "cost_of_goods_sold",
        "себестоимость",
        "себестоимость_товара",
        "закупочная_стоимость",
        "себестоимость_руб",
    ],
    "wb_commission": [
        "wb_commission",
        "комиссия_wb",
        "комиссия_wildberries",
        "комиссия_маркетплейса",
        "вознаграждение_ваилдберриз",
        "вознаграждение_вайлдберриз",
        "вознаграждение_ваилдберриз_вв",
        "вознаграждение_вайлдберриз_вв",
        "вознаграждение_ваилдберриз_вв_без_ндс",
        "вознаграждение_вайлдберриз_вв_без_ндс",
        "вознаграждение_wb",
        "комиссионное_вознаграждение",
        "retail_commission",
        "sales_commission",
    ],
    "logistics": ["логистика", "услуги_по_доставке_товара_покупателю", "доставка", "доставка_товара_покупателю"],
    "penalties": ["общая_сумма_штрафов", "штрафы", "сумма_штрафов"],
    "storage": ["хранение", "хранение_товара"],
    "deductions": ["удержание", "удержания", "прочие_удержания"],
    "acquiring": ["acquiring", "эквайринг", "услуги_эквайринга"],
    "pvz_service": [
        "pvz_service",
        "pickup_point_service",
        "пвз",
        "выдача_возврат",
        "возмещение_издержек_по_перевозке_по_складским_операциям_с_товаром",
    ],
    "loyalty_program": [
        "loyalty_program",
        "стоимость_участия_в_программе_лояльности",
    ],
    "loyalty_points_withheld": [
        "loyalty_points_withheld",
        "сумма_удержанная_за_начисленные_баллы_программы_лояльности",
    ],
    "other_adjustments": ["other_adjustments", "прочие_корректировки", "корректировки"],
}

_STOCK_COLUMN_BLACKLIST = {
    "бренд",
    "предмет",
    "sku",
    "seller_sku",
    "артикул",
    "артикул_продавца",
    "артикул_поставщика",
    "артикул_wb",
    "код_товара",
    "код_номенклатуры",
    "номенклатура",
    "наименование",
    "товар",
    "stock",
    "остаток",
    "остатки",
    "склад_остаток",
    "stocks",
    "на_складе",
    "всего_находится_на_складах",
    "в_пути_до_получателей",
    "в_пути_возвраты_на_склад_wb",
}


def _normalize_text(value: str) -> str:
    text = str(value).strip().lower().replace("ё", "е")
    text = text.replace("\n", " ").replace("\t", " ")
    text = re.sub(r"\s+", " ", text)
    text = text.replace(" ", "_")
    text = re.sub(r"[^\w]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def _name_hint_token(norm_name: str, tokens: Iterable[str]) -> str:
    for token in tokens:
        normalized = _normalize_text(token)
        if normalized and normalized in norm_name:
            return normalized
    return ""


def _column_hint_present(normalized_columns: List[str], required_tokens: Iterable[str]) -> bool:
    required = [_normalize_text(token) for token in required_tokens if str(token).strip()]
    if not required:
        return False
    for token in required:
        if not any(token and (token in col or col in token) for col in normalized_columns if col):
            return False
    return True


def _column_hints_detected(normalized_columns: List[str], required_tokens: Iterable[str]) -> List[str]:
    required = [_normalize_text(token) for token in required_tokens if str(token).strip()]
    detected: List[str] = []
    for token in required:
        if any(token and (token in col or col in token) for col in normalized_columns if col):
            detected.append(token)
    return detected


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(" ", "").replace("%", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _input_hint_path(input_dir: str) -> str:
    normalized = input_dir.replace("\\", "/")
    m = re.search(r"cabinets/([^/]+)/input/?$", normalized)
    if m:
        return f"cabinets/{m.group(1)}/input"
    return input_dir


def _dedupe_columns(columns: List[str]) -> List[str]:
    seen: Dict[str, int] = {}
    out: List[str] = []
    for raw in columns:
        base = str(raw).strip() or "column"
        seen[base] = seen.get(base, 0) + 1
        out.append(base if seen[base] == 1 else f"{base}_{seen[base]}")
    return out


def _normalize_records(columns: List[str], records: Iterable[Dict[str, Any]]) -> Tuple[List[str], List[Dict[str, Any]]]:
    ncols = [_normalize_text(col) for col in columns]
    rows: List[Dict[str, Any]] = []
    for row in records:
        item: Dict[str, Any] = {}
        for key, val in row.items():
            item[_normalize_text(key)] = val
        rows.append(item)
    return ncols, rows


def _read_csv_table(path: str, max_rows: int | None = None) -> Tuple[List[str], List[Dict[str, Any]]]:
    encodings = ["utf-8-sig", "utf-8", "cp1251", "latin-1"]
    last_error: Exception | None = None
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                sample = f.read(4096)
                f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
                except Exception:
                    dialect = csv.excel
                    dialect.delimiter = ";"
                reader = csv.DictReader(f, dialect=dialect)
                cols = _dedupe_columns(list(reader.fieldnames or []))
                rows: List[Dict[str, Any]] = []
                for i, row in enumerate(reader):
                    if max_rows is not None and i >= max_rows:
                        break
                    rows.append({str(k): v for k, v in row.items() if k is not None})
                return cols, rows
        except Exception as e:
            last_error = e
    if last_error:
        raise last_error
    raise RuntimeError("Unable to read CSV")


def _col_to_idx(ref: str) -> int:
    letters = ""
    for ch in ref:
        if ch.isalpha():
            letters += ch.upper()
        else:
            break
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return max(idx - 1, 0)


def _xlsx_shared_strings(zf: zipfile.ZipFile) -> List[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    out: List[str] = []
    for si in root.findall("x:si", ns):
        parts = [(t.text or "") for t in si.findall(".//x:t", ns)]
        out.append("".join(parts))
    return out


def _xlsx_sheet_targets(zf: zipfile.ZipFile) -> List[Tuple[str, str]]:
    if "xl/workbook.xml" not in zf.namelist():
        return []
    wb = ET.fromstring(zf.read("xl/workbook.xml"))
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rid_attr = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"

    rels_path = "xl/_rels/workbook.xml.rels"
    rel_map: Dict[str, str] = {}
    if rels_path in zf.namelist():
        rels = ET.fromstring(zf.read(rels_path))
        rns = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
        for rel in rels.findall("r:Relationship", rns):
            rel_id = str(rel.attrib.get("Id") or "")
            target_raw = str(rel.attrib.get("Target") or "")
            if not rel_id or not target_raw:
                continue
            if target_raw.startswith("/"):
                target = target_raw.lstrip("/")
            elif target_raw.startswith("xl/"):
                target = target_raw
            else:
                target = f"xl/{target_raw}"
            rel_map[rel_id] = target

    out: List[Tuple[str, str]] = []
    for sheet in wb.findall("x:sheets/x:sheet", ns):
        rid = str(sheet.attrib.get(rid_attr) or "")
        name = str(sheet.attrib.get("name") or "").strip()
        target = rel_map.get(rid, "")
        if name and target:
            out.append((name, target))
    return out


def _xlsx_rows_from_sheet(
    zf: zipfile.ZipFile,
    shared: List[str],
    sheet_path: str,
    max_rows: int | None = None,
) -> List[List[Any]]:
    if sheet_path not in zf.namelist():
        return []
    root = ET.fromstring(zf.read(sheet_path))
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    data = root.find("x:sheetData", ns)
    if data is None:
        return []

    out: List[List[Any]] = []
    for row_el in data.findall("x:row", ns):
        if max_rows is not None and len(out) >= max_rows:
            break
        cells: Dict[int, Any] = {}
        max_col = -1
        for c in row_el.findall("x:c", ns):
            col = _col_to_idx(c.attrib.get("r", "A1"))
            max_col = max(max_col, col)
            t = c.attrib.get("t", "")
            if t == "inlineStr":
                parts = [(x.text or "") for x in c.findall(".//x:t", ns)]
                value: Any = "".join(parts)
            else:
                v = c.find("x:v", ns)
                raw = "" if v is None or v.text is None else v.text
                if t == "s":
                    idx = int(raw) if str(raw).isdigit() else -1
                    value = shared[idx] if 0 <= idx < len(shared) else ""
                else:
                    value = raw
            cells[col] = value
        row = ["" for _ in range(max_col + 1)] if max_col >= 0 else []
        for idx, val in cells.items():
            if 0 <= idx < len(row):
                row[idx] = val
        out.append(row)
    return out


def _xlsx_workbook_sheet_columns(path: str) -> List[Tuple[str, List[str]]]:
    with zipfile.ZipFile(path, "r") as zf:
        shared = _xlsx_shared_strings(zf)
        out: List[Tuple[str, List[str]]] = []
        for sheet_name, sheet_path in _xlsx_sheet_targets(zf):
            rows = _xlsx_rows_from_sheet(zf, shared, sheet_path, max_rows=120)
            if not rows:
                continue
            header, _ = _pick_header(rows, max_rows=1)
            if not header:
                continue
            normalized_columns = [_normalize_text(col) for col in header]
            out.append((sheet_name, normalized_columns))
        return out


def _xlsx_sheet_names(path: str) -> List[str]:
    with zipfile.ZipFile(path, "r") as zf:
        if "xl/workbook.xml" not in zf.namelist():
            return []
        wb = ET.fromstring(zf.read("xl/workbook.xml"))
        ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        out: List[str] = []
        for sheet in wb.findall("x:sheets/x:sheet", ns):
            name = str(sheet.attrib.get("name") or "").strip()
            if name:
                out.append(name)
        return out


def _excel_sheet_names(path: str) -> List[str]:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".xlsx":
        return _xlsx_sheet_names(path)
    if ext == ".xls" and pd is not None:
        workbook = pd.ExcelFile(path)
        return [str(name).strip() for name in list(workbook.sheet_names or []) if str(name).strip()]
    return []


def _workbook_sheet_with_required_columns(path: str, required_tokens: Iterable[str]) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext not in EXCEL_EXTENSIONS:
        return ""

    if ext == ".xlsx":
        try:
            for sheet_name, normalized_columns in _xlsx_workbook_sheet_columns(path):
                if _column_hint_present(normalized_columns, required_tokens):
                    return str(sheet_name)
        except Exception:
            pass

    if pd is not None:
        try:
            workbook = pd.ExcelFile(path)
            for sheet_name in list(workbook.sheet_names or []):
                frame = workbook.parse(sheet_name=sheet_name, nrows=0)
                normalized_columns = [_normalize_text(col) for col in list(frame.columns)]
                if _column_hint_present(normalized_columns, required_tokens):
                    return str(sheet_name)
        except Exception:
            pass

    try:
        columns, _ = _read_table(path, max_rows=3)
        normalized_columns = [_normalize_text(col) for col in columns]
        if _column_hint_present(normalized_columns, required_tokens):
            return "sheet1"
    except Exception:
        return ""
    return ""


def _table_columns(path: str) -> List[str]:
    cols, _ = _read_table(path, max_rows=3)
    return [_normalize_text(col) for col in cols]


def _find_ads_sheet_name(sheet_names: List[str]) -> str:
    normalized_tokens = tuple(_normalize_text(token) for token in ADS_SHEET_KEYWORDS)
    for raw in sheet_names:
        norm = _normalize_text(raw)
        if any(token and token in norm for token in normalized_tokens):
            return str(raw)
    return ""


def _xlsx_sheet_path(zf: zipfile.ZipFile) -> str:
    if "xl/worksheets/sheet1.xml" in zf.namelist():
        # Keep old fast path for common single-sheet workbooks.
        # Specific sheet selection is handled below when workbook metadata is available.
        pass
    wb = ET.fromstring(zf.read("xl/workbook.xml"))
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rid_attr = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    preferred_tokens = ("статистика", "statistics", "statistic")
    preferred_rid = ""
    first_rid = ""
    first_target = ""

    rels_path = "xl/_rels/workbook.xml.rels"
    rel_map: Dict[str, str] = {}
    if rels_path in zf.namelist():
        rels = ET.fromstring(zf.read(rels_path))
        rns = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
        for rel in rels.findall("r:Relationship", rns):
            rel_id = str(rel.attrib.get("Id") or "")
            target_raw = str(rel.attrib.get("Target") or "")
            if not rel_id or not target_raw:
                continue
            if target_raw.startswith("/"):
                target = target_raw.lstrip("/")
            elif target_raw.startswith("xl/"):
                target = target_raw
            else:
                target = f"xl/{target_raw}"
            rel_map[rel_id] = target

    first = wb.find("x:sheets/x:sheet", ns)
    if first is None:
        raise RuntimeError("No sheets in workbook")

    for sheet in wb.findall("x:sheets/x:sheet", ns):
        rid = str(sheet.attrib.get(rid_attr) or "")
        if not rid:
            continue
        name = _normalize_text(str(sheet.attrib.get("name") or ""))
        if not first_rid:
            first_rid = rid
            first_target = rel_map.get(rid, "")
        if any(token in name for token in preferred_tokens):
            preferred_rid = rid
            break

    if preferred_rid and preferred_rid in rel_map:
        return rel_map[preferred_rid]
    if first_rid and first_rid in rel_map:
        return rel_map[first_rid]
    if first_target:
        return first_target
    if "xl/worksheets/sheet1.xml" in zf.namelist():
        return "xl/worksheets/sheet1.xml"

    candidates = sorted([n for n in zf.namelist() if n.startswith("xl/worksheets/") and n.endswith(".xml")])
    if not candidates:
        raise RuntimeError("No worksheet xml found")
    return candidates[0]


def _xlsx_rows(path: str) -> List[List[Any]]:
    with zipfile.ZipFile(path, "r") as zf:
        shared = _xlsx_shared_strings(zf)
        sheet = _xlsx_sheet_path(zf)
        root = ET.fromstring(zf.read(sheet))
        ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        data = root.find("x:sheetData", ns)
        if data is None:
            return []
        out: List[List[Any]] = []
        for row_el in data.findall("x:row", ns):
            cells: Dict[int, Any] = {}
            max_col = -1
            for c in row_el.findall("x:c", ns):
                col = _col_to_idx(c.attrib.get("r", "A1"))
                max_col = max(max_col, col)
                t = c.attrib.get("t", "")
                if t == "inlineStr":
                    parts = [(x.text or "") for x in c.findall(".//x:t", ns)]
                    value: Any = "".join(parts)
                else:
                    v = c.find("x:v", ns)
                    raw = "" if v is None or v.text is None else v.text
                    if t == "s":
                        idx = int(raw) if str(raw).isdigit() else -1
                        value = shared[idx] if 0 <= idx < len(shared) else ""
                    else:
                        value = raw
                cells[col] = value
            row = ["" for _ in range(max_col + 1)] if max_col >= 0 else []
            for idx, val in cells.items():
                if 0 <= idx < len(row):
                    row[idx] = val
            out.append(row)
        return out


def _pick_header(rows: List[List[Any]], max_rows: int | None = None) -> Tuple[List[str], List[Dict[str, Any]]]:
    if not rows:
        return [], []
    token_set = set()
    for key, vals in FIELD_SYNONYMS.items():
        token_set.add(_normalize_text(key))
        token_set.update(_normalize_text(v) for v in vals)

    best_idx = 0
    best_score = -1
    for i, row in enumerate(rows[:30]):
        vals = [_normalize_text(str(x)) for x in row if str(x).strip()]
        if len(vals) < 2:
            continue
        score = len(vals) + 10 * sum(1 for x in vals if x in token_set)
        if score > best_score:
            best_score = score
            best_idx = i

    header = _dedupe_columns([str(x).strip() or f"col_{j+1}" for j, x in enumerate(rows[best_idx])])
    records: List[Dict[str, Any]] = []
    for row in rows[best_idx + 1 :]:
        if max_rows is not None and len(records) >= max_rows:
            break
        if not any(str(x).strip() for x in row):
            continue
        item: Dict[str, Any] = {}
        for i in range(max(len(header), len(row))):
            col = header[i] if i < len(header) else f"col_{i+1}"
            item[col] = row[i] if i < len(row) else None
        records.append(item)
    return header, records


def _read_xlsx_table(path: str, max_rows: int | None = None) -> Tuple[List[str], List[Dict[str, Any]]]:
    rows = _xlsx_rows(path)
    header, records = _pick_header(rows, max_rows=max_rows)
    if header:
        return header, records
    raise RuntimeError("XLSX parse failed")


def _read_xls_table(path: str, max_rows: int | None = None) -> Tuple[List[str], List[Dict[str, Any]]]:
    if pd is None:
        raise RuntimeError("No reader for XLS (pandas is not available)")
    frame = pd.read_excel(path, nrows=max_rows)
    return _dedupe_columns([str(c) for c in list(frame.columns)]), frame.to_dict(orient="records")


def _read_table(path: str, max_rows: int | None = None) -> Tuple[List[str], List[Dict[str, Any]]]:
    ext = os.path.splitext(path)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported extension: {ext}")
    if ext == ".csv":
        return _read_csv_table(path, max_rows=max_rows)
    if ext == ".xlsx":
        return _read_xlsx_table(path, max_rows=max_rows)
    return _read_xls_table(path, max_rows=max_rows)


def _match_supplier_goods_column(columns: List[str], variants: Tuple[str, ...]) -> str:
    normalized_variants = {_normalize_text(item) for item in variants if str(item).strip()}
    if not normalized_variants:
        return ""

    for col in columns:
        if col in normalized_variants:
            return col
    for col in columns:
        for variant in normalized_variants:
            if variant and (variant in col or col in variant):
                return col
    return ""


def _is_confirmed_supplier_count_column(column_name: str, reliable_hints: Tuple[str, ...]) -> bool:
    normalized = _normalize_text(column_name)
    if not normalized:
        return False
    for hint in reliable_hints:
        token = _normalize_text(hint)
        if token and (normalized == token or token in normalized):
            return True
    return False


def _is_summary_row(row: Dict[str, Any]) -> bool:
    for value in row.values():
        text = str(value or "").strip()
        if not text:
            continue
        if _as_float(text) is not None:
            continue
        token = _normalize_text(text)
        if token in {"итого", "итог", "всего", "total", "grand_total"} or token.startswith("итого_"):
            return True
    return False


def _extract_supplier_goods_daily_kpi(path: str) -> Dict[str, Any]:
    cols, recs = _read_table(path)
    if not cols or not recs:
        return {}

    normalized_columns, normalized_rows = _normalize_records(cols, recs)
    column_map: Dict[str, str] = {}
    for field, variants in _SUPPLIER_GOODS_DAILY_FIELD_SYNONYMS.items():
        matched = _match_supplier_goods_column(normalized_columns, variants)
        if not matched:
            return {}
        column_map[field] = matched

    totals = {
        "orders_count": 0.0,
        "orders_amount": 0.0,
        "buyouts_count": 0.0,
        "buyouts_amount": 0.0,
    }
    used_rows = 0
    for row in normalized_rows:
        if not isinstance(row, dict):
            continue
        if _is_summary_row(row):
            continue

        row_has_numeric = False
        row_values: Dict[str, float] = {}
        for field, col in column_map.items():
            number = _as_float(row.get(col))
            if number is None:
                number = 0.0
            else:
                row_has_numeric = True
            row_values[field] = float(number)
        if not row_has_numeric:
            continue

        used_rows += 1
        for field in totals:
            totals[field] += float(row_values.get(field, 0.0))

    if used_rows <= 0:
        return {}

    orders_count_col = str(column_map.get("orders_count") or "")
    buyouts_count_col = str(column_map.get("buyouts_count") or "")
    orders_count_confirmed = _is_confirmed_supplier_count_column(
        orders_count_col,
        _SUPPLIER_GOODS_CONFIRMED_ORDERS_COUNT_HINTS,
    )
    buyouts_count_confirmed = _is_confirmed_supplier_count_column(
        buyouts_count_col,
        _SUPPLIER_GOODS_CONFIRMED_BUYOUTS_COUNT_HINTS,
    )

    return {
        "source_file": os.path.basename(path),
        "source_path": path,
        "rows_used": used_rows,
        "matched_columns": column_map,
        "orders_count": int(round(totals["orders_count"])),
        "orders_amount": round(totals["orders_amount"], 2),
        "buyouts_count": int(round(totals["buyouts_count"])),
        "buyouts_amount": round(totals["buyouts_amount"], 2),
        "orders_count_confirmed": bool(orders_count_confirmed),
        "buyouts_count_confirmed": bool(buyouts_count_confirmed),
        "amounts_confirmed": True,
        "kpi_confirmed": bool(orders_count_confirmed and buyouts_count_confirmed),
    }


def load_supplier_goods_daily_kpi(input_dir: str) -> Dict[str, Any]:
    if not os.path.isdir(input_dir):
        return {
            "found": False,
            "input_files_detected": 0,
            "supplier_goods_candidates": [],
            "detection_reason": "",
        }

    supplier_candidates: List[Dict[str, Any]] = []
    input_files_detected = 0
    candidates: List[Dict[str, Any]] = []
    for name in sorted(os.listdir(input_dir)):
        path = os.path.join(input_dir, name)
        if not os.path.isfile(path):
            continue
        if os.path.splitext(name)[1].lower() not in ALLOWED_EXTENSIONS:
            continue
        input_files_detected += 1

        file_name_norm = _normalize_text(name)
        supplier_name_hint = _name_hint_token(file_name_norm, SUPPLIER_GOODS_NAME_KEYWORDS)
        supplier_sheet_hint = _workbook_sheet_with_required_columns(path, SUPPLIER_GOODS_REQUIRED_COLUMN_HINTS)
        supplier_financial_sheet_hint = _workbook_sheet_with_required_columns(path, SUPPLIER_GOODS_FINANCIAL_COLUMN_HINTS)
        candidate_reasons: List[str] = []
        if supplier_name_hint:
            candidate_reasons.append(f"name:{supplier_name_hint}")
        if supplier_sheet_hint:
            candidate_reasons.append(f"workbook_columns:{supplier_sheet_hint}")
        if supplier_financial_sheet_hint:
            candidate_reasons.append(f"financial_columns:{supplier_financial_sheet_hint}")
        if candidate_reasons:
            supplier_candidates.append(
                {
                    "file": name,
                    "reason": ", ".join(candidate_reasons),
                }
            )

        try:
            extracted = _extract_supplier_goods_daily_kpi(path)
        except Exception:
            extracted = {}

        if not extracted and supplier_financial_sheet_hint:
            financial_columns_detected: List[str] = []
            try:
                financial_columns_detected = _column_hints_detected(_table_columns(path), SUPPLIER_GOODS_FINANCIAL_COLUMN_HINTS)
            except Exception:
                financial_columns_detected = []
            extracted = {
                "source_file": os.path.basename(path),
                "source_path": path,
                "rows_used": 0,
                "matched_columns": {},
                "orders_count": 0,
                "orders_amount": 0.0,
                "buyouts_count": 0,
                "buyouts_amount": 0.0,
                "kpi_confirmed": False,
                "orders_count_confirmed": False,
                "buyouts_count_confirmed": False,
                "amounts_confirmed": False,
                "financial_columns_detected": financial_columns_detected,
            }
        if not extracted:
            continue

        score = 0
        for token in _SUPPLIER_GOODS_FILE_TOKENS:
            if _normalize_text(token) in file_name_norm:
                score += 1
        if supplier_name_hint:
            score += 3
        if supplier_sheet_hint:
            score += 5
        if supplier_financial_sheet_hint:
            score += 4
        extracted["match_score"] = score
        extracted["detection_reason"] = ", ".join(candidate_reasons) if candidate_reasons else "field_synonyms"
        if "kpi_confirmed" not in extracted:
            extracted["kpi_confirmed"] = True
        if "orders_count_confirmed" not in extracted:
            extracted["orders_count_confirmed"] = False
        if "buyouts_count_confirmed" not in extracted:
            extracted["buyouts_count_confirmed"] = False
        if "amounts_confirmed" not in extracted:
            extracted["amounts_confirmed"] = bool(extracted.get("kpi_confirmed", False))
        candidates.append(extracted)

    if not candidates:
        return {
            "found": False,
            "input_files_detected": int(input_files_detected),
            "supplier_goods_candidates": supplier_candidates,
            "detection_reason": "",
        }

    candidates.sort(
        key=lambda item: (
            int(item.get("match_score", 0) or 0),
            int(item.get("rows_used", 0) or 0),
            int(os.path.getmtime(str(item.get("source_path") or "")) if str(item.get("source_path") or "") else 0),
        ),
        reverse=True,
    )
    best = dict(candidates[0])
    best["found"] = True
    best["candidates_found"] = len(candidates)
    best["input_files_detected"] = int(input_files_detected)
    best["supplier_goods_candidates"] = supplier_candidates
    best["detection_reason"] = str(best.get("detection_reason") or "")
    best["kpi_confirmed"] = bool(best.get("kpi_confirmed", True))
    best["orders_count_confirmed"] = bool(best.get("orders_count_confirmed", False))
    best["buyouts_count_confirmed"] = bool(best.get("buyouts_count_confirmed", False))
    best["amounts_confirmed"] = bool(best.get("amounts_confirmed", best.get("kpi_confirmed", False)))
    return best


def _canonical_columns(columns: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    ncols = [_normalize_text(c) for c in columns]
    for key, syns in FIELD_SYNONYMS.items():
        variants = {_normalize_text(x) for x in syns}
        matched = None

        # exact match first
        for col in ncols:
            if not col:
                continue
            if col == key or col in variants:
                matched = col
                break

        # then relaxed "contains" matching for WB long headers
        if matched is None:
            for col in ncols:
                if not col:
                    continue
                if col == key or key in col:
                    matched = col
                    break
                if any(v and (v in col or (col and col in v)) for v in variants):
                    matched = col
                    break

        if matched is not None:
            out[key] = matched
    return out


def _extract_stock_by_warehouse_map(
    row: Dict[str, Any],
    normalized_columns: List[str],
    ignored_columns: set[str],
) -> Dict[str, float]:
    stock_by_warehouse: Dict[str, float] = {}
    for col in normalized_columns:
        if not col or col in ignored_columns:
            continue
        if col in _STOCK_COLUMN_BLACKLIST:
            continue
        if any(token in col for token in ("в_пути", "возврат", "находится_на_складах")):
            continue

        value = _as_float(row.get(col))
        if value is None or value <= 0:
            continue
        stock_by_warehouse[col] = float(value)
    return stock_by_warehouse


def _pick_type(scores: Dict[str, int]) -> str | None:
    ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    if not ordered or ordered[0][1] <= 0:
        return None
    if len(ordered) > 1 and ordered[0][1] == ordered[1][1]:
        return None
    return ordered[0][0]


def _is_ads_campaign_total_row(row: Dict[str, Any]) -> bool:
    if not isinstance(row, dict):
        return False
    for value in row.values():
        raw = str(value or "").strip().lower()
        if "всего по кампании" in raw or "итого по кампании" in raw or "campaign total" in raw:
            return True
        token = _normalize_text(raw)
        if not token:
            continue
        if "всего_по_кампании" in token or "итого_по_кампании" in token:
            return True
    return False


def _detect_report_type(path: str) -> Dict[str, Any]:
    name = os.path.basename(path)
    norm_name = _normalize_text(name)
    ext = os.path.splitext(name)[1].lower()
    ads_name_hint_token = _name_hint_token(norm_name, ADS_REPORT_NAME_KEYWORDS)
    ads_name_hint = bool(ads_name_hint_token)
    supplier_name_hint_token = _name_hint_token(norm_name, SUPPLIER_GOODS_NAME_KEYWORDS)
    name_scores = {"sales": 0, "ads": 0, "stocks": 0}
    for t, words in REPORT_NAME_KEYWORDS.items():
        for w in words:
            if _normalize_text(w) in norm_name:
                name_scores[t] += 1
    if ads_name_hint:
        name_scores["ads"] += 3
    if ext in EXCEL_EXTENSIONS and norm_name.startswith(_normalize_text("статистика")):
        name_scores["ads"] += 1
    by_name = _pick_type(name_scores)

    col_scores = {"sales": 0, "ads": 0, "stocks": 0}
    by_cols = None
    sheet_scores = {"sales": 0, "ads": 0, "stocks": 0}
    by_sheet = None
    sheet_names: List[str] = []
    ads_sheet_found = ""
    supplier_goods_sheet_found = ""
    ads_spend_column_sheet = ""
    ads_spend_column_found = False
    read_error = None
    columns: List[str] = []

    if ext in EXCEL_EXTENSIONS:
        try:
            sheet_names = _excel_sheet_names(path)
            ads_sheet_found = _find_ads_sheet_name(sheet_names)
            if ads_sheet_found:
                sheet_scores["ads"] = 10
                by_sheet = "ads"
            supplier_goods_sheet_found = _workbook_sheet_with_required_columns(path, SUPPLIER_GOODS_REQUIRED_COLUMN_HINTS)
            ads_spend_column_sheet = _workbook_sheet_with_required_columns(path, ("Затраты, RUB",))
            ads_spend_column_found = bool(ads_spend_column_sheet)
        except Exception:
            sheet_names = []
            ads_sheet_found = ""
            supplier_goods_sheet_found = ""
            ads_spend_column_sheet = ""
            ads_spend_column_found = False

    try:
        columns, _ = _read_table(path, max_rows=25)
        canon = _canonical_columns(columns)
        normalized_columns = [_normalize_text(col) for col in columns]
        col_scores["sales"] = sum(1 for k in ["revenue", "profit", "orders", "buys", "sales_count", "margin", "margin_pct"] if k in canon)
        col_scores["ads"] = sum(1 for k in ["ads_spend", "orders", "revenue", "impressions", "clicks", "ctr", "cpc", "cpo", "conversion_type", "roi", "ddr"] if k in canon)
        if _column_hint_present(normalized_columns, (ADS_REQUIRED_COLUMN_HINT,)):
            ads_spend_column_found = True
            if not ads_spend_column_sheet:
                ads_spend_column_sheet = "sheet1"
            col_scores["ads"] += 8
        col_scores["stocks"] = sum(2 for k in ["stock"] if k in canon)
        if "sku" in canon:
            col_scores["sales"] += 1
            col_scores["ads"] += 1
            col_scores["stocks"] += 1
        by_cols = _pick_type(col_scores)
    except Exception as e:
        read_error = str(e)

    chosen = by_name
    source = "name"
    if ads_name_hint:
        chosen = "ads"
        source = "ads_name_hint"
    elif ads_spend_column_found:
        chosen = "ads"
        source = "ads_spend_column"
    elif by_sheet == "ads":
        if by_name and by_name != "ads":
            source = "sheet_overrode_name"
        elif by_name == "ads":
            source = "name+sheet"
        else:
            source = "sheet"
        chosen = "ads"
    elif by_cols and (not chosen or col_scores.get(by_cols, 0) > name_scores.get(chosen, 0)):
        chosen = by_cols
        source = "columns" if not by_name else "columns_overrode_name"

    supplier_goods_candidate_reasons: List[str] = []
    if supplier_name_hint_token:
        supplier_goods_candidate_reasons.append(f"name:{supplier_name_hint_token}")
    if supplier_goods_sheet_found:
        supplier_goods_candidate_reasons.append(f"workbook_columns:{supplier_goods_sheet_found}")
    supplier_goods_candidate = bool(supplier_goods_candidate_reasons)

    ads_candidate_reasons: List[str] = []
    if ads_name_hint_token:
        ads_candidate_reasons.append(f"name:{ads_name_hint_token}")
    if ads_sheet_found:
        ads_candidate_reasons.append(f"sheet:{ads_sheet_found}")
    if ads_spend_column_found:
        ads_candidate_reasons.append(f"workbook_column:Затраты, RUB@{ads_spend_column_sheet or 'sheet1'}")
    ads_candidate = bool(ads_candidate_reasons)

    detection_reason = source if chosen else "unknown"
    if source == "ads_name_hint":
        detection_reason = f"ads_by_name:{ads_name_hint_token}"
    elif source == "ads_spend_column":
        detection_reason = f"ads_by_workbook_column:{ads_spend_column_sheet or 'sheet1'}"
    elif source in {"sheet", "name+sheet", "sheet_overrode_name"} and ads_sheet_found:
        detection_reason = f"{source}:{ads_sheet_found}"

    return {
        "path": path,
        "file": name,
        "type": chosen,
        "source": source if chosen else "unknown",
        "detection_reason": detection_reason,
        "name_scores": name_scores,
        "sheet_scores": sheet_scores,
        "column_scores": col_scores,
        "columns": columns,
        "sheet_names": sheet_names,
        "ads_sheet_found": ads_sheet_found,
        "supplier_goods_sheet_found": supplier_goods_sheet_found,
        "supplier_goods_candidate": supplier_goods_candidate,
        "supplier_goods_reason": ", ".join(supplier_goods_candidate_reasons),
        "ads_candidate": ads_candidate,
        "ads_candidate_reason": ", ".join(ads_candidate_reasons),
        "ads_spend_column_found": ads_spend_column_found,
        "ads_spend_column_sheet": ads_spend_column_sheet,
        "ads_name_hint": ads_name_hint,
        "read_error": read_error,
    }


def _discover_files(input_dir: str) -> Tuple[Dict[str, List[str]], List[Dict[str, Any]]]:
    files = {"sales": [], "ads": [], "stocks": [], "unknown": []}
    details: List[Dict[str, Any]] = []
    if not os.path.isdir(input_dir):
        return files, details
    for name in sorted(os.listdir(input_dir)):
        path = os.path.join(input_dir, name)
        if not os.path.isfile(path):
            continue
        if os.path.splitext(name)[1].lower() not in ALLOWED_EXTENSIONS:
            continue
        detail = _detect_report_type(path)
        details.append(detail)
        t = detail.get("type")
        if t in ("sales", "ads", "stocks"):
            files[t].append(path)
        else:
            files["unknown"].append(path)
    return files, details


def discover_input_files(input_dir: str) -> Dict[str, List[str]]:
    files, _ = _discover_files(input_dir)
    return files


def _rows_from_table(
    columns: List[str], records: List[Dict[str, Any]], report_type: str
) -> Tuple[List[Dict[str, Any]], List[str], Dict[str, str]]:
    ncols, nrows = _normalize_records(columns, records)
    canon = _canonical_columns(ncols)
    if report_type == "sales":
        required, useful = ["sku"], [
            "revenue",
            "gross_revenue",
            "wb_realized_revenue",
            "seller_payout",
            "profit",
            "orders",
            "buys",
            "sales_count",
            "margin",
            "margin_pct",
            "cost_price",
            "wb_commission",
            "logistics",
            "penalties",
            "storage",
            "deductions",
            "acquiring",
            "pvz_service",
            "loyalty_program",
            "loyalty_points_withheld",
            "other_adjustments",
        ]
        string_fields = ["warehouse", "seller_sku"]
        # Prefer stable SKU identifiers for weekly detailed report.
        for preferred in ("код_номенклатуры", "артикул_поставщика", "предмет"):
            if preferred in ncols:
                canon["sku"] = preferred
                break
        for preferred in ("артикул_поставщика", "артикул_продавца", "артикул"):
            if preferred in ncols:
                canon["seller_sku"] = preferred
                break
        for preferred in ("склад", "наименование_склада", "warehouse", "наименование_офиса_доставки", "офис_доставки"):
            if preferred in ncols:
                canon["warehouse"] = preferred
                break
    elif report_type == "ads":
        required, useful = ["sku"], [
            "ads_spend",
            "impressions",
            "clicks",
            "add_to_cart",
            "ctr",
            "cpc",
            "orders",
            "buyouts",
            "revenue",
            "acos",
            "romi",
            "roi",
            "ddr",
            "cpo",
            "avg_position",
        ]
        string_fields = ["conversion_type", "query"]
    else:
        required, useful = ["sku", "stock"], ["stock"]
        string_fields = ["seller_sku"]
        for preferred in (
            "код_номенклатуры",
            "nm_id",
            "nmid",
            "артикул_wb",
            "артикул_продавца",
            "артикул_поставщика",
            "артикул",
            "предмет",
        ):
            if preferred in ncols:
                canon["sku"] = preferred
                break
        for preferred in ("артикул_продавца", "артикул_поставщика", "артикул"):
            if preferred in ncols:
                canon["seller_sku"] = preferred
                break
        for preferred in ("всего_находится_на_складах", "остаток", "остатки", "на_складе", "в_пути_до_получателей"):
            if preferred in ncols:
                canon["stock"] = preferred
                break

    if "sku" not in canon:
        for fallback in ("номенклатура", "артикул", "наименование", "товар", "предмет"):
            token = _normalize_text(fallback)
            if token in ncols:
                canon["sku"] = token
                break

    missing = [k for k in required if k not in canon]
    matched_columns = {field: canon[field] for field in useful + string_fields if field in canon}
    if "sku" in canon:
        matched_columns["sku"] = canon["sku"]
    if report_type == "ads":
        ads_metric_fields = ("ads_spend", "impressions", "clicks", "ctr", "cpc", "cpo", "orders", "revenue")
        if not any(field in canon for field in ads_metric_fields):
            missing = list(dict.fromkeys(missing + ["ads_metric_columns"]))
        if missing:
            return [], missing, matched_columns

    rows: List[Dict[str, Any]] = []
    for r in nrows:
        if report_type == "ads" and _is_ads_campaign_total_row(r):
            total_item: Dict[str, Any] = {"_is_campaign_total": True}
            for field in useful:
                col = canon.get(field)
                if not col:
                    continue
                val = _as_float(r.get(col))
                if val is not None:
                    total_item[field] = val
            conv_col = canon.get("conversion_type")
            if conv_col:
                conversion_type = str(r.get(conv_col, "")).strip()
                if conversion_type and conversion_type.lower() != "nan":
                    total_item["conversion_type"] = conversion_type
            rows.append(total_item)
            continue

        sku_col = canon.get("sku")
        if not sku_col:
            continue
        sku = str(r.get(sku_col, "")).strip()
        if not sku or sku.lower() == "nan":
            continue
        item: Dict[str, Any] = {"sku": sku, "_sku_source_field": sku_col}
        for field in useful:
            col = canon.get(field)
            if not col:
                continue
            val = _as_float(r.get(col))
            if val is not None:
                item[field] = val
        for field in string_fields:
            col = canon.get(field)
            if not col:
                continue
            text = str(r.get(col, "")).strip()
            if text and text.lower() != "nan":
                item[field] = text

        if report_type == "sales":
            qty = item.get("sales_count")
            if qty is None:
                qty = item.get("buys")
            if qty is None:
                qty = item.get("orders")
            if qty is not None:
                item["sales_count"] = float(qty)
                if item.get("buys") is None:
                    item["buys"] = float(qty)
            if item.get("orders") is None:
                order_qty = item.get("sales_count")
                if order_qty is None:
                    order_qty = item.get("buys")
                if order_qty is not None:
                    item["orders"] = float(order_qty)

            gross_revenue = item.get("gross_revenue")
            wb_realized_revenue = item.get("wb_realized_revenue")
            seller_payout = item.get("seller_payout")
            # Backward compatibility: old "revenue" column is treated as seller payout when dedicated field is absent.
            if seller_payout is None and item.get("revenue") is not None:
                seller_payout = float(item.get("revenue") or 0.0)
                item["seller_payout"] = seller_payout
            if gross_revenue is None and item.get("revenue") is not None:
                gross_revenue = float(item.get("revenue") or 0.0)
                item["gross_revenue"] = gross_revenue
            revenue_base = None
            for candidate in (seller_payout, wb_realized_revenue, gross_revenue, item.get("revenue")):
                if candidate is None:
                    continue
                revenue_base = float(candidate)
                break
            if revenue_base is not None:
                item["revenue"] = float(revenue_base)

            if revenue_base is not None and item.get("profit") is None:
                cost_price = float(item.get("cost_price") or 0.0)
                wb_commission = float(item.get("wb_commission") or 0.0)
                acquiring = float(item.get("acquiring") or 0.0)
                pvz_service = float(item.get("pvz_service") or 0.0)
                logistics = float(item.get("logistics") or 0.0)
                penalties = float(item.get("penalties") or 0.0)
                storage = float(item.get("storage") or 0.0)
                deductions = float(item.get("deductions") or 0.0)
                loyalty_program = float(item.get("loyalty_program") or 0.0)
                loyalty_points_withheld = float(item.get("loyalty_points_withheld") or 0.0)
                other_adjustments = float(item.get("other_adjustments") or 0.0)
                item["profit"] = (
                    float(revenue_base)
                    - cost_price
                    - wb_commission
                    - acquiring
                    - pvz_service
                    - logistics
                    - penalties
                    - storage
                    - deductions
                    - loyalty_program
                    - loyalty_points_withheld
                    - other_adjustments
                )
        elif report_type == "stocks":
            ignored_columns = set(canon.values())
            ignored_columns.add(canon.get("seller_sku", ""))
            stock_map = _extract_stock_by_warehouse_map(r, ncols, ignored_columns)
            if stock_map:
                item["stock_by_warehouse"] = stock_map

        rows.append(item)
    return rows, missing, matched_columns


def _load_report_with_diagnostics(
    path: str, report_type: str
) -> Tuple[List[Dict[str, Any]], List[str], Dict[str, str], Dict[str, Any]]:
    cols, recs = _read_table(path)
    if not cols and not recs:
        return [], ["empty_table"], {}, {"rows_raw": 0, "rows_usable": 0, "columns_detected": []}

    rows, missing, matched_columns = _rows_from_table(cols, recs, report_type)
    rows_raw = len(recs)
    if report_type == "ads":
        rows_usable = sum(
            1
            for row in rows
            if isinstance(row, dict) and not bool(row.get("_is_campaign_total", False))
        )
    else:
        rows_usable = len(rows)
    diagnostics = {
        "rows_raw": rows_raw,
        "rows_usable": int(rows_usable),
        "columns_detected": sorted(str(key) for key in matched_columns.keys()),
    }
    return rows, missing, matched_columns, diagnostics


def _load_report(path: str, report_type: str) -> Tuple[List[Dict[str, Any]], List[str], Dict[str, str]]:
    rows, missing, matched_columns, _ = _load_report_with_diagnostics(path, report_type)
    return rows, missing, matched_columns


def load_sales_report(path: str) -> List[Dict[str, Any]]:
    rows, _, _ = _load_report(path, "sales")
    return rows


def load_ads_report(path: str) -> List[Dict[str, Any]]:
    rows, _, _ = _load_report(path, "ads")
    return rows


def load_stocks_report(path: str) -> List[Dict[str, Any]]:
    rows, _, _ = _load_report(path, "stocks")
    return rows


def load_local_reports(input_dir: str) -> Dict[str, Any]:
    discovered, details = _discover_files(input_dir)
    detail_by_path = {str(item.get("path")): item for item in details}
    warnings: List[Dict[str, Any]] = []
    sales_rows: List[Dict[str, Any]] = []
    ads_rows: List[Dict[str, Any]] = []
    stocks_rows: List[Dict[str, Any]] = []
    primary_sales_source = ""
    primary_sales_columns: Dict[str, str] = {}
    loaded_files: Dict[str, List[str]] = {"sales": [], "ads": [], "stocks": []}
    ads_columns_detected_set: set[str] = set()
    ads_sheet_found = ""
    ads_rows_raw = 0
    ads_rows_usable = 0
    ads_loader_issues: List[str] = []
    input_files_detected = len(details)
    supplier_goods_candidates: List[Dict[str, str]] = []
    ads_candidates: List[Dict[str, str]] = []
    detection_reason: Dict[str, str] = {}

    for item in details:
        file_name = str(item.get("file") or os.path.basename(str(item.get("path") or "")))
        if file_name:
            detection_reason[file_name] = str(item.get("detection_reason") or item.get("source") or "unknown")
        if bool(item.get("supplier_goods_candidate")):
            supplier_goods_candidates.append(
                {
                    "file": file_name,
                    "reason": str(item.get("supplier_goods_reason") or "candidate"),
                }
            )
        if bool(item.get("ads_candidate")):
            ads_candidates.append(
                {
                    "file": file_name,
                    "reason": str(item.get("ads_candidate_reason") or "candidate"),
                }
            )

    ads_detected_initial = list(discovered.get("ads", []))

    normalized_ads_name_tokens = tuple(_normalize_text(token) for token in ADS_FILE_NAME_KEYWORDS)

    def _is_ads_candidate(detail: Dict[str, Any]) -> bool:
        path = str(detail.get("path") or "")
        ext = os.path.splitext(path)[1].lower()
        if ext not in EXCEL_EXTENSIONS:
            return False
        if str(detail.get("type") or "") == "ads":
            return True
        if bool(detail.get("ads_candidate")):
            return True
        if bool(detail.get("ads_name_hint")):
            return True
        if str(detail.get("ads_sheet_found") or "").strip():
            return True
        if bool(detail.get("ads_spend_column_found")):
            return True
        norm_name = _normalize_text(str(detail.get("file") or ""))
        return any(token and token in norm_name for token in normalized_ads_name_tokens)

    ads_candidate_paths: List[str] = []
    for detail in details:
        if not _is_ads_candidate(detail):
            continue
        path = str(detail.get("path") or "")
        if path and path not in ads_candidate_paths:
            ads_candidate_paths.append(path)

    if not discovered.get("ads") and ads_candidate_paths:
        discovered["ads"] = list(ads_candidate_paths)
        discovered["unknown"] = [path for path in discovered.get("unknown", []) if path not in set(discovered["ads"])]

    total = len(discovered["sales"]) + len(discovered["ads"]) + len(discovered["stocks"]) + len(discovered["unknown"])
    warnings.append({"code": "input_files_found", "message": f"Input files found: total={total}, sales={len(discovered['sales'])}, ads={len(discovered['ads'])}, stocks={len(discovered['stocks'])}, unknown={len(discovered['unknown'])}"})

    if total == 0:
        warnings.append({"code": "input_files_missing", "message": f"No local input files found in {_input_hint_path(input_dir)}"})

    for d in details:
        file_name = str(d.get("file") or "")
        if d.get("type"):
            warnings.append({"code": "input_file_detected_type", "message": f"{file_name} => {d['type']} ({d.get('source','unknown')})"})
        else:
            warnings.append({"code": "input_file_unknown_type", "message": f"Unknown report type, skipped: {file_name}"})
            warnings.append({"code": "input_file_skipped", "message": f"Skipped {file_name}: report type is unknown"})
            if d.get("read_error"):
                warnings.append({"code": "input_file_read_error", "message": f"Cannot inspect {file_name}: {d['read_error']}"})

    if discovered.get("ads") and not ads_detected_initial:
        for path in discovered["ads"]:
            warnings.append(
                {
                    "code": "input_file_detected_type",
                    "message": f"{os.path.basename(path)} => ads (name_or_sheet_fallback)",
                }
            )

    def _select_primary_sales(paths: List[str]) -> str:
        if not paths:
            return ""
        scored: List[Tuple[int, str]] = []
        for path in paths:
            detail = detail_by_path.get(path, {})
            columns = detail.get("columns") or []
            canon = _canonical_columns(columns if isinstance(columns, list) else [])
            file_name = _normalize_text(os.path.basename(path))

            score = 0
            if "sku" in canon:
                score += 8
            if "revenue" in canon:
                score += 6
            if any(key in canon for key in ("sales_count", "buys", "orders")):
                score += 5
            if "profit" in canon:
                score += 3

            if "еженедель" in file_name or "детализирован" in file_name:
                score += 4
            if "воронка" in file_name and "sku" not in canon:
                score -= 6
            scored.append((score, path))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    def _read_many(paths: List[str], report_type: str, target: List[Dict[str, Any]], primary_only: str = "") -> Dict[str, str]:
        nonlocal ads_sheet_found
        nonlocal ads_rows_raw
        nonlocal ads_rows_usable
        matched: Dict[str, str] = {}
        for p in paths:
            name = os.path.basename(p)
            if primary_only and p != primary_only:
                warnings.append({"code": "input_file_skipped", "message": f"Skipped {name}: non-primary sales source"})
                continue
            try:
                rows, missing, matched_columns, load_diag = _load_report_with_diagnostics(p, report_type)
                if report_type == "ads":
                    ads_rows_raw += int(load_diag.get("rows_raw", 0) or 0)
                    ads_rows_usable += int(load_diag.get("rows_usable", 0) or 0)
                    detected_cols = load_diag.get("columns_detected", [])
                    if isinstance(detected_cols, list):
                        for item in detected_cols:
                            token = str(item).strip()
                            if token:
                                ads_columns_detected_set.add(token)
                    detail = detail_by_path.get(p, {})
                    sheet_name = str(detail.get("ads_sheet_found") or "").strip()
                    if sheet_name and not ads_sheet_found:
                        ads_sheet_found = sheet_name
                if rows:
                    target.extend(rows)
                    loaded_files.setdefault(report_type, []).append(name)
                    if report_type == "sales" and p == primary_only:
                        matched = matched_columns
                else:
                    warnings.append({"code": "input_file_skipped", "message": f"Skipped {name}: no usable rows for {report_type}"})
                    if report_type == "ads":
                        ads_loader_issues.append(f"{name}: no usable rows for ads")
                if missing:
                    warnings.append({"code": "required_columns_missing", "message": f"{report_type} report missing required columns {', '.join(missing)} in {name}"})
                    if report_type == "ads":
                        ads_loader_issues.append(f"{name}: missing columns {', '.join(missing)}")
            except Exception as e:
                warnings.append({"code": "input_file_read_error", "message": f"Cannot read {name}: {e}"})
                warnings.append({"code": "input_file_skipped", "message": f"Skipped {name}: read error"})
                if report_type == "ads":
                    ads_loader_issues.append(f"{name}: {e}")
        return matched

    if discovered["sales"]:
        primary_sales_source = _select_primary_sales(discovered["sales"])
        if primary_sales_source:
            warnings.append(
                {
                    "code": "primary_sales_source",
                    "message": f"Primary sales source: {os.path.basename(primary_sales_source)}",
                }
            )
            primary_sales_columns = _read_many(discovered["sales"], "sales", sales_rows, primary_only=primary_sales_source)
            orders_source_field = (
                primary_sales_columns.get("orders")
                or primary_sales_columns.get("sales_count")
                or primary_sales_columns.get("buys")
                or ""
            )
            recognized_order_rows = sum(1 for row in sales_rows if float(row.get("orders") or 0.0) > 0)
            extracted_orders_total = int(
                round(sum(float(row.get("orders") or row.get("sales_count") or row.get("buys") or 0.0) for row in sales_rows))
            )
            print(f"[orders] source_field={orders_source_field or 'not_detected'}")
            print(f"[orders] recognized_rows={recognized_order_rows}")
            print(f"[orders] total_orders={extracted_orders_total}")
            if "orders" not in primary_sales_columns and not orders_source_field:
                warnings.append(
                    {
                        "code": "orders_column_not_detected",
                        "message": "Orders column was not detected in primary sales source; totals.orders may remain 0.",
                    }
                )
            warnings.append(
                {
                    "code": "primary_sales_matched_columns",
                    "message": (
                        "Primary sales matched columns: "
                        f"sku={primary_sales_columns.get('sku','')}, "
                        f"revenue={primary_sales_columns.get('revenue','')}, "
                        f"profit={primary_sales_columns.get('profit','')}, "
                        f"orders={primary_sales_columns.get('orders') or primary_sales_columns.get('sales_count') or primary_sales_columns.get('buys','')}, "
                        f"buys={primary_sales_columns.get('buys') or primary_sales_columns.get('sales_count') or primary_sales_columns.get('orders','')}"
                    ),
                }
            )
    else:
        _read_many(discovered["sales"], "sales", sales_rows)

    _read_many(discovered["ads"], "ads", ads_rows)
    _read_many(discovered["stocks"], "stocks", stocks_rows)

    ads_campaign_totals = {"ads_spend": 0.0, "revenue": 0.0, "orders": 0.0, "impressions": 0.0, "clicks": 0.0}
    ads_campaign_total_rows = 0
    ads_sku_rows_count = 0
    for row in ads_rows:
        if not isinstance(row, dict):
            continue
        if bool(row.get("_is_campaign_total", False)):
            ads_campaign_total_rows += 1
            ads_campaign_totals["ads_spend"] += float(row.get("ads_spend") or 0.0)
            ads_campaign_totals["revenue"] += float(row.get("revenue") or 0.0)
            ads_campaign_totals["orders"] += float(row.get("orders") or 0.0)
            ads_campaign_totals["impressions"] += float(row.get("impressions") or 0.0)
            ads_campaign_totals["clicks"] += float(row.get("clicks") or 0.0)
            continue
        ads_sku_rows_count += 1

    ads_rows_usable = ads_sku_rows_count
    ads_detected_file = (
        os.path.basename(discovered["ads"][0])
        if discovered.get("ads")
        else (os.path.basename(ads_candidate_paths[0]) if ads_candidate_paths else "")
    )
    ads_source_file = loaded_files.get("ads", [])[0] if loaded_files.get("ads") else ads_detected_file
    ads_loaded_from_file = bool(ads_sku_rows_count > 0)
    ads_loader_error = "; ".join(list(dict.fromkeys(ads_loader_issues)))
    if ads_loaded_from_file:
        warnings.append(
            {
                "code": "ads_file_loaded",
                "message": f"Ads report loaded from file: {ads_source_file}",
            }
        )
    elif discovered.get("ads"):
        warnings.append(
            {
                "code": "ads_file_detected_but_not_parsed",
                "message": f"Ads file detected but not parsed: {ads_source_file or os.path.basename(discovered['ads'][0])}",
            }
        )

    if not discovered["sales"] or not sales_rows:
        warnings.append({"code": "sales_report_missing", "message": "No valid sales report found in input/."})
    if not discovered["ads"] or ads_sku_rows_count <= 0:
        warnings.append({"code": "ads_report_missing", "message": "No valid ads report found in input/."})
    if not discovered["stocks"] or not stocks_rows:
        warnings.append({"code": "stocks_report_missing", "message": "No valid stocks report found in input/."})

    return {
        "files": discovered,
        "sales_rows": sales_rows,
        "ads_rows": ads_rows,
        "stocks_rows": stocks_rows,
        "warnings": warnings,
        "debug": {
            "input_dir": input_dir,
            "input_files_detected": int(input_files_detected),
            "discovered": discovered,
            "details": details,
            "supplier_goods_candidates": supplier_goods_candidates,
            "ads_candidates": ads_candidates,
            "detection_reason": detection_reason,
            "primary_sales_source": primary_sales_source,
            "primary_sales_columns": primary_sales_columns,
            "ads_file_candidates_found": len(ads_candidate_paths),
            "ads_file_detected": bool(discovered.get("ads")),
            "ads_source_file": ads_source_file,
            "ads_sheet_found": ads_sheet_found,
            "ads_columns_detected": sorted(ads_columns_detected_set),
            "ads_rows_raw": int(ads_rows_raw),
            "ads_rows_usable": int(ads_rows_usable),
            "ads_loader_error": ads_loader_error,
            "ads_loaded_from_file": ads_loaded_from_file,
            "ads_sku_rows_count": ads_sku_rows_count,
            "ads_campaign_total_rows": ads_campaign_total_rows,
            "ads_campaign_totals": {
                "ads_spend": round(float(ads_campaign_totals["ads_spend"]), 2),
                "ads_revenue": round(float(ads_campaign_totals["revenue"]), 2),
                "ads_orders": int(round(float(ads_campaign_totals["orders"]))),
                "ads_impressions": int(round(float(ads_campaign_totals["impressions"]))),
                "ads_clicks": int(round(float(ads_campaign_totals["clicks"]))),
            },
            "loaded_rows": {"sales": len(sales_rows), "ads": len(ads_rows), "stocks": len(stocks_rows)},
        },
    }


def build_metrics_from_reports(sales_rows: List[Dict[str, Any]], ads_rows: List[Dict[str, Any]], stocks_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    def _row_profit_value(row: Dict[str, Any]) -> float:
        if row.get("profit") is not None:
            return float(row.get("profit") or 0.0)
        revenue_base = (
            float(row.get("seller_payout"))
            if row.get("seller_payout") is not None
            else (
                float(row.get("wb_realized_revenue"))
                if row.get("wb_realized_revenue") is not None
                else (
                    float(row.get("gross_revenue"))
                    if row.get("gross_revenue") is not None
                    else float(row.get("revenue") or 0.0)
                )
            )
        )
        return (
            revenue_base
            - float(row.get("cost_price") or 0.0)
            - float(row.get("wb_commission") or 0.0)
            - float(row.get("acquiring") or 0.0)
            - float(row.get("pvz_service") or 0.0)
            - float(row.get("logistics") or 0.0)
            - float(row.get("penalties") or 0.0)
            - float(row.get("storage") or 0.0)
            - float(row.get("deductions") or 0.0)
            - float(row.get("loyalty_program") or 0.0)
            - float(row.get("loyalty_points_withheld") or 0.0)
            - float(row.get("other_adjustments") or 0.0)
            - float(row.get("tax") or 0.0)
        )

    def _financial_status(
        invalid_rows: int,
        unassigned_present: bool,
        unassigned_profit: float,
        total_profit: float,
        zero_revenue_activity_count: int,
    ) -> tuple[str, str]:
        if invalid_rows <= 0 and not unassigned_present and zero_revenue_activity_count <= 0:
            return "ok", "high"
        high_impact = (
            invalid_rows >= 10
            or abs(unassigned_profit) >= max(200.0, abs(total_profit) * 0.5)
            or zero_revenue_activity_count >= 3
        )
        if high_impact:
            return "partial", "low"
        return "degraded", "medium"

    def _ads_conversion_bucket(value: Any) -> str:
        raw = str(value or "").strip().lower()
        if not raw:
            return "unknown"
        if "ассоц" in raw or "associated" in raw or "assoc" in raw:
            return "associated"
        return "direct"

    ads_campaign_total_rows = [row for row in ads_rows if isinstance(row, dict) and bool(row.get("_is_campaign_total", False))]
    ads_rows = [row for row in ads_rows if isinstance(row, dict) and not bool(row.get("_is_campaign_total", False))]
    ads_campaign_totals = {
        "ads_spend": 0.0,
        "ads_revenue": 0.0,
        "ads_orders": 0.0,
        "ads_impressions": 0.0,
        "ads_clicks": 0.0,
    }
    for row in ads_campaign_total_rows:
        ads_campaign_totals["ads_spend"] += float(row.get("ads_spend") or 0.0)
        ads_campaign_totals["ads_revenue"] += float(row.get("revenue") or 0.0)
        ads_campaign_totals["ads_orders"] += float(row.get("orders") or 0.0)
        ads_campaign_totals["ads_impressions"] += float(row.get("impressions") or 0.0)
        ads_campaign_totals["ads_clicks"] += float(row.get("clicks") or 0.0)

    ads_conversion_diag: Dict[str, Dict[str, float]] = {
        "direct": {"rows": 0.0, "ads_spend": 0.0, "ads_revenue": 0.0, "ads_orders": 0.0},
        "associated": {"rows": 0.0, "ads_spend": 0.0, "ads_revenue": 0.0, "ads_orders": 0.0},
        "unknown": {"rows": 0.0, "ads_spend": 0.0, "ads_revenue": 0.0, "ads_orders": 0.0},
    }
    for row in ads_rows:
        bucket_name = _ads_conversion_bucket(row.get("conversion_type"))
        bucket_diag = ads_conversion_diag[bucket_name]
        bucket_diag["rows"] += 1.0
        bucket_diag["ads_spend"] += float(row.get("ads_spend") or 0.0)
        bucket_diag["ads_revenue"] += float(row.get("revenue") or 0.0)
        bucket_diag["ads_orders"] += float(row.get("orders") or 0.0)

    direct_rows = int(round(float(ads_conversion_diag["direct"]["rows"])))
    associated_rows = int(round(float(ads_conversion_diag["associated"]["rows"])))
    if direct_rows > 0 and associated_rows > 0:
        ads_attribution_quality = "mixed_direct_and_associated"
    elif associated_rows > 0 and direct_rows <= 0:
        ads_attribution_quality = "associated_only"
    elif direct_rows > 0:
        ads_attribution_quality = "direct_only"
    else:
        ads_attribution_quality = "unknown"

    sales_split = split_assigned_vs_unassigned_rows(sales_rows, dataset_name="sales")
    ads_split = split_assigned_vs_unassigned_rows(ads_rows, dataset_name="ads")
    stocks_split = split_assigned_vs_unassigned_rows(stocks_rows, dataset_name="stocks")

    valid_sales_rows = sales_split["assigned"]
    valid_ads_rows = ads_split["assigned"]
    valid_stocks_rows = stocks_split["assigned"]
    invalid_sku_rows = len(sales_split["unassigned"]) + len(ads_split["unassigned"]) + len(stocks_split["unassigned"])
    sales_split_diagnostics = sales_split.get("diagnostics", {}) if isinstance(sales_split, dict) else {}
    ads_split_diagnostics = ads_split.get("diagnostics", {}) if isinstance(ads_split, dict) else {}
    stocks_split_diagnostics = stocks_split.get("diagnostics", {}) if isinstance(stocks_split, dict) else {}

    unassigned_costs = {
        "revenue": 0.0,
        "gross_revenue": 0.0,
        "wb_realized_revenue": 0.0,
        "seller_payout": 0.0,
        "profit": 0.0,
        "cost_price": 0.0,
        "wb_commission": 0.0,
        "acquiring": 0.0,
        "pvz_service": 0.0,
        "logistics": 0.0,
        "penalties": 0.0,
        "storage": 0.0,
        "deductions": 0.0,
        "loyalty_program": 0.0,
        "loyalty_points_withheld": 0.0,
        "other_adjustments": 0.0,
        "tax": 0.0,
        "ads_spend": 0.0,
        "rows": len(sales_split["unassigned"]),
    }
    for row in sales_split["unassigned"]:
        revenue = float(row.get("revenue") or 0.0)
        gross_revenue = float(row.get("gross_revenue") or 0.0)
        wb_realized_revenue = float(row.get("wb_realized_revenue") or 0.0)
        seller_payout = float(row.get("seller_payout") or revenue)
        cost_price = float(row.get("cost_price") or 0.0)
        wb_commission = float(row.get("wb_commission") or 0.0)
        acquiring = float(row.get("acquiring") or 0.0)
        pvz_service = float(row.get("pvz_service") or 0.0)
        logistics = float(row.get("logistics") or 0.0)
        penalties = float(row.get("penalties") or 0.0)
        storage = float(row.get("storage") or 0.0)
        deductions = float(row.get("deductions") or 0.0)
        loyalty_program = float(row.get("loyalty_program") or 0.0)
        loyalty_points_withheld = float(row.get("loyalty_points_withheld") or 0.0)
        other_adjustments = float(row.get("other_adjustments") or 0.0)
        tax = float(row.get("tax") or 0.0)
        row_profit = _row_profit_value(row)

        unassigned_costs["revenue"] += revenue
        unassigned_costs["gross_revenue"] += gross_revenue
        unassigned_costs["wb_realized_revenue"] += wb_realized_revenue
        unassigned_costs["seller_payout"] += seller_payout
        unassigned_costs["profit"] += row_profit
        unassigned_costs["cost_price"] += cost_price
        unassigned_costs["wb_commission"] += wb_commission
        unassigned_costs["acquiring"] += acquiring
        unassigned_costs["pvz_service"] += pvz_service
        unassigned_costs["logistics"] += logistics
        unassigned_costs["penalties"] += penalties
        unassigned_costs["storage"] += storage
        unassigned_costs["deductions"] += deductions
        unassigned_costs["loyalty_program"] += loyalty_program
        unassigned_costs["loyalty_points_withheld"] += loyalty_points_withheld
        unassigned_costs["other_adjustments"] += other_adjustments
        unassigned_costs["tax"] += tax

    for row in ads_split["unassigned"]:
        unassigned_costs["ads_spend"] += float(row.get("ads_spend") or 0.0)

    financial_debug: List[Dict[str, Any]] = []
    invalid_reason_counts: Dict[str, int] = {}
    for row in sales_split["unassigned"] + ads_split["unassigned"] + stocks_split["unassigned"]:
        if not isinstance(row, dict):
            continue
        reason = str(row.get("_sku_validation_reason") or "unknown")
        invalid_reason_counts[reason] = invalid_reason_counts.get(reason, 0) + 1
    for idx, row in enumerate(sales_split["assigned"] + sales_split["unassigned"]):
        if not isinstance(row, dict):
            continue
        is_valid = bool(row.get("_is_valid_sku", False))
        reason_invalid = None if is_valid else str(row.get("_sku_validation_reason") or "unknown")
        entry = {
            "raw_row_index": int(row.get("_raw_row_index", idx) or idx),
            "operation": str(row.get("_operation") or ""),
            "type": str(row.get("_operation_type") or ""),
            "name": str(row.get("_operation_name") or ""),
            "extracted_sku": str(row.get("sku") or ""),
            "is_valid_sku": is_valid,
            "reason_invalid": reason_invalid,
            "revenue_component": round(float(row.get("revenue") or 0.0), 2),
            "gross_revenue_component": round(float(row.get("gross_revenue") or 0.0), 2),
            "wb_realized_revenue_component": round(float(row.get("wb_realized_revenue") or 0.0), 2),
            "seller_payout_component": round(float(row.get("seller_payout") or row.get("revenue") or 0.0), 2),
            "cost_price_component": round(float(row.get("cost_price") or 0.0), 2),
            "wb_commission_component": round(float(row.get("wb_commission") or 0.0), 2),
            "acquiring_component": round(float(row.get("acquiring") or 0.0), 2),
            "pvz_service_component": round(float(row.get("pvz_service") or 0.0), 2),
            "logistics_component": round(float(row.get("logistics") or 0.0), 2),
            "storage_component": round(float(row.get("storage") or 0.0), 2),
            "deductions_component": round(float(row.get("deductions") or 0.0), 2),
            "loyalty_program_component": round(float(row.get("loyalty_program") or 0.0), 2),
            "loyalty_points_withheld_component": round(float(row.get("loyalty_points_withheld") or 0.0), 2),
            "other_adjustments_component": round(float(row.get("other_adjustments") or 0.0), 2),
            "tax_component": round(float(row.get("tax") or 0.0), 2),
            "assigned_to_sku": str(row.get("sku") or "") if is_valid else None,
            "unassigned": not is_valid,
            "source_dataset": str(row.get("_source_dataset") or ""),
            "sku_source_field": str(row.get("_sku_source_field") or ""),
        }
        financial_debug.append(entry)

    bucket: Dict[str, Dict[str, Any]] = {}

    def _sku(s: str) -> Dict[str, Any]:
        if s not in bucket:
            bucket[s] = {
                "sku": s,
                "revenue": 0.0,
                "gross_revenue": 0.0,
                "wb_realized_revenue": 0.0,
                "seller_payout": 0.0,
                "profit": 0.0,
                "orders": 0.0,
                "buys": 0.0,
                "sales_count": 0.0,
                "stock": 0.0,
                "ads_spend": 0.0,
                "impressions": 0.0,
                "clicks": 0.0,
                "ads_orders": 0.0,
                "ads_revenue": 0.0,
                "cost_price": 0.0,
                "wb_commission": 0.0,
                "acquiring": 0.0,
                "pvz_service": 0.0,
                "logistics": 0.0,
                "penalties": 0.0,
                "storage": 0.0,
                "deductions": 0.0,
                "loyalty_program": 0.0,
                "loyalty_points_withheld": 0.0,
                "other_adjustments": 0.0,
                "tax": 0.0,
                "_roi": [],
                "_romi": [],
                "_acos": [],
                "_ctr": [],
                "_cpc": [],
                "_ddr": [],
                "_cpo": [],
                "_conversion_types": {},
                "_ads_rows": 0,
            }
        return bucket[s]

    for row in valid_sales_rows:
        sku = str(row.get("sku") or "").strip()
        if not sku:
            continue
        item = _sku(sku)
        item["revenue"] += float(row.get("revenue") or 0.0)
        item["gross_revenue"] += float(row.get("gross_revenue") or 0.0)
        item["wb_realized_revenue"] += float(row.get("wb_realized_revenue") or 0.0)
        item["seller_payout"] += float(row.get("seller_payout") or row.get("revenue") or 0.0)
        item["profit"] += _row_profit_value(row)
        item["orders"] += float(row.get("orders") or 0.0)
        item["buys"] += float(row.get("buys") or 0.0)
        item["sales_count"] += float(row.get("sales_count") or 0.0)
        item["cost_price"] += float(row.get("cost_price") or 0.0)
        item["wb_commission"] += float(row.get("wb_commission") or 0.0)
        item["acquiring"] += float(row.get("acquiring") or 0.0)
        item["pvz_service"] += float(row.get("pvz_service") or 0.0)
        item["logistics"] += float(row.get("logistics") or 0.0)
        item["penalties"] += float(row.get("penalties") or 0.0)
        item["storage"] += float(row.get("storage") or 0.0)
        item["deductions"] += float(row.get("deductions") or 0.0)
        item["loyalty_program"] += float(row.get("loyalty_program") or 0.0)
        item["loyalty_points_withheld"] += float(row.get("loyalty_points_withheld") or 0.0)
        item["other_adjustments"] += float(row.get("other_adjustments") or 0.0)
        item["tax"] += float(row.get("tax") or 0.0)

    for row in valid_ads_rows:
        sku = str(row.get("sku") or "").strip()
        if not sku:
            continue
        item = _sku(sku)
        item["ads_spend"] += float(row.get("ads_spend") or 0.0)
        item["impressions"] += float(row.get("impressions") or 0.0)
        item["clicks"] += float(row.get("clicks") or 0.0)
        item["ads_orders"] += float(row.get("orders") or 0.0)
        item["ads_revenue"] += float(row.get("revenue") or 0.0)
        item["_ads_rows"] += 1
        if row.get("roi") is not None:
            item["_roi"].append(float(row["roi"]))
        if row.get("romi") is not None:
            item["_romi"].append(float(row["romi"]))
        if row.get("acos") is not None:
            item["_acos"].append(float(row["acos"]))
        if row.get("ctr") is not None:
            item["_ctr"].append(float(row["ctr"]))
        if row.get("cpc") is not None:
            item["_cpc"].append(float(row["cpc"]))
        if row.get("ddr") is not None:
            item["_ddr"].append(float(row["ddr"]))
        if row.get("cpo") is not None:
            item["_cpo"].append(float(row["cpo"]))
        conv_bucket = _ads_conversion_bucket(row.get("conversion_type"))
        item["_conversion_types"][conv_bucket] = int(item["_conversion_types"].get(conv_bucket, 0) or 0) + 1

    for row in valid_stocks_rows:
        sku = str(row.get("sku") or "").strip()
        if not sku:
            continue
        _sku(sku)["stock"] += float(row.get("stock") or 0.0)

    sku_metrics: List[Dict[str, Any]] = []
    zero_revenue_activity_skus: List[str] = []
    for sku, row in bucket.items():
        revenue = float(row["revenue"])
        profit_before_ads = float(row["profit"])
        ads_spend = float(row["ads_spend"])
        profit = profit_before_ads - ads_spend
        margin_pct = (profit / revenue * 100.0) if revenue > 0 else 0.0
        roi = row["_roi"]
        romi = row["_romi"]
        acos = row["_acos"]
        ctr = row["_ctr"]
        cpc = row["_cpc"]
        ddr = row["_ddr"]
        cpo = row["_cpo"]
        ads_rows_present = int(row.get("_ads_rows", 0) or 0) > 0
        conversion_map = row["_conversion_types"] if isinstance(row.get("_conversion_types"), dict) else {}
        if conversion_map:
            non_unknown = [key for key, value in conversion_map.items() if key != "unknown" and int(value or 0) > 0]
            if len(non_unknown) > 1:
                conversion_type = "mixed"
            elif len(non_unknown) == 1:
                conversion_type = non_unknown[0]
            else:
                conversion_type = "unknown"
        else:
            conversion_type = "unknown"

        orders_value = int(round(float(row["orders"])))
        buys_value = int(round(float(row["buys"]) if float(row["buys"]) > 0 else float(row["sales_count"])))
        sales_count_value = int(round(float(row["sales_count"]) if float(row["sales_count"]) > 0 else float(row["buys"])))
        views_value = int(round(float(row["impressions"]))) if ads_rows_present else None
        add_to_cart_value = None
        view_to_order_conversion = (
            round(float(orders_value) / float(views_value) * 100.0, 2)
            if views_value is not None and views_value > 0
            else None
        )
        cart_rate = None
        cart_to_order = None
        buyout_rate = round(float(buys_value) / float(orders_value) * 100.0, 2) if orders_value > 0 else None
        cpo_reported = round(sum(cpo) / len(cpo), 2) if cpo else None
        cpo_orders_based = round(ads_spend / float(orders_value), 2) if orders_value > 0 else None
        has_sales_activity = bool(orders_value > 0 or buys_value > 0 or sales_count_value > 0)
        revenue_attribution_zero = bool(has_sales_activity and abs(revenue) < 1e-9)
        if revenue_attribution_zero:
            zero_revenue_activity_skus.append(sku)

        row_financial_status = "data_issue" if revenue_attribution_zero else "ok"
        sku_metrics.append(
            {
                "sku": sku,
                "revenue": round(revenue, 2),
                "gross_revenue": round(float(row["gross_revenue"]), 2),
                "wb_realized_revenue": round(float(row["wb_realized_revenue"]), 2),
                "seller_payout": round(float(row["seller_payout"]), 2),
                "profit": round(profit, 2),
                "orders": orders_value,
                "buys": buys_value,
                "sales_count": sales_count_value,
                "stock": int(round(float(row["stock"]))),
                "ads_spend": round(ads_spend, 2),
                "impressions": int(round(float(row["impressions"]))),
                "clicks": int(round(float(row["clicks"]))),
                "ads_orders": int(round(float(row["ads_orders"]))),
                "ads_revenue": round(float(row["ads_revenue"]), 2),
                "views": views_value,
                "add_to_cart": add_to_cart_value,
                "cost_price": round(float(row["cost_price"]), 2),
                "wb_commission": round(float(row["wb_commission"]), 2),
                "acquiring": round(float(row["acquiring"]), 2),
                "pvz_service": round(float(row["pvz_service"]), 2),
                "logistics": round(float(row["logistics"]), 2),
                "penalties": round(float(row["penalties"]), 2),
                "storage": round(float(row["storage"]), 2),
                "deductions": round(float(row["deductions"]), 2),
                "loyalty_program": round(float(row["loyalty_program"]), 2),
                "loyalty_points_withheld": round(float(row["loyalty_points_withheld"]), 2),
                "other_adjustments": round(float(row["other_adjustments"]), 2),
                "tax": round(float(row["tax"]), 2),
                "margin_pct": round(margin_pct, 2),
                "view_to_order_conversion": view_to_order_conversion,
                "cart_rate": cart_rate,
                "cart_to_order": cart_to_order,
                "buyout_rate": buyout_rate,
                "roi": round(sum(roi) / len(roi), 2) if roi else None,
                "romi": round(sum(romi) / len(romi), 2) if romi else None,
                "acos": round(sum(acos) / len(acos), 2) if acos else None,
                "ctr": round(sum(ctr) / len(ctr), 2) if ctr else None,
                "cpc": round(sum(cpc) / len(cpc), 2) if cpc else None,
                "ddr": round(sum(ddr) / len(ddr), 2) if ddr else None,
                "cpo": cpo_orders_based,
                "cpo_reported": cpo_reported,
                "conversion_type": conversion_type,
                "has_sales_activity": has_sales_activity,
                "revenue_attribution_zero": revenue_attribution_zero,
                "financial_status": row_financial_status,
            }
        )

    sku_metrics.sort(key=lambda x: (float(x.get("profit", 0.0)), float(x.get("revenue", 0.0))), reverse=True)

    valid_revenue = sum(float(row.get("revenue") or 0.0) for row in valid_sales_rows)
    valid_gross_revenue = sum(float(row.get("gross_revenue") or row.get("revenue") or 0.0) for row in valid_sales_rows)
    valid_wb_realized_revenue = sum(float(row.get("wb_realized_revenue") or 0.0) for row in valid_sales_rows)
    valid_seller_payout = sum(float(row.get("seller_payout") or row.get("revenue") or 0.0) for row in valid_sales_rows)
    valid_sales_profit_before_ads = sum(_row_profit_value(row) for row in valid_sales_rows)
    valid_ads_spend = sum(float(row.get("ads_spend") or 0.0) for row in valid_ads_rows)
    valid_cost_price = sum(float(row.get("cost_price") or 0.0) for row in valid_sales_rows)
    valid_wb_commission = sum(float(row.get("wb_commission") or 0.0) for row in valid_sales_rows)
    valid_acquiring = sum(float(row.get("acquiring") or 0.0) for row in valid_sales_rows)
    valid_pvz_service = sum(float(row.get("pvz_service") or 0.0) for row in valid_sales_rows)
    valid_logistics = sum(float(row.get("logistics") or 0.0) for row in valid_sales_rows)
    valid_storage = sum(float(row.get("storage") or 0.0) for row in valid_sales_rows)
    valid_penalties = sum(float(row.get("penalties") or 0.0) for row in valid_sales_rows)
    valid_deductions = sum(float(row.get("deductions") or 0.0) for row in valid_sales_rows)
    valid_loyalty_program = sum(float(row.get("loyalty_program") or 0.0) for row in valid_sales_rows)
    valid_loyalty_points_withheld = sum(float(row.get("loyalty_points_withheld") or 0.0) for row in valid_sales_rows)
    valid_other_adjustments = sum(float(row.get("other_adjustments") or 0.0) for row in valid_sales_rows)
    valid_tax = sum(float(row.get("tax") or 0.0) for row in valid_sales_rows)

    derived_ads_impressions = sum(float(row.get("impressions") or 0.0) for row in ads_rows)
    derived_ads_clicks = sum(float(row.get("clicks") or 0.0) for row in ads_rows)
    derived_ads_orders = sum(float(row.get("orders") or row.get("sales_count") or row.get("buys") or 0.0) for row in ads_rows)
    derived_ads_revenue = sum(float(row.get("revenue") or 0.0) for row in ads_rows)
    avg_ads_ctr = sum(float(row.get("ctr") or 0.0) for row in ads_rows if row.get("ctr") is not None)
    avg_ads_ctr_count = sum(1 for row in ads_rows if row.get("ctr") is not None)

    unassigned_revenue = float(unassigned_costs["revenue"])
    unassigned_gross_revenue = float(unassigned_costs["gross_revenue"])
    unassigned_wb_realized_revenue = float(unassigned_costs["wb_realized_revenue"])
    unassigned_seller_payout = float(unassigned_costs["seller_payout"])
    unassigned_profit = float(unassigned_costs["profit"]) - float(unassigned_costs["ads_spend"])
    derived_ads_spend = valid_ads_spend + float(unassigned_costs["ads_spend"])
    total_cost_price = valid_cost_price + float(unassigned_costs["cost_price"])
    total_wb_commission = valid_wb_commission + float(unassigned_costs["wb_commission"])
    total_acquiring = valid_acquiring + float(unassigned_costs["acquiring"])
    total_pvz_service = valid_pvz_service + float(unassigned_costs["pvz_service"])
    total_logistics = valid_logistics + float(unassigned_costs["logistics"])
    total_storage = valid_storage + float(unassigned_costs["storage"])
    total_penalties = valid_penalties + float(unassigned_costs["penalties"])
    total_deductions = valid_deductions + float(unassigned_costs["deductions"])
    total_loyalty_program = valid_loyalty_program + float(unassigned_costs["loyalty_program"])
    total_loyalty_points_withheld = valid_loyalty_points_withheld + float(unassigned_costs["loyalty_points_withheld"])
    total_other_adjustments = valid_other_adjustments + float(unassigned_costs["other_adjustments"])
    total_tax = valid_tax + float(unassigned_costs["tax"])

    def _pick_ads_total(campaign_value: float, derived_value: float) -> float:
        if ads_campaign_total_rows and abs(campaign_value) > 1e-9:
            return float(campaign_value)
        return float(derived_value)

    total_ads_spend = _pick_ads_total(float(ads_campaign_totals["ads_spend"]), derived_ads_spend)
    total_ads_revenue = _pick_ads_total(float(ads_campaign_totals["ads_revenue"]), derived_ads_revenue)
    total_ads_orders = _pick_ads_total(float(ads_campaign_totals["ads_orders"]), derived_ads_orders)
    total_ads_impressions = _pick_ads_total(float(ads_campaign_totals["ads_impressions"]), derived_ads_impressions)
    total_ads_clicks = _pick_ads_total(float(ads_campaign_totals["ads_clicks"]), derived_ads_clicks)

    sku_assigned_profit = valid_sales_profit_before_ads - valid_ads_spend
    total_revenue = valid_revenue + unassigned_revenue
    total_gross_revenue = valid_gross_revenue + unassigned_gross_revenue
    total_wb_realized_revenue = valid_wb_realized_revenue + unassigned_wb_realized_revenue
    total_seller_payout = valid_seller_payout + unassigned_seller_payout
    total_revenue_basis = total_seller_payout if abs(total_seller_payout) > 1e-9 else total_revenue
    total_profit = sku_assigned_profit + unassigned_profit
    gross_profit = total_revenue_basis - total_cost_price - total_wb_commission
    net_profit = (
        total_revenue_basis
        - total_cost_price
        - total_wb_commission
        - total_acquiring
        - total_pvz_service
        - total_logistics
        - total_storage
        - total_penalties
        - total_deductions
        - total_loyalty_program
        - total_loyalty_points_withheld
        - total_other_adjustments
        - total_ads_spend
        - total_tax
    )
    margin_pct = (net_profit / total_revenue_basis * 100.0) if total_revenue_basis > 0 else 0.0
    profitability_pct = (net_profit / total_cost_price * 100.0) if total_cost_price > 0 else 0.0

    def _row_item_qty(row: Dict[str, Any]) -> float:
        explicit_quantity = row.get("quantity", None)
        if explicit_quantity is not None:
            return float(explicit_quantity or 0.0)
        return float(row.get("buys") or row.get("sales_count") or row.get("orders") or 0.0)

    def _row_sales_activity_qty(row: Dict[str, Any]) -> float:
        return float(
            row.get("sales_count")
            or row.get("buys")
            or row.get("orders")
            or row.get("quantity")
            or 0.0
        )

    total_item_qty = sum(_row_item_qty(row) for row in sales_rows if isinstance(row, dict))
    total_sales_activity_qty = sum(_row_sales_activity_qty(row) for row in sales_rows if isinstance(row, dict))
    total_sku_activity_count = sum(1 for row in sku_metrics if bool(row.get("has_sales_activity", False)))
    total_stock = sum(float(row.get("stock") or 0.0) for row in stocks_rows)

    totals = {
        "revenue": round(total_revenue_basis, 2),
        "gross_revenue": round(total_gross_revenue, 2),
        "wb_realized_revenue": round(total_wb_realized_revenue, 2),
        "seller_payout": round(total_seller_payout, 2),
        "row_revenue_total": round(total_revenue, 2),
        "profit": round(total_profit, 2),
        "orders": 0,
        "buys": 0,
        "orders_confirmed": False,
        "buys_confirmed": False,
        "data_source_orders": "unknown",
        "data_source_buys": "unknown",
        "item_qty": int(round(total_item_qty)),
        "sales_activity_qty": int(round(total_sales_activity_qty)),
        "sku_activity_count": int(total_sku_activity_count),
        "stock": int(round(total_stock)),
        "ads_spend": round(total_ads_spend, 2),
        "ads_spend_total": round(total_ads_spend, 2),
        "cost_price": round(total_cost_price, 2),
        "wb_commission": round(total_wb_commission, 2),
        "acquiring": round(total_acquiring, 2),
        "pvz_service": round(total_pvz_service, 2),
        "logistics": round(total_logistics, 2),
        "storage": round(total_storage, 2),
        "penalties": round(total_penalties, 2),
        "deductions": round(total_deductions, 2),
        "loyalty_program": round(total_loyalty_program, 2),
        "loyalty_points_withheld": round(total_loyalty_points_withheld, 2),
        "loyalty_total": round(total_loyalty_program + total_loyalty_points_withheld, 2),
        "other_adjustments": round(total_other_adjustments, 2),
        "tax": round(total_tax, 2),
        "ads_impressions": int(round(total_ads_impressions)),
        "ads_impressions_total": int(round(total_ads_impressions)),
        "ads_clicks": int(round(total_ads_clicks)),
        "ads_clicks_total": int(round(total_ads_clicks)),
        "ads_ctr": round(
            (float(total_ads_clicks) / float(total_ads_impressions) * 100.0)
            if total_ads_impressions > 0
            else ((avg_ads_ctr / float(avg_ads_ctr_count)) if avg_ads_ctr_count > 0 else 0.0),
            2,
        ),
        "ads_orders": int(round(total_ads_orders)),
        "ads_orders_total": int(round(total_ads_orders)),
        "ads_revenue": round(total_ads_revenue, 2),
        "ads_revenue_total": round(total_ads_revenue, 2),
        "views": int(round(total_ads_impressions)) if ads_rows else None,
        "add_to_cart": None,
        "ads_acos": round(
            (total_ads_spend / total_ads_revenue * 100.0)
            if total_ads_revenue > 0
            else 0.0,
            2,
        ),
        "ads_romi": round(
            ((total_ads_revenue - total_ads_spend) / total_ads_spend * 100.0)
            if total_ads_spend > 0
            else 0.0,
            2,
        ),
        "sku_assigned_revenue": round(valid_seller_payout, 2),
        "unassigned_revenue": round(unassigned_seller_payout, 2),
        "total_revenue": round(total_revenue_basis, 2),
        "sku_assigned_profit": round(sku_assigned_profit, 2),
        "unassigned_profit": round(unassigned_profit, 2),
        "total_profit": round(total_profit, 2),
        "gross_profit": round(gross_profit, 2),
        "net_profit": round(net_profit, 2),
        "margin_pct": round(margin_pct, 2),
        "profitability_pct": round(profitability_pct, 2),
    }

    unassigned_costs = {
        "revenue": round(float(unassigned_costs["revenue"]), 2),
        "gross_revenue": round(float(unassigned_costs["gross_revenue"]), 2),
        "wb_realized_revenue": round(float(unassigned_costs["wb_realized_revenue"]), 2),
        "seller_payout": round(float(unassigned_costs["seller_payout"]), 2),
        "profit": round(float(unassigned_profit), 2),
        "cost_price": round(float(unassigned_costs["cost_price"]), 2),
        "wb_commission": round(float(unassigned_costs["wb_commission"]), 2),
        "acquiring": round(float(unassigned_costs["acquiring"]), 2),
        "pvz_service": round(float(unassigned_costs["pvz_service"]), 2),
        "logistics": round(float(unassigned_costs["logistics"]), 2),
        "penalties": round(float(unassigned_costs["penalties"]), 2),
        "storage": round(float(unassigned_costs["storage"]), 2),
        "deductions": round(float(unassigned_costs["deductions"]), 2),
        "loyalty_program": round(float(unassigned_costs["loyalty_program"]), 2),
        "loyalty_points_withheld": round(float(unassigned_costs["loyalty_points_withheld"]), 2),
        "other_adjustments": round(float(unassigned_costs["other_adjustments"]), 2),
        "tax": round(float(unassigned_costs["tax"]), 2),
        "ads_spend": round(float(unassigned_costs["ads_spend"]), 2),
        "rows": int(unassigned_costs["rows"]),
    }

    unassigned_costs_present = bool(
        unassigned_costs["rows"] > 0
        or abs(unassigned_costs["revenue"]) > 0
        or abs(unassigned_costs["profit"]) > 0
        or abs(unassigned_costs["cost_price"]) > 0
        or abs(unassigned_costs["wb_commission"]) > 0
        or abs(unassigned_costs["acquiring"]) > 0
        or abs(unassigned_costs["pvz_service"]) > 0
        or abs(unassigned_costs["logistics"]) > 0
        or abs(unassigned_costs["penalties"]) > 0
        or abs(unassigned_costs["storage"]) > 0
        or abs(unassigned_costs["deductions"]) > 0
        or abs(unassigned_costs["loyalty_program"]) > 0
        or abs(unassigned_costs["loyalty_points_withheld"]) > 0
        or abs(unassigned_costs["other_adjustments"]) > 0
        or abs(unassigned_costs["tax"]) > 0
        or abs(unassigned_costs["ads_spend"]) > 0
    )
    sku_attribution = evaluate_sku_attribution(
        valid_sku_count=len(sku_metrics),
        sales_unassigned=sales_split["unassigned"],
        ads_unassigned=ads_split["unassigned"],
        stocks_unassigned=stocks_split["unassigned"],
        sales_activity_qty=total_sales_activity_qty,
    )
    sku_attribution_status = str(sku_attribution.get("sku_attribution_status") or "ok")
    attribution_guard_triggered = bool(sku_attribution.get("attribution_guard_triggered", False))

    financial_integrity = evaluate_financial_integrity(
        totals={
            "total_revenue": total_revenue_basis,
            "wb_commission": total_wb_commission,
            "logistics": total_logistics,
            "storage": total_storage,
            "penalties": total_penalties,
            "deductions": (
                total_deductions
                + total_loyalty_program
                + total_loyalty_points_withheld
                + total_other_adjustments
                + total_acquiring
                + total_pvz_service
            ),
            "cost_price": total_cost_price,
            "tax": total_tax,
            "ads_spend_total": total_ads_spend,
        },
        data_sources={
            "revenue": "aggregated_rows",
            "commission": "aggregated_rows",
            "logistics": "aggregated_rows",
            "storage": "aggregated_rows",
            "penalties": "aggregated_rows",
            "deductions": "aggregated_rows",
            "cost_price": "aggregated_rows",
            "tax": "aggregated_rows",
            "ads_spend": ("ads_campaign_totals" if ads_campaign_total_rows else ("ads_rows" if ads_rows else "unknown")),
        },
        sku_attribution_status=sku_attribution_status,
        ads_rows_count=len(ads_rows),
    )
    financial_completeness_pct = float(financial_integrity.get("financial_completeness_pct", 0.0) or 0.0)
    financial_finality_status = str(financial_integrity.get("financial_finality_status") or "unavailable")

    has_financial_activity = bool(
        abs(total_revenue_basis) > 0
        or abs(total_acquiring) > 0
        or abs(total_pvz_service) > 0
        or abs(total_logistics) > 0
        or abs(total_storage) > 0
        or abs(total_penalties) > 0
        or abs(total_deductions) > 0
        or abs(total_loyalty_program) > 0
        or abs(total_loyalty_points_withheld) > 0
        or abs(total_other_adjustments) > 0
        or abs(total_tax) > 0
        or abs(total_ads_spend) > 0
    )
    cost_price_missing = bool(has_financial_activity and abs(total_cost_price) <= 1e-9)
    wb_commission_missing = bool(has_financial_activity and abs(total_wb_commission) <= 1e-9)
    expense_attribution_partial = bool(
        unassigned_costs_present or int(invalid_sku_rows) > 0 or sku_attribution_status != "ok"
    )
    net_profit_partial = bool(
        financial_finality_status != "final"
        or cost_price_missing
        or wb_commission_missing
        or expense_attribution_partial
    )
    financial_margin_not_final = net_profit_partial
    if financial_finality_status == "final":
        financial_status = "ok"
    elif financial_finality_status == "partial":
        financial_status = "partial"
    else:
        financial_status = "degraded"

    ads_analysis_enabled = bool(len(ads_rows) > 0 or len(ads_campaign_total_rows) > 0)
    report_reliability_level = resolve_report_reliability_level(
        sku_attribution_status=sku_attribution_status,
        financial_finality_status=financial_finality_status,
        ads_analysis_enabled=ads_analysis_enabled,
    )
    ai_reliability = report_reliability_level

    financial_kpi = {
        "revenue": round(total_revenue_basis, 2),
        "gross_revenue": round(total_gross_revenue, 2),
        "wb_realized_revenue": round(total_wb_realized_revenue, 2),
        "seller_payout": round(total_seller_payout, 2),
        "row_revenue_total": round(total_revenue, 2),
        "cost_price": round(total_cost_price, 2),
        "wb_commission": round(total_wb_commission, 2),
        "acquiring": round(total_acquiring, 2),
        "pvz_service": round(total_pvz_service, 2),
        "logistics": round(total_logistics, 2),
        "storage": round(total_storage, 2),
        "penalties": round(total_penalties, 2),
        "deductions": round(total_deductions, 2),
        "loyalty_program": round(total_loyalty_program, 2),
        "loyalty_points_withheld": round(total_loyalty_points_withheld, 2),
        "loyalty_total": round(total_loyalty_program + total_loyalty_points_withheld, 2),
        "other_adjustments": round(total_other_adjustments, 2),
        "tax": round(total_tax, 2),
        "ads_spend": round(total_ads_spend, 2),
        "gross_profit": round(gross_profit, 2),
        "net_profit": round(net_profit, 2),
        "margin_pct": round(margin_pct, 2),
        "profitability_pct": round(profitability_pct, 2),
        "cost_price_missing": cost_price_missing,
        "wb_commission_missing": wb_commission_missing,
        "expense_attribution_partial": expense_attribution_partial,
        "net_profit_partial": net_profit_partial,
        "financial_margin_not_final": financial_margin_not_final,
        "completeness_pct": round(financial_completeness_pct, 2),
        "components": financial_integrity.get("components", {}),
        "available_components": int(financial_integrity.get("available_components", 0) or 0),
        "total_components": int(financial_integrity.get("total_components", 0) or 0),
        "financial_finality_status": financial_finality_status,
        "is_partial": net_profit_partial,
        "revenue_basis": "seller_payout",
        "net_profit_formula": {
            "revenue_basis": round(total_revenue_basis, 2),
            "cost_price": round(total_cost_price, 2),
            "wb_commission": round(total_wb_commission, 2),
            "acquiring": round(total_acquiring, 2),
            "pvz_service": round(total_pvz_service, 2),
            "logistics": round(total_logistics, 2),
            "storage": round(total_storage, 2),
            "penalties": round(total_penalties, 2),
            "deductions": round(total_deductions, 2),
            "loyalty_program": round(total_loyalty_program, 2),
            "loyalty_points_withheld": round(total_loyalty_points_withheld, 2),
            "other_adjustments": round(total_other_adjustments, 2),
            "ads_spend": round(total_ads_spend, 2),
            "tax": round(total_tax, 2),
            "net_profit": round(net_profit, 2),
        },
    }

    data_quality = {
        "valid_sku_count": len(sku_metrics),
        "invalid_sku_rows": int(invalid_sku_rows),
        "invalid_sku_reason_counts": invalid_reason_counts,
        "unassigned_costs_present": unassigned_costs_present,
        "unassigned_rows": int(unassigned_costs["rows"]),
        "unassigned_profit": float(unassigned_costs["profit"]),
        "financial_status": financial_status,
        "ai_decision_reliability": ai_reliability,
        "zero_revenue_activity_sku_count": len(zero_revenue_activity_skus),
        "zero_revenue_activity_skus": zero_revenue_activity_skus[:50],
        "sku_attribution_status": sku_attribution_status,
        "invalid_sku_rows_parser_error": int(sku_attribution.get("invalid_sku_rows_parser_error", 0) or 0),
        "invalid_sku_rows_missing_field": int(sku_attribution.get("invalid_sku_rows_missing_field", 0) or 0),
        "unassigned_rows_true": int(sku_attribution.get("unassigned_rows_true", 0) or 0),
        "attribution_guard_triggered": attribution_guard_triggered,
        "no_valid_sku_with_sales_activity": bool(sku_attribution.get("no_valid_sku_with_sales_activity", False)),
        "cost_price_missing": cost_price_missing,
        "wb_commission_missing": wb_commission_missing,
        "expense_attribution_partial": expense_attribution_partial,
        "net_profit_partial": net_profit_partial,
        "financial_margin_not_final": financial_margin_not_final,
        "financial_completeness_pct": round(financial_completeness_pct, 2),
        "financial_finality_status": financial_finality_status,
        "financial_components": financial_integrity.get("components", {}),
        "available_financial_components": int(financial_integrity.get("available_components", 0) or 0),
        "total_financial_components": int(financial_integrity.get("total_components", 0) or 0),
        "territorial_analysis_enabled": bool(sku_attribution_status != "broken"),
        "profit_contribution_enabled": bool(sku_attribution_status != "broken"),
        "ads_analysis_enabled": ads_analysis_enabled,
        "report_reliability_level": report_reliability_level,
        "sku_split_diagnostics": {
            "sales": sales_split_diagnostics if isinstance(sales_split_diagnostics, dict) else {},
            "ads": ads_split_diagnostics if isinstance(ads_split_diagnostics, dict) else {},
            "stocks": stocks_split_diagnostics if isinstance(stocks_split_diagnostics, dict) else {},
        },
    }

    ads_diagnostics = {
        "rows": len(ads_rows),
        "campaign_total_rows": len(ads_campaign_total_rows),
        "campaign_totals": {
            "ads_spend": round(float(ads_campaign_totals["ads_spend"]), 2),
            "ads_revenue": round(float(ads_campaign_totals["ads_revenue"]), 2),
            "ads_orders": int(round(float(ads_campaign_totals["ads_orders"]))),
            "ads_impressions": int(round(float(ads_campaign_totals["ads_impressions"]))),
            "ads_clicks": int(round(float(ads_campaign_totals["ads_clicks"]))),
        },
        "derived_totals": {
            "ads_spend": round(derived_ads_spend, 2),
            "ads_revenue": round(derived_ads_revenue, 2),
            "ads_orders": int(round(derived_ads_orders)),
            "ads_impressions": int(round(derived_ads_impressions)),
            "ads_clicks": int(round(derived_ads_clicks)),
        },
        "selected_totals": {
            "ads_spend": round(total_ads_spend, 2),
            "ads_revenue": round(total_ads_revenue, 2),
            "ads_orders": int(round(total_ads_orders)),
            "ads_impressions": int(round(total_ads_impressions)),
            "ads_clicks": int(round(total_ads_clicks)),
        },
        "conversion_breakdown": {
            "direct": {
                "rows": int(round(ads_conversion_diag["direct"]["rows"])),
                "ads_spend": round(float(ads_conversion_diag["direct"]["ads_spend"]), 2),
                "ads_revenue": round(float(ads_conversion_diag["direct"]["ads_revenue"]), 2),
                "ads_orders": int(round(float(ads_conversion_diag["direct"]["ads_orders"]))),
            },
            "associated": {
                "rows": int(round(ads_conversion_diag["associated"]["rows"])),
                "ads_spend": round(float(ads_conversion_diag["associated"]["ads_spend"]), 2),
                "ads_revenue": round(float(ads_conversion_diag["associated"]["ads_revenue"]), 2),
                "ads_orders": int(round(float(ads_conversion_diag["associated"]["ads_orders"]))),
            },
            "unknown": {
                "rows": int(round(ads_conversion_diag["unknown"]["rows"])),
                "ads_spend": round(float(ads_conversion_diag["unknown"]["ads_spend"]), 2),
                "ads_revenue": round(float(ads_conversion_diag["unknown"]["ads_revenue"]), 2),
                "ads_orders": int(round(float(ads_conversion_diag["unknown"]["ads_orders"]))),
            },
        },
        "attribution_quality": ads_attribution_quality,
    }

    return {
        "sku_metrics": sku_metrics,
        "totals": totals,
        "unassigned_costs": unassigned_costs,
        "data_quality": data_quality,
        "financial_debug": financial_debug,
        "financial_kpi": financial_kpi,
        "ads_diagnostics": ads_diagnostics,
        "financial": {
            "revenue": totals["total_revenue"],
            "gross_revenue": totals.get("gross_revenue"),
            "wb_realized_revenue": totals.get("wb_realized_revenue"),
            "seller_payout": totals.get("seller_payout"),
            "cost_price": totals["cost_price"],
            "wb_commission": totals["wb_commission"],
            "acquiring": totals.get("acquiring"),
            "pvz_service": totals.get("pvz_service"),
            "gross_profit": totals["gross_profit"],
            "profit": totals["net_profit"],
            "net_profit": totals["net_profit"],
            "margin_pct": totals["margin_pct"],
            "profitability_pct": totals["profitability_pct"],
            "ads_spend": totals["ads_spend"],
            "logistics": totals["logistics"],
            "storage": totals["storage"],
            "penalties": totals["penalties"],
            "deductions": totals["deductions"],
            "loyalty_program": totals.get("loyalty_program"),
            "loyalty_points_withheld": totals.get("loyalty_points_withheld"),
            "other_adjustments": totals.get("other_adjustments"),
            "tax": totals.get("tax"),
            "financial_completeness_pct": financial_kpi["completeness_pct"],
            "financial_finality_status": financial_kpi.get("financial_finality_status", "unavailable"),
            "is_partial": financial_kpi["is_partial"],
            "ads_attribution_quality": ads_attribution_quality,
        },
        "funnel": {
            "orders": totals["orders"],
            "buys": totals["buys"],
            "orders_confirmed": bool(totals["orders_confirmed"]),
            "buys_confirmed": bool(totals["buys_confirmed"]),
            "item_qty": totals["item_qty"],
            "sales_activity_qty": totals["sales_activity_qty"],
            "sku_activity_count": totals["sku_activity_count"],
        },
        "ads": {
            "spend": totals["ads_spend"],
            "spend_total": totals["ads_spend_total"],
            "impressions": totals["ads_impressions"],
            "impressions_total": totals["ads_impressions_total"],
            "clicks": totals["ads_clicks"],
            "clicks_total": totals["ads_clicks_total"],
            "ctr": totals["ads_ctr"],
            "orders": totals["ads_orders"],
            "orders_total": totals["ads_orders_total"],
            "revenue": totals["ads_revenue"],
            "revenue_total": totals["ads_revenue_total"],
            "acos": totals["ads_acos"],
            "romi": totals["ads_romi"],
            "rows": len(ads_rows),
            "campaign_total_rows": len(ads_campaign_total_rows),
            "attribution_quality": ads_attribution_quality,
        },
        "stock": {"total_stock": totals["stock"]},
    }


def build_facts_from_reports(seller_id: str, run_date: str, seller_name: str, metrics: Dict[str, Any], discovered_files: Dict[str, List[str]], warnings: List[Dict[str, Any]], source_mode: str) -> Dict[str, Any]:
    totals = metrics.get("totals", {}) if isinstance(metrics, dict) else {}
    data_quality = metrics.get("data_quality", {}) if isinstance(metrics, dict) else {}
    daily_kpi = metrics.get("daily_kpi", {}) if isinstance(metrics, dict) else {}
    if not isinstance(daily_kpi, dict):
        daily_kpi = {}
    codes = {str(w.get("code", "")) for w in warnings if isinstance(w, dict)}
    debug = {"input_files_found", "input_file_detected_type"}
    severe = {
        "input_files_missing",
        "sales_report_missing",
        "required_columns_missing",
        "wb_api_zero_sales_rows",
        "financial_data_missing",
    }
    medium = {
        "ads_report_missing",
        "stocks_report_missing",
        "input_file_unknown_type",
        "input_file_read_error",
        "input_file_skipped",
        "wb_api_financial_degraded",
    }
    effective = codes - debug

    invalid_sku_rows = int(data_quality.get("invalid_sku_rows", 0) or 0)
    unassigned_present = bool(data_quality.get("unassigned_costs_present", False))
    financial_status = str(data_quality.get("financial_status") or "ok")
    ai_reliability = str(data_quality.get("ai_decision_reliability") or "high")
    sku_attribution_status = str(data_quality.get("sku_attribution_status") or "ok")
    financial_finality_status = str(data_quality.get("financial_finality_status") or "unavailable")

    if source_mode == "fallback_mock":
        confidence = "low"
    elif severe & effective:
        confidence = "low"
    elif medium & effective:
        confidence = "medium"
    else:
        confidence = "high"

    if financial_status == "partial" or financial_finality_status in {"sparse", "unavailable"}:
        confidence = "low"
    elif financial_status == "degraded" and confidence == "high":
        confidence = "medium"
    elif sku_attribution_status == "broken":
        confidence = "low"
    elif (invalid_sku_rows > 0 or unassigned_present) and confidence == "high":
        confidence = "medium"

    daily_orders_count = int(daily_kpi.get("daily_orders_count", 0) or 0)
    daily_orders_amount = float(
        daily_kpi.get("daily_orders_amount", 0.0) or 0.0
    )
    daily_buyouts_count = int(daily_kpi.get("daily_buyouts_count", 0) or 0)
    daily_buyouts_amount = float(
        daily_kpi.get("daily_buyouts_amount", 0.0) or 0.0
    )
    data_source_orders = str(daily_kpi.get("data_source_orders") or "unknown")
    data_source_buyouts = str(daily_kpi.get("data_source_buyouts") or "unknown")
    data_source_orders_count = str(daily_kpi.get("data_source_orders_count") or data_source_orders)
    data_source_orders_amount = str(daily_kpi.get("data_source_orders_amount") or "unknown")
    data_source_buyouts_count = str(daily_kpi.get("data_source_buyouts_count") or data_source_buyouts)
    data_source_buyouts_amount = str(daily_kpi.get("data_source_buyouts_amount") or "unknown")

    financial_kpi = metrics.get("financial_kpi", {}) if isinstance(metrics, dict) else {}
    if not isinstance(financial_kpi, dict):
        financial_kpi = {}
    ads_metrics = metrics.get("ads", {}) if isinstance(metrics, dict) else {}
    if not isinstance(ads_metrics, dict):
        ads_metrics = {}
    ads_diagnostics = metrics.get("ads_diagnostics", {}) if isinstance(metrics, dict) else {}
    if not isinstance(ads_diagnostics, dict):
        ads_diagnostics = {}
    ads_rows_count = int(ads_diagnostics.get("rows", 0) or 0)
    ads_spend_value = float(
        totals.get("ads_spend_total", totals.get("ads_spend", ads_metrics.get("spend", 0.0))) or 0.0
    )
    ads_attribution_quality = str(
        ads_diagnostics.get("attribution_quality", ads_metrics.get("attribution_quality", "unknown")) or "unknown"
    )
    financial_kpi_payload = {
        "revenue": float(financial_kpi.get("revenue", totals.get("total_revenue", totals.get("revenue", 0.0))) or 0.0),
        "gross_revenue": float(financial_kpi.get("gross_revenue", totals.get("gross_revenue", 0.0)) or 0.0),
        "wb_realized_revenue": float(
            financial_kpi.get("wb_realized_revenue", totals.get("wb_realized_revenue", 0.0)) or 0.0
        ),
        "seller_payout": float(financial_kpi.get("seller_payout", totals.get("seller_payout", totals.get("revenue", 0.0))) or 0.0),
        "row_revenue_total": float(financial_kpi.get("row_revenue_total", totals.get("row_revenue_total", 0.0)) or 0.0),
        "cost_price": float(financial_kpi.get("cost_price", totals.get("cost_price", 0.0)) or 0.0),
        "wb_commission": float(financial_kpi.get("wb_commission", totals.get("wb_commission", 0.0)) or 0.0),
        "acquiring": float(financial_kpi.get("acquiring", totals.get("acquiring", 0.0)) or 0.0),
        "pvz_service": float(financial_kpi.get("pvz_service", totals.get("pvz_service", 0.0)) or 0.0),
        "logistics": float(financial_kpi.get("logistics", totals.get("logistics", 0.0)) or 0.0),
        "storage": float(financial_kpi.get("storage", totals.get("storage", 0.0)) or 0.0),
        "penalties": float(financial_kpi.get("penalties", totals.get("penalties", 0.0)) or 0.0),
        "deductions": float(financial_kpi.get("deductions", totals.get("deductions", 0.0)) or 0.0),
        "loyalty_program": float(financial_kpi.get("loyalty_program", totals.get("loyalty_program", 0.0)) or 0.0),
        "loyalty_points_withheld": float(
            financial_kpi.get("loyalty_points_withheld", totals.get("loyalty_points_withheld", 0.0)) or 0.0
        ),
        "loyalty_total": float(financial_kpi.get("loyalty_total", totals.get("loyalty_total", 0.0)) or 0.0),
        "other_adjustments": float(financial_kpi.get("other_adjustments", totals.get("other_adjustments", 0.0)) or 0.0),
        "tax": float(financial_kpi.get("tax", totals.get("tax", 0.0)) or 0.0),
        "ads_spend": float(financial_kpi.get("ads_spend", totals.get("ads_spend", 0.0)) or 0.0),
        "gross_profit": float(financial_kpi.get("gross_profit", totals.get("gross_profit", 0.0)) or 0.0),
        "net_profit": float(financial_kpi.get("net_profit", totals.get("net_profit", totals.get("total_profit", totals.get("profit", 0.0)))) or 0.0),
        "margin_pct": float(financial_kpi.get("margin_pct", totals.get("margin_pct", 0.0)) or 0.0),
        "profitability_pct": float(financial_kpi.get("profitability_pct", totals.get("profitability_pct", 0.0)) or 0.0),
        "cost_price_missing": bool(financial_kpi.get("cost_price_missing", False)),
        "wb_commission_missing": bool(financial_kpi.get("wb_commission_missing", False)),
        "expense_attribution_partial": bool(financial_kpi.get("expense_attribution_partial", False)),
        "net_profit_partial": bool(financial_kpi.get("net_profit_partial", False)),
        "financial_margin_not_final": bool(financial_kpi.get("financial_margin_not_final", False)),
        "completeness_pct": float(financial_kpi.get("completeness_pct", data_quality.get("financial_completeness_pct", 0.0)) or 0.0),
        "financial_finality_status": str(
            financial_kpi.get("financial_finality_status", data_quality.get("financial_finality_status", "unavailable"))
            or "unavailable"
        ),
        "components": financial_kpi.get("components", data_quality.get("financial_components", {})),
        "is_partial": bool(financial_kpi.get("is_partial", False)),
    }
    commerce_kpi = {
        "daily_orders_count": daily_orders_count,
        "daily_orders_amount": round(daily_orders_amount, 2),
        "daily_buyouts_count": daily_buyouts_count,
        "daily_buyouts_amount": round(daily_buyouts_amount, 2),
        "avg_check": round((daily_buyouts_amount / daily_buyouts_count) if daily_buyouts_count > 0 else 0.0, 2),
        "data_source_orders": data_source_orders,
        "data_source_buyouts": data_source_buyouts,
        "data_source_orders_count": data_source_orders_count,
        "data_source_orders_amount": data_source_orders_amount,
        "data_source_buyouts_count": data_source_buyouts_count,
        "data_source_buyouts_amount": data_source_buyouts_amount,
        "orders_amount_confirmed": bool(daily_kpi.get("orders_amount_confirmed", False)),
        "buyouts_amount_confirmed": bool(daily_kpi.get("buyouts_amount_confirmed", False)),
    }

    return {
        "seller_id": seller_id,
        "seller_name": seller_name,
        "run_date": run_date,
        "generated_at": _utc_now_iso(),
        "data_confidence": confidence,
        "source_mode": source_mode,
        "daily_orders_count": daily_orders_count,
        "daily_orders_amount": round(daily_orders_amount, 2),
        "daily_buyouts_count": daily_buyouts_count,
        "daily_buyouts_amount": round(daily_buyouts_amount, 2),
        "data_source_orders": data_source_orders,
        "data_source_buyouts": data_source_buyouts,
        "data_source_orders_count": data_source_orders_count,
        "data_source_orders_amount": data_source_orders_amount,
        "data_source_buyouts_count": data_source_buyouts_count,
        "data_source_buyouts_amount": data_source_buyouts_amount,
        "orders_amount_confirmed": bool(daily_kpi.get("orders_amount_confirmed", False)),
        "buyouts_amount_confirmed": bool(daily_kpi.get("buyouts_amount_confirmed", False)),
        "ads_rows": ads_rows_count,
        "ads_spend": round(ads_spend_value, 2),
        "ads_loaded_from_file": False,
        "ads_source_file": "",
        "ads_attribution_quality": ads_attribution_quality,
        "input_summary": {
            "sales_files_found": len(discovered_files.get("sales", [])),
            "ads_files_found": len(discovered_files.get("ads", [])),
            "stocks_files_found": len(discovered_files.get("stocks", [])),
            "unknown_files_found": len(discovered_files.get("unknown", [])),
            "source_mode": source_mode,
            "confidence": confidence,
        },
        "commerce_kpi": commerce_kpi,
        "financial_kpi": financial_kpi_payload,
        "kpi": {
            "revenue": financial_kpi_payload["revenue"],
            "profit": financial_kpi_payload["net_profit"],
            "orders": daily_orders_count,
            "buyouts": daily_buyouts_count,
            "orders_amount": round(daily_orders_amount, 2),
            "buyouts_amount": round(daily_buyouts_amount, 2),
        },
        "data_quality": {
            "valid_sku_count": int(data_quality.get("valid_sku_count", 0) or 0),
            "invalid_sku_rows": invalid_sku_rows,
            "invalid_sku_reason_counts": data_quality.get("invalid_sku_reason_counts", {}),
            "unassigned_costs_present": unassigned_present,
            "unassigned_rows": int(data_quality.get("unassigned_rows", 0) or 0),
            "unassigned_profit": float(data_quality.get("unassigned_profit", 0.0) or 0.0),
            "financial_status": financial_status,
            "ai_decision_reliability": ai_reliability,
            "sku_attribution_status": sku_attribution_status,
            "invalid_sku_rows_parser_error": int(data_quality.get("invalid_sku_rows_parser_error", 0) or 0),
            "invalid_sku_rows_missing_field": int(data_quality.get("invalid_sku_rows_missing_field", 0) or 0),
            "unassigned_rows_true": int(data_quality.get("unassigned_rows_true", 0) or 0),
            "attribution_guard_triggered": bool(data_quality.get("attribution_guard_triggered", False)),
            "zero_revenue_activity_sku_count": int(data_quality.get("zero_revenue_activity_sku_count", 0) or 0),
            "zero_revenue_activity_skus": data_quality.get("zero_revenue_activity_skus", []),
            "ads_attribution_quality": ads_attribution_quality,
            "cost_price_missing": bool(data_quality.get("cost_price_missing", financial_kpi_payload["cost_price_missing"])),
            "wb_commission_missing": bool(data_quality.get("wb_commission_missing", financial_kpi_payload["wb_commission_missing"])),
            "expense_attribution_partial": bool(
                data_quality.get("expense_attribution_partial", financial_kpi_payload["expense_attribution_partial"])
            ),
            "net_profit_partial": bool(data_quality.get("net_profit_partial", financial_kpi_payload["net_profit_partial"])),
            "financial_margin_not_final": bool(
                data_quality.get("financial_margin_not_final", financial_kpi_payload["financial_margin_not_final"])
            ),
            "financial_completeness_pct": float(
                data_quality.get("financial_completeness_pct", financial_kpi_payload["completeness_pct"]) or 0.0
            ),
            "financial_finality_status": str(
                data_quality.get("financial_finality_status", financial_kpi_payload.get("financial_finality_status", "unavailable"))
                or "unavailable"
            ),
            "territorial_analysis_enabled": bool(data_quality.get("territorial_analysis_enabled", True)),
            "profit_contribution_enabled": bool(data_quality.get("profit_contribution_enabled", True)),
            "ads_analysis_enabled": bool(data_quality.get("ads_analysis_enabled", ads_rows_count > 0)),
            "report_reliability_level": str(data_quality.get("report_reliability_level") or "medium"),
        },
    }
