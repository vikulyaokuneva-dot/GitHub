from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping


FINANCIAL_COMPONENT_KEYS = (
    "revenue",
    "commission",
    "logistics",
    "storage",
    "penalties",
    "deductions",
    "cost_price",
    "tax",
    "ads_spend",
)

_PARSER_ERROR_REASONS = {
    "parser_error",
    "invalid_literal",
    "contains_non_digits",
    "contains_non_digits_or_chars",
    "contains_invalid_chars",
    "length_out_of_range",
    "invalid_chars",
    "unknown",
}
_MISSING_FIELD_REASONS = {"missing_field", "empty", "zero_value", "missing_or_zero", "empty_or_zero"}


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _reason(row: Mapping[str, Any]) -> str:
    return str(row.get("_sku_validation_reason") or "").strip().lower() or "unknown"


def _is_true_unassigned_financial_row(row: Mapping[str, Any]) -> bool:
    reason = _reason(row)
    if reason not in _MISSING_FIELD_REASONS:
        return False

    revenue = abs(_safe_float(row.get("revenue")))
    cost_price = abs(_safe_float(row.get("cost_price")))
    wb_commission = abs(_safe_float(row.get("wb_commission")))
    logistics = abs(_safe_float(row.get("logistics")))
    storage = abs(_safe_float(row.get("storage")))
    penalties = abs(_safe_float(row.get("penalties")))
    deductions = abs(_safe_float(row.get("deductions")))
    ads_spend = abs(_safe_float(row.get("ads_spend")))
    has_only_costs = revenue <= 1e-9 and (cost_price + wb_commission + logistics + storage + penalties + deductions + ads_spend) > 1e-9
    return bool(has_only_costs)


def evaluate_sku_attribution(
    *,
    valid_sku_count: int,
    sales_unassigned: Iterable[Mapping[str, Any]],
    ads_unassigned: Iterable[Mapping[str, Any]],
    stocks_unassigned: Iterable[Mapping[str, Any]],
    sales_activity_qty: float,
) -> Dict[str, Any]:
    parser_error_count = 0
    missing_field_count = 0
    true_unassigned_count = 0

    for row in list(sales_unassigned) + list(ads_unassigned) + list(stocks_unassigned):
        if not isinstance(row, Mapping):
            continue
        reason = _reason(row)
        if _is_true_unassigned_financial_row(row):
            true_unassigned_count += 1
            continue
        if reason in _MISSING_FIELD_REASONS:
            missing_field_count += 1
            continue
        if reason in _PARSER_ERROR_REASONS:
            parser_error_count += 1
        else:
            parser_error_count += 1

    invalid_total = parser_error_count + missing_field_count + true_unassigned_count
    no_valid_with_sales = bool(int(valid_sku_count) <= 0 and _safe_float(sales_activity_qty) > 0)

    if no_valid_with_sales or (invalid_total >= 10 and int(valid_sku_count) <= 0):
        status = "broken"
    elif invalid_total > 0:
        status = "degraded"
    else:
        status = "ok"

    return {
        "sku_attribution_status": status,
        "invalid_sku_rows_parser_error": int(parser_error_count),
        "invalid_sku_rows_missing_field": int(missing_field_count),
        "unassigned_rows_true": int(true_unassigned_count),
        "attribution_guard_triggered": bool(status != "ok"),
        "no_valid_sku_with_sales_activity": no_valid_with_sales,
    }


def evaluate_financial_integrity(
    *,
    totals: Mapping[str, Any],
    data_sources: Mapping[str, Any] | None = None,
    sku_attribution_status: str,
    ads_rows_count: int = 0,
) -> Dict[str, Any]:
    safe_totals = totals if isinstance(totals, Mapping) else {}
    safe_sources = data_sources if isinstance(data_sources, Mapping) else {}

    revenue = _safe_float(safe_totals.get("total_revenue", safe_totals.get("revenue")))
    commission = _safe_float(safe_totals.get("wb_commission"))
    logistics = _safe_float(safe_totals.get("logistics"))
    storage = _safe_float(safe_totals.get("storage"))
    penalties = _safe_float(safe_totals.get("penalties"))
    deductions = _safe_float(safe_totals.get("deductions"))
    cost_price = _safe_float(safe_totals.get("cost_price"))
    tax = _safe_float(safe_totals.get("tax"))
    ads_spend = _safe_float(safe_totals.get("ads_spend_total", safe_totals.get("ads_spend")))

    has_activity = bool(
        abs(revenue) > 1e-9
        or abs(commission) > 1e-9
        or abs(logistics) > 1e-9
        or abs(storage) > 1e-9
        or abs(penalties) > 1e-9
        or abs(deductions) > 1e-9
        or abs(cost_price) > 1e-9
        or abs(tax) > 1e-9
        or abs(ads_spend) > 1e-9
        or int(ads_rows_count) > 0
    )

    component_values = {
        "revenue": revenue,
        "commission": commission,
        "logistics": logistics,
        "storage": storage,
        "penalties": penalties,
        "deductions": deductions,
        "cost_price": cost_price,
        "tax": tax,
        "ads_spend": ads_spend,
    }

    components: Dict[str, Dict[str, Any]] = {}
    available_count = 0
    trusted_count = 0
    for key in FINANCIAL_COMPONENT_KEYS:
        value = component_values.get(key, 0.0)
        source = str(safe_sources.get(key) or "aggregated_rows")
        available = bool(has_activity and abs(value) > 1e-9) or (key == "ads_spend" and int(ads_rows_count) > 0)
        confirmed = bool(source.strip().lower() not in {"", "unknown"})
        trusted = bool(available and confirmed and str(sku_attribution_status or "ok") != "broken")
        if available:
            available_count += 1
        if trusted:
            trusted_count += 1
        components[key] = {
            "available": available,
            "confirmed": confirmed,
            "source": source,
            "trusted_for_final_reporting": trusted,
        }

    total_components = len(FINANCIAL_COMPONENT_KEYS)
    completeness_pct = (float(available_count) / float(total_components) * 100.0) if total_components > 0 else 0.0

    if available_count <= 0:
        finality = "unavailable"
    elif available_count <= 2:
        finality = "sparse"
    elif trusted_count == total_components and str(sku_attribution_status or "ok") == "ok":
        finality = "final"
    else:
        finality = "partial"

    return {
        "components": components,
        "available_components": int(available_count),
        "total_components": int(total_components),
        "financial_completeness_pct": round(completeness_pct, 2),
        "financial_finality_status": finality,
        "is_partial": bool(finality != "final"),
    }


def resolve_report_reliability_level(
    *,
    sku_attribution_status: str,
    financial_finality_status: str,
    ads_analysis_enabled: bool,
) -> str:
    sku_status = str(sku_attribution_status or "ok")
    financial_status = str(financial_finality_status or "unavailable")
    if sku_status == "broken" or financial_status in {"unavailable", "sparse"}:
        return "low"
    if financial_status in {"partial"} or not bool(ads_analysis_enabled):
        return "medium"
    return "high"

