from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

from ..api.endpoints import REALIZATION
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
    for key in ("date", "sale_dt", "order_dt", "lastChangeDate", "create_dt"):
        raw = str(row.get(key) or "").strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", raw):
            return raw[:10]
    return ""


def load_realization_from_api(client: WBApiClient, date_from: str, date_to: str) -> Dict[str, Any]:
    response = client.request_json(
        endpoint=REALIZATION,
        params={
            "dateFrom": date_from,
            "dateTo": date_to,
            "limit": 100000,
            "rrdid": 0,
        },
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
            row.get("supplierArticle")
            or row.get("vendorCode")
            or row.get("barcode")
            or nm_id
        )
        seller_sku = _as_sku(row.get("supplierArticle") or row.get("vendorCode") or row.get("techSize"))
        warehouse = _pick_text(row, ("warehouseName", "warehouse", "officeName", "giOfficeName", "oblastOkrugName"))
        order_ref = _pick_text(row, ("srid", "saleID", "saleId", "odid", "gNumber"))

        quantity = _as_float(
            row.get("quantity")
            or row.get("sa_quantity")
            or row.get("sales_qty")
            or row.get("saleQty")
            or row.get("ordersCount")
            or row.get("order_count"),
            default=0.0,
        )
        revenue = _as_float(
            row.get("revenue")
            or row.get("ppvz_for_pay")
            or row.get("forPay")
            or row.get("retail_amount")
            or row.get("retailPriceWithDiscRub"),
            default=0.0,
        )
        cost_price = _as_float(
            row.get("cost_price")
            or row.get("costPrice")
            or row.get("purchasePrice")
            or row.get("supplierPrice"),
            default=0.0,
        )
        wb_commission = _as_float(
            row.get("wb_commission")
            or row.get("commission")
            or row.get("retailCommission")
            or row.get("ppvz_sales_commission")
            or row.get("ppvz_sales_commission_value"),
            default=0.0,
        )
        logistics = _as_float(
            row.get("logistics")
            or row.get("delivery_rub")
            or row.get("deliveryAmount")
            or row.get("deliveryCost"),
            default=0.0,
        )
        penalties = _as_float(
            row.get("penalties")
            or row.get("penalty")
            or row.get("penaltyAmount"),
            default=0.0,
        )
        storage = _as_float(
            row.get("storage")
            or row.get("storage_fee")
            or row.get("storageFee"),
            default=0.0,
        )
        deductions = _as_float(
            row.get("deductions")
            or row.get("deduction")
            or row.get("acquiringFee"),
            default=0.0,
        )
        explicit_profit = row.get("profit")
        if explicit_profit is None:
            explicit_profit = row.get("netProfit")
        if explicit_profit is None:
            explicit_profit = row.get("income")
        profit_value = (
            _as_float(explicit_profit, default=revenue - cost_price - wb_commission - logistics - penalties - storage - deductions)
        )

        item: Dict[str, Any] = {
            "date": row_date,
            "sku": sku,
            "nm_id": nm_id,
            "quantity": quantity,
            "revenue": round(revenue, 2),
            "order_ref": order_ref,
            "warehouse": warehouse,
            "seller_sku": seller_sku,
            # compatibility with current metrics layer
            "price": round(revenue, 2),
            "profit": round(profit_value, 2),
            "orders": quantity,
            "buys": quantity,
            "sales_count": quantity,
            "cost_price": round(cost_price, 2),
            "wb_commission": round(wb_commission, 2),
            "logistics": round(logistics, 2),
            "penalties": round(penalties, 2),
            "storage": round(storage, 2),
            "deductions": round(deductions, 2),
            "_raw_row_index": index,
            "_source_dataset": "realization_api",
        }
        rows.append(item)

    api_debug = {
        "endpoint": REALIZATION.name,
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

