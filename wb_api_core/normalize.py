from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Tuple

_MISSING_LITERALS = {"", "none", "null", "nan", "n/a", "na", "-", "unknown"}
_ZERO_LITERALS = {"0", "0.0", "00", "000"}
_VALID_TOKEN_RE = re.compile(r"^[\w.\-]+$", flags=re.UNICODE)


def _normalize_number_text(value: Any) -> str:
    return str(value or "").strip().replace("\u00a0", "").replace(" ", "").replace(",", ".")


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return float(default)
    if isinstance(value, (int, float)):
        return float(value)
    text = _normalize_number_text(value)
    if not text:
        return float(default)
    try:
        return float(text)
    except Exception:
        return float(default)


def _parse_float_with_diag(
    row: Dict[str, Any],
    keys: Iterable[str],
    *,
    diag: Dict[str, Any],
) -> Tuple[float | None, str]:
    for key in keys:
        if key not in row:
            continue
        value = row.get(key)
        if value is None or str(value).strip() == "":
            continue
        if isinstance(value, (int, float)):
            return float(value), key
        text = _normalize_number_text(value)
        if not text:
            continue
        try:
            number = float(text)
        except Exception:
            diag["parse_errors_count"] = int(diag.get("parse_errors_count", 0) or 0) + 1
            continue
        parsed_fields = diag.setdefault("money_string_fields_parsed", set())
        if isinstance(parsed_fields, set):
            parsed_fields.add(key)
        return number, key
    return None, ""


