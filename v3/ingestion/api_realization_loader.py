from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

from ..api.endpoints import REALIZATION
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


def _pick_optional_float(row: Dict[str, Any], keys: Iterable[str]) -> tuple[float | None, str]:
    for key in keys:
        if key not in row:
            continue
        raw_value = row.get(key)
        if raw_value is None:
            continue
        text = str(raw_value).strip()
        if not text:
            continue
        return _as_float(raw_value), key
    return None, ""


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
        operation_name = _pick_text(
            row,
            (
                "supplier_oper_name",
                "supplierOperName",
                "operationTypeName",
                "operationName",
                "operation",
                "doc_type_name",
                "docTypeName",
            ),
        )
        operation_type = _pick_text(
            row,
            (
                "supplier_oper_type_name",
                "supplierOperTypeName",
                "supplier_oper_type",
                "supplierOperType",
                "operationType",
                "operation_type",
            ),
        )
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
        seller_sku_raw = _pick_text(row, ("supplierArticle", "vendorCode", "techSize"))
        seller_sku = _as_sku(seller_sku_raw)
        warehouse = _pick_text(row, ("warehouseName", "warehouse", "officeName", "giOfficeName", "oblastOkrugName"))
        order_ref = _pick_text(row, ("srid", "saleID", "saleId", "odid", "gNumber"))

        quantity_value, _ = _pick_optional_float(
            row,
            (
                "quantity",
                "sa_quantity",
                "sales_qty",
                "saleQty",
                "ordersCount",
                "order_count",
            ),
        )
        quantity = float(quantity_value) if quantity_value is not None else 0.0

        row_amount_value, row_amount_key = _pick_optional_float(
            row,
            (
                "retail_amount",
                "retailAmount",
                "sale_amount",
                "saleAmount",
            ),
        )
        unit_price_discounted_value, unit_price_discounted_key = _pick_optional_float(
            row,
            (
                "retail_price_withdisc_rub",
                "retailPriceWithDiscRub",
                "priceWithDisc",
                "finishedPrice",
            ),
        )
        retail_price_value, retail_price_key = _pick_optional_float(
            row,
            (
                "retail_price",
                "retailPrice",
            ),
        )
        if row_amount_value is None and unit_price_discounted_value is not None:
            qty_for_amount = abs(quantity) if abs(quantity) > 1e-9 else 1.0
            row_amount_value = float(unit_price_discounted_value) * float(qty_for_amount)
            row_amount_key = f"derived:{unit_price_discounted_key or 'unit_price_discounted'}*quantity"

        revenue_value, _ = _pick_optional_float(
            row,
            (
                "revenue",
                "retail_amount",
                "retailAmount",
                "sale_amount",
                "saleAmount",
                "retail_price_withdisc_rub",
                "retailPriceWithDiscRub",
                "priceWithDisc",
                "finishedPrice",
                "totalPrice",
                "ppvz_for_pay",
                "ppvzForPay",
                "forPay",
            ),
        )
        revenue = float(revenue_value) if revenue_value is not None else 0.0

        payout_value, payout_key = _pick_optional_float(
            row,
            (
                "ppvz_for_pay",
                "ppvzForPay",
                "to_pay",
                "toPay",
                "forPay",
                "payout",
            ),
        )
        payout = float(payout_value) if payout_value is not None else 0.0

        cost_price = _as_float(
            row.get("cost_price")
            or row.get("costPrice")
            or row.get("purchasePrice")
            or row.get("supplierPrice"),
            default=0.0,
        )
        wb_commission_value, wb_commission_key = _pick_optional_float(
            row,
            (
                "wb_commission",
                "commission",
                "retailCommission",
                "ppvz_sales_commission",
                "ppvz_sales_commission_value",
                "ppvzSalesCommission",
                "commission_amount",
                "commissionAmount",
            ),
        )
        wb_commission = float(wb_commission_value) if wb_commission_value is not None else 0.0
        logistics_value, logistics_key = _pick_optional_float(
            row,
            (
                "logistics",
                "delivery_rub",
                "deliveryRub",
                "deliveryAmount",
                "deliveryCost",
                "logistics_cost",
            ),
        )
        logistics = float(logistics_value) if logistics_value is not None else 0.0
        penalties_value, penalties_key = _pick_optional_float(
            row,
            (
                "penalties",
                "penalty",
                "penaltyAmount",
                "fine",
            ),
        )
        penalties = float(penalties_value) if penalties_value is not None else 0.0
        storage_value, storage_key = _pick_optional_float(
            row,
            (
                "storage",
                "storage_fee",
                "storageFee",
            ),
        )
        storage = float(storage_value) if storage_value is not None else 0.0
        deductions_value, deductions_key = _pick_optional_float(
            row,
            (
                "deductions",
                "deduction",
                "acquiringFee",
            ),
        )
        deductions = float(deductions_value) if deductions_value is not None else 0.0
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
            "_sku_source_field": "nm_id" if sku and sku == _as_sku(nm_id) else "supplierArticle",
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
            "_semantic_contract_version": "financial_kernel_v1",
        }
        if operation_name:
            item["supplier_oper_name"] = operation_name
            item["operationTypeName"] = operation_name
        if operation_type:
            item["supplier_oper_type_name"] = operation_type
            item["supplierOperTypeName"] = operation_type
        if row_amount_value is not None:
            item["retail_amount"] = round(float(row_amount_value), 2)
        if unit_price_discounted_value is not None:
            item["retail_price_withdisc_rub"] = round(float(unit_price_discounted_value), 2)
        if retail_price_value is not None:
            item["retail_price"] = round(float(retail_price_value), 2)
        if wb_commission_key:
            item["ppvz_sales_commission"] = round(float(wb_commission), 2)
        if logistics_key:
            item["delivery_rub"] = round(float(logistics), 2)
        if storage_key:
            item["storage_fee"] = round(float(storage), 2)
        if penalties_key:
            item["penalty"] = round(float(penalties), 2)
        if deductions_key:
            item["deduction"] = round(float(deductions), 2)
        if payout_key:
            item["ppvz_for_pay"] = round(float(payout), 2)
        if nm_id:
            item["nmId"] = nm_id
        if seller_sku_raw:
            item["supplierArticle"] = seller_sku_raw
            item["_supplier_article"] = seller_sku_raw
        if row_amount_key:
            item["_row_amount_source_field"] = row_amount_key
        item["_semantic_mapping"] = {
            "operation_name_source": "api_row" if operation_name else "missing",
            "row_amount_source": row_amount_key or "missing",
            "commission_source": wb_commission_key or "missing",
            "payout_source": payout_key or "missing",
            "logistics_source": logistics_key or "missing",
            "storage_source": storage_key or "missing",
            "penalty_source": penalties_key or "missing",
            "deduction_source": deductions_key or "missing",
            "unit_price_source": unit_price_discounted_key or "missing",
            "retail_price_source": retail_price_key or "missing",
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
