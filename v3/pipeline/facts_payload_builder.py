from __future__ import annotations

from typing import Any, Dict, List


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def build_facts_runtime_patch(
    *,
    source_mode: str,
    api_debug: Dict[str, Any],
    metrics: Dict[str, Any],
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
    daily_kpi: Dict[str, Any],
    data_source_revenue: str,
    data_source_wb_commission: str,
    data_source_logistics: str,
    data_source_storage: str,
    data_source_ads_spend: str,
    source_flags: Dict[str, Any],
    source_policy: Dict[str, Any],
    event_date_model: Dict[str, Any],
    order_kpi: Dict[str, Any],
    buyout_kpi: Dict[str, Any],
    daily_status_matrix: Dict[str, Any],
    event_ledger: Dict[str, Any],
    render_kpi: Dict[str, Any],
) -> Dict[str, Any]:
    safe_metrics = metrics if isinstance(metrics, dict) else {}
    safe_ads_summary = ads_summary if isinstance(ads_summary, dict) else {}
    safe_financial_kpi = financial_kpi if isinstance(financial_kpi, dict) else {}
    safe_daily_kpi = daily_kpi if isinstance(daily_kpi, dict) else {}
    safe_event_date_model = event_date_model if isinstance(event_date_model, dict) else {}
    safe_order_kpi = order_kpi if isinstance(order_kpi, dict) else {}
    safe_buyout_kpi = buyout_kpi if isinstance(buyout_kpi, dict) else {}
    safe_status_matrix = daily_status_matrix if isinstance(daily_status_matrix, dict) else {}
    safe_event_ledger = event_ledger if isinstance(event_ledger, dict) else {}
    safe_render_kpi = render_kpi if isinstance(render_kpi, dict) else {}

    ads_columns_detected = (
        [str(item) for item in safe_ads_summary.get("ads_columns_detected", []) if str(item).strip()]
        if isinstance(safe_ads_summary.get("ads_columns_detected"), list)
        else []
    )

    return {
        "source_mode": source_mode,
        "api_debug": api_debug,
        "commerce_kpi": safe_metrics.get("commerce_kpi", {}),
        "financial_kpi": safe_metrics.get("financial_kpi", {}),
        "ads_rows": int(safe_ads_summary.get("ads_rows", ads_rows_count) or 0),
        "ads_spend": round(_safe_float(safe_ads_summary.get("ads_spend", safe_financial_kpi.get("ads_spend", 0.0))), 2),
        "ads_loaded_from_file": bool(safe_ads_summary.get("ads_loaded_from_file", ads_loaded_from_file)),
        "ads_source_file": str(safe_ads_summary.get("ads_source_file", ads_source_file) or ""),
        "ads_file_candidates_found": int(safe_ads_summary.get("ads_file_candidates_found", 0) or 0),
        "ads_file_detected": bool(safe_ads_summary.get("ads_file_detected", False)),
        "ads_sheet_found": str(safe_ads_summary.get("ads_sheet_found") or ""),
        "ads_columns_detected": ads_columns_detected,
        "ads_rows_raw": int(safe_ads_summary.get("ads_rows_raw", 0) or 0),
        "ads_rows_usable": int(safe_ads_summary.get("ads_rows_usable", ads_rows_count) or 0),
        "ads_loader_error": str(safe_ads_summary.get("ads_loader_error") or ""),
        "ads_attribution_quality": str(safe_ads_summary.get("ads_attribution_quality", ads_attribution_quality) or "unknown"),
        "data_source_orders_count": data_source_orders_count,
        "data_source_buyouts_count": data_source_buyouts_count,
        "data_source_orders_amount": data_source_orders_amount,
        "data_source_buyouts_amount": data_source_buyouts_amount,
        "orders_count_confirmed": bool(safe_daily_kpi.get("orders_count_confirmed", False)),
        "buyouts_count_confirmed": bool(safe_daily_kpi.get("buyouts_count_confirmed", False)),
        "data_source_revenue": data_source_revenue,
        "data_source_wb_commission": data_source_wb_commission,
        "data_source_logistics": data_source_logistics,
        "data_source_storage": data_source_storage,
        "data_source_ads_spend": data_source_ads_spend,
        "sku_activity_orders_hint": int(safe_daily_kpi.get("sku_activity_orders_hint", 0) or 0),
        "sku_activity_buyouts_hint": int(safe_daily_kpi.get("sku_activity_buyouts_hint", 0) or 0),
        "commerce_activity": safe_metrics.get("commerce_activity", {}) if isinstance(safe_metrics.get("commerce_activity"), dict) else {},
        "orders_count_unknown_reason": str(safe_daily_kpi.get("orders_count_unknown_reason") or ""),
        "buyouts_count_unknown_reason": str(safe_daily_kpi.get("buyouts_count_unknown_reason") or ""),
        "source_flags": source_flags,
        "source_policy": source_policy if isinstance(source_policy, dict) else {},
        "event_date_model": safe_event_date_model,
        "order_kpi": safe_order_kpi,
        "buyout_kpi": safe_buyout_kpi,
        "daily_status_matrix": safe_status_matrix,
        "event_ledger": safe_event_ledger,
        "render_kpi": safe_render_kpi,
    }


