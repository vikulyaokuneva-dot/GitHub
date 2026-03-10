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

ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}

REPORT_NAME_KEYWORDS = {
    "sales": ["воронка", "продаж", "реализац", "детализирован", "еженедель", "sales", "sale", "realization", "статистик"],
    "ads": ["реклам", "кампан", "продвиж", "ads", "advert", "campaign", "promo"],
    "stocks": ["остат", "склад", "stock", "inventory"],
}

FIELD_SYNONYMS = {
    "sku": ["sku", "nm_id", "nmid", "артикул", "артикул_wb", "артикул_продавца", "номенклатура", "код_товара", "код_номенклатуры", "наименование", "товар", "предмет"],
    "seller_sku": ["seller_sku", "supplier_sku", "артикул_поставщика", "артикул_продавца", "артикул", "vendor_code"],
    "warehouse": ["warehouse", "склад", "склад_продажи", "склад_отгрузки", "warehouse_name", "наименование_склада", "наименование_офиса_доставки", "офис_доставки", "office"],
    "revenue": [
        "revenue",
        "выручка",
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
    "ctr": ["ctr", "ctr_%", "кликабельность"],
    "acos": ["acos", "acos_%", "ддр", "доля_рекламных_расходов"],
    "romi": ["romi", "roi", "окупаемость_рекламы", "рентабельность_рекламы"],
    "margin": ["margin", "маржа", "маржинальность"],
    "margin_pct": ["margin_pct", "маржа_pct", "маржа_процент", "margin_percent"],
    "logistics": ["логистика", "услуги_по_доставке_товара_покупателю", "доставка", "доставка_товара_покупателю"],
    "penalties": ["общая_сумма_штрафов", "штрафы", "сумма_штрафов"],
    "storage": ["хранение"],
    "deductions": ["удержания", "прочие_удержания"],
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


def _xlsx_sheet_path(zf: zipfile.ZipFile) -> str:
    if "xl/worksheets/sheet1.xml" in zf.namelist():
        return "xl/worksheets/sheet1.xml"
    wb = ET.fromstring(zf.read("xl/workbook.xml"))
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rid_attr = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    first = wb.find("x:sheets/x:sheet", ns)
    if first is None:
        raise RuntimeError("No sheets in workbook")
    rid = first.attrib.get(rid_attr, "")
    rels_path = "xl/_rels/workbook.xml.rels"
    if rid and rels_path in zf.namelist():
        rels = ET.fromstring(zf.read(rels_path))
        rns = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
        for rel in rels.findall("r:Relationship", rns):
            if rel.attrib.get("Id") == rid:
                target = rel.attrib.get("Target", "")
                if target.startswith("/"):
                    return target.lstrip("/")
                if target.startswith("xl/"):
                    return target
                return f"xl/{target}"
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


def _detect_report_type(path: str) -> Dict[str, Any]:
    name = os.path.basename(path)
    norm_name = _normalize_text(name)
    name_scores = {"sales": 0, "ads": 0, "stocks": 0}
    for t, words in REPORT_NAME_KEYWORDS.items():
        for w in words:
            if _normalize_text(w) in norm_name:
                name_scores[t] += 1
    by_name = _pick_type(name_scores)

    col_scores = {"sales": 0, "ads": 0, "stocks": 0}
    by_cols = None
    read_error = None
    columns: List[str] = []
    try:
        columns, _ = _read_table(path, max_rows=25)
        canon = _canonical_columns(columns)
        col_scores["sales"] = sum(1 for k in ["revenue", "profit", "orders", "buys", "sales_count", "margin", "margin_pct"] if k in canon)
        col_scores["ads"] = sum(1 for k in ["ads_spend", "roi", "ddr", "cpo"] if k in canon)
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
    if by_cols and (not chosen or col_scores.get(by_cols, 0) > name_scores.get(chosen, 0)):
        chosen = by_cols
        source = "columns" if not by_name else "columns_overrode_name"

    return {
        "path": path,
        "file": name,
        "type": chosen,
        "source": source if chosen else "unknown",
        "name_scores": name_scores,
        "column_scores": col_scores,
        "columns": columns,
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
            "profit",
            "orders",
            "buys",
            "sales_count",
            "margin",
            "margin_pct",
            "logistics",
            "penalties",
            "storage",
            "deductions",
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
            "ctr",
            "orders",
            "revenue",
            "acos",
            "romi",
            "roi",
            "ddr",
            "cpo",
        ]
        string_fields = []
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
    rows: List[Dict[str, Any]] = []
    for r in nrows:
        sku_col = canon.get("sku")
        if not sku_col:
            continue
        sku = str(r.get(sku_col, "")).strip()
        if not sku or sku.lower() == "nan":
            continue
        item: Dict[str, Any] = {"sku": sku}
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

            if item.get("revenue") is not None and item.get("profit") is None:
                logistics = float(item.get("logistics") or 0.0)
                penalties = float(item.get("penalties") or 0.0)
                storage = float(item.get("storage") or 0.0)
                deductions = float(item.get("deductions") or 0.0)
                item["profit"] = float(item["revenue"]) - logistics - penalties - storage - deductions
        elif report_type == "stocks":
            ignored_columns = set(canon.values())
            ignored_columns.add(canon.get("seller_sku", ""))
            stock_map = _extract_stock_by_warehouse_map(r, ncols, ignored_columns)
            if stock_map:
                item["stock_by_warehouse"] = stock_map

        rows.append(item)
    return rows, missing, matched_columns


def _load_report(path: str, report_type: str) -> Tuple[List[Dict[str, Any]], List[str], Dict[str, str]]:
    cols, recs = _read_table(path)
    if not cols and not recs:
        return [], ["empty_table"], {}
    return _rows_from_table(cols, recs, report_type)


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
        matched: Dict[str, str] = {}
        for p in paths:
            name = os.path.basename(p)
            if primary_only and p != primary_only:
                warnings.append({"code": "input_file_skipped", "message": f"Skipped {name}: non-primary sales source"})
                continue
            try:
                rows, missing, matched_columns = _load_report(p, report_type)
                if rows:
                    target.extend(rows)
                    if report_type == "sales" and p == primary_only:
                        matched = matched_columns
                else:
                    warnings.append({"code": "input_file_skipped", "message": f"Skipped {name}: no usable rows for {report_type}"})
                if missing:
                    warnings.append({"code": "required_columns_missing", "message": f"{report_type} report missing required columns {', '.join(missing)} in {name}"})
            except Exception as e:
                warnings.append({"code": "input_file_read_error", "message": f"Cannot read {name}: {e}"})
                warnings.append({"code": "input_file_skipped", "message": f"Skipped {name}: read error"})
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

    if not discovered["sales"] or not sales_rows:
        warnings.append({"code": "sales_report_missing", "message": "No valid sales report found in input/."})
    if not discovered["ads"] or not ads_rows:
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
            "discovered": discovered,
            "details": details,
            "primary_sales_source": primary_sales_source,
            "primary_sales_columns": primary_sales_columns,
            "loaded_rows": {"sales": len(sales_rows), "ads": len(ads_rows), "stocks": len(stocks_rows)},
        },
    }


