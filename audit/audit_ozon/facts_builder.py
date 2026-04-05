"""Facts builder for Ozon express audit MVP."""

from __future__ import annotations

import re
from typing import Any


SKU_TOKENS = ("sku", "артикул", "nm", "offer_id")
ORDERS_TOKENS = ("заказ", "orders", "продажи")
REVENUE_TOKENS = ("выручка", "revenue", "сумма")
STOCK_TOKENS = ("остаток", "stock", "qty")


def _norm(text: Any) -> str:
    value = str(text or "").lower().replace("\xa0", " ").strip()
    value = re.sub(r"\s+", " ", value)
    return value


def _parse_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, str):
            cleaned = value.replace(" ", "").replace(",", ".")
            return float(cleaned)
        return float(value)
    except Exception:
        return None


def _parse_int(value: Any) -> int | None:
    parsed = _parse_float(value)
    if parsed is None:
        return None
    try:
        return int(parsed)
    except Exception:
        return None


def _find_column(columns: list[str], hints: tuple[str, ...]) -> str | None:
    scored: list[tuple[int, str]] = []
    for col in columns:
        col_norm = _norm(col)
        if not col_norm:
            continue
        score = 0
        for token in hints:
            tok = _norm(token)
            if not tok:
                continue
            if col_norm == tok:
                score += 100
            elif tok in col_norm:
                score += 10
        if score > 0:
            scored.append((score, col))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def _sku_value(row: dict[str, Any], sku_col: str | None) -> str:
    if not sku_col:
        return ""
    value = row.get(sku_col)
    if value is None:
        return ""
    text = str(value).strip()
    return text


def build_ozon_facts(data: dict[str, Any]) -> dict[str, Any]:
    columns = [str(x) for x in (data.get("columns") or [])]
    rows = data.get("rows") or []
    if not isinstance(rows, list):
        rows = []

    sku_col = _find_column(columns, SKU_TOKENS)
    orders_col = _find_column(columns, ORDERS_TOKENS)
    revenue_col = _find_column(columns, REVENUE_TOKENS)
    stock_col = _find_column(columns, STOCK_TOKENS)

    sku_unique: set[str] = set()
    total_orders = 0
    total_revenue = 0.0
    revenue_known = bool(revenue_col)

    sku_rows: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        sku = _sku_value(item, sku_col)
        if sku:
            sku_unique.add(sku)

        orders = _parse_int(item.get(orders_col)) if orders_col else None
        revenue = _parse_float(item.get(revenue_col)) if revenue_col else None
        stock = _parse_float(item.get(stock_col)) if stock_col else None

        if orders is not None and orders > 0:
            total_orders += orders
        if revenue is not None:
            total_revenue += revenue

        sku_rows.append(
            {
                "sku": sku or None,
                "orders": orders,
                "revenue": revenue,
                "stock": stock,
            }
        )

    sku_count = len([x for x in sku_unique if x])

    top_source = "orders" if orders_col else "revenue" if revenue_col else ""
    sorted_rows = list(sku_rows)
    if top_source == "orders":
        sorted_rows.sort(key=lambda x: (x.get("orders") is not None, x.get("orders") or 0), reverse=True)
    elif top_source == "revenue":
        sorted_rows.sort(key=lambda x: (x.get("revenue") is not None, x.get("revenue") or 0.0), reverse=True)
    top_sku = [x for x in sorted_rows if x.get("sku")][:10]

    problem_sku: list[dict[str, Any]] = []
    for row in sku_rows:
        sku = row.get("sku")
        if not sku:
            continue
        orders = row.get("orders")
        stock = row.get("stock")
        has_no_sales = orders_col is not None and (orders is None or orders <= 0)
        has_stock = stock_col is not None and stock is not None and stock > 0
        low_turnover = (
            orders_col is not None
            and stock_col is not None
            and stock is not None
            and stock > 0
            and (orders is None or orders <= 1)
        )
        if has_no_sales or low_turnover:
            reason = "без продаж"
            if low_turnover:
                reason = "низкая оборачиваемость"
            elif has_no_sales and has_stock:
                reason = "остаток есть, продаж нет"
            problem_sku.append(
                {
                    "sku": sku,
                    "orders": orders,
                    "revenue": row.get("revenue"),
                    "stock": stock,
                    "reason": reason,
                }
            )

    problem_sku = problem_sku[:20]

    return {
        "summary": {
            "total_orders": int(total_orders),
            "total_revenue": round(total_revenue, 2) if revenue_known else None,
            "sku_count": int(sku_count),
        },
        "top_sku": top_sku,
        "problem_sku": problem_sku,
        "detected_columns": {
            "sku": sku_col,
            "orders": orders_col,
            "revenue": revenue_col,
            "stock": stock_col,
        },
        "data_quality": {
            "row_count": int(data.get("row_count") or 0),
            "has_orders": bool(orders_col),
            "has_revenue": bool(revenue_col),
            "has_stock": bool(stock_col),
        },
    }
