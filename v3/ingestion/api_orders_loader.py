from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

from ..api.endpoints import ORDERS
from ..api.wb_client import WBApiClient


def _as_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return default
    text = text.replace(" ", "").replace(",", ".")
    try:
        return float(text)
    except Exception:
        return default


def _as_sku(value: Any) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"\d+(\.0+)?", text):
        return text.split(".", 1)[0]
    return text


def _pick_text(row: Dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _row_date_iso(row: Dict[str, Any]) -> str:
    for key in ("date", "lastChangeDate", "order_dt", "createdAt"):
        raw = str(row.get(key) or "").strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", raw):
            return raw[:10]
    return ""


def load_orders_from_api(client: WBApiClient, date_from: str, date_to: str) -> Dict[str, Any]:
    response = client.request_json(
        endpoint=ORDERS,
        params={"dateFrom": date_from},
        allow_204=True,
        empty_on_204=[],
    )
    payload = response.get("payload", [])
    rows_raw = client.extract_rows(payload, ("data", "items", "rows"))

    rows: List[Dict[str, Any]] = []
    for index, row in enumerate(rows_raw):
        row_date = _row_date_iso(row)
        if row_date and row_date > date_to:
            continue
        nm_id = _pick_text(row, ("nmId", "nm_id", "nmid", "nmID"))
        sku = _as_sku(
            row.get("supplierArticle")
            or row.get("vendorCode")
            or row.get("barcode")
            or nm_id
        )
        order_id = _pick_text(row, ("srid", "odid", "orderId", "gNumber", "orderUID"))
        quantity = _as_float(
            row.get("quantity")
            or row.get("orderQty")
            or row.get("orderCount")
            or row.get("ordersCount")
            or row.get("orders"),
            default=0.0,
        )
        if quantity <= 0:
            quantity = 1.0 if order_id else 0.0
        price = _as_float(
            row.get("totalPrice")
            or row.get("priceWithDisc")
            or row.get("finishedPrice")
            or row.get("convertedPrice")
            or row.get("price"),
            default=0.0,
        )
        warehouse = _pick_text(row, ("warehouseName", "warehouse", "officeName", "oblastOkrugName"))

        item: Dict[str, Any] = {
            "date": row_date,
            "sku": sku,
            "nm_id": nm_id,
            "order_id": order_id,
            "srid": order_id,
            "quantity": quantity,
            "price": round(price, 2),
            "warehouse": warehouse,
            # compatibility with current metrics layer
            "revenue": round(price, 2),
            "profit": 0.0,
            "orders": quantity,
            "buys": 0.0,
            "sales_count": 0.0,
            "cost_price": 0.0,
            "wb_commission": 0.0,
            "logistics": 0.0,
            "penalties": 0.0,
            "storage": 0.0,
            "deductions": 0.0,
            "_raw_row_index": index,
            "_source_dataset": "orders_api",
        }
        rows.append(item)

    api_debug = {
        "endpoint": ORDERS.name,
        "success": bool(response.get("success", False)),
        "fail": not bool(response.get("success", False)),
        "rows_loaded": len(rows),
        "date_from": date_from,
        "date_to": date_to,
        "error_text": str(response.get("error") or ""),
        "status_code": response.get("status_code"),
        "attempts": int(response.get("attempts", 0) or 0),
    }
    return {
        "rows": rows,
        "api_debug": api_debug,
    }

