from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Sequence

from ..api.endpoints import (
    BASE_STATISTICS,
    FINANCE_SALES_REPORTS_DETAILED,
    FINANCE_SALES_REPORTS_LIST,
    REALIZATION,
    WBEndpoint,
)
from ..api.wb_client import WBApiClient
from ..validation.sku_normalization import normalize_sku

# Keep fields centralized and minimal for v3 financial contour:
# kernel semantics, payout/profit decomposition, SKU attribution and diagnostics.
FINANCE_REALIZATION_FIELDS: tuple[str, ...] = (
    "date",
    "nmId",
    "supplierArticle",
    "vendorCode",
    "barcode",
    "title",
    "brand",
    "subject",
    "supplierOperName",
    "supplierOperTypeName",
    "quantity",
    "retailAmount",
    "retailPriceWithDiscRub",
    "retailPrice",
    "ppvzSalesCommission",
    "deliveryRub",
    "storageFee",
    "penaltyAmount",
    "deduction",
    "ppvzForPay",
    "tax",
    "srid",
    "saleID",
    "saleId",
    "odid",
    "gNumber",
    "warehouseName",
    "officeName",
    "giOfficeName",
    "oblastOkrugName",
)

_MONEY_QUANT = Decimal("0.01")
_NEW_FINANCE_HINT_KEYS = {
    "retailAmount",
    "ppvzForPay",
    "ppvzSalesCommission",
    "deliveryRub",
    "storageFee",
    "supplierOperName",
    "supplierOperTypeName",
    "title",
}
_DEPRECATED_NO_LONGER_USED_FIELDS = ("suppliercontract_code", "ppvz_supplier_id")


def _as_sku(value: Any) -> str:
    return str(normalize_sku(value) or "")


def _row_date_iso(row: Dict[str, Any]) -> str:
    for key in ("date", "sale_dt", "order_dt", "lastChangeDate", "create_dt", "dateFrom", "dateTo"):
        raw = str(row.get(key) or "").strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", raw):
            return raw[:10]
    return ""


def _normalize_numeric_text(text: str) -> str:
    return str(text or "").strip().replace("\u00a0", "").replace(" ", "").replace(",", ".")


def _as_decimal(value: Any) -> tuple[Decimal | None, bool, bool]:
    if value is None or isinstance(value, bool):
        return None, False, False
    if isinstance(value, Decimal):
        return value, False, False
    if isinstance(value, int):
        return Decimal(value), False, False
    if isinstance(value, float):
        return Decimal(str(value)), False, False
    text_raw = str(value or "").strip()
    if not text_raw:
        return None, False, False
    text = _normalize_numeric_text(text_raw)
    try:
        return Decimal(text), True, False
    except (InvalidOperation, ValueError):
        return None, True, True


def _decimal_to_float(value: Decimal | None, *, default: float = 0.0) -> float:
    if value is None:
        return float(default)
    return float(value.quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP))


def _pick_text(row: Dict[str, Any], keys: Iterable[str], used_fields: set[str]) -> tuple[str, str]:
    for key in keys:
        value = str(row.get(key) or "").strip()
        if value:
            used_fields.add(key)
            return value, key
    return "", ""


