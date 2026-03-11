from __future__ import annotations

from typing import Any, Dict, List

from ..pipeline.daily_stage_support import sync_from_entry


def run_daily_email_stage(payload: Dict[str, Any]) -> Dict[str, Any]:
    sync_from_entry(globals())

    data: Dict[str, Any] = dict(payload or {})
    job = data.get("job", {})
    if not isinstance(job, dict):
        job = {}
    daily_kpi = data.get("daily_kpi", {})
    if not isinstance(daily_kpi, dict):
        daily_kpi = {}
    ads_summary = data.get("ads_summary", {})
    if not isinstance(ads_summary, dict):
        ads_summary = {}
    decisions_summary = data.get("decisions_summary", {})
    if not isinstance(decisions_summary, dict):
        decisions_summary = {}
    logistics_summary = data.get("logistics_summary", {})
    if not isinstance(logistics_summary, dict):
        logistics_summary = {}
    totals = data.get("totals", {})
    if not isinstance(totals, dict):
        totals = {}
    data_quality = data.get("data_quality", {})
    if not isinstance(data_quality, dict):
        data_quality = {}

    decision_groups: Dict[str, List[Dict[str, Any]]] = {}
    if isinstance(decisions_summary, dict):
        for key in ("scale", "fix", "watch", "liquidate"):
            rows = decisions_summary.get(key, [])
            decision_groups[key] = [x for x in rows if isinstance(x, dict)] if isinstance(rows, list) else []
    else:
        decision_groups = {"scale": [], "fix": [], "watch": [], "liquidate": []}

    short_recommendations = _build_short_recommendations(
        decision_groups=decision_groups,
        logistics_summary=logistics_summary if isinstance(logistics_summary, dict) else {},
    )
    ai_day_conclusion = _build_ai_day_conclusion(
        run_date=str(data.get("run_date") or ""),
        totals=totals if isinstance(totals, dict) else {},
        daily_kpi=daily_kpi if isinstance(daily_kpi, dict) else {},
        data_quality=data_quality if isinstance(data_quality, dict) else {},
        key_insights=data.get("key_insights", []),
        recommendations=short_recommendations,
    )

    job["email_summary"] = build_email_summary(
        daily_kpi=daily_kpi if isinstance(daily_kpi, dict) else {},
        ads_summary=ads_summary if isinstance(ads_summary, dict) else {},
        net_profit=float(data.get("net_profit", 0.0) or 0.0),
        gross_profit=float(data.get("gross_profit_total", 0.0) or 0.0),
        cost_price=float(data.get("cost_price_total", 0.0) or 0.0),
        wb_commission=float(data.get("wb_commission", 0.0) or 0.0),
        logistics=float(data.get("logistics_total", 0.0) or 0.0),
        storage=float(data.get("storage_total", 0.0) or 0.0),
        penalties=float(data.get("penalties_total", 0.0) or 0.0),
        deductions=float(data.get("deductions_total", 0.0) or 0.0),
        ads_spend_total=float(data.get("ads_spend_total", 0.0) or 0.0),
        margin_pct=float(data.get("margin_pct_total", 0.0) or 0.0),
        profitability_pct=float(data.get("profitability_pct_total", 0.0) or 0.0),
        financial_completeness_pct=float(data.get("financial_completeness_pct", 0.0) or 0.0),
        financial_partial=bool(data.get("financial_partial", False)),
        ads_rows=int(data.get("ads_rows_count", 0) or 0),
        ads_impressions=int(data.get("ads_impressions", 0) or 0),
        ads_clicks=int(data.get("ads_clicks", 0) or 0),
        ads_orders=int(data.get("ads_orders", 0) or 0),
        ads_loaded_from_file=bool(data.get("ads_loaded_from_file", False)),
        ads_source_file=str(data.get("ads_source_file") or ""),
        ads_attribution_quality=str(data.get("ads_attribution_quality") or "unknown"),
        daily_revenue=float(data.get("daily_buyouts_amount", 0.0) or 0.0),
        financial_revenue=float(data.get("revenue_total", 0.0) or 0.0),
        daily_orders_count=int(data.get("daily_orders_count", 0) or 0),
        avg_check=float(data.get("avg_check", 0.0) or 0.0),
        daily_orders_amount=float(data.get("daily_orders_amount", 0.0) or 0.0),
        daily_buyouts_count=int(data.get("daily_buyouts_count", 0) or 0),
        daily_buyouts_amount=float(data.get("daily_buyouts_amount", 0.0) or 0.0),
        key_insights=data.get("key_insights", []),
        recommendations=short_recommendations,
        ai_day_conclusion=ai_day_conclusion,
    )

    data.update(
        {
            "job": job,
            "decision_groups": decision_groups,
            "short_recommendations": short_recommendations,
            "ai_day_conclusion": ai_day_conclusion,
        }
    )
    return data