def build_metrics_from_reports(sales_rows: List[Dict[str, Any]], ads_rows: List[Dict[str, Any]], stocks_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    def _row_profit_value(row: Dict[str, Any]) -> float:
        if row.get("profit") is not None:
            return float(row.get("profit") or 0.0)
        return (
            float(row.get("revenue") or 0.0)
            - float(row.get("logistics") or 0.0)
            - float(row.get("penalties") or 0.0)
            - float(row.get("storage") or 0.0)
            - float(row.get("deductions") or 0.0)
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

    sales_split = split_assigned_vs_unassigned_rows(sales_rows)
    ads_split = split_assigned_vs_unassigned_rows(ads_rows)
    stocks_split = split_assigned_vs_unassigned_rows(stocks_rows)

    valid_sales_rows = sales_split["assigned"]
    valid_ads_rows = ads_split["assigned"]
    valid_stocks_rows = stocks_split["assigned"]
    invalid_sku_rows = len(sales_split["unassigned"]) + len(ads_split["unassigned"]) + len(stocks_split["unassigned"])

    unassigned_costs = {
        "revenue": 0.0,
        "profit": 0.0,
        "logistics": 0.0,
        "penalties": 0.0,
        "storage": 0.0,
        "deductions": 0.0,
        "ads_spend": 0.0,
        "rows": len(sales_split["unassigned"]),
    }
    for row in sales_split["unassigned"]:
        revenue = float(row.get("revenue") or 0.0)
        logistics = float(row.get("logistics") or 0.0)
        penalties = float(row.get("penalties") or 0.0)
        storage = float(row.get("storage") or 0.0)
        deductions = float(row.get("deductions") or 0.0)
        row_profit = _row_profit_value(row)

        unassigned_costs["revenue"] += revenue
        unassigned_costs["profit"] += row_profit
        unassigned_costs["logistics"] += logistics
        unassigned_costs["penalties"] += penalties
        unassigned_costs["storage"] += storage
        unassigned_costs["deductions"] += deductions

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
            "logistics_component": round(float(row.get("logistics") or 0.0), 2),
            "storage_component": round(float(row.get("storage") or 0.0), 2),
            "deductions_component": round(float(row.get("deductions") or 0.0), 2),
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
                "logistics": 0.0,
                "penalties": 0.0,
                "storage": 0.0,
                "deductions": 0.0,
                "_roi": [],
                "_romi": [],
                "_acos": [],
                "_ctr": [],
                "_ddr": [],
                "_cpo": [],
            }
        return bucket[s]

    for row in valid_sales_rows:
        sku = str(row.get("sku") or "").strip()
        if not sku:
            continue
        item = _sku(sku)
        item["revenue"] += float(row.get("revenue") or 0.0)
        item["profit"] += _row_profit_value(row)
        item["orders"] += float(row.get("orders") or 0.0)
        item["buys"] += float(row.get("buys") or 0.0)
        item["sales_count"] += float(row.get("sales_count") or 0.0)
        item["logistics"] += float(row.get("logistics") or 0.0)
        item["penalties"] += float(row.get("penalties") or 0.0)
        item["storage"] += float(row.get("storage") or 0.0)
        item["deductions"] += float(row.get("deductions") or 0.0)

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
        if row.get("roi") is not None:
            item["_roi"].append(float(row["roi"]))
        if row.get("romi") is not None:
            item["_romi"].append(float(row["romi"]))
        if row.get("acos") is not None:
            item["_acos"].append(float(row["acos"]))
        if row.get("ctr") is not None:
            item["_ctr"].append(float(row["ctr"]))
        if row.get("ddr") is not None:
            item["_ddr"].append(float(row["ddr"]))
        if row.get("cpo") is not None:
            item["_cpo"].append(float(row["cpo"]))

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
        ddr = row["_ddr"]
        cpo = row["_cpo"]

        orders_value = int(round(float(row["orders"])))
        buys_value = int(round(float(row["buys"]) if float(row["buys"]) > 0 else float(row["sales_count"])))
        sales_count_value = int(round(float(row["sales_count"]) if float(row["sales_count"]) > 0 else float(row["buys"])))
        has_sales_activity = bool(orders_value > 0 or buys_value > 0 or sales_count_value > 0)
        revenue_attribution_zero = bool(has_sales_activity and abs(revenue) < 1e-9)
        if revenue_attribution_zero:
            zero_revenue_activity_skus.append(sku)

        row_financial_status = "data_issue" if revenue_attribution_zero else "ok"
        sku_metrics.append(
            {
                "sku": sku,
                "revenue": round(revenue, 2),
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
                "logistics": round(float(row["logistics"]), 2),
                "penalties": round(float(row["penalties"]), 2),
                "storage": round(float(row["storage"]), 2),
                "deductions": round(float(row["deductions"]), 2),
                "margin_pct": round(margin_pct, 2),
                "roi": round(sum(roi) / len(roi), 2) if roi else None,
                "romi": round(sum(romi) / len(romi), 2) if romi else None,
                "acos": round(sum(acos) / len(acos), 2) if acos else None,
                "ctr": round(sum(ctr) / len(ctr), 2) if ctr else None,
                "ddr": round(sum(ddr) / len(ddr), 2) if ddr else None,
                "cpo": round(sum(cpo) / len(cpo), 2) if cpo else None,
                "has_sales_activity": has_sales_activity,
                "revenue_attribution_zero": revenue_attribution_zero,
                "financial_status": row_financial_status,
            }
        )

    sku_metrics.sort(key=lambda x: (float(x.get("profit", 0.0)), float(x.get("revenue", 0.0))), reverse=True)

    valid_revenue = sum(float(row.get("revenue") or 0.0) for row in valid_sales_rows)
    valid_sales_profit_before_ads = sum(_row_profit_value(row) for row in valid_sales_rows)
    valid_ads_spend = sum(float(row.get("ads_spend") or 0.0) for row in valid_ads_rows)
    valid_logistics = sum(float(row.get("logistics") or 0.0) for row in valid_sales_rows)
    valid_storage = sum(float(row.get("storage") or 0.0) for row in valid_sales_rows)
    valid_penalties = sum(float(row.get("penalties") or 0.0) for row in valid_sales_rows)
    valid_deductions = sum(float(row.get("deductions") or 0.0) for row in valid_sales_rows)

    total_ads_impressions = sum(float(row.get("impressions") or 0.0) for row in ads_rows)
    total_ads_clicks = sum(float(row.get("clicks") or 0.0) for row in ads_rows)
    total_ads_orders = sum(float(row.get("orders") or row.get("sales_count") or row.get("buys") or 0.0) for row in ads_rows)
    total_ads_revenue = sum(float(row.get("revenue") or 0.0) for row in ads_rows)
    avg_ads_ctr = sum(float(row.get("ctr") or 0.0) for row in ads_rows if row.get("ctr") is not None)
    avg_ads_ctr_count = sum(1 for row in ads_rows if row.get("ctr") is not None)

    unassigned_revenue = float(unassigned_costs["revenue"])
    unassigned_profit = float(unassigned_costs["profit"]) - float(unassigned_costs["ads_spend"])

    sku_assigned_profit = valid_sales_profit_before_ads - valid_ads_spend
    total_revenue = valid_revenue + unassigned_revenue
    total_profit = sku_assigned_profit + unassigned_profit

    total_orders = sum(float(row.get("orders") or 0.0) for row in sales_rows)
    total_buys = sum(
        float(row.get("buys") or row.get("sales_count") or row.get("orders") or 0.0)
        for row in sales_rows
    )
    total_stock = sum(float(row.get("stock") or 0.0) for row in stocks_rows)

    totals = {
        "revenue": round(total_revenue, 2),
        "profit": round(total_profit, 2),
        "orders": int(round(total_orders)),
        "buys": int(round(total_buys)),
        "stock": int(round(total_stock)),
        "ads_spend": round(valid_ads_spend + float(unassigned_costs["ads_spend"]), 2),
        "logistics": round(valid_logistics + float(unassigned_costs["logistics"]), 2),
        "storage": round(valid_storage + float(unassigned_costs["storage"]), 2),
        "penalties": round(valid_penalties + float(unassigned_costs["penalties"]), 2),
        "deductions": round(valid_deductions + float(unassigned_costs["deductions"]), 2),
        "ads_impressions": int(round(total_ads_impressions)),
        "ads_clicks": int(round(total_ads_clicks)),
        "ads_ctr": round(
            (float(total_ads_clicks) / float(total_ads_impressions) * 100.0)
            if total_ads_impressions > 0
            else ((avg_ads_ctr / float(avg_ads_ctr_count)) if avg_ads_ctr_count > 0 else 0.0),
            2,
        ),
        "ads_orders": int(round(total_ads_orders)),
        "ads_revenue": round(total_ads_revenue, 2),
        "ads_acos": round(
            ((valid_ads_spend + float(unassigned_costs["ads_spend"])) / total_ads_revenue * 100.0)
            if total_ads_revenue > 0
            else 0.0,
            2,
        ),
        "ads_romi": round(
            ((total_ads_revenue - (valid_ads_spend + float(unassigned_costs["ads_spend"])))
            / (valid_ads_spend + float(unassigned_costs["ads_spend"])) * 100.0)
            if (valid_ads_spend + float(unassigned_costs["ads_spend"])) > 0
            else 0.0,
            2,
        ),
        "sku_assigned_revenue": round(valid_revenue, 2),
        "unassigned_revenue": round(unassigned_revenue, 2),
        "total_revenue": round(total_revenue, 2),
        "sku_assigned_profit": round(sku_assigned_profit, 2),
        "unassigned_profit": round(unassigned_profit, 2),
        "total_profit": round(total_profit, 2),
    }

    unassigned_costs = {
        "revenue": round(float(unassigned_costs["revenue"]), 2),
        "profit": round(float(unassigned_profit), 2),
        "logistics": round(float(unassigned_costs["logistics"]), 2),
        "penalties": round(float(unassigned_costs["penalties"]), 2),
        "storage": round(float(unassigned_costs["storage"]), 2),
        "deductions": round(float(unassigned_costs["deductions"]), 2),
        "ads_spend": round(float(unassigned_costs["ads_spend"]), 2),
        "rows": int(unassigned_costs["rows"]),
    }

    unassigned_costs_present = bool(
        unassigned_costs["rows"] > 0
        or abs(unassigned_costs["revenue"]) > 0
        or abs(unassigned_costs["profit"]) > 0
        or abs(unassigned_costs["logistics"]) > 0
        or abs(unassigned_costs["penalties"]) > 0
        or abs(unassigned_costs["storage"]) > 0
        or abs(unassigned_costs["deductions"]) > 0
        or abs(unassigned_costs["ads_spend"]) > 0
    )
    financial_status, ai_reliability = _financial_status(
        invalid_rows=int(invalid_sku_rows),
        unassigned_present=unassigned_costs_present,
        unassigned_profit=float(unassigned_costs["profit"]),
        total_profit=float(totals["total_profit"]),
        zero_revenue_activity_count=len(zero_revenue_activity_skus),
    )

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
    }

    return {
        "sku_metrics": sku_metrics,
        "totals": totals,
        "unassigned_costs": unassigned_costs,
        "data_quality": data_quality,
        "financial_debug": financial_debug,
        "financial": {
            "revenue": totals["total_revenue"],
            "profit": totals["total_profit"],
            "ads_spend": totals["ads_spend"],
            "logistics": totals["logistics"],
            "storage": totals["storage"],
            "penalties": totals["penalties"],
            "deductions": totals["deductions"],
        },
        "funnel": {"orders": totals["orders"], "buys": totals["buys"]},
        "ads": {
            "spend": totals["ads_spend"],
            "impressions": totals["ads_impressions"],
            "clicks": totals["ads_clicks"],
            "ctr": totals["ads_ctr"],
            "orders": totals["ads_orders"],
            "revenue": totals["ads_revenue"],
            "acos": totals["ads_acos"],
            "romi": totals["ads_romi"],
        },
        "stock": {"total_stock": totals["stock"]},
    }


