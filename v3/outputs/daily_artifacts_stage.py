from __future__ import annotations

from typing import Any, Dict

from ..pipeline.daily_stage_support import sync_from_entry


def prepare_daily_output_payload(context: Dict[str, Any]) -> Dict[str, Any]:
    sync_from_entry(globals())

    payload: Dict[str, Any] = dict(context or {})
    warnings_collector = payload.get("warnings_collector")
    if not isinstance(warnings_collector, WarningsCollector):
        warnings_collector = WarningsCollector()

    facts = payload.get("facts", {})
    if not isinstance(facts, dict):
        facts = {}
    job = payload.get("job", {})
    if not isinstance(job, dict):
        job = {}
    metrics = payload.get("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}
    data_quality = payload.get("data_quality", {})
    if not isinstance(data_quality, dict):
        data_quality = {}
    daily_kpi = payload.get("daily_kpi", {})
    if not isinstance(daily_kpi, dict):
        daily_kpi = {}
    ads_summary = payload.get("ads_summary", {})
    if not isinstance(ads_summary, dict):
        ads_summary = {}
    decisions_summary = payload.get("decisions_summary", {})
    if not isinstance(decisions_summary, dict):
        decisions_summary = {}
    director_strategy = payload.get("director_strategy", {})
    if not isinstance(director_strategy, dict):
        director_strategy = {}
    health_summary = payload.get("health_summary", {})
    if not isinstance(health_summary, dict):
        health_summary = {}
    outcomes_payload = payload.get("outcomes_payload", {})
    if not isinstance(outcomes_payload, dict):
        outcomes_payload = {}

    decision_rows_added = int(payload.get("decision_rows_added", 0) or 0)
    outcomes_evaluated = int(payload.get("outcomes_evaluated", 0) or 0)
    confidence = str(payload.get("confidence") or "low")

    sku_metrics = payload.get("sku_metrics", [])
    if not isinstance(sku_metrics, list):
        sku_metrics = []
    abc_rows = payload.get("abc_rows", [])
    if not isinstance(abc_rows, list):
        abc_rows = []
    profit_contribution = payload.get("profit_contribution", {})
    if not isinstance(profit_contribution, dict):
        profit_contribution = {}
    territorial_distribution = payload.get("territorial_distribution", {})
    if not isinstance(territorial_distribution, dict):
        territorial_distribution = {}
    territorial_summary = payload.get("territorial_summary", {})
    if not isinstance(territorial_summary, dict):
        territorial_summary = {}
    logistics_summary = payload.get("logistics_summary", {})
    if not isinstance(logistics_summary, dict):
        logistics_summary = {}
    unassigned_costs = payload.get("unassigned_costs", {})
    if not isinstance(unassigned_costs, dict):
        unassigned_costs = {}

    financial_kpi = payload.get("financial_kpi", {})
    if not isinstance(financial_kpi, dict):
        financial_kpi = {}
    totals = metrics.get("totals", {}) if isinstance(metrics, dict) else {}
    if not isinstance(totals, dict):
        totals = {}

    ads_rows_count = int(payload.get("ads_rows_count", 0) or 0)
    ads_loaded_from_file = bool(payload.get("ads_loaded_from_file", False))
    ads_source_file = str(payload.get("ads_source_file") or "")
    ads_attribution_quality = str(payload.get("ads_attribution_quality") or "unknown")

    if not isinstance(financial_kpi, dict):
        fallback_financial_assembly = assemble_financial_kpi(
            totals=totals if isinstance(totals, dict) else {},
            data_quality=data_quality if isinstance(data_quality, dict) else {},
        )
        financial_kpi = (
            fallback_financial_assembly.get("financial_kpi", {})
            if isinstance(fallback_financial_assembly, dict)
            else {}
        )
        if not isinstance(financial_kpi, dict):
            financial_kpi = {}
    revenue_total = _safe_float(financial_kpi.get("revenue", totals.get("total_revenue", totals.get("revenue", 0.0))))
    profit_total = _safe_float(totals.get("profit", totals.get("total_profit", 0.0)))
    daily_orders_count = int(round(_safe_float(daily_kpi.get("daily_orders_count", 0))))
    daily_orders_amount = _safe_float(daily_kpi.get("daily_orders_amount", 0.0))
    daily_buyouts_count = int(round(_safe_float(daily_kpi.get("daily_buyouts_count", 0))))
    daily_buyouts_amount = _safe_float(daily_kpi.get("daily_buyouts_amount", 0.0))
    avg_check = (daily_buyouts_amount / daily_buyouts_count) if (daily_buyouts_amount > 0 and daily_buyouts_count > 0) else 0.0

    cost_price_total = _safe_float(financial_kpi.get("cost_price", totals.get("cost_price", 0.0)))
    wb_commission = _safe_float(financial_kpi.get("wb_commission", totals.get("wb_commission", 0.0)))
    logistics_total = _safe_float(financial_kpi.get("logistics", totals.get("logistics", 0.0)))
    storage_total = _safe_float(financial_kpi.get("storage", totals.get("storage", 0.0)))
    penalties_total = _safe_float(financial_kpi.get("penalties", totals.get("penalties", 0.0)))
    deductions_total = _safe_float(financial_kpi.get("deductions", totals.get("deductions", 0.0)))
    ads_spend_total = _safe_float(financial_kpi.get("ads_spend", totals.get("ads_spend", 0.0)))
    gross_profit_total = _safe_float(financial_kpi.get("gross_profit", revenue_total - cost_price_total - wb_commission))
    net_profit = _safe_float(financial_kpi.get("net_profit", totals.get("net_profit", profit_total)))
    margin_pct_total = _safe_float(financial_kpi.get("margin_pct", (net_profit / revenue_total * 100.0) if revenue_total > 0 else 0.0))
    profitability_pct_total = _safe_float(financial_kpi.get("profitability_pct", (net_profit / cost_price_total * 100.0) if cost_price_total > 0 else 0.0))
    financial_completeness_pct = _safe_float(financial_kpi.get("completeness_pct", 0.0))
    financial_partial = bool(financial_kpi.get("is_partial", False))

    ads_impressions = int(round(_safe_float(totals.get("ads_impressions", 0))))
    ads_clicks = int(round(_safe_float(totals.get("ads_clicks", 0))))
    ads_ctr = _safe_float(totals.get("ads_ctr", 0.0))
    ads_orders = int(round(_safe_float(totals.get("ads_orders", 0))))
    ads_revenue = _safe_float(totals.get("ads_revenue", 0.0))
    ads_acos = _safe_float(totals.get("ads_acos", 0.0))
    ads_romi = _safe_float(totals.get("ads_romi", 0.0))

    key_insights = _build_key_insights(
        facts=facts,
        health_summary=health_summary if isinstance(health_summary, dict) else {},
        outcomes_payload=outcomes_payload if isinstance(outcomes_payload, dict) else {},
        decision_rows_added=decision_rows_added,
    )

    payload.update(
        {
            "warnings_collector": warnings_collector,
            "facts": facts,
            "job": job,
            "metrics": metrics,
            "data_quality": data_quality,
            "daily_kpi": daily_kpi,
            "ads_summary": ads_summary,
            "decisions_summary": decisions_summary,
            "director_strategy": director_strategy,
            "health_summary": health_summary,
            "outcomes_payload": outcomes_payload,
            "decision_rows_added": decision_rows_added,
            "outcomes_evaluated": outcomes_evaluated,
            "confidence": confidence,
            "sku_metrics": sku_metrics,
            "abc_rows": abc_rows,
            "profit_contribution": profit_contribution,
            "territorial_distribution": territorial_distribution,
            "territorial_summary": territorial_summary,
            "logistics_summary": logistics_summary,
            "unassigned_costs": unassigned_costs,
            "financial_kpi": financial_kpi,
            "totals": totals,
            "ads_rows_count": ads_rows_count,
            "ads_loaded_from_file": ads_loaded_from_file,
            "ads_source_file": ads_source_file,
            "ads_attribution_quality": ads_attribution_quality,
            "revenue_total": revenue_total,
            "profit_total": profit_total,
            "daily_orders_count": daily_orders_count,
            "daily_orders_amount": daily_orders_amount,
            "daily_buyouts_count": daily_buyouts_count,
            "daily_buyouts_amount": daily_buyouts_amount,
            "avg_check": avg_check,
            "cost_price_total": cost_price_total,
            "wb_commission": wb_commission,
            "logistics_total": logistics_total,
            "storage_total": storage_total,
            "penalties_total": penalties_total,
            "deductions_total": deductions_total,
            "ads_spend_total": ads_spend_total,
            "gross_profit_total": gross_profit_total,
            "net_profit": net_profit,
            "margin_pct_total": margin_pct_total,
            "profitability_pct_total": profitability_pct_total,
            "financial_completeness_pct": financial_completeness_pct,
            "financial_partial": financial_partial,
            "ads_impressions": ads_impressions,
            "ads_clicks": ads_clicks,
            "ads_ctr": ads_ctr,
            "ads_orders": ads_orders,
            "ads_revenue": ads_revenue,
            "ads_acos": ads_acos,
            "ads_romi": ads_romi,
            "key_insights": key_insights,
        }
    )
    return payload
