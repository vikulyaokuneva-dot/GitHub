from __future__ import annotations

import re
from typing import Any, Dict, List

from src.cogs import calc_cogs_for_rows

from .financial_models import (
    AccountFinancialTotals,
    CommissionBreakdown,
    FINANCIAL_ROW_FIELD_ALIASES,
    FinancialKernelInput,
    FinancialKernelOutput,
    SKUFinancialRow,
)


def _safe_div(a: float, b: float) -> float:
    return float(a) / float(b) if b else 0.0


def _as_float(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def _as_int(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        return int(float(value))
    except Exception:
        return 0


def _as_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_sku_token(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    cleaned = text.replace("\xa0", " ").replace(",", ".").strip()
    try:
        if re.match(r"^\d+(\.0+)?$", cleaned):
            return str(int(float(cleaned)))
    except Exception:
        pass
    return cleaned


def _normalize_seller_token(value: Any) -> str:
    text = str(value or "").replace("\xa0", " ").strip().lower()
    return " ".join(text.split())


def _first_alias_value(row: Dict[str, Any], semantic_group: str, *extra_keys: str) -> Any:
    aliases = list(FINANCIAL_ROW_FIELD_ALIASES.get(semantic_group, ()))
    if extra_keys:
        aliases.extend(extra_keys)
    for key in aliases:
        if key in row:
            return row.get(key)
    return None


def _operation_label(row: Dict[str, Any]) -> str:
    # Keep parity with v2 calc_financial_metrics operation extraction order.
    raw = row.get("supplier_oper_name") or row.get("operationTypeName") or row.get("doc_type_name")
    return _as_text(raw)


def _is_sale(operation: str) -> bool:
    sale_markers = ("продаж", "реализац", "РїСЂРѕРґР°Р¶")
    return_markers = ("возврат", "return", "refund", "сторно", "РІРѕР·РІСЂР°С‚")
    return any(marker in operation for marker in sale_markers) and not any(
        marker in operation for marker in return_markers
    )


def _is_return(operation: str) -> bool:
    return_markers = ("возврат", "return", "refund", "сторно", "РІРѕР·РІСЂР°С‚")
    return any(marker in operation for marker in return_markers)


def _is_logistics(operation: str) -> bool:
    return ("логист" in operation) or ("доставк" in operation) or ("Р»РѕРіРёСЃС‚" in operation)


def _is_storage(operation: str) -> bool:
    return ("хран" in operation) or ("storage" in operation) or ("С…СЂР°РЅ" in operation)


def _is_penalty(operation: str) -> bool:
    return ("штраф" in operation) or ("С€С‚СЂР°С„" in operation) or ("penalty" in operation) or ("fine" in operation)


def describe_financial_kernel_contract() -> Dict[str, Any]:
    """
    Return formal contract metadata for the v3 financial kernel skeleton.

    This descriptor is used as migration documentation and for smoke checks.
    """

    return {
        "input": {
            "realization_rows": "List[Dict[str, Any]]",
            "tax_rate": "float",
            "cogs_rows": "List[Dict[str, Any]] | None",
            "cogs_file_found": "bool | None",
            "source_meta": "Dict[str, Any]",
        },
        "output": {
            "account_financial_totals": "AccountFinancialTotals",
            "sku_financials": "Dict[int, SKUFinancialRow]",
            "commission_breakdown": "CommissionBreakdown",
            "cogs_diagnostics": "Dict[str, Any]",
            "warnings": "List[Dict[str, Any]]",
            "source_meta": "Dict[str, Any]",
            "kernel_status": "str",
        },
        "financial_row_aliases": FINANCIAL_ROW_FIELD_ALIASES,
        "migration_mode": "account_and_cogs_and_sku_pnl_ported_connected",
    }


def validate_financial_kernel_input(payload: FinancialKernelInput) -> Dict[str, Any]:
    """
    Validate only contract-level readiness (no business calculations).

    This does not reject rows; it reports semantic coverage by alias groups.
    """

    rows = payload.realization_rows if isinstance(payload.realization_rows, list) else []
    row_count = len([row for row in rows if isinstance(row, dict)])

    matched_groups: Dict[str, int] = {}
    for group_name, aliases in FINANCIAL_ROW_FIELD_ALIASES.items():
        matched = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            if any(alias in row for alias in aliases):
                matched += 1
        matched_groups[group_name] = matched

    required_groups = [
        "operation_name",
        "quantity",
        "row_amount",
    ]
    missing_groups = [name for name in required_groups if matched_groups.get(name, 0) <= 0]

    return {
        "rows_total": row_count,
        "matched_groups": matched_groups,
        "required_groups": required_groups,
        "missing_required_groups": missing_groups,
        "ready_for_formula_port": bool(row_count > 0 and not missing_groups),
    }


def run_financial_kernel(payload: FinancialKernelInput) -> FinancialKernelOutput:
    """
    Skeleton entrypoint for future v2->v3 financial parity migration.

    Current step ports account-level formulas, COGS mapping, and SKU P&L
    with parity-oriented behavior vs v2.
    """

    validation = validate_financial_kernel_input(payload)
    rows = [row for row in (payload.realization_rows or []) if isinstance(row, dict)]
    warnings: List[Dict[str, Any]] = []
    missing_groups = validation.get("missing_required_groups", [])
    if isinstance(missing_groups, list) and missing_groups:
        warnings.append(
            {
                "code": "financial_kernel_input_missing_groups",
                "message": "Missing required semantic groups: " + ", ".join(str(item) for item in missing_groups),
            }
        )
    if not rows:
        warnings.append(
            {
                "code": "financial_kernel_rows_empty",
                "message": "No financial rows were provided for account-level calculation.",
            }
        )

    sales_qty = 0
    returns_qty = 0

    gross_revenue = 0.0
    turnover_wb = 0.0
    turnover_wb_rows_count = 0

    commission = 0.0
    base_commission = 0.0
    pvz_compensation = 0.0
    payment_services_compensation = 0.0
    payment_services_compensation_amount = 0.0

    logistics = 0.0
    storage = 0.0
    penalties = 0.0
    payout = 0.0
    qty_by_sku: Dict[int, int] = {}
    sku_seller_tokens: Dict[int, set[str]] = {}
    sku_map: Dict[int, Dict[str, float]] = {}

    def _sku_bucket(sku_id: int) -> Dict[str, float]:
        if sku_id not in sku_map:
            sku_map[sku_id] = {
                "sales_qty": 0.0,
                "returns_qty": 0.0,
                "sales_revenue": 0.0,
                "returns_revenue_est": 0.0,
                "commission": 0.0,
                "logistics": 0.0,
                "storage": 0.0,
                "penalties": 0.0,
                "payout": 0.0,
            }
        return sku_map[sku_id]

    def _estimate_amount(row_amount_value: float, unit_price_value: float, qty_value: int) -> float:
        qty_eff = abs(qty_value) if qty_value else 1
        if row_amount_value:
            return abs(row_amount_value)
        return abs(unit_price_value) * qty_eff

    use_base_before_agent = any(abs(_as_float(row.get("wb_reward_before_agent"))) > 1e-12 for row in rows)

    for row in rows:
        operation = _operation_label(row)
        qty = _as_int(_first_alias_value(row, "quantity"))

        row_amount = _as_float(_first_alias_value(row, "row_amount"))
        unit_price = _as_float(
            _first_alias_value(row, "unit_price_discounted")
            or _first_alias_value(row, "retail_price")
        )
        row_retail_price = _as_float(_first_alias_value(row, "retail_price"))

        row_commission = _as_float(
            row.get("ppvz_sales_commission")
            or row.get("ppvzSalesCommission")
            or row.get("commission_amount")
            or row.get("commissionAmount")
            or 0
        )
        row_base_commission = _as_float(row.get("wb_reward_before_agent"))
        if row_base_commission == 0:
            row_base_commission = row_commission if (not use_base_before_agent or row_commission != 0) else 0.0
        row_pvz_compensation = _as_float(row.get("pvz_compensation"))
        row_payment_services_compensation = _as_float(row.get("payment_services_compensation"))
        row_payment_services_compensation_amount = _as_float(row.get("payment_services_compensation_amount"))
        row_commission_total = (
            float(row_base_commission)
            + float(row_pvz_compensation)
            + float(row_payment_services_compensation)
            + float(row_payment_services_compensation_amount)
        )

        row_logistics = _as_float(
            row.get("deliveryService")
            or row.get("delivery_service")
            or row.get("deliveryServiceRub")
            or row.get("delivery_service_rub")
            or row.get("delivery_rub")
            or row.get("deliveryRub")
            or row.get("deliveryCost")
            or row.get("delivery_cost")
            or row.get("logistics")
            or row.get("logistics_cost")
            or row.get("logistics_amount")
            or 0
        )
        row_storage = _as_float(row.get("storage_fee") or row.get("storageFee") or row.get("storage") or 0)
        row_penalty = _as_float(row.get("penalty") or row.get("penaltyAmount") or row.get("fine") or 0)
        row_payout = _as_float(row.get("ppvz_for_pay") or row.get("ppvzForPay") or row.get("to_pay") or row.get("toPay") or 0)
        sku = row.get("nm_id") or row.get("nmId") or row.get("nmID") or row.get("nm")
        sku_i = _as_int(sku)
        seller_token = _normalize_seller_token(
            row.get("_supplier_article")
            or row.get("supplierArticle")
            or row.get("Артикул поставщика")
            or row.get("Артикул продавца")
            or ""
        )

        if _is_sale(operation):
            if qty > 0:
                sales_qty += qty
                if sku_i:
                    qty_by_sku[sku_i] = qty_by_sku.get(sku_i, 0) + qty
                    if seller_token:
                        sku_seller_tokens.setdefault(sku_i, set()).add(seller_token)

            gross_revenue += row_amount if row_amount else unit_price * (qty if qty else 1)
            if row_retail_price:
                turnover_wb += row_retail_price
                turnover_wb_rows_count += 1

            commission += row_commission_total
            base_commission += row_base_commission
            pvz_compensation += row_pvz_compensation
            payment_services_compensation += row_payment_services_compensation
            payment_services_compensation_amount += row_payment_services_compensation_amount
            payout += row_payout

            logistics += abs(row_logistics) if row_logistics else 0.0
            storage += abs(row_storage) if row_storage else 0.0
            penalties += abs(row_penalty) if row_penalty else 0.0

            if sku_i:
                sku_bucket = _sku_bucket(sku_i)
                if qty > 0:
                    sku_bucket["sales_qty"] += float(qty)
                sku_bucket["sales_revenue"] += float(row_amount) if row_amount else float(unit_price) * float(qty if qty else 1)
                sku_bucket["commission"] += float(row_commission_total)
                sku_bucket["payout"] += float(row_payout)
                if row_logistics:
                    sku_bucket["logistics"] += float(abs(row_logistics))
                if row_storage:
                    sku_bucket["storage"] += float(abs(row_storage))
                if row_penalty:
                    sku_bucket["penalties"] += float(abs(row_penalty))
            continue

        if _is_return(operation):
            if qty != 0:
                returns_qty += abs(qty)

            commission += row_commission_total
            base_commission += row_base_commission
            pvz_compensation += row_pvz_compensation
            payment_services_compensation += row_payment_services_compensation
            payment_services_compensation_amount += row_payment_services_compensation_amount
            logistics += abs(row_logistics) if row_logistics else 0.0
            storage += abs(row_storage) if row_storage else 0.0
            penalties += abs(row_penalty) if row_penalty else 0.0
            payout += row_payout

            if sku_i:
                sku_bucket = _sku_bucket(sku_i)
                if qty != 0:
                    sku_bucket["returns_qty"] += float(abs(qty))
                sku_bucket["returns_revenue_est"] += float(_estimate_amount(row_amount, unit_price, qty))
                sku_bucket["commission"] += float(row_commission_total)
                if row_logistics:
                    sku_bucket["logistics"] += float(abs(row_logistics))
                if row_storage:
                    sku_bucket["storage"] += float(abs(row_storage))
                if row_penalty:
                    sku_bucket["penalties"] += float(abs(row_penalty))
                sku_bucket["payout"] += float(row_payout)
            continue

        if _is_logistics(operation):
            logistics += abs(row_logistics) if row_logistics else 0.0
            rebill = _as_float(row.get("rebill_logistic_cost"))
            logistics += abs(rebill) if rebill else 0.0
            payout += row_payout

            if sku_i:
                sku_bucket = _sku_bucket(sku_i)
                if row_logistics:
                    sku_bucket["logistics"] += float(abs(row_logistics))
                if rebill:
                    sku_bucket["logistics"] += float(abs(rebill))
                sku_bucket["payout"] += float(row_payout)
            continue

        if _is_storage(operation):
            storage += abs(row_storage) if row_storage else 0.0
            payout += row_payout

            if sku_i:
                sku_bucket = _sku_bucket(sku_i)
                if row_storage:
                    sku_bucket["storage"] += float(abs(row_storage))
                sku_bucket["payout"] += float(row_payout)
            continue

        if _is_penalty(operation):
            penalties += abs(row_penalty) if row_penalty else 0.0
            payout += row_payout

            if sku_i:
                sku_bucket = _sku_bucket(sku_i)
                if row_penalty:
                    sku_bucket["penalties"] += float(abs(row_penalty))
                sku_bucket["payout"] += float(row_payout)
            continue

        commission += row_commission_total
        base_commission += row_base_commission
        pvz_compensation += row_pvz_compensation
        payment_services_compensation += row_payment_services_compensation
        payment_services_compensation_amount += row_payment_services_compensation_amount
        logistics += abs(row_logistics) if row_logistics else 0.0
        storage += abs(row_storage) if row_storage else 0.0
        penalties += abs(row_penalty) if row_penalty else 0.0
        payout += row_payout

        if sku_i:
            sku_bucket = _sku_bucket(sku_i)
            sku_bucket["commission"] += float(row_commission_total)
            if row_logistics:
                sku_bucket["logistics"] += float(abs(row_logistics))
            if row_storage:
                sku_bucket["storage"] += float(abs(row_storage))
            if row_penalty:
                sku_bucket["penalties"] += float(abs(row_penalty))
            sku_bucket["payout"] += float(row_payout)

    tax = gross_revenue * float(payload.tax_rate or 0.0)

    cogs_by_sku: Dict[int, float] = {}
    missing_sku_qty: Dict[int, int] = {}
    cogs_rows_loaded = 0
    cogs_sku_total = 0
    cogs_matched_sku = 0
    cogs_unmatched_sku: List[int] = []
    cogs_match_key = "nm_id|seller_article"

    legacy_mode = payload.cogs_rows is None and payload.cogs_file_found is None
    file_found = bool(payload.cogs_file_found) if payload.cogs_file_found is not None else bool(payload.cogs_rows is not None)
    if legacy_mode:
        cogs_total, cogs_by_sku, missing_sku_qty = calc_cogs_for_rows(qty_by_sku)
        cogs_status = "legacy_static_map"
        cogs_rows_loaded = int(len(cogs_by_sku))
        cogs_sku_total = int(len(cogs_by_sku))
        cogs_matched_sku = int(len(cogs_by_sku))
        cogs_unmatched_sku = sorted(int(sku) for sku in missing_sku_qty.keys())[:200]
    else:
        cogs_total = 0.0
        parsed_cogs_rows = [row for row in (payload.cogs_rows or []) if isinstance(row, dict)]
        cogs_rows_loaded = int(len(parsed_cogs_rows))
        cogs_by_sku_id: Dict[int, float] = {}
        cogs_by_sku_token: Dict[str, float] = {}
        cogs_by_seller_token: Dict[str, float] = {}
        for item in parsed_cogs_rows:
            cost = _as_float(item.get("cogs"))
            if cost <= 0:
                continue
            sku_token = _normalize_sku_token(item.get("sku_token") or item.get("sku"))
            seller_cogs_token = _normalize_seller_token(item.get("seller_sku_token") or item.get("seller_sku"))
            if sku_token:
                cogs_by_sku_token[sku_token] = float(cost)
                try:
                    sku_id = int(float(sku_token))
                    if sku_id > 0:
                        cogs_by_sku_id[sku_id] = float(cost)
                except Exception:
                    pass
            if seller_cogs_token:
                cogs_by_seller_token[seller_cogs_token] = float(cost)

        cogs_sku_total = int(len(set(list(cogs_by_sku_token.keys()) + list(cogs_by_seller_token.keys()))))
        for sku_i, qty in qty_by_sku.items():
            if int(qty) <= 0:
                continue
            sku_cost = None
            if sku_i in cogs_by_sku_id:
                sku_cost = cogs_by_sku_id.get(sku_i)
            if sku_cost is None:
                sku_token = _normalize_sku_token(sku_i)
                if sku_token and sku_token in cogs_by_sku_token:
                    sku_cost = cogs_by_sku_token.get(sku_token)
            if sku_cost is None:
                for seller_token in sorted(sku_seller_tokens.get(sku_i) or []):
                    if seller_token in cogs_by_seller_token:
                        sku_cost = cogs_by_seller_token.get(seller_token)
                        break
            if sku_cost is None or float(sku_cost or 0.0) <= 0:
                missing_sku_qty[int(sku_i)] = int(qty)
                cogs_unmatched_sku.append(int(sku_i))
                continue
            sku_cost_total = float(sku_cost) * int(qty)
            cogs_by_sku[int(sku_i)] = round(sku_cost_total, 2)
            cogs_total += sku_cost_total

        cogs_total = round(cogs_total, 2)
        cogs_matched_sku = int(len(cogs_by_sku))
        total_sku_with_qty = int(len([sku for sku, qty in qty_by_sku.items() if int(qty) > 0]))
        cogs_unmatched_sku = sorted(set(cogs_unmatched_sku))[:200]
        if not file_found:
            cogs_status = "file_not_found"
        elif cogs_rows_loaded <= 0:
            cogs_status = "file_found_not_read"
        elif total_sku_with_qty > 0 and cogs_matched_sku == 0:
            cogs_status = "file_read_not_matched"
        elif total_sku_with_qty > 0 and cogs_matched_sku < total_sku_with_qty:
            cogs_status = "partial_match"
        else:
            cogs_status = "full_match"

    profit = gross_revenue - commission - logistics - storage - penalties - tax - cogs_total
    margin = _safe_div(profit, gross_revenue)
    sku_financials: Dict[int, SKUFinancialRow] = {}
    total_sku_sales_revenue = sum(float(bucket.get("sales_revenue", 0.0) or 0.0) for bucket in sku_map.values())
    for sku_i, sku_metrics in sku_map.items():
        sales_revenue = float(sku_metrics.get("sales_revenue", 0.0) or 0.0)
        returns_revenue_est = float(sku_metrics.get("returns_revenue_est", 0.0) or 0.0)
        net_revenue = sales_revenue - returns_revenue_est
        sku_tax = (tax * (sales_revenue / total_sku_sales_revenue)) if total_sku_sales_revenue else 0.0
        sku_cogs = float(cogs_by_sku.get(int(sku_i), 0.0) or 0.0)
        sku_profit = (
            net_revenue
            - float(sku_metrics.get("commission", 0.0) or 0.0)
            - float(sku_metrics.get("logistics", 0.0) or 0.0)
            - float(sku_metrics.get("storage", 0.0) or 0.0)
            - float(sku_metrics.get("penalties", 0.0) or 0.0)
            - sku_tax
            - sku_cogs
        )
        sku_margin = _safe_div(sku_profit, net_revenue)
        sku_financials[int(sku_i)] = SKUFinancialRow(
            sales_qty=int(round(float(sku_metrics.get("sales_qty", 0.0) or 0.0))),
            returns_qty=int(round(float(sku_metrics.get("returns_qty", 0.0) or 0.0))),
            sales_revenue=round(sales_revenue, 2),
            returns_revenue_est=round(returns_revenue_est, 2),
            net_revenue=round(net_revenue, 2),
            commission=round(float(sku_metrics.get("commission", 0.0) or 0.0), 2),
            logistics=round(float(sku_metrics.get("logistics", 0.0) or 0.0), 2),
            storage=round(float(sku_metrics.get("storage", 0.0) or 0.0), 2),
            penalties=round(float(sku_metrics.get("penalties", 0.0) or 0.0), 2),
            payout=round(float(sku_metrics.get("payout", 0.0) or 0.0), 2),
            tax_alloc=round(sku_tax, 2),
            cogs=round(sku_cogs, 2),
            profit=round(sku_profit, 2),
            margin=round(float(sku_margin or 0.0), 4),
        )

    turnover_wb_value: float | None
    if turnover_wb_rows_count > 0:
        turnover_wb_value = round(turnover_wb, 2)
    else:
        turnover_wb_value = None

    totals = AccountFinancialTotals(
        rows_count=len(rows),
        sales_qty=int(sales_qty),
        returns_qty=int(returns_qty),
        gross_revenue=round(gross_revenue, 2),
        turnover_wb=turnover_wb_value,
        turnover_wb_rows_count=int(turnover_wb_rows_count),
        commission=round(commission, 2),
        logistics=round(logistics, 2),
        storage=round(storage, 2),
        penalties=round(penalties, 2),
        payout=round(payout, 2),
        tax_rate=float(payload.tax_rate or 0.0),
        tax=round(tax, 2),
        cogs_total=round(cogs_total, 2),
        profit=round(profit, 2),
        margin=round(margin, 4),
    )
    commission_breakdown = CommissionBreakdown(
        base_commission=round(base_commission, 2),
        pvz_compensation=round(pvz_compensation, 2),
        payment_services_compensation=round(payment_services_compensation, 2),
        payment_services_compensation_amount=round(payment_services_compensation_amount, 2),
        total_commission=round(commission, 2),
    )
    cogs_diagnostics: Dict[str, Any] = {
        "mode": "v2_parity_account_and_sku_pnl_connected",
        "cogs_status": cogs_status,
        "cogs_file_found": bool(file_found),
        "cogs_rows_loaded": int(cogs_rows_loaded),
        "cogs_sku_total": int(cogs_sku_total),
        "cogs_matched_sku": int(cogs_matched_sku),
        "cogs_unmatched_sku": cogs_unmatched_sku,
        "cogs_match_key": cogs_match_key,
        "cogs_total": round(cogs_total, 2),
        "cogs_coverage_pct": round((float(cogs_matched_sku) / float(len(qty_by_sku)) * 100.0), 2) if len(qty_by_sku) > 0 else None,
        # account-level aliases requested for quick coverage interpretation
        "matched_rows": int(cogs_matched_sku),
        "unmatched_rows": int(max(len(qty_by_sku) - cogs_matched_sku, 0)),
        "matched_qty": int(sum(int(qty_by_sku.get(sku, 0)) for sku in cogs_by_sku.keys())),
        "coverage_ratio": _safe_div(float(cogs_matched_sku), float(len(qty_by_sku))) if len(qty_by_sku) > 0 else None,
        "missing_sku_qty": missing_sku_qty,
        "formula_ported": True,
        "cogs_ported": True,
        "sku_pnl_ported": True,
        "validation": validation,
    }
    cogs_warning_by_status = {
        "file_not_found": ("cogs_file_missing", "COGS file was not found; profit is calculated without COGS coverage."),
        "file_found_not_read": ("cogs_rows_empty", "COGS source exists but no valid COGS rows were loaded."),
        "file_read_not_matched": ("cogs_no_matches", "COGS rows loaded but none matched sold SKUs."),
        "partial_match": ("cogs_partial_matches", "COGS rows matched only part of sold SKUs."),
    }
    if cogs_status in cogs_warning_by_status:
        code, message = cogs_warning_by_status[cogs_status]
        warnings.append({"code": code, "message": message})

    return FinancialKernelOutput(
        account_financial_totals=totals,
        sku_financials=sku_financials,
        commission_breakdown=commission_breakdown,
        cogs_diagnostics=cogs_diagnostics,
        warnings=warnings,
        source_meta=dict(payload.source_meta or {}),
        kernel_status="financial_kernel_connected_active_pipeline",
    )