def build_facts_from_reports(seller_id: str, run_date: str, seller_name: str, metrics: Dict[str, Any], discovered_files: Dict[str, List[str]], warnings: List[Dict[str, Any]], source_mode: str) -> Dict[str, Any]:
    totals = metrics.get("totals", {}) if isinstance(metrics, dict) else {}
    data_quality = metrics.get("data_quality", {}) if isinstance(metrics, dict) else {}
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

    if source_mode == "fallback_mock":
        confidence = "low"
    elif severe & effective:
        confidence = "low"
    elif medium & effective:
        confidence = "medium"
    else:
        confidence = "high"

    if financial_status == "partial":
        confidence = "low"
    elif financial_status == "degraded" and confidence == "high":
        confidence = "medium"
    elif (invalid_sku_rows > 0 or unassigned_present) and confidence == "high":
        confidence = "medium"

    return {
        "seller_id": seller_id,
        "seller_name": seller_name,
        "run_date": run_date,
        "generated_at": _utc_now_iso(),
        "data_confidence": confidence,
        "source_mode": source_mode,
        "input_summary": {
            "sales_files_found": len(discovered_files.get("sales", [])),
            "ads_files_found": len(discovered_files.get("ads", [])),
            "stocks_files_found": len(discovered_files.get("stocks", [])),
            "unknown_files_found": len(discovered_files.get("unknown", [])),
            "source_mode": source_mode,
            "confidence": confidence,
        },
        "kpi": {
            "revenue": float(totals.get("total_revenue", totals.get("revenue", 0.0)) or 0.0),
            "profit": float(totals.get("total_profit", totals.get("profit", 0.0)) or 0.0),
            "orders": int(totals.get("orders", 0) or 0),
            "buyouts": int(totals.get("buys", 0) or 0),
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
            "zero_revenue_activity_sku_count": int(data_quality.get("zero_revenue_activity_sku_count", 0) or 0),
            "zero_revenue_activity_skus": data_quality.get("zero_revenue_activity_skus", []),
        },
    }
