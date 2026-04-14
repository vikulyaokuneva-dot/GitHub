from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

from ..api.endpoints import ORDERS
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
        if row_date and (row_date < date_from or row_date > date_to):
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
        order_id = _pick_text(row, ("srid", "odid", "orderId", "gNumber", "orderUID"))
        seller_sku = _pick_text(row, ("supplierArticle", "supplier_article", "vendorCode", "sellerSku"))
        sa_name = _pick_text(row, ("subject", "subjectName", "sa_name", "nmName"))
        tech_size = _pick_text(row, ("techSize", "tech_size", "size", "tsName"))
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
        region = _pick_text(
            row,
            (
                "regionName",
                "region",
                "oblastOkrugName",
                "destinationRegion",
                "countryName",
            ),
        )
        destination = _pick_text(
            row,
            (
                "destination",
                "destinationRegion",
                "destinationCountry",
                "oblastOkrugName",
                "address",
            ),
        )
        demand_geography_available = bool(region or destination or warehouse)

        item: Dict[str, Any] = {
            "date": row_date,
            "sku": sku,
            "nm_id": nm_id,
            "seller_sku": seller_sku,
            "sa_name": sa_name,
            "tech_size": tech_size,
            "order_id": order_id,
            "srid": order_id,
            "quantity": quantity,
            "price": round(price, 2),
            "warehouse": warehouse,
            "warehouse_name": warehouse,
            "region": region,
            "destination": destination,
            "demand_geography_available": demand_geography_available,
            "_sku_source_field": "nm_id" if sku and sku == _as_sku(nm_id) else "supplierArticle",
            "revenue": round(price, 2),
            "profit": 0.0,
            "orders": quantity,
            "buys": 0.0,
            "sales_count": 0.0,
            "orders_count": quantity,
            "order_amount": round(price, 2),
            "buyouts_count": 0.0,
            "buyout_amount": 0.0,
            "funnel_stage": "order",
            "funnel_lower_event": True,
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
