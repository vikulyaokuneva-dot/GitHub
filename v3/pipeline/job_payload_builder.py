from __future__ import annotations

from typing import Any, Dict


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def build_daily_job_payload(
    *,
    input_debug: Dict[str, Any],
    api_debug: Dict[str, Any],
    daily_kpi: Dict[str, Any],
    ads_summary: Dict[str, Any],
    ads_rows_count: int,
    financial_kpi: Dict[str, Any],
    ads_loaded_from_file: bool,
    ads_source_file: str,
    ads_attribution_quality: str,
    data_source_orders_count: str,
    data_source_buyouts_count: str,
    data_source_orders_amount: str,
    data_source_buyouts_amount: str,
    data_source_revenue: str,
    data_source_wb_commission: str,
    data_source_logistics: str,
    data_source_storage: str,
    data_source_ads_spend: str,
    source_flags: Dict[str, Any],
    facts_financial_status: str,
    metrics: Dict[str, Any],
) -> Dict[str, Any]:
    safe_daily_kpi = daily_kpi if isinstance(daily_kpi, dict) else {}
    safe_ads_summary = ads_summary if isinstance(ads_summary, dict) else {}
    safe_financial_kpi = financial_kpi if isinstance(financial_kpi, dict) else {}
    safe_metrics = metrics if isinstance(metrics, dict) else {}
    event_date_model = safe_metrics.get("event_date_model", {})
    if not isinstance(event_date_model, dict):
        event_date_model = {}
    order_kpi = safe_metrics.get("order_kpi", {})
    if not isinstance(order_kpi, dict):
        order_kpi = {}
    buyout_kpi = safe_metrics.get("buyout_kpi", {})
    if not isinstance(buyout_kpi, dict):
        buyout_kpi = {}
    daily_status_matrix = safe_metrics.get("daily_status_matrix", {})
    if not isinstance(daily_status_matrix, dict):
        daily_status_matrix = {}
    render_kpi = safe_metrics.get("render_kpi", {})
    if not isinstance(render_kpi, dict):
        render_kpi = {}
    event_ledger = safe_metrics.get("event_ledger", {})
    if not isinstance(event_ledger, dict):
        event_ledger = {}
    return {
        "input_debug": input_debug,
        "api_debug": api_debug,
        "daily_orders_count": int(safe_daily_kpi.get("daily_orders_count", 0) or 0),
        "daily_orders_amount": round(_safe_float(safe_daily_kpi.get("daily_orders_amount", 0.0)), 2),
        "daily_buyouts_count": int(safe_daily_kpi.get("daily_buyouts_count", 0) or 0),
        "daily_buyouts_amount": round(_safe_float(safe_daily_kpi.get("daily_buyouts_amount", 0.0)), 2),
        "ads_rows": int(safe_ads_summary.get("ads_rows", ads_rows_count) or 0),
        "ads_spend": round(_safe_float(safe_ads_summary.get("ads_spend", safe_financial_kpi.get("ads_spend", 0.0))), 2),
        "ads_loaded_from_file": bool(safe_ads_summary.get("ads_loaded_from_file", ads_loaded_from_file)),
        "ads_source_file": str(safe_ads_summary.get("ads_source_file", ads_source_file) or ""),
        "ads_file_candidates_found": int(safe_ads_summary.get("ads_file_candidates_found", 0) or 0),
        "ads_file_detected": bool(safe_ads_summary.get("ads_file_detected", False)),
        "ads_sheet_found": str(safe_ads_summary.get("ads_sheet_found") or ""),
        "ads_columns_detected": (
            [str(item) for item in safe_ads_summary.get("ads_columns_detected", []) if str(item).strip()]
            if isinstance(safe_ads_summary.get("ads_columns_detected"), list)
            else []
        ),
        "ads_rows_raw": int(safe_ads_summary.get("ads_rows_raw", 0) or 0),
        "ads_rows_usable": int(safe_ads_summary.get("ads_rows_usable", ads_rows_count) or 0),
        "ads_loader_error": str(safe_ads_summary.get("ads_loader_error") or ""),
        "ads_attribution_quality": str(safe_ads_summary.get("ads_attribution_quality", ads_attribution_quality) or "unknown"),
        "data_source_orders": data_source_orders_count,
        "data_source_orders_count": data_source_orders_count,
        "data_source_orders_amount": data_source_orders_amount,
        "data_source_buyouts": data_source_buyouts_count,
        "data_source_buyouts_count": data_source_buyouts_count,
        "data_source_buyouts_amount": data_source_buyouts_amount,
        "orders_count_confirmed": bool(safe_daily_kpi.get("orders_count_confirmed", False)),
        "buyouts_count_confirmed": bool(safe_daily_kpi.get("buyouts_count_confirmed", False)),
        "sku_activity_orders_hint": int(safe_daily_kpi.get("sku_activity_orders_hint", 0) or 0),
        "sku_activity_buyouts_hint": int(safe_daily_kpi.get("sku_activity_buyouts_hint", 0) or 0),
        "orders_count_unknown_reason": str(safe_daily_kpi.get("orders_count_unknown_reason") or ""),
        "buyouts_count_unknown_reason": str(safe_daily_kpi.get("buyouts_count_unknown_reason") or ""),
        "commerce_activity": safe_metrics.get("commerce_activity", {}) if isinstance(safe_metrics.get("commerce_activity"), dict) else {},
        "data_source_revenue": data_source_revenue,
        "data_source_wb_commission": data_source_wb_commission,
        "data_source_logistics": data_source_logistics,
        "data_source_storage": data_source_storage,
        "data_source_ads_spend": data_source_ads_spend,
        "source_flags": source_flags,
        "orders_amount_confirmed": bool(safe_daily_kpi.get("orders_amount_confirmed", False)),
        "buyouts_amount_confirmed": bool(safe_daily_kpi.get("buyouts_amount_confirmed", False)),
        "financial_completeness_pct": round(_safe_float(safe_financial_kpi.get("completeness_pct", 0.0)), 2),
        "financial_partial": bool(safe_financial_kpi.get("is_partial", False)),
        "data_quality": facts_financial_status,
        "event_date_model": event_date_model,
        "order_kpi": order_kpi,
        "buyout_kpi": buyout_kpi,
        "daily_status_matrix": daily_status_matrix,
        "render_kpi": render_kpi,
        "event_ledger": event_ledger,
    }
