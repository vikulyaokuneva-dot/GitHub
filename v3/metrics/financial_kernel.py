from __future__ import annotations

from typing import Any, Dict, List

from .financial_models import (
    AccountFinancialTotals,
    CommissionBreakdown,
    FINANCIAL_ROW_FIELD_ALIASES,
    FinancialKernelInput,
    FinancialKernelOutput,
)


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
        "migration_mode": "skeleton_only_no_formulas_ported",
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
    warnings: List[Dict[str, Any]] = [
        {
            "code": "financial_kernel_skeleton_not_implemented",
            "message": "Financial formulas are not ported yet; skeleton contract only.",
        }
    ]
    missing_groups = validation.get("missing_required_groups", [])
    if isinstance(missing_groups, list) and missing_groups:
        warnings.append(
            {
                "code": "financial_kernel_input_missing_groups",
                "message": "Missing required semantic groups: " + ", ".join(str(item) for item in missing_groups),
            }
        )

    totals = AccountFinancialTotals(
        rows_count=int(validation.get("rows_total", 0) or 0),
        tax_rate=float(payload.tax_rate),
    )
    commission_breakdown = CommissionBreakdown(total_commission=0.0)
    cogs_diagnostics: Dict[str, Any] = {
        "mode": "skeleton",
        "cogs_rows_loaded": len(payload.cogs_rows or []),
        "cogs_file_found": payload.cogs_file_found,
        "formula_ported": False,
        "validation": validation,
    }

    return FinancialKernelOutput(
        account_financial_totals=totals,
        sku_financials={},
        commission_breakdown=commission_breakdown,
        cogs_diagnostics=cogs_diagnostics,
        warnings=warnings,
        source_meta=dict(payload.source_meta or {}),
        kernel_status="skeleton_not_connected",
    )
