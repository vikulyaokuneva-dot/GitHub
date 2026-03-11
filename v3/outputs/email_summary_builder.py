from __future__ import annotations

from typing import Any, Dict, List

from ..domain.source_policy import SOURCE_UNKNOWN


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def build_email_summary(
    *,
    daily_kpi: Dict[str, Any],
    ads_summary: Dict[str, Any],
    net_profit: float,
    gross_profit: float,
    cost_price: float,
    wb_commission: float,
    logistics: float,
    storage: float,
    penalties: float,
    deductions: float,
    ads_spend_total: float,
    margin_pct: float,
    profitability_pct: float,
    financial_completeness_pct: float,
    financial_partial: bool,
    ads_rows: int,
    ads_impressions: int,
    ads_clicks: int,
    ads_orders: int,
    ads_loaded_from_file: bool,
    ads_source_file: str,
    ads_attribution_quality: str,
    daily_revenue: float,
    financial_revenue: float,
    daily_orders_count: int,
    avg_check: float,
    daily_orders_amount: float,
    daily_buyouts_count: int,
    daily_buyouts_amount: float,
    key_insights: List[str],
    recommendations: List[str],
    ai_day_conclusion: str,
) -> Dict[str, Any]:
    safe_daily_kpi = daily_kpi if isinstance(daily_kpi, dict) else {}
    safe_ads_summary = ads_summary if isinstance(ads_summary, dict) else {}
    ads_spend = round(_safe_float(safe_ads_summary.get("ads_spend", ads_spend_total)), 2)

    return {
        "profit": round(net_profit, 2),
        "net_profit": round(net_profit, 2),
        "gross_profit": round(gross_profit, 2),
        "cost_price": round(cost_price, 2),
        "wb_commission": round(wb_commission, 2),
        "logistics": round(logistics, 2),
        "storage": round(storage, 2),
        "penalties": round(penalties, 2),
        "deductions": round(deductions, 2),
        "ads_spend": ads_spend,
        "margin_pct": round(margin_pct, 2),
        "profitability_pct": round(profitability_pct, 2),
        "financial_completeness_pct": round(financial_completeness_pct, 2),
        "financial_partial": financial_partial,
        "ads_rows": ads_rows,
        "ads_impressions": ads_impressions,
        "ads_clicks": ads_clicks,
        "ads_orders": ads_orders,
        "ads_loaded_from_file": bool(ads_loaded_from_file),
        "ads_source_file": ads_source_file,
        "ads_attribution_quality": ads_attribution_quality,
        "ads_applied_to_profit": bool(ads_spend_total > 0),
        "revenue": round(daily_revenue, 2),
        "financial_revenue": round(financial_revenue, 2),
        "orders": daily_orders_count,
        "avg_check": round(avg_check, 2),
        "daily_orders_count": daily_orders_count,
        "daily_orders_amount": round(daily_orders_amount, 2),
        "daily_buyouts_count": daily_buyouts_count,
        "daily_buyouts_amount": round(daily_buyouts_amount, 2),
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
    }
