from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping


SOURCE_KEYS = ("orders", "sales", "stocks", "finance", "supplier_goods", "funnel_goods")

SKU_FACT_FIELDS = (
    "sku",
    "vendor_code",
    "nm_id",
    "name",
    "orders_qty",
    "orders_revenue",
    "sales_qty",
    "sales_revenue",
    "realized_sales_qty",
    "realized_revenue",
    "stock_qty_live",
    "stock_snapshot_date",
    "stock_wb_qty",
    "stock_mp_qty",
    "stock_total_qty",
    "stock_value",
    "source_flags",
)


def _safe_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first_text(row: Mapping[str, Any], keys: Iterable[str]) -> str | None:
    for key in keys:
        if key not in row:
            continue
        value = _safe_text(row.get(key))
        if value is not None:
            return value
    return None


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().replace("\u00a0", "").replace(" ", "").replace(",", ".")
        if value == "":
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_number(row: Mapping[str, Any], keys: Iterable[str]) -> float | None:
    for key in keys:
        if key not in row:
            continue
        value = row.get(key)
        if value is None:
            continue
        if isinstance(value, str) and value.strip() == "":
            continue
        parsed = _safe_float(value)
        if parsed is not None:
            return parsed
    return None


def _sum_metric(current: Any, increment: float | None) -> float | None:
    if increment is None:
        return _safe_float(current)
    existing = _safe_float(current)
    if existing is None:
        return round(float(increment), 2)
    return round(existing + float(increment), 2)


def _set_if_missing(fact: Dict[str, Any], field: str, value: Any) -> None:
    if value is None or value == "":
        return
    if fact.get(field) in (None, ""):
        fact[field] = value


def _new_fact() -> Dict[str, Any]:
    fact = {field: None for field in SKU_FACT_FIELDS if field != "source_flags"}
    fact["source_flags"] = {key: False for key in SOURCE_KEYS}
    return fact


def _row_identity(row: Mapping[str, Any]) -> Dict[str, str | None]:
    nm_id = _first_text(row, ("nm_id", "nmId", "nmID", "nmid", "nm"))
    vendor_code = _first_text(
        row,
        (
            "vendor_code",
            "vendorCode",
            "seller_sku",
            "sellerSku",
            "supplierArticle",
            "supplier_article",
            "offer_id",
        ),
    )
    sku = _first_text(row, ("sku", "article", "barcode", "vendor_code", "seller_sku", "supplierArticle"))
    if sku is None:
        sku = nm_id or vendor_code
    name = _first_text(row, ("name", "title", "nmName", "subject_name", "subjectName"))
    return {
        "nm_id": nm_id,
        "vendor_code": vendor_code,
        "sku": sku,
        "name": name,
    }


def _identity_aliases(identity: Mapping[str, Any]) -> List[str]:
    aliases: List[str] = []
    nm_id = _safe_text(identity.get("nm_id"))
    vendor_code = _safe_text(identity.get("vendor_code"))
    sku = _safe_text(identity.get("sku"))
    if nm_id:
        aliases.append(f"nm:{nm_id}")
    if vendor_code:
        aliases.append(f"vendor:{vendor_code}")
    if sku:
        aliases.append(f"sku:{sku}")
    return aliases


