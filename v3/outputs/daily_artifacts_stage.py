from __future__ import annotations

import json
import os
from typing import Any, Dict

from ..domain.event_model import build_render_kpi_values
from ..pipeline.daily_stage_support import sync_from_entry
from ..validation.report_guardrails import apply_report_guardrails


def prepare_daily_output_payload(context: Dict[str, Any]) -> Dict[str, Any]:
    sync_from_entry(globals())

    payload: Dict[str, Any] = dict(context or {})

    def _read_optional_artifact(name: str) -> Dict[str, Any]:
        out_dir_local = str(payload.get("out_dir") or "")
        if not out_dir_local:
            return {}
        path = os.path.join(out_dir_local, name)
        if not os.path.isfile(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}
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
    analytics = payload.get("analytics", {})
    if not isinstance(analytics, dict):
        analytics = {}
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
    health_payload = payload.get("health_payload", {})
    if not isinstance(health_payload, dict):
        health_payload = {}
    if not health_payload and isinstance(analytics, dict):
        health_from_analytics = analytics.get("health_score")
        if isinstance(health_from_analytics, dict):
            health_payload = health_from_analytics
    if not health_payload:
        health_payload = _read_optional_artifact("health_score.json")
    if not health_payload and isinstance(metrics, dict):
        health_from_metrics = metrics.get("health_score")
        if isinstance(health_from_metrics, dict):
            health_payload = health_from_metrics
    health_summary = payload.get("health_summary", {})
    if not isinstance(health_summary, dict) or not health_summary:
        health_summary = health_payload.get("summary", {}) if isinstance(health_payload, dict) else {}
    if not isinstance(health_summary, dict):
        health_summary = {}
    outcomes_payload = payload.get("outcomes_payload", {})
    if not isinstance(outcomes_payload, dict):
        outcomes_payload = {}
    cabinet_funnel = payload.get("cabinet_funnel", {})
    if not isinstance(cabinet_funnel, dict) or not cabinet_funnel:
        cabinet_funnel = _read_optional_artifact("cabinet_funnel.json")
    sales_funnel_diagnostics = payload.get("sales_funnel_diagnostics", {})
    if not isinstance(sales_funnel_diagnostics, dict):
        sales_funnel_diagnostics = {}
    if not sales_funnel_diagnostics and isinstance(cabinet_funnel, dict):
        embedded = cabinet_funnel.get("sku_diagnostics")
        if isinstance(embedded, dict):
            sales_funnel_diagnostics = embedded
    if not sales_funnel_diagnostics and isinstance(metrics, dict):
        fallback_diagnostics = metrics.get("sales_funnel_diagnostics")
        if isinstance(fallback_diagnostics, dict):
            sales_funnel_diagnostics = fallback_diagnostics
    sales_funnel_summary = sales_funnel_diagnostics.get("summary", {}) if isinstance(sales_funnel_diagnostics, dict) else {}
    if not isinstance(sales_funnel_summary, dict):
        sales_funnel_summary = {}
    funnel_alerts = payload.get("funnel_alerts", {})
    if not isinstance(funnel_alerts, dict) or not funnel_alerts:
        funnel_alerts = _read_optional_artifact("funnel_alerts.json")
    sku_alerts = payload.get("sku_alerts", {})
    if not isinstance(sku_alerts, dict) or not sku_alerts:
        sku_alerts = _read_optional_artifact("sku_alerts.json")
    sku_watchlists = payload.get("sku_watchlists", {})
    if not isinstance(sku_watchlists, dict) or not sku_watchlists:
        sku_watchlists = _read_optional_artifact("sku_watchlists.json")

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
    if not profit_contribution and isinstance(analytics, dict):
        profit_from_analytics = analytics.get("profit_contribution")
        if isinstance(profit_from_analytics, dict):
            profit_contribution = profit_from_analytics
    if not profit_contribution:
        profit_contribution = _read_optional_artifact("profit_contribution.json")
    if not profit_contribution and isinstance(metrics, dict):
        profit_from_metrics = metrics.get("profit_contribution")
        if isinstance(profit_from_metrics, dict):
            profit_contribution = profit_from_metrics
    analytics["profit_contribution"] = profit_contribution if isinstance(profit_contribution, dict) else {}
    keyword_monitoring = payload.get("keyword_monitoring", {})
    if not isinstance(keyword_monitoring, dict):
        keyword_monitoring = {}
    if not keyword_monitoring and isinstance(analytics, dict):
        keyword_from_analytics = analytics.get("keyword_monitoring")
        if isinstance(keyword_from_analytics, dict):
            keyword_monitoring = keyword_from_analytics
    if not keyword_monitoring:
        keyword_monitoring = _read_optional_artifact("keyword_monitoring.json")
    if not keyword_monitoring and isinstance(metrics, dict):
        keyword_from_metrics = metrics.get("keyword_monitoring")
        if isinstance(keyword_from_metrics, dict):
            keyword_monitoring = keyword_from_metrics
    keyword_summary = keyword_monitoring.get("summary", {}) if isinstance(keyword_monitoring, dict) else {}
    if not isinstance(keyword_summary, dict):
        keyword_summary = {}
    analytics["keyword_monitoring"] = keyword_monitoring if isinstance(keyword_monitoring, dict) else {}
    advertising_efficiency = payload.get("advertising_efficiency", {})
    if not isinstance(advertising_efficiency, dict):
        advertising_efficiency = {}
    if not advertising_efficiency and isinstance(analytics, dict):
        ads_eff_from_analytics = analytics.get("advertising_efficiency")
        if isinstance(ads_eff_from_analytics, dict):
            advertising_efficiency = ads_eff_from_analytics
    if not advertising_efficiency:
        advertising_efficiency = _read_optional_artifact("advertising_efficiency.json")
    if not advertising_efficiency and isinstance(metrics, dict):
        ads_eff_from_metrics = metrics.get("advertising_efficiency")
        if isinstance(ads_eff_from_metrics, dict):
            advertising_efficiency = ads_eff_from_metrics
    analytics["advertising_efficiency"] = advertising_efficiency if isinstance(advertising_efficiency, dict) else {}
    portfolio_ads_summary = (
        advertising_efficiency.get("portfolio_ads_summary", advertising_efficiency.get("summary", {}))
        if isinstance(advertising_efficiency, dict)
        else {}
    )
    if not isinstance(portfolio_ads_summary, dict):
        portfolio_ads_summary = {}
    query_profitability = advertising_efficiency.get("query_profitability", {}) if isinstance(advertising_efficiency, dict) else {}
    if not isinstance(query_profitability, dict):
        query_profitability = {}
    territorial_distribution = payload.get("territorial_distribution", {})
    if not isinstance(territorial_distribution, dict):
        territorial_distribution = {}
    if not territorial_distribution and isinstance(analytics, dict):
        territorial_from_analytics = analytics.get("territorial_distribution")
        if isinstance(territorial_from_analytics, dict):
            territorial_distribution = territorial_from_analytics
    if not territorial_distribution:
        territorial_distribution = _read_optional_artifact("territorial_distribution.json")
    if not territorial_distribution and isinstance(metrics, dict):
        territorial_from_metrics = metrics.get("territorial_distribution")
        if isinstance(territorial_from_metrics, dict):
            territorial_distribution = territorial_from_metrics
    analytics["territorial_distribution"] = territorial_distribution if isinstance(territorial_distribution, dict) else {}

    territorial_summary = payload.get("territorial_summary", {})
    if not isinstance(territorial_summary, dict) or not territorial_summary:
        territorial_summary = territorial_distribution.get("summary", {}) if isinstance(territorial_distribution, dict) else {}
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
    event_date_model = payload.get("event_date_model", metrics.get("event_date_model", facts.get("event_date_model", {})))
    if not isinstance(event_date_model, dict):
        event_date_model = {}
    order_kpi = payload.get("order_kpi", metrics.get("order_kpi", facts.get("order_kpi", {})))
    if not isinstance(order_kpi, dict):
        order_kpi = {}
    buyout_kpi = payload.get("buyout_kpi", metrics.get("buyout_kpi", facts.get("buyout_kpi", {})))
    if not isinstance(buyout_kpi, dict):
        buyout_kpi = {}
    daily_status_matrix = payload.get(
        "daily_status_matrix",
        metrics.get("daily_status_matrix", facts.get("daily_status_matrix", {})),
    )
    if not isinstance(daily_status_matrix, dict):
        daily_status_matrix = {}
    event_ledger = payload.get("event_ledger", metrics.get("event_ledger", facts.get("event_ledger", {})))
    if not isinstance(event_ledger, dict):
        event_ledger = {}
    render_kpi = payload.get("render_kpi", metrics.get("render_kpi", facts.get("render_kpi", {})))
    if not isinstance(render_kpi, dict) or not render_kpi:
        render_kpi = build_render_kpi_values(
            order_kpi=order_kpi if isinstance(order_kpi, dict) else {},
            buyout_kpi=buyout_kpi if isinstance(buyout_kpi, dict) else {},
            financial_kpi=financial_kpi if isinstance(financial_kpi, dict) else {},
            daily_status_matrix=daily_status_matrix if isinstance(daily_status_matrix, dict) else {},
        )

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
    revenue_total_legacy = _safe_float(financial_kpi.get("revenue", totals.get("total_revenue", totals.get("revenue", 0.0))))
    profit_total = _safe_float(totals.get("profit", totals.get("total_profit", 0.0)))
    daily_orders_count_legacy = int(round(_safe_float(daily_kpi.get("daily_orders_count", 0))))
    daily_orders_amount_legacy = _safe_float(daily_kpi.get("daily_orders_amount", 0.0))
    daily_buyouts_count_legacy = int(round(_safe_float(daily_kpi.get("daily_buyouts_count", 0))))
    daily_buyouts_amount_legacy = _safe_float(daily_kpi.get("daily_buyouts_amount", 0.0))
    avg_check_legacy = (
        (daily_buyouts_amount_legacy / daily_buyouts_count_legacy)
        if (daily_buyouts_amount_legacy > 0 and daily_buyouts_count_legacy > 0)
        else 0.0
    )

    daily_orders_count = render_kpi.get("orders_count")
    daily_orders_amount = render_kpi.get("orders_amount")
    daily_buyouts_count = render_kpi.get("buyouts_count")
    daily_buyouts_amount = render_kpi.get("buyouts_amount")
    avg_check = render_kpi.get("avg_check")

    cost_price_total = financial_kpi.get("cost_price")
    wb_commission = financial_kpi.get("wb_commission")
    logistics_total = financial_kpi.get("logistics")
    storage_total = financial_kpi.get("storage")
    penalties_total = financial_kpi.get("penalties")
    deductions_total = financial_kpi.get("deductions")
    ads_spend_total = financial_kpi.get("ads_spend")
    revenue_total = render_kpi.get("revenue")
    gross_profit_total = render_kpi.get("gross_profit")
    net_profit = render_kpi.get("net_profit")
    margin_pct_total = render_kpi.get("margin_pct")
    profitability_pct_total = render_kpi.get("profitability_pct")

    financial_status = str(daily_status_matrix.get("financials") or "unknown")
    if financial_status in {"confirmed", "partial"}:
        if revenue_total is None:
            revenue_total = _safe_float(financial_kpi.get("revenue", totals.get("total_revenue", totals.get("revenue", 0.0))))
        if cost_price_total is None:
            cost_price_total = _safe_float(financial_kpi.get("cost_price", totals.get("cost_price", 0.0)))
        if wb_commission is None:
            wb_commission = _safe_float(financial_kpi.get("wb_commission", totals.get("wb_commission", 0.0)))
        if logistics_total is None:
            logistics_total = _safe_float(financial_kpi.get("logistics", totals.get("logistics", 0.0)))
        if storage_total is None:
            storage_total = _safe_float(financial_kpi.get("storage", totals.get("storage", 0.0)))
        if penalties_total is None:
            penalties_total = _safe_float(financial_kpi.get("penalties", totals.get("penalties", 0.0)))
        if deductions_total is None:
            deductions_total = _safe_float(financial_kpi.get("deductions", totals.get("deductions", 0.0)))
        if ads_spend_total is None:
            ads_spend_total = _safe_float(financial_kpi.get("ads_spend", totals.get("ads_spend", 0.0)))
        if gross_profit_total is None:
            gross_profit_total = _safe_float(
                financial_kpi.get(
                    "gross_profit",
                    _safe_float(revenue_total) - _safe_float(cost_price_total) - _safe_float(wb_commission),
                )
            )
        if net_profit is None:
            net_profit = _safe_float(financial_kpi.get("net_profit", totals.get("net_profit", profit_total)))

    margin_pct_total_legacy = _safe_float(
        financial_kpi.get(
            "margin_pct",
            (_safe_float(net_profit) / _safe_float(revenue_total) * 100.0) if _safe_float(revenue_total) > 0 else 0.0,
        )
    )
    profitability_pct_total_legacy = _safe_float(
        financial_kpi.get(
            "profitability_pct",
            (_safe_float(net_profit) / _safe_float(cost_price_total) * 100.0) if _safe_float(cost_price_total) > 0 else 0.0,
        )
    )
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
    if not isinstance(key_insights, list):
        key_insights = []
    sales_funnel_top_groups = sales_funnel_summary.get("top_problem_groups", []) if isinstance(sales_funnel_summary, dict) else []
    if isinstance(sales_funnel_top_groups, list) and sales_funnel_top_groups:
        top_group = sales_funnel_top_groups[0] if isinstance(sales_funnel_top_groups[0], dict) else {}
        top_issue_type = str(top_group.get("issue_type") or "").strip()
        top_issue_count = int(top_group.get("count", 0) or 0)
        if top_issue_type and top_issue_count > 0:
            key_insights = list(key_insights) + [f"SKU funnel: top problem {top_issue_type} ({top_issue_count} SKU)."]
    winner_query_count = int(keyword_summary.get("winner_query_count", 0) or 0)
    growth_query_count = int(keyword_summary.get("growth_query_count", 0) or 0)
    costly_query_count = int(keyword_summary.get("costly_query_count", 0) or 0)
    low_relevance_query_count = int(keyword_summary.get("low_relevance_query_count", 0) or 0)
    no_orders_query_count = int(keyword_summary.get("no_orders_query_count", 0) or 0)
    if winner_query_count > 0:
        key_insights = list(key_insights) + [f"Keyword winners detected: {winner_query_count} queries."]
    if growth_query_count > 0:
        key_insights = list(key_insights) + [f"Keyword growth opportunities: {growth_query_count} queries."]
    if (costly_query_count + low_relevance_query_count + no_orders_query_count) > 0:
        key_insights = list(key_insights) + [
            f"Keyword risks detected: costly={costly_query_count}, low_relevance={low_relevance_query_count}, no_orders={no_orders_query_count}."
        ]

    ads_efficiency_mode = str(
        portfolio_ads_summary.get("analysis_mode", advertising_efficiency.get("analysis_mode", "disabled"))
        if isinstance(advertising_efficiency, dict)
        else "disabled"
    ).strip().lower()
    portfolio_ads_profit = _safe_float(portfolio_ads_summary.get("portfolio_profit_from_ads", 0.0))
    portfolio_ads_romi = _safe_float(portfolio_ads_summary.get("portfolio_ROMI", 0.0))
    top_unprofitable_queries = portfolio_ads_summary.get("top_unprofitable_queries", []) if isinstance(portfolio_ads_summary, dict) else []
    if not isinstance(top_unprofitable_queries, list):
        top_unprofitable_queries = []

    if ads_efficiency_mode == "full":
        key_insights = list(key_insights) + [
            f"Advertising efficiency: ROMI={round(portfolio_ads_romi, 2)}%, profit={round(portfolio_ads_profit, 2)} RUB."
        ]
        if top_unprofitable_queries:
            key_insights = list(key_insights) + [
                f"Advertising budget leakage risk: {len(top_unprofitable_queries)} unprofitable queries detected."
            ]
    elif ads_efficiency_mode == "preview":
        key_insights = list(key_insights) + [
            "Advertising efficiency is provisional: orders are visible, but buyout-confirmed profitability is not final yet."
        ]
    territorial_problematic_count = int(territorial_summary.get("skus_below_60_localization", 0) or 0)
    territorial_penalty_total = _safe_float(territorial_summary.get("aggregate_estimated_irp_penalty_total", 0.0))
    weighted_localization_share = _safe_float(territorial_summary.get("weighted_average_localization_share", 0.0))
    territorial_analysis_mode = str(
        territorial_summary.get("analysis_mode", territorial_distribution.get("analysis_mode", "disabled"))
    ).strip().lower()
    territorial_recommendation_status = str(
        territorial_summary.get("recommendation_status", territorial_distribution.get("recommendation_status", "blocked_by_data"))
    ).strip().lower()
    territorial_suppressed = bool(
        territorial_summary.get("suppressed_due_to_data_quality", territorial_distribution.get("suppressed_due_to_data_quality", False))
    )

    if territorial_analysis_mode == "full" and territorial_recommendation_status == "actionable" and not territorial_suppressed:
        if territorial_problematic_count > 0:
            key_insights = list(key_insights) + [
                f"Confirmed territorial distribution risk: {territorial_problematic_count} SKU below 60% localization."
            ]
        if territorial_penalty_total > 0:
            key_insights = list(key_insights) + [
                f"Confirmed estimated IRP exposure: {round(territorial_penalty_total, 2)} RUB."
            ]
    elif territorial_analysis_mode in {"preview", "disabled"} or territorial_suppressed:
        key_insights = list(key_insights) + [
            "????????????? ???? ?????????????? ???????, ?? ??? ??????? ?????? ?? ??????? ?????? ? ????????????? ???????/????????."
        ]

    if weighted_localization_share > 0:
        key_insights = list(key_insights) + [
            f"Weighted localization share: {round(weighted_localization_share, 2)}%."
        ]

    payload.update(
        {
            "warnings_collector": warnings_collector,
            "facts": facts,
            "job": job,
            "metrics": metrics,
            "analytics": analytics,
            "data_quality": data_quality,
            "daily_kpi": daily_kpi,
            "ads_summary": ads_summary,
            "decisions_summary": decisions_summary,
            "director_strategy": director_strategy,
            "health_payload": health_payload,
            "health_summary": health_summary,
            "outcomes_payload": outcomes_payload,
            "cabinet_funnel": cabinet_funnel,
            "sales_funnel_diagnostics": sales_funnel_diagnostics,
            "sales_funnel_summary": sales_funnel_summary,
            "funnel_alerts": funnel_alerts,
            "sku_alerts": sku_alerts,
            "sku_watchlists": sku_watchlists,
            "decision_rows_added": decision_rows_added,
            "outcomes_evaluated": outcomes_evaluated,
            "confidence": confidence,
            "sku_metrics": sku_metrics,
            "abc_rows": abc_rows,
            "profit_contribution": profit_contribution,
            "keyword_monitoring": keyword_monitoring,
            "keyword_summary": keyword_summary,
            "advertising_efficiency": advertising_efficiency,
            "query_profitability": query_profitability,
            "portfolio_ads_summary": portfolio_ads_summary,
            "territorial_distribution": territorial_distribution,
            "territorial_summary": territorial_summary,
            "logistics_summary": logistics_summary,
            "unassigned_costs": unassigned_costs,
            "financial_kpi": financial_kpi,
            "totals": totals,
            "event_date_model": event_date_model,
            "order_kpi": order_kpi,
            "buyout_kpi": buyout_kpi,
            "daily_status_matrix": daily_status_matrix,
            "render_kpi": render_kpi,
            "event_ledger": event_ledger,
            "ads_rows_count": ads_rows_count,
            "ads_loaded_from_file": ads_loaded_from_file,
            "ads_source_file": ads_source_file,
            "ads_attribution_quality": ads_attribution_quality,
            "revenue_total": revenue_total,
            "revenue_total_legacy": revenue_total_legacy,
            "profit_total": profit_total,
            "daily_orders_count": daily_orders_count,
            "daily_orders_count_legacy": daily_orders_count_legacy,
            "daily_orders_amount": daily_orders_amount,
            "daily_orders_amount_legacy": daily_orders_amount_legacy,
            "daily_buyouts_count": daily_buyouts_count,
            "daily_buyouts_count_legacy": daily_buyouts_count_legacy,
            "daily_buyouts_amount": daily_buyouts_amount,
            "daily_buyouts_amount_legacy": daily_buyouts_amount_legacy,
            "avg_check": avg_check,
            "avg_check_legacy": avg_check_legacy,
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
            "margin_pct_total_legacy": margin_pct_total_legacy,
            "profitability_pct_total": profitability_pct_total,
            "profitability_pct_total_legacy": profitability_pct_total_legacy,
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
    payload = apply_report_guardrails(payload)
    return payload
