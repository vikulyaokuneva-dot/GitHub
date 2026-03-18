from __future__ import annotations

from typing import Any, Dict, List, Mapping, Tuple

from ..validation.data_integrity import evaluate_financial_integrity


def _to_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_or_none(value: float | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _as_int(value: Any, default: int = 0) -> int:
    number = _to_float_or_none(value)
    if number is None:
        return int(default)
    return int(round(number))


def _first_non_empty_mapping(*values: Any) -> Dict[str, Any]:
    for value in values:
        if isinstance(value, Mapping) and value:
            return dict(value)
    return {}


def _pick_metric_from_sources(
    *,
    aliases: Tuple[str, ...],
    source_payloads: List[Tuple[str, Dict[str, Any]]],
) -> Tuple[float | None, str]:
    for source_name, payload in source_payloads:
        if not isinstance(payload, Mapping):
            continue
        for key in aliases:
            if key not in payload:
                continue
            candidate = _to_float_or_none(payload.get(key))
            if candidate is None:
                continue
            return float(candidate), str(source_name)
    return None, "unknown"


def _build_source_payloads(
    *,
    totals: Dict[str, Any],
    data_quality: Dict[str, Any],
) -> List[Tuple[str, Dict[str, Any]]]:
    safe_totals = totals if isinstance(totals, dict) else {}
    safe_quality = data_quality if isinstance(data_quality, dict) else {}

    local_payload = _first_non_empty_mapping(
        safe_totals.get("local_report_financial"),
        safe_totals.get("local_financial"),
        safe_totals.get("financial_local"),
        safe_totals.get("supplier_goods_daily"),
        safe_quality.get("local_report_financial"),
        safe_quality.get("local_financial"),
        safe_quality.get("financial_local"),
        safe_quality.get("supplier_goods_daily"),
    )
    api_payload = _first_non_empty_mapping(
        safe_totals.get("api_financial"),
        safe_totals.get("financial_api"),
        safe_totals.get("wb_api_financial"),
        safe_quality.get("api_financial"),
        safe_quality.get("financial_api"),
        safe_quality.get("wb_api_financial"),
    )
    fallback_payload = safe_totals if isinstance(safe_totals, dict) else {}

    return [
        ("local_report", local_payload),
        ("api", api_payload),
        ("fallback", fallback_payload),
    ]


def assemble_financial_kpi(*, totals: Dict[str, Any], data_quality: Dict[str, Any]) -> Dict[str, Any]:
    safe_totals = totals if isinstance(totals, dict) else {}
    safe_data_quality = data_quality if isinstance(data_quality, dict) else {}
    source_payloads = _build_source_payloads(totals=safe_totals, data_quality=safe_data_quality)

    gross_revenue, gross_revenue_source = _pick_metric_from_sources(
        aliases=("gross_revenue", "retail_revenue"),
        source_payloads=source_payloads,
    )
    wb_realized_revenue, wb_realized_source = _pick_metric_from_sources(
        aliases=("wb_realized_revenue", "realized_revenue"),
        source_payloads=source_payloads,
    )
    seller_payout, payout_source = _pick_metric_from_sources(
        aliases=("seller_payout", "payout", "k_perechisleniyu"),
        source_payloads=source_payloads,
    )
    revenue_raw, revenue_source = _pick_metric_from_sources(
        aliases=("revenue", "total_revenue", "row_revenue_total"),
        source_payloads=source_payloads,
    )
    if revenue_raw is None:
        if wb_realized_revenue is not None:
            revenue = wb_realized_revenue
            revenue_source = wb_realized_source
        elif gross_revenue is not None:
            revenue = gross_revenue
            revenue_source = gross_revenue_source
        else:
            revenue = seller_payout
            revenue_source = payout_source
    else:
        revenue = revenue_raw

    cost_price, cost_price_source = _pick_metric_from_sources(
        aliases=("cost_price", "cogs"),
        source_payloads=source_payloads,
    )
    wb_commission, commission_source = _pick_metric_from_sources(
        aliases=("wb_commission", "commission"),
        source_payloads=source_payloads,
    )
    acquiring, acquiring_source = _pick_metric_from_sources(
        aliases=("acquiring",),
        source_payloads=source_payloads,
    )
    pvz_service, pvz_source = _pick_metric_from_sources(
        aliases=("pvz_service",),
        source_payloads=source_payloads,
    )
    logistics, logistics_source = _pick_metric_from_sources(
        aliases=("logistics",),
        source_payloads=source_payloads,
    )
    storage, storage_source = _pick_metric_from_sources(
        aliases=("storage",),
        source_payloads=source_payloads,
    )
    penalties, penalties_source = _pick_metric_from_sources(
        aliases=("penalties",),
        source_payloads=source_payloads,
    )
    deductions, deductions_source = _pick_metric_from_sources(
        aliases=("deductions",),
        source_payloads=source_payloads,
    )
    loyalty_program, loyalty_program_source = _pick_metric_from_sources(
        aliases=("loyalty_program",),
        source_payloads=source_payloads,
    )
    loyalty_points_withheld, loyalty_points_source = _pick_metric_from_sources(
        aliases=("loyalty_points_withheld",),
        source_payloads=source_payloads,
    )
    other_adjustments, other_adjustments_source = _pick_metric_from_sources(
        aliases=("other_adjustments",),
        source_payloads=source_payloads,
    )
    tax, tax_source = _pick_metric_from_sources(
        aliases=("tax",),
        source_payloads=source_payloads,
    )
    ads_spend, ads_source = _pick_metric_from_sources(
        aliases=("ads_spend_total", "ads_spend"),
        source_payloads=source_payloads,
    )

    explicit_net_profit, explicit_profit_source = _pick_metric_from_sources(
        aliases=("net_profit", "profit", "total_profit"),
        source_payloads=source_payloads,
    )

    gross_profit: float | None = None
    if revenue is not None and cost_price is not None and wb_commission is not None:
        gross_profit = revenue - cost_price - wb_commission

    formula_components: List[float | None] = [
        cost_price,
        wb_commission,
        acquiring,
        pvz_service,
        logistics,
        storage,
        penalties,
        deductions,
        loyalty_program,
        loyalty_points_withheld,
        other_adjustments,
        ads_spend,
        tax,
    ]
    net_profit: float | None = explicit_net_profit
    if net_profit is None and revenue is not None and all(component is not None for component in formula_components):
        net_profit = revenue - sum(float(component) for component in formula_components if component is not None)
        explicit_profit_source = "derived_formula"

    margin_pct: float | None = None
    if net_profit is not None and revenue is not None and abs(revenue) > 1e-9:
        margin_pct = net_profit / revenue * 100.0

    profitability_pct: float | None = None
    if net_profit is not None and cost_price is not None and abs(cost_price) > 1e-9:
        profitability_pct = net_profit / cost_price * 100.0

    invalid_rows = _as_int(safe_data_quality.get("invalid_sku_rows", 0), default=0)
    unassigned_present = bool(safe_data_quality.get("unassigned_costs_present", False))
    sku_attribution_status = str(safe_data_quality.get("sku_attribution_status") or "ok")

    has_financial_activity = any(
        value is not None and abs(float(value)) > 1e-9
        for value in (
            revenue,
            acquiring,
            pvz_service,
            logistics,
            storage,
            penalties,
            deductions,
            loyalty_program,
            loyalty_points_withheld,
            other_adjustments,
            tax,
            ads_spend,
        )
    )
    cost_price_missing = bool(has_financial_activity and cost_price is None)
    wb_commission_missing = bool(has_financial_activity and wb_commission is None)
    expense_attribution_partial = bool(invalid_rows > 0 or unassigned_present)

    integrity_sources = (
        safe_data_quality.get("data_sources", {})
        if isinstance(safe_data_quality.get("data_sources"), dict)
        else {}
    )
    integrity_sources = dict(integrity_sources)
    integrity_sources.update(
        {
            "revenue": revenue_source,
            "commission": commission_source,
            "logistics": logistics_source,
            "storage": storage_source,
            "penalties": penalties_source,
            "deductions": deductions_source,
            "cost_price": cost_price_source,
            "tax": tax_source,
            "ads_spend": ads_source,
        }
    )

    integrity = evaluate_financial_integrity(
        totals={
            "revenue": revenue,
            "total_revenue": revenue,
            "wb_commission": wb_commission,
            "logistics": logistics,
            "storage": storage,
            "penalties": penalties,
            "deductions": deductions,
            "cost_price": cost_price,
            "tax": tax,
            "ads_spend_total": ads_spend,
        },
        data_sources=integrity_sources,
        sku_attribution_status=sku_attribution_status,
        ads_rows_count=_as_int(safe_data_quality.get("ads_rows", 0), default=0),
    )
    completeness_pct = float(integrity.get("financial_completeness_pct", 0.0) or 0.0)
    financial_finality_status = str(integrity.get("financial_finality_status") or "unavailable")

    net_profit_partial = bool(
        financial_finality_status != "final"
        or cost_price_missing
        or wb_commission_missing
        or expense_attribution_partial
        or net_profit is None
    )
    financial_margin_not_final = bool(net_profit_partial)

    if financial_finality_status == "final" and not net_profit_partial:
        financial_status = "ok"
    elif financial_finality_status in {"partial", "sparse"} or net_profit_partial:
        financial_status = "partial"
    else:
        financial_status = "degraded"
    financial_partial = bool(financial_status != "ok")

    financial_kpi = {
        "revenue": _round_or_none(revenue, 2),
        "gross_revenue": _round_or_none(gross_revenue, 2),
        "wb_realized_revenue": _round_or_none(wb_realized_revenue, 2),
        "seller_payout": _round_or_none(seller_payout, 2),
        "revenue_basis": "seller_payout" if seller_payout is not None else "revenue",
        "cost_price": _round_or_none(cost_price, 2),
        "wb_commission": _round_or_none(wb_commission, 2),
        "acquiring": _round_or_none(acquiring, 2),
        "pvz_service": _round_or_none(pvz_service, 2),
        "logistics": _round_or_none(logistics, 2),
        "storage": _round_or_none(storage, 2),
        "penalties": _round_or_none(penalties, 2),
        "deductions": _round_or_none(deductions, 2),
        "loyalty_program": _round_or_none(loyalty_program, 2),
        "loyalty_points_withheld": _round_or_none(loyalty_points_withheld, 2),
        "loyalty_total": _round_or_none(
            (loyalty_program or 0.0) + (loyalty_points_withheld or 0.0), 2
        )
        if loyalty_program is not None or loyalty_points_withheld is not None
        else None,
        "other_adjustments": _round_or_none(other_adjustments, 2),
        "tax": _round_or_none(tax, 2),
        "cogs": _round_or_none(cost_price, 2),
        "ads_spend": _round_or_none(ads_spend, 2),
        "gross_profit": _round_or_none(gross_profit, 2),
        "net_profit": _round_or_none(net_profit, 2),
        "margin_pct": _round_or_none(margin_pct, 2),
        "profitability_pct": _round_or_none(profitability_pct, 2),
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
        "is_partial": financial_partial,
        "financial_status": financial_status,
        "financial_partial": financial_partial,
        "basis": "buyouts",
        "source_priority": {
            "revenue": revenue_source,
            "seller_payout": payout_source,
            "wb_commission": commission_source,
            "logistics": logistics_source,
            "ads_spend": ads_source,
            "net_profit": explicit_profit_source,
            "acquiring": acquiring_source,
            "pvz_service": pvz_source,
            "storage": storage_source,
            "penalties": penalties_source,
            "deductions": deductions_source,
            "loyalty_program": loyalty_program_source,
            "loyalty_points_withheld": loyalty_points_source,
            "other_adjustments": other_adjustments_source,
            "tax": tax_source,
        },
        "net_profit_formula": {
            "revenue_basis": _round_or_none(revenue, 2),
            "cost_price": _round_or_none(cost_price, 2),
            "wb_commission": _round_or_none(wb_commission, 2),
            "acquiring": _round_or_none(acquiring, 2),
            "pvz_service": _round_or_none(pvz_service, 2),
            "logistics": _round_or_none(logistics, 2),
            "storage": _round_or_none(storage, 2),
            "penalties": _round_or_none(penalties, 2),
            "deductions": _round_or_none(deductions, 2),
            "loyalty_program": _round_or_none(loyalty_program, 2),
            "loyalty_points_withheld": _round_or_none(loyalty_points_withheld, 2),
            "other_adjustments": _round_or_none(other_adjustments, 2),
            "ads_spend": _round_or_none(ads_spend, 2),
            "tax": _round_or_none(tax, 2),
            "net_profit": _round_or_none(net_profit, 2),
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
            "is_partial": bool(financial_partial),
            "financial_status": financial_status,
            "financial_partial": financial_partial,
        },
    }
