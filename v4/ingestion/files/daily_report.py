"""Daily local report parser for audit mode.

Input: file path.
Output: raw parsed rows + derived rows for realization/sales/orders.
Does not normalize and does not compute KPI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...core.contracts import SourceKind, SourceStatus, SourceStatusCode
from .registry import read_tabular_rows


def _pick(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in row and row.get(key) not in (None, ""):
            return row.get(key)
    return None


def _reason_text(row: dict[str, Any]) -> str:
    value = _pick(
        row,
        (
            "Обоснование для оплаты",
            "reason",
            "payment_reason",
            "supplier_oper_name",
            "operationType",
            "operation_type",
        ),
    )
    return str(value or "").strip()


def _is_sale_reason(reason: str) -> bool:
    text = reason.lower()
    return any(token in text for token in ("продаж", "sale", "реализац"))


def _is_return_reason(reason: str) -> bool:
    text = reason.lower()
    return "возврат" in text or "return" in text


def parse(path: str) -> tuple[dict[str, Any], SourceStatus]:
    file_path = Path(path)
    warnings: list[str] = []

    try:
        rows = read_tabular_rows(file_path)
    except Exception as exc:
        status = SourceStatus(
            source_name="daily_report",
            kind=SourceKind.FILE,
            status=SourceStatusCode.ERROR,
            is_required=True,
            rows_loaded=None,
            error_code="daily_report_parse_failed",
            error_message=str(exc),
            warnings=["daily report parse failed"],
            debug={"path": str(file_path)},
        )
        return {"rows": []}, status

    sales_rows: list[dict[str, Any]] = []
    orders_rows: list[dict[str, Any]] = []
    stocks_rows: list[dict[str, Any]] = []

    for row in rows:
        reason = _reason_text(row)
        qty = _pick(row, ("Кол-во", "quantity", "qty"))
        sale_date = _pick(row, ("Дата продажи", "sale_date", "sale_dt", "date"))
        order_date = _pick(row, ("Дата заказа покупателем", "order_date", "order_dt"))

        if _is_sale_reason(reason) or _is_return_reason(reason):
            sales_rows.append(
                {
                    "operationType": reason or "sale",
                    "sale_amount": _pick(
                        row,
                        (
                            "Вайлдберриз реализовал Товар (Пр)",
                            "sale_amount",
                            "revenue",
                            "retail_amount",
                        ),
                    ),
                    "forPay": _pick(
                        row,
                        (
                            "К перечислению Продавцу за реализованный Товар",
                            "forPay",
                            "payout",
                        ),
                    ),
                    "quantity": qty,
                    "date": sale_date,
                    "nmId": _pick(row, ("Код номенклатуры", "nmId", "nm_id")),
                }
            )
            orders_rows.append(
                {
                    "quantity": qty,
                    "date": order_date or sale_date,
                    "price": _pick(
                        row,
                        (
                            "Цена розничная",
                            "Цена розничная с учетом согласованной скидки",
                            "price",
                            "retail_price",
                        ),
                    ),
                    "nmId": _pick(row, ("Код номенклатуры", "nmId", "nm_id")),
                }
            )

        stock_qty = _pick(row, ("Остаток", "stock_qty", "stock", "quantity_stock"))
        if stock_qty not in (None, ""):
            stocks_rows.append(
                {
                    "nmId": _pick(row, ("Код номенклатуры", "nmId", "nm_id")),
                    "warehouseName": _pick(row, ("Склад", "warehouse", "warehouseName")),
                    "quantity": stock_qty,
                    "date": sale_date,
                }
            )

    status_code = SourceStatusCode.OK if rows else SourceStatusCode.MISSING
    if rows and (not sales_rows or not orders_rows):
        warnings.append("daily report parsed, but derived sales/orders rows are limited")

    status = SourceStatus(
        source_name="daily_report",
        kind=SourceKind.FILE,
        status=status_code,
        is_required=True,
        rows_loaded=len(rows) if rows else None,
        warnings=warnings,
        debug={
            "path": str(file_path),
            "rows_total": len(rows),
            "sales_rows": len(sales_rows),
            "orders_rows": len(orders_rows),
            "stocks_rows": len(stocks_rows),
        },
    )

    payload = {
        "rows": rows,
        "sales_rows": sales_rows,
        "orders_rows": orders_rows,
        "stocks_rows": stocks_rows,
    }
    return payload, status