def apply_facts_data_quality_patch(
    *,
    current_data_quality: Any,
    ads_attribution_quality: str,
    financial_partial: bool,
    financial_data_degraded_flag: bool,
) -> Dict[str, Any] | None:
    if not isinstance(current_data_quality, dict):
        return None
    out = dict(current_data_quality)
    fact_financial_status = str(out.get("financial_status") or "ok")
    out["ads_attribution_quality"] = ads_attribution_quality
    if financial_partial:
        out["financial_status"] = "partial"
    elif financial_data_degraded_flag and fact_financial_status == "ok":
        out["financial_status"] = "degraded"
    return out


def build_profit_contribution_summary(
    *,
    p1_rows: List[Dict[str, Any]],
    p2_rows: List[Dict[str, Any]],
    p3_rows: List[Dict[str, Any]],
    top_profit_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "p1_count": len(p1_rows) if isinstance(p1_rows, list) else 0,
        "p2_count": len(p2_rows) if isinstance(p2_rows, list) else 0,
        "p3_count": len(p3_rows) if isinstance(p3_rows, list) else 0,
        "top_profit_skus": [
            str(item.get("sku"))
            for item in (top_profit_rows if isinstance(top_profit_rows, list) else [])
            if isinstance(item, dict) and str(item.get("sku") or "").strip()
        ][:5],
    }


def build_territorial_distribution_summary(territorial_summary: Dict[str, Any]) -> Dict[str, Any]:
    safe_summary = territorial_summary if isinstance(territorial_summary, dict) else {}
    insufficient_distribution_data_count = int(
        safe_summary.get("insufficient_distribution_data_count", safe_summary.get("insufficient_data_count", 0))
        or 0
    )
    no_stock_data_count = int(safe_summary.get("no_stock_data_count", 0) or 0)
    insufficient_total_count = int(
        safe_summary.get("insufficient_total_count", safe_summary.get("insufficient_data_count", 0)) or 0
    )
    return {
        "sku_total": int(safe_summary.get("sku_total", safe_summary.get("sku_analyzed", 0)) or 0),
        "sku_with_ktr": int(
            safe_summary.get(
                "sku_with_ktr",
                int(safe_summary.get("balanced_count", 0) or 0)
                + int(safe_summary.get("moderate_mismatch_count", 0) or 0)
                + int(safe_summary.get("misallocated_count", 0) or 0),
            )
            or 0
        ),
        "balanced_count": int(safe_summary.get("balanced_count", 0) or 0),
        "moderate_mismatch_count": int(safe_summary.get("moderate_mismatch_count", 0) or 0),
        "misallocated_count": int(safe_summary.get("misallocated_count", 0) or 0),
        "insufficient_distribution_data_count": insufficient_distribution_data_count,
        "no_stock_data_count": no_stock_data_count,
        "insufficient_total_count": insufficient_total_count,
        "avg_ktr": float(safe_summary.get("avg_ktr", 0.0) or 0.0),
        "top_misaligned_skus": (
            [str(value) for value in safe_summary.get("top_misaligned_skus", []) if str(value or "").strip()][:5]
            if isinstance(safe_summary.get("top_misaligned_skus"), list)
            else []
        ),
    }


def build_logistics_ktr_summary(logistics_summary: Dict[str, Any]) -> Dict[str, Any]:
    safe_summary = logistics_summary if isinstance(logistics_summary, dict) else {}
    return {
        "sku_total": int(safe_summary.get("sku_total", 0) or 0),
        "sku_with_ktr": int(safe_summary.get("sku_with_ktr", 0) or 0),
        "efficient_count": int(safe_summary.get("efficient_count", 0) or 0),
        "acceptable_count": int(safe_summary.get("acceptable_count", 0) or 0),
        "inefficient_count": int(safe_summary.get("inefficient_count", 0) or 0),
        "critical_count": int(safe_summary.get("critical_count", 0) or 0),
        "low_confidence_count": int(safe_summary.get("low_confidence_count", 0) or 0),
        "avg_ktr": float(safe_summary.get("avg_ktr", 0.0) or 0.0),
        "avg_locality_score": float(safe_summary.get("avg_locality_score", 0.0) or 0.0),
        "top_critical_skus": (
            [str(value) for value in safe_summary.get("top_critical_skus", []) if str(value or "").strip()][:5]
            if isinstance(safe_summary.get("top_critical_skus"), list)
            else []
        ),
    }


def build_decision_memory_summary(decision_memory_summary: Dict[str, Any]) -> Dict[str, Any]:
    safe_summary = decision_memory_summary if isinstance(decision_memory_summary, dict) else {}
    return {
        "total_logged": int(safe_summary.get("total_logged", 0) or 0),
        "pending": int(safe_summary.get("pending", 0) or 0),
        "success": int(safe_summary.get("success", 0) or 0),
        "fail": int(safe_summary.get("fail", 0) or 0),
        "neutral": int(safe_summary.get("neutral", 0) or 0),
    }


def build_history_summary(history_summary: Dict[str, Any], run_date: str) -> Dict[str, Any]:
    safe_summary = history_summary if isinstance(history_summary, dict) else {}
    return {
        "snapshots_count": int(safe_summary.get("snapshots_count", 0) or 0),
        "latest_snapshot_date": str(safe_summary.get("latest_snapshot_date") or run_date),
    }
