from __future__ import annotations

from typing import Any, Dict, List

from .financial_models import (
    AccountFinancialTotals,
    CommissionBreakdown,
    FINANCIAL_ROW_FIELD_ALIASES,
    FinancialKernelInput,
    FinancialKernelOutput,
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
    # v2 parity: sale if contains "продаж" and does not contain "возврат".
    return ("продаж" in operation) and ("возврат" not in operation)


def _is_return(operation: str) -> bool:
    return ("возврат" in operation) or ("return" in operation)


def _is_logistics(operation: str) -> bool:
    return "логист" in operation


def _is_storage(operation: str) -> bool:
    return "хран" in operation


def _is_penalty(operation: str) -> bool:
    return ("штраф" in operation) or ("penalty" in operation) or ("fine" in operation)


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
        "migration_mode": "account_level_formulas_ported_cogs_sku_pending",
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

    Current step intentionally does NOT port formulas.
    It returns a structured placeholder output and diagnostics only.
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
            row.get("delivery_rub")
            or row.get("deliveryRub")
            or row.get("logistics")
            or row.get("logistics_cost")
            or 0
        )
        row_storage = _as_float(row.get("storage_fee") or row.get("storageFee") or row.get("storage") or 0)
        row_penalty = _as_float(row.get("penalty") or row.get("penaltyAmount") or row.get("fine") or 0)
        row_payout = _as_float(row.get("ppvz_for_pay") or row.get("ppvzForPay") or row.get("to_pay") or row.get("toPay") or 0)

        if _is_sale(operation):
            if qty > 0:
                sales_qty += qty

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
            continue

        if _is_logistics(operation):
            logistics += abs(row_logistics) if row_logistics else 0.0
            rebill = _as_float(row.get("rebill_logistic_cost"))
            logistics += abs(rebill) if rebill else 0.0
            payout += row_payout
            continue

        if _is_storage(operation):
            storage += abs(row_storage) if row_storage else 0.0
            payout += row_payout
            continue

        if _is_penalty(operation):
            penalties += abs(row_penalty) if row_penalty else 0.0
            payout += row_payout
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

    tax = gross_revenue * float(payload.tax_rate or 0.0)
    cogs_total = 0.0  # not ported in this step by design
    profit = gross_revenue - commission - logistics - storage - penalties - tax - cogs_total
    margin = _safe_div(profit, gross_revenue)

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
        "mode": "not_ported",
        "cogs_rows_loaded": len(payload.cogs_rows or []),
        "cogs_file_found": payload.cogs_file_found,
        "formula_ported": False,
        "cogs_ported": False,
        "sku_pnl_ported": False,
        "validation": validation,
    }
    warnings.append(
        {
            "code": "financial_kernel_partial_port",
            "message": "Account-level formulas are ported; COGS and SKU P&L are not ported yet.",
        }
    )

    return FinancialKernelOutput(
        account_financial_totals=totals,
        sku_financials={},
        commission_breakdown=commission_breakdown,
        cogs_diagnostics=cogs_diagnostics,
        warnings=warnings,
        source_meta=dict(payload.source_meta or {}),
        kernel_status="account_level_ported_partial",
    )
