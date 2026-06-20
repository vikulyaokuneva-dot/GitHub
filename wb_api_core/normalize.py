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


def _pick_iso_date(row: Dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        raw = str(row.get(key) or "").strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", raw):
            return raw[:10]
    return ""


def _row_date_iso(row: Dict[str, Any]) -> str:
    return _pick_iso_date(
        row,
        ("date", "orderDate", "saleDate", "orderDt", "saleDt", "lastChangeDate", "order_dt", "sale_dt", "createdAt"),
    )


def _period_date_iso(period: Dict[str, Any]) -> str:
    if not isinstance(period, dict):
        return ""
    for key in ("start", "date", "end"):
        raw = str(period.get(key) or "").strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", raw):
            return raw[:10]
    return ""


def _finance_report_date_iso(row: Dict[str, Any]) -> str:
    return _pick_iso_date(row, ("rrDate", "rr_dt", "dateFrom", "date_from", "dateTo", "date_to")) or _row_date_iso(row)


def _finance_order_date_iso(row: Dict[str, Any]) -> str:
    return _pick_iso_date(row, ("orderDt", "orderDate", "order_dt"))


def _finance_sale_date_iso(row: Dict[str, Any]) -> str:
    return _pick_iso_date(row, ("saleDt", "saleDate", "sale_dt"))


def _contains_any(text: str, markers: Iterable[str]) -> bool:
    return any(marker in text for marker in markers)


def _finance_row_operation_text(*values: Any) -> str:
    parts = [str(value or "").strip().lower() for value in values if str(value or "").strip()]
    return " ".join(parts)


def _finance_row_group(operation_text: str) -> str:
    sale_markers = ("продаж", "реализац")
    return_markers = ("возврат", "return", "refund", "сторно")
    logistics_markers = ("логист", "доставк", "перевоз")
    storage_markers = ("хран", "storage")
    penalty_markers = ("штраф", "penalty", "fine")
    deduction_markers = ("удержан", "deduct", "коррект", "acquiring")
    reimbursement_markers = ("возмещ", "компенсац", "reimburse", "compensat")

    if _contains_any(operation_text, return_markers):
        return "return"
    if _contains_any(operation_text, sale_markers):
        return "sale"
    if _contains_any(operation_text, reimbursement_markers):
        return "reimbursement"
    if _contains_any(operation_text, logistics_markers):
        return "logistics"
    if _contains_any(operation_text, storage_markers):
        return "storage"
    if _contains_any(operation_text, penalty_markers):
        return "penalty"
    if _contains_any(operation_text, deduction_markers):
        return "deduction"
    return "other"


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
        report_date = _finance_report_date_iso(row)
        order_date = _finance_order_date_iso(row)
        sale_date = _finance_sale_date_iso(row)
        nm_id = _pick_text(row, ("nmId", "nm_id", "nmid", "nmID"))
        seller_sku = _pick_text(row, ("supplierArticle", "vendorCode", "supplier_article"))
        quantity, _ = _parse_float_with_diag(
            row,
            ("quantity", "qty", "count", "sa_quantity", "sales_qty", "saleQty"),
            diag=diag,
        )
        retail_amount_raw = _pick_raw_value(row, ("retailAmount", "retail_amount", "saleAmount", "sale_amount"))
        retail_amount, retail_amount_key = _parse_float_with_diag(
            row,
            ("retailAmount", "retail_amount", "saleAmount", "sale_amount"),
            diag=diag,
        )
        retail_price_with_discount, retail_price_key = _parse_float_with_diag(
            row,
            ("retailPriceWithDisc", "retailPriceWithDiscRub", "retail_price_withdisc_rub", "priceWithDisc", "finishedPrice"),
            diag=diag,
        )
        qty_for_amount = abs(float(quantity or 0.0)) if abs(float(quantity or 0.0)) > 1e-9 else 1.0
        sale_customer_price = retail_price_with_discount
        sale_customer_amount = None
        if retail_price_with_discount is not None:
            sale_customer_amount = retail_price_with_discount * qty_for_amount
        elif retail_amount is not None:
            sale_customer_amount = retail_amount
            sale_customer_price = retail_amount / qty_for_amount if qty_for_amount > 1e-9 else retail_amount

        gross_revenue, gross_key = _parse_float_with_diag(
            row,
            (
                "wb_realized_revenue",
                "wbRealizedRevenue",
                "wb_realized_amount",
                "wbRealizedAmount",
                "realized_sales_revenue",
                "realized_revenue",
                "gross_revenue",
            ),
            diag=diag,
        )
        if gross_revenue is None:
            gross_revenue = retail_amount
            gross_key = retail_amount_key
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
        logistics_amount, _ = _parse_float_with_diag(
            row,
            (
                "deliveryRub",
                "delivery_rub",
                "deliveryCost",
                "delivery_cost",
                "deliveryServiceAmount",
                "delivery_service_amount",
                "deliveryServicesAmount",
                "delivery_services_amount",
                "deliveryServiceRub",
                "delivery_service_rub",
                "logistics_amount",
                "logistics",
                "logistics_cost",
                "Услуги по доставке товара покупателю",
                "Услуги доставки",
            ),
            diag=diag,
        )
        deliveries_qty, _ = _parse_float_with_diag(
            row,
            (
                "deliveryAmount",
                "delivery_amount",
                "deliveryCount",
                "delivery_count",
                "deliveryQty",
                "delivery_qty",
                "deliveries_qty",
                "deliveries_count",
                "Количество доставок",
            ),
            diag=diag,
        )
        explicit_returns_qty, _ = _parse_float_with_diag(
            row,
            (
                "returnAmount",
                "return_amount",
                "returnCount",
                "return_count",
                "returnQty",
                "return_qty",
                "returns_qty",
                "quantityReturn",
                "quantity_return",
                "Количество возвратов",
            ),
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
        operation_name = _pick_text(row, ("sellerOperName", "supplierOperName", "docTypeName", "operationTypeName", "operationName"))
        document_type = _pick_text(row, ("docTypeName", "sellerOperName", "supplierOperName"))
        operation_text = _finance_row_operation_text(operation_name, document_type)
        row_group = _finance_row_group(operation_text)
        quantity_abs = abs(float(quantity or 0.0))
        realized_sales_qty = quantity_abs if row_group == "sale" and quantity_abs > 1e-9 else None
        realized_sales_revenue = (
            float(gross_revenue or 0.0)
            if row_group == "sale" and abs(float(gross_revenue or 0.0)) > 1e-9
            else None
        )
        sale_customer_amount_for_totals = sale_customer_amount if row_group == "sale" else None
        returns_qty = explicit_returns_qty
        if returns_qty is None and row_group == "return" and quantity_abs > 1e-9:
            returns_qty = quantity_abs
        tracked_values = (
            float(gross_revenue or 0.0),
            float(seller_payout or 0.0),
            float(wb_commission or 0.0),
            float(logistics_amount or 0.0),
            float(storage or 0.0),
            float(penalties or 0.0),
            float(deductions or 0.0),
            float(acquiring or 0.0),
            float(tax or 0.0),
            float(sale_customer_amount or 0.0),
        )
        has_financial_effect = any(abs(value) > 1e-9 for value in tracked_values)
        is_zero_technical = row_group == "reimbursement" and not has_financial_effect

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
                "date": report_date,
                "report_date": report_date,
                "order_date": order_date,
                "sale_date": sale_date,
                "sku": _normalize_sku(nm_id or seller_sku or row.get("barcode")),
                "nm_id": nm_id,
                "seller_sku": seller_sku,
                "quantity": float(quantity or 0.0),
                "sale_customer_price": round(float(sale_customer_price), 2) if sale_customer_price is not None else None,
                "sale_customer_amount": round(float(sale_customer_amount_for_totals), 2)
                if sale_customer_amount_for_totals is not None
                else None,
                "retail_amount_raw": retail_amount_raw,
                "retail_amount": round(float(retail_amount), 2) if retail_amount is not None else None,
                "retail_price_with_discount": round(float(retail_price_with_discount), 2)
                if retail_price_with_discount is not None
                else None,
                "gross_revenue": round(float(gross_revenue or 0.0), 2),
                "wb_realized_revenue": round(float(gross_revenue), 2) if gross_revenue is not None else None,
                "realized_sales_qty": round(float(realized_sales_qty), 2) if realized_sales_qty is not None else None,
                "realized_sales_revenue": round(float(realized_sales_revenue), 2) if realized_sales_revenue is not None else None,
                "seller_payout": round(float(seller_payout or 0.0), 2),
                "wb_commission": round(float(wb_commission or 0.0), 2),
                "deliveries_qty": round(float(deliveries_qty), 2) if deliveries_qty is not None else None,
                "returns_qty": round(float(returns_qty), 2) if returns_qty is not None else None,
                "logistics": round(float(logistics_amount or 0.0), 2),
                "logistics_amount": round(float(logistics_amount), 2) if logistics_amount is not None else None,
                "storage": round(float(storage or 0.0), 2),
                "penalties": round(float(penalties or 0.0), 2),
                "deductions": round(float(deductions or 0.0), 2),
                "acquiring": round(float(acquiring or 0.0), 2),
                "tax": round(float(tax or 0.0), 2),
                "warehouse": _pick_text(row, ("warehouseName", "warehouse", "officeName")),
                "operation_name": operation_name,
                "document_type": document_type,
                "row_group": row_group,
                "has_financial_effect": has_financial_effect,
                "is_zero_technical": is_zero_technical,
                "include_in_totals": has_financial_effect and not is_zero_technical,
                "include_gross_revenue": row_group == "sale" and abs(float(gross_revenue or 0.0)) > 1e-9,
                "include_realized_sales": row_group == "sale"
                and (
                    (realized_sales_qty is not None and abs(float(realized_sales_qty)) > 1e-9)
                    or (realized_sales_revenue is not None and abs(float(realized_sales_revenue)) > 1e-9)
                ),
                "include_sale_customer_amount": row_group == "sale" and sale_customer_amount_for_totals is not None,
                "include_deliveries_qty": deliveries_qty is not None and abs(float(deliveries_qty)) > 1e-9,
                "include_returns_qty": returns_qty is not None and abs(float(returns_qty)) > 1e-9,
                "include_seller_payout": has_financial_effect and not is_zero_technical and abs(float(seller_payout or 0.0)) > 1e-9,
                "include_wb_commission": has_financial_effect and not is_zero_technical and abs(float(wb_commission or 0.0)) > 1e-9,
                "include_logistics": has_financial_effect and not is_zero_technical and logistics_amount is not None and abs(float(logistics_amount)) > 1e-9,
                "include_storage": has_financial_effect and not is_zero_technical and abs(float(storage or 0.0)) > 1e-9,
                "include_penalties": has_financial_effect and not is_zero_technical and abs(float(penalties or 0.0)) > 1e-9,
                "include_deductions": has_financial_effect and not is_zero_technical and abs(float(deductions or 0.0)) > 1e-9,
                "include_acquiring": has_financial_effect and not is_zero_technical and abs(float(acquiring or 0.0)) > 1e-9,
                "include_tax": has_financial_effect and not is_zero_technical and abs(float(tax or 0.0)) > 1e-9,
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


def _normalize_ads(rows_raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for index, row in enumerate(rows_raw):
        if not isinstance(row, dict):
            continue
        nm_id = _pick_text(row, ("nmId", "nm_id", "nmid", "nmID", "sku"))
        rows.append(
            {
                "date": row.get("date", ""),
                "sku": _normalize_sku(nm_id),
                "nm_id": nm_id,
                "ads_spend": round(_safe_float(row.get("ads_spend"), default=0.0), 2),
                "impressions": round(_safe_float(row.get("impressions"), default=0.0), 0),
                "clicks": round(_safe_float(row.get("clicks"), default=0.0), 0),
                "add_to_cart": round(_safe_float(row.get("add_to_cart"), default=0.0), 0),
                "orders": round(_safe_float(row.get("orders"), default=0.0), 0),
                "ctr": row.get("ctr"),
                "cpo": row.get("cpo"),
                "source": "ads_api",
                "_raw_row_index": index,
            }
        )
    return rows


def normalize_bundle(raw_bundle: Dict[str, Any]) -> Dict[str, Any]:
    cabinet_commerce_rows = _normalize_cabinet_commerce(list((raw_bundle.get("cabinet_commerce") or {}).get("rows_raw", [])))
    finance_final_rows, finance_mapping = _normalize_finance_final(list((raw_bundle.get("finance_final") or {}).get("rows_raw", [])))
    orders_rows = _normalize_orders(list((raw_bundle.get("orders") or {}).get("rows_raw", [])))
    sales_rows = _normalize_sales(list((raw_bundle.get("sales") or {}).get("rows_raw", [])))
    stocks_rows = _normalize_stocks(list((raw_bundle.get("stocks") or {}).get("rows_raw", [])))
    ads_rows = _normalize_ads(list((raw_bundle.get("ads") or {}).get("rows_raw", [])))
    return {
        "cabinet_commerce_rows": cabinet_commerce_rows,
        "finance_final_rows": finance_final_rows,
        "orders_rows": orders_rows,
        "sales_rows": sales_rows,
        "stocks_rows": stocks_rows,
        "ads_rows": ads_rows,
        "debug": {
            "counts": {
                "cabinet_commerce": len(cabinet_commerce_rows),
                "finance_final": len(finance_final_rows),
                "orders": len(orders_rows),
                "sales": len(sales_rows),
                "stocks": len(stocks_rows),
                "ads": len(ads_rows),
            },
            "finance_mapping": finance_mapping,
        },
    }
