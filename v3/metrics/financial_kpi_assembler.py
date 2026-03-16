from __future__ import annotations

from typing import Any, Dict, List

from ..validation.data_integrity import evaluate_financial_integrity


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def assemble_financial_kpi(*, totals: Dict[str, Any], data_quality: Dict[str, Any]) -> Dict[str, Any]:
    safe_totals = totals if isinstance(totals, dict) else {}
    safe_data_quality = data_quality if isinstance(data_quality, dict) else {}

    gross_revenue = _safe_float(safe_totals.get("gross_revenue", 0.0))
    wb_realized_revenue = _safe_float(safe_totals.get("wb_realized_revenue", 0.0))
    seller_payout = _safe_float(
        safe_totals.get(
            "seller_payout",
            safe_totals.get("total_revenue", safe_totals.get("revenue", 0.0)),
        )
    )
    revenue = (
        seller_payout
        if abs(seller_payout) > 1e-9
        else _safe_float(safe_totals.get("total_revenue", safe_totals.get("revenue", 0.0)))
    )

    cost_price = _safe_float(safe_totals.get("cost_price", 0.0))
    wb_commission = _safe_float(safe_totals.get("wb_commission", 0.0))
    acquiring = _safe_float(safe_totals.get("acquiring", 0.0))
    pvz_service = _safe_float(safe_totals.get("pvz_service", 0.0))
    logistics = _safe_float(safe_totals.get("logistics", 0.0))
    storage = _safe_float(safe_totals.get("storage", 0.0))
    penalties = _safe_float(safe_totals.get("penalties", 0.0))
    deductions = _safe_float(safe_totals.get("deductions", 0.0))
    loyalty_program = _safe_float(safe_totals.get("loyalty_program", 0.0))
    loyalty_points_withheld = _safe_float(safe_totals.get("loyalty_points_withheld", 0.0))
    other_adjustments = _safe_float(safe_totals.get("other_adjustments", 0.0))
    tax = _safe_float(safe_totals.get("tax", 0.0))
    ads_spend = _safe_float(safe_totals.get("ads_spend_total", safe_totals.get("ads_spend", 0.0)))

    gross_profit = revenue - cost_price - wb_commission
    net_profit = (
        revenue
        - cost_price
        - wb_commission
        - acquiring
        - pvz_service
        - logistics
        - storage
        - penalties
        - deductions
        - loyalty_program
        - loyalty_points_withheld
        - other_adjustments
        - ads_spend
        - tax
    )
    margin_pct = (net_profit / revenue * 100.0) if revenue > 0 else 0.0
    profitability_pct = (net_profit / cost_price * 100.0) if cost_price > 0 else 0.0

    invalid_rows = int(_safe_float(safe_data_quality.get("invalid_sku_rows", 0)))
    unassigned_present = bool(safe_data_quality.get("unassigned_costs_present", False))
    sku_attribution_status = str(safe_data_quality.get("sku_attribution_status") or "ok")

    has_financial_activity = bool(
        abs(revenue) > 1e-9
        or abs(acquiring) > 1e-9
        or abs(pvz_service) > 1e-9
        or abs(logistics) > 1e-9
        or abs(storage) > 1e-9
        or abs(penalties) > 1e-9
        or abs(deductions) > 1e-9
        or abs(loyalty_program) > 1e-9
        or abs(loyalty_points_withheld) > 1e-9
        or abs(other_adjustments) > 1e-9
        or abs(tax) > 1e-9
        or abs(ads_spend) > 1e-9
    )
    cost_price_missing = bool(has_financial_activity and abs(cost_price) <= 1e-9)
    wb_commission_missing = bool(has_financial_activity and abs(wb_commission) <= 1e-9)
    expense_attribution_partial = bool(invalid_rows > 0 or unassigned_present)

    integrity = evaluate_financial_integrity(
        totals=safe_totals,
        data_sources=safe_data_quality.get("data_sources", {}) if isinstance(safe_data_quality.get("data_sources"), dict) else {},
        sku_attribution_status=sku_attribution_status,
        ads_rows_count=int(_safe_float(safe_data_quality.get("ads_rows", 0))),
    )
    completeness_pct = float(integrity.get("financial_completeness_pct", 0.0) or 0.0)
    financial_finality_status = str(integrity.get("financial_finality_status") or "unavailable")

    net_profit_partial = bool(
        financial_finality_status != "final"
        or cost_price_missing
        or wb_commission_missing
        or expense_attribution_partial
    )
    financial_margin_not_final = bool(net_profit_partial)

    financial_kpi = {
        "revenue": round(revenue, 2),
        "gross_revenue": round(gross_revenue, 2),
        "wb_realized_revenue": round(wb_realized_revenue, 2),
        "seller_payout": round(seller_payout, 2),
        "revenue_basis": "seller_payout",
        "cost_price": round(cost_price, 2),
        "wb_commission": round(wb_commission, 2),
        "acquiring": round(acquiring, 2),
        "pvz_service": round(pvz_service, 2),
        "logistics": round(logistics, 2),
        "storage": round(storage, 2),
        "penalties": round(penalties, 2),
        "deductions": round(deductions, 2),
        "loyalty_program": round(loyalty_program, 2),
        "loyalty_points_withheld": round(loyalty_points_withheld, 2),
        "loyalty_total": round(loyalty_program + loyalty_points_withheld, 2),
        "other_adjustments": round(other_adjustments, 2),
        "tax": round(tax, 2),
        "cogs": round(cost_price, 2),
        "ads_spend": round(ads_spend, 2),
        "gross_profit": round(gross_profit, 2),
        "net_profit": round(net_profit, 2),
        "margin_pct": round(margin_pct, 2),
        "profitability_pct": round(profitability_pct, 2),
        "cost_price_missing": cost_price_missing,
        "wb_commission_missing": wb_commission_missing,
        "expense_attribution_partial": expense_attribution_partial,
        "net_profit_partial": net_profit_partial,
        "financial_margin_not_final": financial_margin_not_final,
        "completeness_pct": round(completeness_pct, 2),
        "components": integrity.get("components", {}),
        "available_components": int(integrity.get("available_components", 0) or 0),
        "total_components": int(integrity.get("total_components", 0) or 0),
        "financial_finality_status": financial_finality_status,
        "is_partial": net_profit_partial,
        "basis": "buyouts",
        "net_profit_formula": {
            "revenue_basis": round(revenue, 2),
            "cost_price": round(cost_price, 2),
            "wb_commission": round(wb_commission, 2),
            "acquiring": round(acquiring, 2),
            "pvz_service": round(pvz_service, 2),
            "logistics": round(logistics, 2),
            "storage": round(storage, 2),
            "penalties": round(penalties, 2),
            "deductions": round(deductions, 2),
            "loyalty_program": round(loyalty_program, 2),
            "loyalty_points_withheld": round(loyalty_points_withheld, 2),
            "other_adjustments": round(other_adjustments, 2),
            "ads_spend": round(ads_spend, 2),
            "tax": round(tax, 2),
            "net_profit": round(net_profit, 2),
        },
    }

    warning_additions: List[Dict[str, Any]] = []
    if cost_price_missing:
        warning_additions.append(
            {
                "code": "cost_price_missing",
                "message": "Cost price is missing; financial net profit is partial.",
            }
        )
    if wb_commission_missing:
        warning_additions.append(
            {
                "code": "wb_commission_missing",
                "message": "WB commission is missing; financial net profit is partial.",
            }
        )
    if expense_attribution_partial:
        warning_additions.append(
            {
                "code": "expense_attribution_partial",
                "message": "Expense attribution is partial due to unassigned or invalid SKU rows.",
            }
        )
    if net_profit_partial:
        warning_additions.append(
            {
                "code": "net_profit_partial",
                "message": "Net profit is partial due to missing or partially attributed financial components.",
            }
        )
    if financial_margin_not_final:
        warning_additions.append(
            {
                "code": "financial_margin_not_final",
                "message": "Financial margin is not final because net profit is partial.",
            }
        )

    return {
        "financial_kpi": financial_kpi,
        "warning_additions": warning_additions,
        "flags": {
            "cost_price_missing": bool(cost_price_missing),
            "wb_commission_missing": bool(wb_commission_missing),
            "expense_attribution_partial": bool(expense_attribution_partial),
            "net_profit_partial": bool(net_profit_partial),
            "financial_margin_not_final": bool(financial_margin_not_final),
            "completeness_pct": round(completeness_pct, 2),
            "financial_finality_status": financial_finality_status,
            "is_partial": bool(net_profit_partial),
        },
    }
