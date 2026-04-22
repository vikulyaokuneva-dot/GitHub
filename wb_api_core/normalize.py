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


def _pick_raw_value(row: Dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key not in row:
            continue
        value = row.get(key)
        if value is None or str(value).strip() == "":
            continue
        return value
    return None


def _optional_float(row: Dict[str, Any], keys: Iterable[str]) -> float | None:
    value = _pick_raw_value(row, keys)
    if value is None:
        return None
    return round(_safe_float(value, default=0.0), 2)


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    return None


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
    for key in ("date", "orderDate", "saleDate", "orderDt", "saleDt", "lastChangeDate", "order_dt", "sale_dt", "createdAt"):
        raw = str(row.get(key) or "").strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", raw):
            return raw[:10]
    return ""


def _period_date_iso(period: Dict[str, Any]) -> str:
    if not isinstance(period, dict):
        return ""
    for key in ("start", "date", "end"):
        raw = str(period.get(key) or "").strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", raw):
            return raw[:10]
    return ""


def _normalize_cabinet_commerce(rows_raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for index, row in enumerate(rows_raw):
        if not isinstance(row, dict):
            continue
        product = row.get("product") if isinstance(row.get("product"), dict) else {}
        statistic = row.get("statistic") if isinstance(row.get("statistic"), dict) else {}
        selected = statistic.get("selected") if isinstance(statistic.get("selected"), dict) else {}
        period = selected.get("period") if isinstance(selected.get("period"), dict) else {}

        nm_id = _pick_text(product, ("nmId", "nm_id", "nmID")) or _pick_text(row, ("nmId", "nm_id", "nmID"))
        seller_sku = _pick_text(product, ("vendorCode", "supplierArticle", "sellerSku")) or _pick_text(
            row,
            ("vendorCode", "supplierArticle", "sellerSku"),
        )
        rows.append(
            {
                "date": _period_date_iso(period) or _row_date_iso(selected) or _row_date_iso(row),
                "sku": _normalize_sku(nm_id or seller_sku),
                "nm_id": nm_id,
                "seller_sku": seller_sku,
                "title": _pick_text(product, ("title", "name", "nmName")),
                "brand": _pick_text(product, ("brandName", "brand")),
                "subject_id": _pick_text(product, ("subjectId", "subject_id")),
                "subject_name": _pick_text(product, ("subjectName", "subject")),
                "open_count": _safe_float(selected.get("openCount") or selected.get("openCardCount"), default=0.0),
                "cart_count": _safe_float(selected.get("cartCount") or selected.get("addToCartCount"), default=0.0),
                "order_count": _safe_float(selected.get("orderCount"), default=0.0),
                "order_sum": _safe_float(selected.get("orderSum"), default=0.0),
                "buyout_count": _safe_float(selected.get("buyoutCount"), default=0.0),
                "buyout_sum": _safe_float(selected.get("buyoutSum"), default=0.0),
                "cancel_count": _safe_float(selected.get("cancelCount"), default=0.0),
                "cancel_sum": _safe_float(selected.get("cancelSum"), default=0.0),
                "currency": _pick_text(row, ("currency",)) or _pick_text(selected, ("currency",)),
                "source": "sales_funnel_api",
                "_raw_row_index": index,
            }
        )
    return rows


def _normalize_orders(rows_raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for index, row in enumerate(rows_raw):
        if not isinstance(row, dict):
            continue
        nm_id = _pick_text(row, ("nmId", "nm_id", "nmid", "nmID"))
        seller_sku = _pick_text(row, ("supplierArticle", "supplier_article", "vendorCode", "sellerSku"))
        order_id = _pick_text(row, ("srid", "odid", "orderId", "gNumber", "orderUID"))
        raw_quantity = _pick_raw_value(row, ("quantity", "orderQty", "orderCount", "ordersCount", "orders"))
        quantity = _safe_float(
            raw_quantity,
            default=0.0,
        )
        if quantity <= 0:
            quantity = 1.0 if order_id else 0.0
        amount = _safe_float(
            row.get("priceWithDisc")
            or row.get("finishedPrice")
            or row.get("totalPrice")
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
                "last_change_date": _pick_text(row, ("lastChangeDate", "last_change_date")),
                "raw_quantity": raw_quantity,
                "quantity": quantity,
                "amount": round(amount, 2),
                "warehouse": _pick_text(row, ("warehouseName", "warehouse", "officeName")),
                "total_price": _optional_float(row, ("totalPrice",)),
                "finished_price": _optional_float(row, ("finishedPrice",)),
                "price_with_disc": _optional_float(row, ("priceWithDisc",)),
                "discount_percent": _optional_float(row, ("discountPercent",)),
                "status": _pick_text(row, ("status", "orderStatus", "supplierStatus")),
                "is_cancel": _optional_bool(row.get("isCancel")),
                "cancel_date": _pick_text(row, ("cancelDate", "cancel_date")),
                "is_supply": _optional_bool(row.get("isSupply")),
                "is_realization": _optional_bool(row.get("isRealization")),
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
            or row.get("priceWithDisc")
            or row.get("finishedPrice")
            or row.get("totalPrice")
            or row.get("forPay"),
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


def _normalize_finance_final(rows_raw: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
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
                ("retailPriceWithDisc", "retailPriceWithDiscRub", "retail_price_withdisc_rub", "priceWithDisc", "finishedPrice"),
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
            ("paidStorage", "storageFee", "storage_fee", "storage"),
            diag=diag,
        )
        penalties, _ = _parse_float_with_diag(
            row,
            ("penaltyAmount", "penalty", "penalties", "fine"),
            diag=diag,
        )
        deductions, _ = _parse_float_with_diag(
            row,
            ("deduction", "deductions"),
            diag=diag,
        )
        acquiring, _ = _parse_float_with_diag(
            row,
            ("acquiringFee", "acquiring_fee", "acquiring"),
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
                "acquiring": round(float(acquiring or 0.0), 2),
                "tax": round(float(tax or 0.0), 2),
                "warehouse": _pick_text(row, ("warehouseName", "warehouse", "officeName")),
                "operation_name": _pick_text(row, ("docTypeName", "sellerOperName", "supplierOperName", "operationTypeName", "operationName")),
                "document_type": _pick_text(row, ("docTypeName", "sellerOperName", "supplierOperName")),
                "source": "finance_detailed_api",
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
    cabinet_commerce_rows = _normalize_cabinet_commerce(list((raw_bundle.get("cabinet_commerce") or {}).get("rows_raw", [])))
    finance_final_rows, finance_mapping = _normalize_finance_final(list((raw_bundle.get("finance_final") or {}).get("rows_raw", [])))
    orders_rows = _normalize_orders(list((raw_bundle.get("orders") or {}).get("rows_raw", [])))
    sales_rows = _normalize_sales(list((raw_bundle.get("sales") or {}).get("rows_raw", [])))
    stocks_rows = _normalize_stocks(list((raw_bundle.get("stocks") or {}).get("rows_raw", [])))
    return {
        "cabinet_commerce_rows": cabinet_commerce_rows,
        "finance_final_rows": finance_final_rows,
        "orders_rows": orders_rows,
        "sales_rows": sales_rows,
        "stocks_rows": stocks_rows,
        "debug": {
            "counts": {
                "cabinet_commerce": len(cabinet_commerce_rows),
                "finance_final": len(finance_final_rows),
                "orders": len(orders_rows),
                "sales": len(sales_rows),
                "stocks": len(stocks_rows),
            },
            "finance_mapping": finance_mapping,
        },
    }