def _merge_fact_values(primary: Dict[str, Any], secondary: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in secondary.items():
        if key == "source_flags":
            flags = primary.setdefault("source_flags", {name: False for name in SOURCE_KEYS})
            for source_key, enabled in dict(value or {}).items():
                flags[source_key] = bool(flags.get(source_key, False) or enabled)
            continue
        if primary.get(key) in (None, "") and value not in (None, ""):
            primary[key] = value
    return primary


def _get_fact(
    facts: Dict[str, Dict[str, Any]],
    alias_index: Dict[str, str],
    identity: Mapping[str, Any],
) -> Dict[str, Any] | None:
    aliases = _identity_aliases(identity)
    if not aliases:
        return None

    matched_keys = [alias_index[alias] for alias in aliases if alias in alias_index]
    primary_key = matched_keys[0] if matched_keys else aliases[0]
    if primary_key not in facts:
        facts[primary_key] = _new_fact()

    for duplicate_key in set(matched_keys[1:]):
        if duplicate_key == primary_key or duplicate_key not in facts:
            continue
        facts[primary_key] = _merge_fact_values(facts[primary_key], facts.pop(duplicate_key))
        for alias, key in list(alias_index.items()):
            if key == duplicate_key:
                alias_index[alias] = primary_key

    fact = facts[primary_key]
    _set_if_missing(fact, "nm_id", identity.get("nm_id"))
    _set_if_missing(fact, "vendor_code", identity.get("vendor_code"))
    _set_if_missing(fact, "sku", identity.get("sku") or identity.get("vendor_code") or identity.get("nm_id"))
    _set_if_missing(fact, "name", identity.get("name"))
    for alias in aliases:
        alias_index[alias] = primary_key
    return fact


def _mark_source(fact: Dict[str, Any], source_key: str) -> None:
    flags = fact.setdefault("source_flags", {key: False for key in SOURCE_KEYS})
    flags[source_key] = True


def _rows(items: Any) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []
    return [dict(item) for item in items if isinstance(item, Mapping)]


def _add_orders(
    facts: Dict[str, Dict[str, Any]],
    alias_index: Dict[str, str],
    rows: List[Dict[str, Any]],
) -> None:
    for row in rows:
        fact = _get_fact(facts, alias_index, _row_identity(row))
        if fact is None:
            continue
        _mark_source(fact, "orders")
        qty = _first_number(row, ("orders_qty", "order_qty", "quantity", "qty", "orders", "orders_count", "orderCount"))
        revenue = _first_number(
            row,
            (
                "orders_revenue",
                "orders_amount",
                "order_revenue",
                "amount",
                "priceWithDisc",
                "finishedPrice",
                "totalPrice",
                "convertedPrice",
                "price",
            ),
        )
        fact["orders_qty"] = _sum_metric(fact.get("orders_qty"), qty)
        fact["orders_revenue"] = _sum_metric(fact.get("orders_revenue"), revenue)


def _add_sales(
    facts: Dict[str, Dict[str, Any]],
    alias_index: Dict[str, str],
    rows: List[Dict[str, Any]],
) -> None:
    for row in rows:
        fact = _get_fact(facts, alias_index, _row_identity(row))
        if fact is None:
            continue
        _mark_source(fact, "sales")
        qty = _first_number(
            row,
            ("sales_qty", "sale_qty", "quantity", "qty", "sales", "sales_count", "saleQty", "sa_quantity"),
        )
        revenue = _first_number(
            row,
            (
                "sales_revenue",
                "sales_amount",
                "amount",
                "priceWithDisc",
                "finishedPrice",
                "totalPrice",
                "forPay",
                "revenue",
            ),
        )
        fact["sales_qty"] = _sum_metric(fact.get("sales_qty"), qty)
        fact["sales_revenue"] = _sum_metric(fact.get("sales_revenue"), revenue)


def _add_stocks(
    facts: Dict[str, Dict[str, Any]],
    alias_index: Dict[str, str],
    rows: List[Dict[str, Any]],
    *,
    default_snapshot_date: Any = None,
) -> None:
    for row in rows:
        fact = _get_fact(facts, alias_index, _row_identity(row))
        if fact is None:
            continue
        _mark_source(fact, "stocks")
        qty = _first_number(
            row,
            ("stock_qty_live", "stock", "total_units", "quantityFull", "quantity_full", "quantity", "qty", "stocks"),
        )
        snapshot_date = _first_text(row, ("stock_snapshot_date", "snapshot_date", "date", "lastChangeDate")) or _safe_text(
            default_snapshot_date
        )
        fact["stock_qty_live"] = _sum_metric(fact.get("stock_qty_live"), qty)
        if snapshot_date is not None and (
            fact.get("stock_snapshot_date") in (None, "") or snapshot_date > str(fact.get("stock_snapshot_date"))
        ):
            fact["stock_snapshot_date"] = snapshot_date[:10]


def _finance_is_sale_like(row: Mapping[str, Any]) -> bool:
    if any(key in row for key in ("realized_sales_qty", "realized_sales_revenue", "realized_revenue")):
        return True
    text = " ".join(
        str(row.get(key) or "").strip().lower()
        for key in ("row_group", "operation_name", "operationName", "sellerOperName", "docTypeName")
        if str(row.get(key) or "").strip()
    )
    if not text:
        return False
    return any(marker in text for marker in ("sale", "sales", "realization", "продаж", "реализац"))


def _add_finance(
    facts: Dict[str, Dict[str, Any]],
    alias_index: Dict[str, str],
    rows: List[Dict[str, Any]],
) -> None:
    for row in rows:
        fact = _get_fact(facts, alias_index, _row_identity(row))
        if fact is None:
            continue
        _mark_source(fact, "finance")
        if not _finance_is_sale_like(row):
            continue
        qty = _first_number(row, ("realized_sales_qty", "sales_qty", "quantity", "qty", "saleQty"))
        revenue = _first_number(
            row,
            (
                "realized_revenue",
                "realized_sales_revenue",
                "gross_revenue",
                "retailAmount",
                "saleAmount",
                "priceWithDisc",
                "finishedPrice",
            ),
        )
        fact["realized_sales_qty"] = _sum_metric(fact.get("realized_sales_qty"), qty)
        fact["realized_revenue"] = _sum_metric(fact.get("realized_revenue"), revenue)


def _add_goods_stock(
    facts: Dict[str, Dict[str, Any]],
    alias_index: Dict[str, str],
    rows: List[Dict[str, Any]],
    *,
    source_key: str,
) -> None:
    for row in rows:
        fact = _get_fact(facts, alias_index, _row_identity(row))
        if fact is None:
            continue
        _mark_source(fact, source_key)
        stock_wb_qty = _first_number(row, ("stock_wb_qty", "wb_stock_qty", "stock_wb", "stocks_wb", "wb_qty"))
        stock_mp_qty = _first_number(row, ("stock_mp_qty", "mp_stock_qty", "stock_mp", "stocks_mp", "mp_qty"))
        stock_value = _first_number(row, ("stock_value", "stock_value_rub", "stock_amount", "stock_sum", "value"))
        explicit_total = _first_number(row, ("stock_total_qty", "total_stock_qty", "stock_qty_total", "total_qty"))

        fact["stock_wb_qty"] = _sum_metric(fact.get("stock_wb_qty"), stock_wb_qty)
        fact["stock_mp_qty"] = _sum_metric(fact.get("stock_mp_qty"), stock_mp_qty)
        fact["stock_value"] = _sum_metric(fact.get("stock_value"), stock_value)
        fact["stock_total_qty"] = _sum_metric(fact.get("stock_total_qty"), explicit_total)


def _finalize_fact(row: Dict[str, Any]) -> Dict[str, Any]:
    out = {field: row.get(field) for field in SKU_FACT_FIELDS}
    if out.get("sku") in (None, ""):
        out["sku"] = out.get("vendor_code") or out.get("nm_id")
    if out.get("stock_total_qty") is None and (out.get("stock_wb_qty") is not None or out.get("stock_mp_qty") is not None):
        out["stock_total_qty"] = round(float(out.get("stock_wb_qty") or 0.0) + float(out.get("stock_mp_qty") or 0.0), 2)
    if out.get("orders_qty") is not None:
        out["orders"] = out.get("orders_qty")
    if out.get("orders_revenue") is not None:
        out["orders_amount"] = out.get("orders_revenue")
    if out.get("sales_revenue") is not None:
        out["sales_amount"] = out.get("sales_revenue")
    if out.get("stock_qty_live") is not None:
        out["stock"] = out.get("stock_qty_live")
    revenue = out.get("realized_revenue")
    if revenue is None:
        revenue = out.get("sales_revenue")
    if revenue is None:
        revenue = out.get("orders_revenue")
    if revenue is not None:
        out["revenue"] = revenue
    return out


def build_sku_fact_table(
    *,
    orders_rows: Any = None,
    sales_rows: Any = None,
    stocks_rows: Any = None,
    finance_rows: Any = None,
    supplier_goods_rows: Any = None,
    funnel_goods_rows: Any = None,
    stock_snapshot_date: Any = None,
) -> Dict[str, Any]:
    facts: Dict[str, Dict[str, Any]] = {}
    alias_index: Dict[str, str] = {}

    normalized_orders = _rows(orders_rows)
    normalized_sales = _rows(sales_rows)
    normalized_stocks = _rows(stocks_rows)
    normalized_finance = _rows(finance_rows)
    normalized_supplier_goods = _rows(supplier_goods_rows)
    normalized_funnel_goods = _rows(funnel_goods_rows)

    _add_orders(facts, alias_index, normalized_orders)
    _add_sales(facts, alias_index, normalized_sales)
    _add_stocks(facts, alias_index, normalized_stocks, default_snapshot_date=stock_snapshot_date)
    _add_finance(facts, alias_index, normalized_finance)
    _add_goods_stock(facts, alias_index, normalized_supplier_goods, source_key="supplier_goods")
    _add_goods_stock(facts, alias_index, normalized_funnel_goods, source_key="funnel_goods")

    rows = [_finalize_fact(row) for row in facts.values()]
    rows.sort(key=lambda item: (str(item.get("nm_id") or ""), str(item.get("sku") or "")))

    source_flags = {
        "orders": bool(normalized_orders),
        "sales": bool(normalized_sales),
        "stocks": bool(normalized_stocks),
        "finance": bool(normalized_finance),
        "supplier_goods": bool(normalized_supplier_goods),
        "funnel_goods": bool(normalized_funnel_goods),
    }
    return {
        "sku_metrics": rows,
        "rows": rows,
        "source_flags": source_flags,
        "summary": {
            "sku_rows_count": len(rows),
            "sources": dict(source_flags),
        },
        "warnings": [],
    }


def build_sku_fact_rows(**kwargs: Any) -> List[Dict[str, Any]]:
    return list(build_sku_fact_table(**kwargs).get("sku_metrics", []))
