from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from ..metrics.sku_alerts_builder import build_sku_alerts
from ..metrics.sku_watchlists_builder import build_sku_watchlists
from .daily_stage_support import sync_from_entry


def run_daily_ai_stage(context: Dict[str, Any]) -> Dict[str, Any]:
    sync_from_entry(globals())

    ctx: Dict[str, Any] = dict(context or {})
    seller_id = str(ctx.get("seller_id") or "")
    run_date = str(ctx.get("run_date") or "")
    started_at = str(ctx.get("started_at") or "")
    source_mode = str(ctx.get("source_mode") or "local_reports")
    out_dir = str(ctx.get("out_dir") or "")

    metrics = ctx.get("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}
    analytics = ctx.get("analytics", {})
    if not isinstance(analytics, dict):
        analytics = {}
    abc_rows = ctx.get("abc_rows", [])
    if not isinstance(abc_rows, list):
        abc_rows = []
    facts = ctx.get("facts", {})
    if not isinstance(facts, dict):
        facts = {}
    territorial_distribution = ctx.get("territorial_distribution", {})
    if not isinstance(territorial_distribution, dict):
        territorial_distribution = {}
    source_flags = ctx.get("source_flags", {})
    if not isinstance(source_flags, dict):
        source_flags = {}
    api_debug = ctx.get("api_debug", {})
    if not isinstance(api_debug, dict):
        api_debug = {}
    input_debug = ctx.get("input_debug", {})
    if not isinstance(input_debug, dict):
        input_debug = {}
    daily_kpi = ctx.get("daily_kpi", {})
    if not isinstance(daily_kpi, dict):
        daily_kpi = {}
    ads_summary = ctx.get("ads_summary", {})
    if not isinstance(ads_summary, dict):
        ads_summary = {}
    financial_kpi = ctx.get("financial_kpi", {})
    if not isinstance(financial_kpi, dict):
        financial_kpi = {}
    sku_daily_dynamics = ctx.get("sku_daily_dynamics", {})
    if not isinstance(sku_daily_dynamics, dict):
        sku_daily_dynamics = {}
    cabinet_funnel = ctx.get("cabinet_funnel", {})
    if not isinstance(cabinet_funnel, dict):
        cabinet_funnel = {}
    sales_funnel_diagnostics = ctx.get("sales_funnel_diagnostics", {})
    if not isinstance(sales_funnel_diagnostics, dict):
        sales_funnel_diagnostics = {}
    if not sales_funnel_diagnostics and isinstance(cabinet_funnel.get("sku_diagnostics"), dict):
        sales_funnel_diagnostics = cabinet_funnel.get("sku_diagnostics", {})
    funnel_alerts = ctx.get("funnel_alerts", {})
    if not isinstance(funnel_alerts, dict):
        funnel_alerts = {}
    logistics_ktr = ctx.get("logistics_ktr", {})
    if not isinstance(logistics_ktr, dict):
        logistics_ktr = {}
    facts_financial_status = str(ctx.get("facts_financial_status") or "ok")
    financial_data_missing_flag = bool(ctx.get("financial_data_missing_flag", False))
    ads_rows_count = int(ctx.get("ads_rows_count", 0) or 0)
    ads_loaded_from_file = bool(ctx.get("ads_loaded_from_file", False))
    ads_source_file = str(ctx.get("ads_source_file") or "")
    ads_attribution_quality = str(ctx.get("ads_attribution_quality") or "unknown")
    data_source_orders_count = str(ctx.get("data_source_orders_count") or _SOURCE_UNKNOWN)
    data_source_buyouts_count = str(ctx.get("data_source_buyouts_count") or _SOURCE_UNKNOWN)
    data_source_orders_amount = str(ctx.get("data_source_orders_amount") or _SOURCE_UNKNOWN)
    data_source_buyouts_amount = str(ctx.get("data_source_buyouts_amount") or _SOURCE_UNKNOWN)
    data_source_revenue = str(ctx.get("data_source_revenue") or _SOURCE_UNKNOWN)
    data_source_wb_commission = str(ctx.get("data_source_wb_commission") or _SOURCE_UNKNOWN)
    data_source_logistics = str(ctx.get("data_source_logistics") or _SOURCE_UNKNOWN)
    data_source_storage = str(ctx.get("data_source_storage") or _SOURCE_UNKNOWN)
    data_source_ads_spend = str(ctx.get("data_source_ads_spend") or _SOURCE_UNKNOWN)
    warnings_collector = ctx.get("warnings_collector")
    if not isinstance(warnings_collector, WarningsCollector):
        warnings_collector = WarningsCollector()

    profit_contribution = ctx.get("profit_contribution", {})
    if not isinstance(profit_contribution, dict):
        profit_contribution = {}
    if not profit_contribution and isinstance(metrics, dict):
        profit_from_metrics = metrics.get("profit_contribution")
        if isinstance(profit_from_metrics, dict):
            profit_contribution = profit_from_metrics
    if isinstance(metrics, dict):
        metrics["profit_contribution"] = profit_contribution if isinstance(profit_contribution, dict) else {}
    analytics["profit_contribution"] = profit_contribution if isinstance(profit_contribution, dict) else {}
    keyword_monitoring = ctx.get("keyword_monitoring", {})
    if not isinstance(keyword_monitoring, dict):
        keyword_monitoring = {}
    if not keyword_monitoring and isinstance(metrics, dict):
        keyword_from_metrics = metrics.get("keyword_monitoring")
        if isinstance(keyword_from_metrics, dict):
            keyword_monitoring = keyword_from_metrics
    if not keyword_monitoring and isinstance(analytics, dict):
        keyword_from_analytics = analytics.get("keyword_monitoring")
        if isinstance(keyword_from_analytics, dict):
            keyword_monitoring = keyword_from_analytics
    if isinstance(metrics, dict):
        metrics["keyword_monitoring"] = keyword_monitoring if isinstance(keyword_monitoring, dict) else {}
    analytics["keyword_monitoring"] = keyword_monitoring if isinstance(keyword_monitoring, dict) else {}
    health_payload = compute_sku_health(
        facts,
        metrics,
        sku_rows=ctx.get("sku_metrics"),
        sales_funnel_diagnostics=sales_funnel_diagnostics,
    )
    health_summary = health_payload.get("summary", {}) if isinstance(health_payload, dict) else {}
    if not isinstance(health_summary, dict):
        health_summary = {}
    if isinstance(metrics, dict):
        metrics["health_score"] = health_payload if isinstance(health_payload, dict) else {}
        metrics["health_summary"] = health_summary
    analytics["health_score"] = health_payload if isinstance(health_payload, dict) else {}
    analytics["health_summary"] = health_summary
    health_status = str(health_summary.get("status") or "").strip().lower()
    if health_status in {"partial", "insufficient_data"}:
        warnings_collector.add_warning(
            "sku_health_partial_data",
            f"SKU health score computed with status={health_status}.",
        )
    sku_alerts = build_sku_alerts(
        run_date=run_date,
        sku_daily_dynamics=sku_daily_dynamics if isinstance(sku_daily_dynamics, dict) else {},
        logistics_ktr=logistics_ktr if isinstance(logistics_ktr, dict) else {},
        health_payload=health_payload if isinstance(health_payload, dict) else {},
        history_root=(Path(out_dir).parent / "history") if out_dir else None,
    )
    sku_watchlists = build_sku_watchlists(
        run_date=run_date,
        sku_daily_dynamics=sku_daily_dynamics if isinstance(sku_daily_dynamics, dict) else {},
        sku_alerts=sku_alerts if isinstance(sku_alerts, dict) else {},
        logistics_ktr=logistics_ktr if isinstance(logistics_ktr, dict) else {},
        limit_per_group=5,
    )
    growth_simulation = simulate_growth(metrics if isinstance(metrics, dict) else {})
    opportunity_scores = compute_opportunity_scores(
        metrics if isinstance(metrics, dict) else {},
        abc_rows if isinstance(abc_rows, list) else [],
        health_payload if isinstance(health_payload, dict) else {},
    )
    decisions_layer_payload = build_decisions_layer(
        metrics=metrics if isinstance(metrics, dict) else {},
        abc_rows=abc_rows if isinstance(abc_rows, list) else [],
        health_payload=health_payload if isinstance(health_payload, dict) else {},
        territorial_distribution=territorial_distribution if isinstance(territorial_distribution, dict) else {},
        logistics_ktr=ctx.get("logistics_ktr", {}) if isinstance(ctx.get("logistics_ktr"), dict) else {},
        opportunity_scores=opportunity_scores if isinstance(opportunity_scores, dict) else {},
        growth_simulation=growth_simulation if isinstance(growth_simulation, dict) else {},
    )
    decisions_payload = decisions_layer_payload.get("decisions_payload", {})
    if not isinstance(decisions_payload, dict):
        decisions_payload = {}
    decisions_summary = decisions_payload.get("summary", {}) if isinstance(decisions_payload, dict) else {}
    director_strategy = decisions_layer_payload.get("director_strategy", {})
    if not isinstance(director_strategy, dict):
        director_strategy = {}

    job = build_daily_job(
        seller_id=seller_id,
        run_date=run_date,
        started_at=started_at,
        finished_at=_utc_now_iso(),
        source_mode=source_mode,
        out_dir=out_dir,
        financial_data_missing_flag=financial_data_missing_flag,
        facts_financial_status=facts_financial_status,
        financial_kpi=financial_kpi if isinstance(financial_kpi, dict) else {},
        input_debug=input_debug if isinstance(input_debug, dict) else {},
        api_debug=api_debug if isinstance(api_debug, dict) else {},
        daily_kpi=daily_kpi if isinstance(daily_kpi, dict) else {},
        ads_summary=ads_summary if isinstance(ads_summary, dict) else {},
        ads_rows_count=ads_rows_count,
        ads_loaded_from_file=bool(ads_loaded_from_file),
        ads_source_file=ads_source_file,
        ads_attribution_quality=ads_attribution_quality,
        data_source_orders_count=data_source_orders_count,
        data_source_buyouts_count=data_source_buyouts_count,
        data_source_orders_amount=data_source_orders_amount,
        data_source_buyouts_amount=data_source_buyouts_amount,
        data_source_revenue=data_source_revenue,
        data_source_wb_commission=data_source_wb_commission,
        data_source_logistics=data_source_logistics,
        data_source_storage=data_source_storage,
        data_source_ads_spend=data_source_ads_spend,
        source_flags=source_flags if isinstance(source_flags, dict) else {},
        metrics=metrics if isinstance(metrics, dict) else {},
    )

    write_daily_ai_artifacts(
        out_dir=out_dir,
        health_payload=health_payload if isinstance(health_payload, dict) else {},
        decisions_payload=decisions_payload if isinstance(decisions_payload, dict) else {},
        growth_simulation=growth_simulation if isinstance(growth_simulation, dict) else {},
        opportunity_scores=opportunity_scores if isinstance(opportunity_scores, dict) else {},
        director_strategy=director_strategy if isinstance(director_strategy, dict) else {},
        api_debug=api_debug if isinstance(api_debug, dict) else {},
        sku_alerts=sku_alerts if isinstance(sku_alerts, dict) else {},
        sku_watchlists=sku_watchlists if isinstance(sku_watchlists, dict) else {},
    )

    decision_rows_added = log_decisions(
        seller_id=seller_id,
        run_date=run_date,
        metrics=metrics if isinstance(metrics, dict) else {},
        decisions=decisions_payload if isinstance(decisions_payload, dict) else {},
        artifacts_dir=Path(out_dir),
    )
    if decision_rows_added > 0:
        warnings_collector.add_warning(
            "decision_memory_updated",
            f"Decision memory updated: added {decision_rows_added} records.",
        )

    memory_dir = Path(out_dir).parent / "memory"
    outcomes_payload = evaluate_decision_outcomes(
        seller_id=seller_id,
        run_date=run_date,
        artifacts_dir=Path(out_dir),
        memory_dir=memory_dir,
    )
    outcomes_file = save_outcomes(
        seller_id=seller_id,
        run_date=run_date,
        outcomes=outcomes_payload,
        memory_dir=memory_dir,
    )
    outcomes_evaluated = int(outcomes_payload.get("evaluated", 0) or 0)
    if outcomes_evaluated > 0:
        warnings_collector.add_warning("decision_outcomes_evaluated", f"Decision outcomes evaluated: {outcomes_evaluated}")
    else:
        warnings_collector.add_warning(
            "no_decisions_ready_for_outcome",
            "No decisions are ready for outcome evaluation yet",
        )

    decision_memory_summary = outcomes_payload.get("decision_memory_summary", {})
    if not isinstance(decision_memory_summary, dict):
        decision_memory_summary = {}
    facts = attach_decision_memory_summary_to_facts(
        facts if isinstance(facts, dict) else {},
        decision_memory_summary,
    )
    job = attach_daily_job_decision_outcomes(
        job if isinstance(job, dict) else {},
        decision_rows_added=int(decision_rows_added),
        outcomes_evaluated=int(outcomes_evaluated),
        outcomes_file=str(outcomes_file),
    )

    write_facts_and_warnings(
        out_dir=out_dir,
        facts=facts if isinstance(facts, dict) else {},
        warnings=warnings_collector.export_warnings(),
    )

    ctx.update(
        {
            "warnings_collector": warnings_collector,
            "analytics": analytics,
            "profit_contribution": profit_contribution,
            "keyword_monitoring": keyword_monitoring,
            "health_payload": health_payload,
            "health_summary": health_summary,
            "sku_alerts": sku_alerts,
            "sku_watchlists": sku_watchlists,
            "growth_simulation": growth_simulation,
            "opportunity_scores": opportunity_scores,
            "decisions_layer_payload": decisions_layer_payload,
            "decisions_payload": decisions_payload,
            "decisions_summary": decisions_summary,
            "director_strategy": director_strategy,
            "cabinet_funnel": cabinet_funnel,
            "sales_funnel_diagnostics": sales_funnel_diagnostics,
            "funnel_alerts": funnel_alerts,
            "decision_rows_added": decision_rows_added,
            "outcomes_payload": outcomes_payload,
            "outcomes_file": outcomes_file,
            "outcomes_evaluated": outcomes_evaluated,
            "facts": facts,
            "job": job,
        }
    )
    return ctx