def _pick_text(row: Dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _normalize_sku(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered in _MISSING_LITERALS or lowered in _ZERO_LITERALS:
        return None
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return None
    if re.fullmatch(r"\d+(\.0+)?", compact):
        digits = compact.split(".", 1)[0]
        if digits in _ZERO_LITERALS:
            return None
        return digits
    if not _VALID_TOKEN_RE.fullmatch(compact):
        return None
    return compact


def _row_date_iso(row: Dict[str, Any]) -> str:
    for key in ("date", "orderDate", "saleDate", "lastChangeDate", "order_dt", "sale_dt", "createdAt"):
        raw = str(row.get(key) or "").strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", raw):
            return raw[:10]
    return ""


def _normalize_orders(rows_raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for index, row in enumerate(rows_raw):
        if not isinstance(row, dict):
            continue
        nm_id = _pick_text(row, ("nmId", "nm_id", "nmid", "nmID"))
        seller_sku = _pick_text(row, ("supplierArticle", "supplier_article", "vendorCode", "sellerSku"))
        order_id = _pick_text(row, ("srid", "odid", "orderId", "gNumber", "orderUID"))
        quantity = _safe_float(
            row.get("quantity")
            or row.get("orderQty")
            or row.get("orderCount")
            or row.get("ordersCount")
            or row.get("orders"),
            default=0.0,
        )
        if quantity <= 0:
            quantity = 1.0 if order_id else 0.0
        amount = _safe_float(
            row.get("totalPrice")
            or row.get("priceWithDisc")
            or row.get("finishedPrice")
            or row.get("convertedPrice")
            or row.get("price"),
            default=0.0,
        )
        rows.append(
            {
                "date": _row_date_iso(row),
                "sku": _normalize_sku(nm_id or seller_sku or row.get("barcode")),
                "nm_id": nm_id,
                "seller_sku": seller_sku,
                "order_id": order_id,
                "quantity": quantity,
                "amount": round(amount, 2),
                "source": "orders_api",
                "_raw_row_index": index,
            }
        )
    return rows


def _normalize_sales(rows_raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for index, row in enumerate(rows_raw):
        if not isinstance(row, dict):
            continue
        nm_id = _pick_text(row, ("nmId", "nm_id", "nmid", "nmID"))
        seller_sku = _pick_text(row, ("supplierArticle", "supplier_article", "vendorCode", "sellerSku"))
        sale_id = _pick_text(row, ("srid", "saleID", "saleId", "gNumber", "odid"))
        quantity = _safe_float(
            row.get("quantity")
            or row.get("sa_quantity")
            or row.get("saleQty")
            or row.get("sales_qty"),
            default=0.0,
        )
        if quantity <= 0:
            quantity = 1.0 if sale_id else 0.0
        amount = _safe_float(
            row.get("revenue")
            or row.get("forPay")
            or row.get("totalPrice")
            or row.get("finishedPrice")
            or row.get("priceWithDisc"),
            default=0.0,
        )
        rows.append(
            {
                "date": _row_date_iso(row),
                "sku": _normalize_sku(nm_id or seller_sku or row.get("barcode")),
                "nm_id": nm_id,
                "seller_sku": seller_sku,
                "sale_id": sale_id,
                "quantity": quantity,
                "amount": round(amount, 2),
                "source": "sales_api",
                "_raw_row_index": index,
            }
        )
    return rows


def _normalize_stocks(rows_raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for index, row in enumerate(rows_raw):
        if not isinstance(row, dict):
            continue
        nm_id = _pick_text(row, ("nmId", "nm_id", "nmid", "nmID"))
        seller_sku = _pick_text(row, ("supplierArticle", "supplier_article", "vendorCode", "sellerSku"))
        quantity_full = _safe_float(row.get("quantityFull") or row.get("quantity_full"), default=0.0)
        quantity = _safe_float(row.get("quantity") or row.get("qty"), default=0.0)
        in_way_to_client = _safe_float(row.get("inWayToClient"), default=0.0)
        in_way_from_client = _safe_float(row.get("inWayFromClient"), default=0.0)
        stock = max(quantity_full, quantity, quantity + in_way_to_client + in_way_from_client, 0.0)
        rows.append(
            {
                "date": _row_date_iso(row),
                "sku": _normalize_sku(nm_id or seller_sku or row.get("barcode")),
                "nm_id": nm_id,
                "seller_sku": seller_sku,
                "stock": round(stock, 2),
                "warehouse": _pick_text(row, ("warehouseName", "warehouse", "officeName")),
                "source": "stocks_api",
                "_raw_row_index": index,
            }
        )
    return rows


def _normalize_realization(rows_raw: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    diag: Dict[str, Any] = {
        "parse_errors_count": 0,
        "missing_required_fields": set(),
        "money_string_fields_parsed": set(),
    }

    for index, row in enumerate(rows_raw):
        if not isinstance(row, dict):
            continue
        row_date = _row_date_iso(row)
        nm_id = _pick_text(row, ("nmId", "nm_id", "nmid", "nmID"))
        seller_sku = _pick_text(row, ("supplierArticle", "vendorCode", "supplier_article"))
        quantity, _ = _parse_float_with_diag(
            row,
            ("quantity", "qty", "count", "sa_quantity", "sales_qty", "saleQty"),
            diag=diag,
        )
        gross_revenue, gross_key = _parse_float_with_diag(
            row,
            ("retailAmount", "retail_amount", "saleAmount", "sale_amount"),
            diag=diag,
        )
        if gross_revenue is None:
            unit_price, _ = _parse_float_with_diag(
                row,
                ("retailPriceWithDiscRub", "retail_price_withdisc_rub", "priceWithDisc", "finishedPrice"),
                diag=diag,
            )
            qty_for_amount = abs(float(quantity or 0.0)) if abs(float(quantity or 0.0)) > 1e-9 else 1.0
            if unit_price is not None:
                gross_revenue = unit_price * qty_for_amount
                gross_key = "derived"
        seller_payout, payout_key = _parse_float_with_diag(
            row,
            ("ppvzForPay", "ppvz_for_pay", "toPay", "to_pay", "forPay", "payout"),
            diag=diag,
        )
        wb_commission, commission_key = _parse_float_with_diag(
            row,
            ("ppvzSalesCommission", "ppvz_sales_commission", "commissionAmount", "commission_amount", "commission"),
            diag=diag,
        )
        logistics, _ = _parse_float_with_diag(
            row,
            ("deliveryRub", "delivery_rub", "deliveryAmount", "deliveryCost", "logistics", "logistics_cost"),
            diag=diag,
        )
        storage, _ = _parse_float_with_diag(
            row,
            ("storageFee", "storage_fee", "storage"),
            diag=diag,
        )
        penalties, _ = _parse_float_with_diag(
            row,
            ("penaltyAmount", "penalty", "penalties", "fine"),
            diag=diag,
        )
        deductions, _ = _parse_float_with_diag(
            row,
            ("deduction", "deductions", "acquiringFee", "acquiring"),
            diag=diag,
        )
        tax, _ = _parse_float_with_diag(
            row,
            ("tax", "taxAmount"),
            diag=diag,
        )

        if not gross_key:
            missing = diag.setdefault("missing_required_fields", set())
            if isinstance(missing, set):
                missing.add("gross_revenue")
        if not payout_key:
            missing = diag.setdefault("missing_required_fields", set())
            if isinstance(missing, set):
                missing.add("seller_payout")
        if not commission_key:
            missing = diag.setdefault("missing_required_fields", set())
            if isinstance(missing, set):
                missing.add("wb_commission")

        rows.append(
            {
                "date": row_date,
                "sku": _normalize_sku(nm_id or seller_sku or row.get("barcode")),
                "nm_id": nm_id,
                "seller_sku": seller_sku,
                "quantity": float(quantity or 0.0),
                "gross_revenue": round(float(gross_revenue or 0.0), 2),
                "seller_payout": round(float(seller_payout or 0.0), 2),
                "wb_commission": round(float(wb_commission or 0.0), 2),
                "logistics": round(float(logistics or 0.0), 2),
                "storage": round(float(storage or 0.0), 2),
                "penalties": round(float(penalties or 0.0), 2),
                "deductions": round(float(deductions or 0.0), 2),
                "tax": round(float(tax or 0.0), 2),
                "warehouse": _pick_text(row, ("warehouseName", "warehouse", "officeName")),
                "operation_name": _pick_text(row, ("supplierOperName", "operationTypeName", "operationName")),
                "source": "finance_api",
                "_raw_row_index": index,
            }
        )

    normalized_diag = {
        "parse_errors_count": int(diag.get("parse_errors_count", 0) or 0),
        "missing_required_fields": sorted(diag.get("missing_required_fields", set())),
        "money_string_fields_parsed": sorted(diag.get("money_string_fields_parsed", set())),
    }
    return rows, normalized_diag


def normalize_bundle(raw_bundle: Dict[str, Any]) -> Dict[str, Any]:
    orders_rows = _normalize_orders(list((raw_bundle.get("orders") or {}).get("rows_raw", [])))
    sales_rows = _normalize_sales(list((raw_bundle.get("sales") or {}).get("rows_raw", [])))
    stocks_rows = _normalize_stocks(list((raw_bundle.get("stocks") or {}).get("rows_raw", [])))
    realization_rows, finance_mapping = _normalize_realization(list((raw_bundle.get("realization") or {}).get("rows_raw", [])))
    return {
        "orders_rows": orders_rows,
        "sales_rows": sales_rows,
        "stocks_rows": stocks_rows,
        "realization_rows": realization_rows,
        "debug": {
            "counts": {
                "orders": len(orders_rows),
                "sales": len(sales_rows),
                "stocks": len(stocks_rows),
                "realization": len(realization_rows),
            },
            "finance_mapping": finance_mapping,
        },
    }
