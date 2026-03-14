from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

from ..api.endpoints import SALES
from ..api.wb_client import WBApiClient
from ..validation.sku_normalization import normalize_sku


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
    return str(normalize_sku(value) or "")


def _pick_text(row: Dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _row_date_iso(row: Dict[str, Any]) -> str:
    for key in ("date", "lastChangeDate", "sale_dt", "saleDate", "createdAt"):
        raw = str(row.get(key) or "").strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", raw):
            return raw[:10]
    return ""


def load_sales_from_api(client: WBApiClient, date_from: str, date_to: str) -> Dict[str, Any]:
    response = client.request_json(
        endpoint=SALES,
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
            nm_id
            or row.get("nmId")
            or row.get("nm_id")
            or row.get("nmid")
            or row.get("supplierArticle")
            or row.get("vendorCode")
            or row.get("barcode")
        )
        order_ref = _pick_text(row, ("srid", "saleID", "saleId", "gNumber", "odid"))
        quantity = _as_float(
            row.get("quantity")
            or row.get("sa_quantity")
            or row.get("saleQty")
            or row.get("sales_qty"),
            default=0.0,
        )
        if quantity <= 0:
            quantity = 1.0 if order_ref else 0.0
        revenue = _as_float(
            row.get("revenue")
            or row.get("forPay")
            or row.get("totalPrice")
            or row.get("finishedPrice")
            or row.get("priceWithDisc"),
            default=0.0,
        )
        warehouse = _pick_text(row, ("warehouseName", "warehouse", "officeName", "oblastOkrugName"))

        item: Dict[str, Any] = {
            "date": row_date,
            "sku": sku,
            "nm_id": nm_id,
            "quantity": quantity,
            "revenue": round(revenue, 2),
            "order_ref": order_ref,
            "warehouse": warehouse,
            "_sku_source_field": "nm_id" if sku and sku == _as_sku(nm_id) else "supplierArticle",
            "price": round(revenue, 2),
            "profit": round(revenue, 2),
            "orders": quantity,
            "buys": quantity,
            "sales_count": quantity,
            "cost_price": 0.0,
            "wb_commission": 0.0,
            "logistics": 0.0,
            "penalties": 0.0,
            "storage": 0.0,
            "deductions": 0.0,
            "_raw_row_index": index,
            "_source_dataset": "sales_api",
        }
        rows.append(item)

    api_debug = {
        "endpoint": SALES.name,
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