def _pick_present_key(row: Dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        if key in row and str(row.get(key) or "").strip():
            return key
    return ""


def _pick_optional_decimal(
    row: Dict[str, Any],
    keys: Iterable[str],
    *,
    used_fields: set[str],
    parse_errors: List[int],
    money_string_fields_parsed: set[str] | None = None,
) -> tuple[Decimal | None, str]:
    for key in keys:
        if key not in row:
            continue
        parsed, from_string, parse_error = _as_decimal(row.get(key))
        if parse_error:
            parse_errors[0] += 1
            continue
        if parsed is None:
            continue
        used_fields.add(key)
        if from_string and money_string_fields_parsed is not None:
            money_string_fields_parsed.add(key)
        return parsed, key
    return None, ""


def _looks_like_realization_row(row: Dict[str, Any]) -> bool:
    row_keys = set(row.keys())
    expected = {
        "date",
        "nmId",
        "nm_id",
        "supplierArticle",
        "supplierOperName",
        "supplier_oper_name",
        "retailAmount",
        "retail_amount",
        "ppvzForPay",
        "ppvz_for_pay",
    }
    return bool(row_keys.intersection(expected))


def _extract_report_ids(payload: Any) -> List[str]:
    ids: set[str] = set()

    def _collect_id(raw_value: Any) -> None:
        text = str(raw_value or "").strip()
        if text:
            ids.add(text)

    def _visit(node: Any) -> None:
        if isinstance(node, dict):
            _collect_id(node.get("reportId"))
            _collect_id(node.get("report_id"))
            for value in node.values():
                if isinstance(value, (dict, list)):
                    _visit(value)
        elif isinstance(node, list):
            for value in node:
                if isinstance(value, (dict, list)):
                    _visit(value)

    _visit(payload)
    return sorted(ids)


def _extract_finance_rows(payload: Any, client: WBApiClient) -> tuple[List[Dict[str, Any]], List[str], bool]:
    report_ids = _extract_report_ids(payload)
    rows: List[Dict[str, Any]] = []
    payload_has_hint = False

    def _append_rows(items: Any) -> None:
        nonlocal payload_has_hint
        if isinstance(items, list) and items:
            payload_has_hint = True
            for value in items:
                if isinstance(value, dict) and _looks_like_realization_row(value):
                    rows.append(value)

    if isinstance(payload, list):
        _append_rows(payload)
    elif isinstance(payload, dict):
        if payload:
            payload_has_hint = True
        _append_rows(payload.get("rows"))
        _append_rows(payload.get("details"))
        for key in ("data", "items", "reports", "result"):
            value = payload.get(key)
            if not isinstance(value, list):
                continue
            if value:
                payload_has_hint = True
            nested_detected = False
            for item in value:
                if not isinstance(item, dict):
                    continue
                if _looks_like_realization_row(item):
                    rows.append(item)
                    continue
                nested = item.get("rows")
                if not isinstance(nested, list):
                    nested = item.get("details")
                if not isinstance(nested, list):
                    nested = item.get("data")
                if isinstance(nested, list):
                    nested_detected = True
                    _append_rows(nested)
            if not nested_detected and not rows:
                _append_rows(value)

    if not rows:
        extracted = client.extract_rows(payload, ("data", "items", "rows", "details"))
        if extracted:
            payload_has_hint = True
            rows = [row for row in extracted if isinstance(row, dict)]

    return rows, report_ids, payload_has_hint


def _map_row_to_internal(
    row: Dict[str, Any],
    *,
    index: int,
    source_dataset: str,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    used_fields: set[str] = set()
    money_string_fields_parsed: set[str] = set()
    parse_errors = [0]
    deprecated_seen = [key for key in _DEPRECATED_NO_LONGER_USED_FIELDS if key in row]

    operation_name, _ = _pick_text(
        row,
        (
            "supplierOperName",
            "supplier_oper_name",
            "operationTypeName",
            "operationName",
            "operation",
            "docTypeName",
            "doc_type_name",
        ),
        used_fields,
    )
    operation_type, _ = _pick_text(
        row,
        (
            "supplierOperTypeName",
            "supplier_oper_type_name",
            "supplierOperType",
            "supplier_oper_type",
            "operationType",
            "operation_type",
        ),
        used_fields,
    )
    nm_id, _ = _pick_text(row, ("nmId", "nm_id", "nmid", "nmID"), used_fields)
    sku_source_key = _pick_present_key(
        row,
        ("nmId", "nm_id", "nmid", "nmID", "supplierArticle", "vendorCode", "barcode"),
    )
    sku = _as_sku(
        nm_id
        or row.get("nmId")
        or row.get("nm_id")
        or row.get("nmid")
        or row.get("supplierArticle")
        or row.get("vendorCode")
        or row.get("barcode")
    )
    if sku_source_key:
        used_fields.add(sku_source_key)
    seller_sku_raw, seller_sku_source = _pick_text(row, ("supplierArticle", "vendorCode", "techSize"), used_fields)
    if seller_sku_source:
        used_fields.add(seller_sku_source)
    seller_sku = _as_sku(seller_sku_raw)
    title, _ = _pick_text(row, ("title", "nmName", "name"), used_fields)
    brand, _ = _pick_text(row, ("brand", "brandName"), used_fields)
    subject, _ = _pick_text(row, ("subject", "subjectName", "nmSubjectName"), used_fields)
    warehouse, _ = _pick_text(
        row,
        ("warehouseName", "warehouse", "officeName", "giOfficeName", "oblastOkrugName"),
        used_fields,
    )
    order_ref, _ = _pick_text(row, ("srid", "saleID", "saleId", "odid", "gNumber"), used_fields)
    row_date = _row_date_iso(row)
    if row_date:
        used_fields.add("date")

    quantity_decimal, _ = _pick_optional_decimal(
        row,
        ("quantity", "qty", "count", "sa_quantity", "sales_qty", "saleQty", "ordersCount", "order_count"),
        used_fields=used_fields,
        parse_errors=parse_errors,
    )
    quantity = float(quantity_decimal) if quantity_decimal is not None else 0.0

    row_amount_decimal, row_amount_key = _pick_optional_decimal(
        row,
        ("retailAmount", "retail_amount", "saleAmount", "sale_amount"),
        used_fields=used_fields,
        parse_errors=parse_errors,
        money_string_fields_parsed=money_string_fields_parsed,
    )
    unit_price_discounted_decimal, unit_price_discounted_key = _pick_optional_decimal(
        row,
        ("retailPriceWithDiscRub", "retail_price_withdisc_rub", "priceWithDisc", "finishedPrice"),
        used_fields=used_fields,
        parse_errors=parse_errors,
        money_string_fields_parsed=money_string_fields_parsed,
    )
    if row_amount_decimal is None and unit_price_discounted_decimal is not None:
        qty_for_amount = abs(quantity) if abs(quantity) > 1e-9 else 1.0
        row_amount_decimal = unit_price_discounted_decimal * Decimal(str(qty_for_amount))
        row_amount_key = f"derived:{unit_price_discounted_key or 'unit_price_discounted'}*quantity"

    retail_price_decimal, retail_price_key = _pick_optional_decimal(
        row,
        ("retailPrice", "retail_price"),
        used_fields=used_fields,
        parse_errors=parse_errors,
        money_string_fields_parsed=money_string_fields_parsed,
    )
    revenue_decimal_extra, _ = _pick_optional_decimal(
        row,
        ("revenue", "forPay", "totalPrice", "ppvzForPay", "ppvz_for_pay"),
        used_fields=used_fields,
        parse_errors=parse_errors,
        money_string_fields_parsed=money_string_fields_parsed,
    )
    revenue_decimal = row_amount_decimal if row_amount_decimal is not None else revenue_decimal_extra

    payout_decimal, payout_key = _pick_optional_decimal(
        row,
        ("ppvzForPay", "ppvz_for_pay", "toPay", "to_pay", "forPay", "payout"),
        used_fields=used_fields,
        parse_errors=parse_errors,
        money_string_fields_parsed=money_string_fields_parsed,
    )
    commission_decimal, commission_key = _pick_optional_decimal(
        row,
        (
            "ppvzSalesCommission",
            "ppvz_sales_commission",
            "commissionAmount",
            "commission_amount",
            "wb_commission",
            "commission",
            "retailCommission",
        ),
        used_fields=used_fields,
        parse_errors=parse_errors,
        money_string_fields_parsed=money_string_fields_parsed,
    )
    logistics_decimal, logistics_key = _pick_optional_decimal(
        row,
        ("deliveryRub", "delivery_rub", "deliveryAmount", "deliveryCost", "logistics", "logistics_cost"),
        used_fields=used_fields,
        parse_errors=parse_errors,
        money_string_fields_parsed=money_string_fields_parsed,
    )
    penalties_decimal, penalties_key = _pick_optional_decimal(
        row,
        ("penaltyAmount", "penalty", "penalties", "fine"),
        used_fields=used_fields,
        parse_errors=parse_errors,
        money_string_fields_parsed=money_string_fields_parsed,
    )
    storage_decimal, storage_key = _pick_optional_decimal(
        row,
        ("storageFee", "storage_fee", "storage"),
        used_fields=used_fields,
        parse_errors=parse_errors,
        money_string_fields_parsed=money_string_fields_parsed,
    )
    deductions_decimal, deductions_key = _pick_optional_decimal(
        row,
        ("deduction", "deductions", "acquiringFee", "acquiring"),
        used_fields=used_fields,
        parse_errors=parse_errors,
        money_string_fields_parsed=money_string_fields_parsed,
    )
    tax_decimal, tax_key = _pick_optional_decimal(
        row,
        ("tax", "taxAmount"),
        used_fields=used_fields,
        parse_errors=parse_errors,
        money_string_fields_parsed=money_string_fields_parsed,
    )
    if tax_key:
        used_fields.add(tax_key)
    cost_price_decimal, _ = _pick_optional_decimal(
        row,
        ("cost_price", "costPrice", "purchasePrice", "supplierPrice"),
        used_fields=used_fields,
        parse_errors=parse_errors,
        money_string_fields_parsed=money_string_fields_parsed,
    )
    explicit_profit_decimal, _ = _pick_optional_decimal(
        row,
        ("profit", "netProfit", "income"),
        used_fields=used_fields,
        parse_errors=parse_errors,
        money_string_fields_parsed=money_string_fields_parsed,
    )

    revenue = _decimal_to_float(revenue_decimal, default=0.0)
    cost_price = _decimal_to_float(cost_price_decimal, default=0.0)
    wb_commission = _decimal_to_float(commission_decimal, default=0.0)
    logistics = _decimal_to_float(logistics_decimal, default=0.0)
    penalties = _decimal_to_float(penalties_decimal, default=0.0)
    storage = _decimal_to_float(storage_decimal, default=0.0)
    deductions = _decimal_to_float(deductions_decimal, default=0.0)
    tax = _decimal_to_float(tax_decimal, default=0.0)
    payout = _decimal_to_float(payout_decimal, default=0.0)
    profit = (
        _decimal_to_float(explicit_profit_decimal, default=0.0)
        if explicit_profit_decimal is not None
        else round(revenue - cost_price - wb_commission - logistics - penalties - storage - deductions, 2)
    )

    item: Dict[str, Any] = {
        "date": row_date,
        "sku": sku,
        "nm_id": nm_id,
        "quantity": quantity,
        "revenue": round(revenue, 2),
        "price": round(revenue, 2),
        "profit": round(profit, 2),
        "orders": quantity,
        "buys": quantity,
        "sales_count": quantity,
        "cost_price": round(cost_price, 2),
        "wb_commission": round(wb_commission, 2),
        "logistics": round(logistics, 2),
        "penalties": round(penalties, 2),
        "storage": round(storage, 2),
        "deductions": round(deductions, 2),
        "tax": round(tax, 2),
        "seller_payout": round(payout, 2),
        "order_ref": order_ref,
        "warehouse": warehouse,
        "seller_sku": seller_sku,
        "title": title,
        "brand": brand,
        "subject": subject,
        "_sku_source_field": sku_source_key or ("supplierArticle" if seller_sku_raw else ""),
        "_raw_row_index": index,
        "_source_dataset": source_dataset,
        "_semantic_contract_version": "financial_kernel_v1",
    }
    if operation_name:
        item["supplier_oper_name"] = operation_name
        item["supplierOperName"] = operation_name
        item["operationTypeName"] = operation_name
    if operation_type:
        item["supplier_oper_type_name"] = operation_type
        item["supplierOperTypeName"] = operation_type
    if row_amount_decimal is not None:
        item["retail_amount"] = round(_decimal_to_float(row_amount_decimal), 2)
    if unit_price_discounted_decimal is not None:
        item["retail_price_withdisc_rub"] = round(_decimal_to_float(unit_price_discounted_decimal), 2)
    if retail_price_decimal is not None:
        item["retail_price"] = round(_decimal_to_float(retail_price_decimal), 2)
    if commission_key:
        item["ppvz_sales_commission"] = round(wb_commission, 2)
    if logistics_key:
        item["delivery_rub"] = round(logistics, 2)
    if storage_key:
        item["storage_fee"] = round(storage, 2)
    if penalties_key:
        item["penalty"] = round(penalties, 2)
    if deductions_key:
        item["deduction"] = round(deductions, 2)
    if payout_key:
        item["ppvz_for_pay"] = round(payout, 2)
    if nm_id:
        item["nmId"] = nm_id
    if seller_sku_raw:
        item["supplierArticle"] = seller_sku_raw
        item["_supplier_article"] = seller_sku_raw
    if row_amount_key:
        item["_row_amount_source_field"] = row_amount_key

    required_missing: List[str] = []
    if not operation_name:
        required_missing.append("operation_name")
    if row_amount_decimal is None:
        required_missing.append("row_amount")
    if commission_decimal is None:
        required_missing.append("wb_commission")
    if payout_decimal is None:
        required_missing.append("payout")

    row_diag = {
        "matched_fields": used_fields,
        "unmapped_fields": {key for key in row.keys() if key not in used_fields},
        "missing_required_fields": required_missing,
        "money_string_fields_parsed": money_string_fields_parsed,
        "parse_errors_count": int(parse_errors[0]),
        "deprecated_fields_seen": deprecated_seen,
        "mode": "new_camel_case" if any(key in row for key in _NEW_FINANCE_HINT_KEYS) else "legacy_compat",
        "semantic_mapping": {
            "operation_name_source": "api_row" if operation_name else "missing",
            "row_amount_source": row_amount_key or "missing",
            "commission_source": commission_key or "missing",
            "payout_source": payout_key or "missing",
            "logistics_source": logistics_key or "missing",
            "storage_source": storage_key or "missing",
            "penalty_source": penalties_key or "missing",
            "deduction_source": deductions_key or "missing",
            "unit_price_source": unit_price_discounted_key or "missing",
            "retail_price_source": retail_price_key or "missing",
        },
    }
    item["_semantic_mapping"] = row_diag["semantic_mapping"]
    return item, row_diag


def _map_rows_to_internal(
    rows_raw: List[Dict[str, Any]],
    *,
    date_from: str,
    date_to: str,
    source_dataset: str,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    matched_fields: set[str] = set()
    unmapped_fields: set[str] = set()
    missing_required_fields: set[str] = set()
    money_string_fields_parsed: set[str] = set()
    deprecated_fields_seen: set[str] = set()
    parse_errors_count = 0
    mode_counts = {"new_camel_case": 0, "legacy_compat": 0}

    for index, row in enumerate(rows_raw):
        if not isinstance(row, dict):
            continue
        row_date = _row_date_iso(row)
        if row_date and (row_date < date_from or row_date > date_to):
            continue
        item, row_diag = _map_row_to_internal(row, index=index, source_dataset=source_dataset)
        rows.append(item)
        matched_fields.update(set(row_diag.get("matched_fields", set())))
        unmapped_fields.update(set(row_diag.get("unmapped_fields", set())))
        missing_required_fields.update(set(row_diag.get("missing_required_fields", [])))
        money_string_fields_parsed.update(set(row_diag.get("money_string_fields_parsed", set())))
        deprecated_fields_seen.update(set(row_diag.get("deprecated_fields_seen", [])))
        parse_errors_count += int(row_diag.get("parse_errors_count", 0) or 0)
        mode_key = str(row_diag.get("mode") or "legacy_compat")
        mode_counts[mode_key] = int(mode_counts.get(mode_key, 0)) + 1

    mapping_diagnostics = {
        "matched_fields": sorted(matched_fields),
        "unmapped_fields": sorted(unmapped_fields),
        "missing_required_fields": sorted(missing_required_fields),
        "money_string_fields_parsed": sorted(money_string_fields_parsed),
        "parse_errors_count": int(parse_errors_count),
        "deprecated_fields_seen": sorted(deprecated_fields_seen),
        "mode_counts": mode_counts,
    }
    return rows, mapping_diagnostics


def _finance_details_by_report_id_endpoint(report_id: str) -> WBEndpoint:
    return WBEndpoint(
        name="finance_sales_reports_detailed_by_id",
        base=BASE_STATISTICS,
        path=f"/api/finance/v1/sales-reports/detailed/{report_id}",
    )


def load_finance_sales_reports_list(client: WBApiClient, date_from: str, date_to: str) -> Dict[str, Any]:
    response = client.request_json(
        endpoint=FINANCE_SALES_REPORTS_LIST,
        method="POST",
        json_body={"dateFrom": date_from, "dateTo": date_to},
        allow_204=True,
        empty_on_204={"data": []},
    )
    payload = response.get("payload", {})
    rows_raw = client.extract_rows(payload, ("data", "items", "rows", "reports"))
    report_ids = _extract_report_ids(payload)
    api_debug = {
        "endpoint": FINANCE_SALES_REPORTS_LIST.name,
        "success": bool(response.get("success", False)),
        "fail": not bool(response.get("success", False)),
        "rows_loaded": len(rows_raw),
        "date_from": date_from,
        "date_to": date_to,
        "status_code": response.get("status_code"),
        "error_text": str(response.get("error") or ""),
        "attempts": int(response.get("attempts", 0) or 0),
        "report_ids": report_ids,
    }
    return {
        "rows": rows_raw,
        "report_ids": report_ids,
        "api_debug": api_debug,
    }


def load_finance_sales_report_details_by_report_id(
    client: WBApiClient,
    *,
    report_id: str,
    date_from: str,
    date_to: str,
    fields: Sequence[str] | None = None,
) -> Dict[str, Any]:
    report_id_text = str(report_id or "").strip()
    response = client.request_json(
        endpoint=_finance_details_by_report_id_endpoint(report_id_text),
        method="POST",
        json_body={"fields": list(fields or FINANCE_REALIZATION_FIELDS)},
        allow_204=True,
        empty_on_204={"data": []},
    )
    payload = response.get("payload", {})
    rows_raw, extracted_report_ids, payload_has_hint = _extract_finance_rows(payload, client)
    rows, mapping_diagnostics = _map_rows_to_internal(
        rows_raw,
        date_from=date_from,
        date_to=date_to,
        source_dataset="realization_api_finance_report_id",
    )
    incompatible = bool(
        bool(response.get("success", False))
        and payload_has_hint
        and not rows_raw
        and payload not in ({}, [], None)
    )
    success = bool(response.get("success", False)) and not incompatible
    error_text = str(response.get("error") or "")
    if incompatible and not error_text:
        error_text = "incompatible finance report payload: rows were not detected"
    api_debug = {
        "endpoint": REALIZATION.name,
        "success": success,
        "fail": not success,
        "rows_loaded": len(rows),
        "date_from": date_from,
        "date_to": date_to,
        "status_code": response.get("status_code"),
        "error_text": error_text,
        "attempts": int(response.get("attempts", 0) or 0),
        "finance_api_mode": "new_by_report_id",
        "finance_endpoint_used": f"/api/finance/v1/sales-reports/detailed/{report_id_text}",
        "finance_report_ids": sorted(set([report_id_text] + extracted_report_ids)),
        "finance_requested_fields_count": len(list(fields or FINANCE_REALIZATION_FIELDS)),
        "finance_requested_fields": list(fields or FINANCE_REALIZATION_FIELDS),
        "finance_mapping_diagnostics": mapping_diagnostics,
        "finance_payload_incompatible": incompatible,
    }
    return {
        "rows": rows,
        "api_debug": api_debug,
    }


def _load_realization_from_finance_detailed_period(
    client: WBApiClient,
    *,
    date_from: str,
    date_to: str,
) -> Dict[str, Any]:
    fields = list(FINANCE_REALIZATION_FIELDS)
    response = client.request_json(
        endpoint=FINANCE_SALES_REPORTS_DETAILED,
        method="POST",
        json_body={"dateFrom": date_from, "dateTo": date_to, "fields": fields},
        allow_204=True,
        empty_on_204={"data": []},
    )
    payload = response.get("payload", {})
    rows_raw, report_ids, payload_has_hint = _extract_finance_rows(payload, client)
    rows, mapping_diagnostics = _map_rows_to_internal(
        rows_raw,
        date_from=date_from,
        date_to=date_to,
        source_dataset="realization_api_finance",
    )

    incompatible = bool(
        bool(response.get("success", False))
        and payload_has_hint
        and not rows_raw
        and payload not in ({}, [], None)
    )
    success = bool(response.get("success", False)) and not incompatible
    error_text = str(response.get("error") or "")
    if incompatible and not error_text:
        error_text = "incompatible finance payload: rows were not detected"

    api_debug = {
        "endpoint": REALIZATION.name,
        "success": success,
        "fail": not success,
        "rows_loaded": len(rows),
        "date_from": date_from,
        "date_to": date_to,
        "error_text": error_text,
        "status_code": response.get("status_code"),
        "attempts": int(response.get("attempts", 0) or 0),
        "finance_api_mode": "new",
        "finance_endpoint_used": FINANCE_SALES_REPORTS_DETAILED.path,
        "finance_report_ids": report_ids,
        "finance_requested_fields_count": len(fields),
        "finance_requested_fields": fields,
        "finance_mapping_diagnostics": mapping_diagnostics,
        "finance_payload_incompatible": incompatible,
    }
    return {
        "rows": rows,
        "api_debug": api_debug,
    }


def _load_realization_from_legacy(
    client: WBApiClient,
    *,
    date_from: str,
    date_to: str,
) -> Dict[str, Any]:
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
    rows, mapping_diagnostics = _map_rows_to_internal(
        rows_raw,
        date_from=date_from,
        date_to=date_to,
        source_dataset="realization_api_legacy",
    )
    success = bool(response.get("success", False))
    api_debug = {
        "endpoint": REALIZATION.name,
        "success": success,
        "fail": not success,
        "rows_loaded": len(rows),
        "date_from": date_from,
        "date_to": date_to,
        "error_text": str(response.get("error") or ""),
        "status_code": response.get("status_code"),
        "attempts": int(response.get("attempts", 0) or 0),
        "finance_api_mode": "legacy_direct",
        "finance_endpoint_used": REALIZATION.path,
        "finance_report_ids": [],
        "finance_requested_fields_count": 0,
        "finance_requested_fields": [],
        "finance_mapping_diagnostics": mapping_diagnostics,
        "finance_payload_incompatible": False,
    }
    return {
        "rows": rows,
        "api_debug": api_debug,
    }


def _should_fallback_to_legacy(primary_debug: Dict[str, Any]) -> bool:
    if not bool(primary_debug.get("success", False)):
        return True
    if bool(primary_debug.get("finance_payload_incompatible", False)):
        return True
    return False


def _build_fallback_bundle(primary: Dict[str, Any], legacy: Dict[str, Any]) -> Dict[str, Any]:
    primary_debug = primary.get("api_debug", {}) if isinstance(primary.get("api_debug"), dict) else {}
    legacy_debug = legacy.get("api_debug", {}) if isinstance(legacy.get("api_debug"), dict) else {}
    rows = list(legacy.get("rows", [])) if isinstance(legacy.get("rows"), list) else []
    requested_fields = primary_debug.get("finance_requested_fields", list(FINANCE_REALIZATION_FIELDS))
    if not isinstance(requested_fields, list):
        requested_fields = list(FINANCE_REALIZATION_FIELDS)

    fallback_reason = "finance_primary_failed"
    if bool(primary_debug.get("finance_payload_incompatible", False)):
        fallback_reason = "finance_primary_incompatible_response"

    api_debug = dict(legacy_debug)
    api_debug.update(
        {
            "endpoint": REALIZATION.name,
            "rows_loaded": len(rows),
            "finance_api_mode": "legacy_fallback",
            "finance_endpoint_used": REALIZATION.path,
            "finance_legacy_endpoint_used": REALIZATION.path,
            "finance_primary_endpoint_attempted": str(
                primary_debug.get("finance_endpoint_used") or FINANCE_SALES_REPORTS_DETAILED.path
            ),
            "finance_primary_status_code": primary_debug.get("status_code"),
            "finance_primary_error_text": str(primary_debug.get("error_text") or ""),
            "finance_primary_payload_incompatible": bool(primary_debug.get("finance_payload_incompatible", False)),
            "finance_primary_mapping_diagnostics": primary_debug.get("finance_mapping_diagnostics", {}),
            "finance_requested_fields_count": int(primary_debug.get("finance_requested_fields_count", len(requested_fields)) or 0),
            "finance_requested_fields": requested_fields,
            "finance_report_ids": list(primary_debug.get("finance_report_ids", []))
            if isinstance(primary_debug.get("finance_report_ids"), list)
            else [],
            "finance_fallback_used": True,
            "finance_fallback_reason": fallback_reason,
        }
    )
    return {
        "rows": rows,
        "api_debug": api_debug,
    }


def load_realization_from_api(client: WBApiClient, date_from: str, date_to: str) -> Dict[str, Any]:
    primary_bundle = _load_realization_from_finance_detailed_period(
        client,
        date_from=date_from,
        date_to=date_to,
    )
    primary_debug = primary_bundle.get("api_debug", {}) if isinstance(primary_bundle.get("api_debug"), dict) else {}
    if not _should_fallback_to_legacy(primary_debug):
        return primary_bundle

    legacy_bundle = _load_realization_from_legacy(
        client,
        date_from=date_from,
        date_to=date_to,
    )
    return _build_fallback_bundle(primary_bundle, legacy_bundle)
