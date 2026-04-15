from __future__ import annotations

from typing import Any, Dict, List

from ..domain.source_policy import SOURCE_UNKNOWN
from .render_policy import format_int_or_unknown, format_money_or_unknown, format_pct_or_unknown


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return round(numeric, 2)


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def build_email_summary(
    *,
    daily_kpi: Dict[str, Any],
    ads_summary: Dict[str, Any],
    net_profit: Any,
    gross_profit: Any,
    cost_price: Any,
    wb_commission: Any,
    logistics: Any,
    storage: Any,
    penalties: Any,
    deductions: Any,
    ads_spend_total: Any,
    margin_pct: Any,
    profitability_pct: Any,
    financial_completeness_pct: Any,
    financial_partial: bool,
    ads_rows: Any,
    ads_impressions: Any,
    ads_clicks: Any,
    ads_orders: Any,
    ads_loaded_from_file: bool,
    ads_source_file: str,
    ads_attribution_quality: str,
    daily_revenue: Any,
    financial_revenue: Any,
    daily_orders_count: Any,
    avg_check: Any,
    daily_orders_amount: Any,
    daily_buyouts_count: Any,
    daily_buyouts_amount: Any,
    key_insights: List[str],
    recommendations: List[str],
    ai_day_conclusion: str,
    event_date_model: Dict[str, Any],
    order_kpi: Dict[str, Any],
    buyout_kpi: Dict[str, Any],
    financial_kpi: Dict[str, Any],
    daily_status_matrix: Dict[str, Any],
    render_kpi: Dict[str, Any],
    funnel_snapshot: Dict[str, Any] | None = None,
    sku_watchlists: Dict[str, Any] | None = None,
    sku_alerts: Dict[str, Any] | None = None,
    sku_attribution_status: str = "ok",
    financial_finality_status: str = "unavailable",
    report_reliability_level: str = "medium",
) -> Dict[str, Any]:
    safe_daily_kpi = daily_kpi if isinstance(daily_kpi, dict) else {}
    safe_ads_summary = ads_summary if isinstance(ads_summary, dict) else {}
    safe_event_date_model = event_date_model if isinstance(event_date_model, dict) else {}
    safe_order_kpi = order_kpi if isinstance(order_kpi, dict) else {}
    safe_buyout_kpi = buyout_kpi if isinstance(buyout_kpi, dict) else {}
    safe_financial_kpi = financial_kpi if isinstance(financial_kpi, dict) else {}
    safe_status_matrix = daily_status_matrix if isinstance(daily_status_matrix, dict) else {}
    safe_render_kpi = render_kpi if isinstance(render_kpi, dict) else {}
    safe_funnel_snapshot = funnel_snapshot if isinstance(funnel_snapshot, dict) else {}
    safe_sku_watchlists = sku_watchlists if isinstance(sku_watchlists, dict) else {}
    safe_sku_alerts = sku_alerts if isinstance(sku_alerts, dict) else {}
    ads_spend = _round_or_none(safe_ads_summary.get("ads_spend", ads_spend_total))
    ads_spend_numeric = _safe_float(ads_spend)

    summary = {
        "profit": _round_or_none(net_profit),
        "net_profit": _round_or_none(net_profit),
        "gross_profit": _round_or_none(gross_profit),
        "cost_price": _round_or_none(cost_price),
        "wb_commission": _round_or_none(wb_commission),
        "logistics": _round_or_none(logistics),
        "storage": _round_or_none(storage),
        "penalties": _round_or_none(penalties),
        "deductions": _round_or_none(deductions),
        "ads_spend": ads_spend,
        "margin_pct": _round_or_none(margin_pct),
        "profitability_pct": _round_or_none(profitability_pct),
        "financial_completeness_pct": _round_or_none(financial_completeness_pct),
        "financial_partial": financial_partial,
        "ads_rows": _int_or_none(ads_rows),
        "ads_impressions": _int_or_none(ads_impressions),
        "ads_clicks": _int_or_none(ads_clicks),
        "ads_orders": _int_or_none(ads_orders),
        "ads_loaded_from_file": bool(ads_loaded_from_file),
        "ads_source_file": ads_source_file,
        "ads_attribution_quality": ads_attribution_quality,
        "ads_applied_to_profit": bool(ads_spend_numeric is not None and ads_spend_numeric > 0),
        "revenue": _round_or_none(daily_revenue),
        "financial_revenue": _round_or_none(financial_revenue),
        "orders": _int_or_none(daily_orders_count),
        "avg_check": _round_or_none(avg_check),
        "daily_orders_count": _int_or_none(daily_orders_count),
        "daily_orders_amount": _round_or_none(daily_orders_amount),
        "daily_buyouts_count": _int_or_none(daily_buyouts_count),
        "daily_buyouts_amount": _round_or_none(daily_buyouts_amount),
        "data_source_orders": str(safe_daily_kpi.get("data_source_orders") or SOURCE_UNKNOWN),
        "data_source_orders_count": str(
            safe_daily_kpi.get("data_source_orders_count")
            or safe_daily_kpi.get("data_source_orders")
            or SOURCE_UNKNOWN
        ),
        "data_source_orders_amount": str(safe_daily_kpi.get("data_source_orders_amount") or SOURCE_UNKNOWN),
        "data_source_buyouts": str(safe_daily_kpi.get("data_source_buyouts") or SOURCE_UNKNOWN),
        "data_source_buyouts_count": str(
            safe_daily_kpi.get("data_source_buyouts_count")
            or safe_daily_kpi.get("data_source_buyouts")
            or SOURCE_UNKNOWN
        ),
        "data_source_buyouts_amount": str(safe_daily_kpi.get("data_source_buyouts_amount") or SOURCE_UNKNOWN),
        "orders_count_confirmed": bool(safe_daily_kpi.get("orders_count_confirmed", False)),
        "buyouts_count_confirmed": bool(safe_daily_kpi.get("buyouts_count_confirmed", False)),
        "key_insights": key_insights[:3],
        "recommendations": recommendations,
        "ai_day_conclusion": ai_day_conclusion,
        "event_date_model": safe_event_date_model,
        "order_kpi": safe_order_kpi,
        "buyout_kpi": safe_buyout_kpi,
        "financial_kpi": safe_financial_kpi,
        "financial_date_aligned": bool(safe_financial_kpi.get("financial_date_aligned", True)),
        "financial_actual_date": str(safe_financial_kpi.get("financial_actual_date") or ""),
        "financial_target_date": str(
            safe_financial_kpi.get("financial_target_date")
            or safe_event_date_model.get("operational_date")
            or ""
        ),
        "financial_date_misaligned": bool(safe_financial_kpi.get("financial_date_misaligned", False)),
        "financial_alignment_status": str(safe_financial_kpi.get("financial_alignment_status") or "aligned"),
        "financial_alignment_reason": str(safe_financial_kpi.get("financial_alignment_reason") or ""),
        "daily_status_matrix": safe_status_matrix,
        "render_kpi": safe_render_kpi,
        "funnel_snapshot": safe_funnel_snapshot,
        "sku_watchlists": safe_sku_watchlists,
        "sku_alerts": safe_sku_alerts,
        "sku_attribution_status": str(sku_attribution_status or "ok"),
        "financial_finality_status": str(financial_finality_status or "unavailable"),
        "report_reliability_level": str(report_reliability_level or "medium"),
    }

    summary["display"] = {
        "orders_count": format_int_or_unknown(summary.get("daily_orders_count"), unknown_label="нет данных"),
        "orders_amount": format_money_or_unknown(summary.get("daily_orders_amount"), unknown_label="нет данных"),
        "buyouts_count": format_int_or_unknown(summary.get("daily_buyouts_count"), unknown_label="нет данных"),
        "buyouts_amount": format_money_or_unknown(summary.get("daily_buyouts_amount"), unknown_label="нет данных"),
        "avg_check": format_money_or_unknown(summary.get("avg_check"), unknown_label="нет данных"),
        "financial_revenue": format_money_or_unknown(summary.get("financial_revenue"), unknown_label="нет данных", decimals=0),
        "net_profit": format_money_or_unknown(summary.get("net_profit"), unknown_label="нет данных", decimals=0),
        "margin_pct": format_pct_or_unknown(summary.get("margin_pct"), unknown_label="нет данных"),
        "profitability_pct": format_pct_or_unknown(summary.get("profitability_pct"), unknown_label="нет данных"),
    }
    return summary
