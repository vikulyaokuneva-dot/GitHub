from __future__ import annotations

from typing import Any, Dict, List

from ..pipeline.facts_payload_builder import (
    apply_facts_data_quality_patch,
    build_decision_memory_summary,
    build_facts_runtime_patch,
    build_history_summary,
    build_logistics_ktr_summary,
    build_profit_contribution_summary,
    build_territorial_distribution_summary,
)
from ..sources.wb_reports_loader import build_facts_from_reports


def _dict_or_empty(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _build_facts_sections_from_metrics(
    *,
    metrics: Dict[str, Any],
    financial_kpi: Dict[str, Any],
    ads_summary: Dict[str, Any],
    data_quality: Dict[str, Any],
) -> Dict[str, Any]:
    safe_metrics = metrics if isinstance(metrics, dict) else {}

    finance_source = (
        safe_metrics.get("financial_kpi")
        if isinstance(safe_metrics.get("financial_kpi"), dict)
        else (financial_kpi if isinstance(financial_kpi, dict) else {})
    )

    sales_funnel = safe_metrics.get("sales_funnel")
    if not isinstance(sales_funnel, dict):
        sales_funnel = {}
    funnel_source: Dict[str, Any] = {}
    if isinstance(sales_funnel.get("funnel"), dict):
        funnel_source = dict(sales_funnel.get("funnel") or {})
    elif isinstance(safe_metrics.get("funnel"), dict):
        funnel_source = dict(safe_metrics.get("funnel") or {})

    ads_source = (
        safe_metrics.get("ads")
        if isinstance(safe_metrics.get("ads"), dict)
        else (ads_summary if isinstance(ads_summary, dict) else {})
    )

    return {
        "finance": _dict_or_empty(finance_source),
        "funnel": _dict_or_empty(funnel_source),
        "ads": _dict_or_empty(ads_source),
        "data_quality": _dict_or_empty(data_quality),
    }


def build_daily_facts_base(
    *,
    seller_id: str,
    run_date: str,
    seller_name: str,
    metrics: Dict[str, Any],
    discovered_files: Dict[str, Any],
    warnings: List[Dict[str, Any]],
    source_mode: str,
    api_debug: Dict[str, Any],
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
    financial_data_degraded_flag: bool,
    event_date_model: Dict[str, Any],
    order_kpi: Dict[str, Any],
    buyout_kpi: Dict[str, Any],
    daily_status_matrix: Dict[str, Any],
    event_ledger: Dict[str, Any],
    render_kpi: Dict[str, Any],
) -> Dict[str, Any]:
    facts = build_facts_from_reports(
        seller_id=seller_id,
        run_date=run_date,
        seller_name=seller_name,
        metrics=metrics if isinstance(metrics, dict) else {},
        discovered_files=discovered_files if isinstance(discovered_files, dict) else {},
        warnings=warnings if isinstance(warnings, list) else [],
        source_mode=source_mode,
    )
    if not isinstance(facts, dict):
        facts = {}
    facts.update(
        build_facts_runtime_patch(
            source_mode=source_mode,
            api_debug=api_debug if isinstance(api_debug, dict) else {},
            metrics=metrics if isinstance(metrics, dict) else {},
            ads_summary=ads_summary if isinstance(ads_summary, dict) else {},
            ads_rows_count=int(ads_rows_count),
            financial_kpi=financial_kpi if isinstance(financial_kpi, dict) else {},
            ads_loaded_from_file=bool(ads_loaded_from_file),
            ads_source_file=str(ads_source_file or ""),
            ads_attribution_quality=str(ads_attribution_quality or "unknown"),
            data_source_orders_count=str(data_source_orders_count),
            data_source_buyouts_count=str(data_source_buyouts_count),
            data_source_orders_amount=str(data_source_orders_amount),
            data_source_buyouts_amount=str(data_source_buyouts_amount),
            daily_kpi=daily_kpi if isinstance(daily_kpi, dict) else {},
            data_source_revenue=str(data_source_revenue),
            data_source_wb_commission=str(data_source_wb_commission),
            data_source_logistics=str(data_source_logistics),
            data_source_storage=str(data_source_storage),
            data_source_ads_spend=str(data_source_ads_spend),
            source_flags=source_flags if isinstance(source_flags, dict) else {},
            source_policy=source_policy if isinstance(source_policy, dict) else {},
            event_date_model=event_date_model if isinstance(event_date_model, dict) else {},
            order_kpi=order_kpi if isinstance(order_kpi, dict) else {},
            buyout_kpi=buyout_kpi if isinstance(buyout_kpi, dict) else {},
            daily_status_matrix=daily_status_matrix if isinstance(daily_status_matrix, dict) else {},
            event_ledger=event_ledger if isinstance(event_ledger, dict) else {},
            render_kpi=render_kpi if isinstance(render_kpi, dict) else {},
        )
    )
    patched_data_quality = apply_facts_data_quality_patch(
        current_data_quality=facts.get("data_quality"),
        ads_attribution_quality=str(ads_attribution_quality or "unknown"),
        financial_partial=bool((financial_kpi if isinstance(financial_kpi, dict) else {}).get("is_partial", False)),
        financial_data_degraded_flag=bool(financial_data_degraded_flag),
    )
    if isinstance(patched_data_quality, dict):
        facts["data_quality"] = patched_data_quality
    sections = _build_facts_sections_from_metrics(
        metrics=metrics if isinstance(metrics, dict) else {},
        financial_kpi=financial_kpi if isinstance(financial_kpi, dict) else {},
        ads_summary=ads_summary if isinstance(ads_summary, dict) else {},
        data_quality=(
            patched_data_quality
            if isinstance(patched_data_quality, dict)
            else (metrics.get("data_quality") if isinstance(metrics, dict) and isinstance(metrics.get("data_quality"), dict) else {})
        ),
    )
    facts["finance"] = _dict_or_empty(sections.get("finance"))
    facts["funnel"] = _dict_or_empty(sections.get("funnel"))
    facts["ads"] = _dict_or_empty(sections.get("ads"))
    if isinstance(sections.get("data_quality"), dict):
        facts["data_quality"] = dict(sections.get("data_quality") or {})
    return facts


def attach_daily_facts_sections(
    *,
    facts: Dict[str, Any],
    p1_rows: List[Dict[str, Any]],
    p2_rows: List[Dict[str, Any]],
    p3_rows: List[Dict[str, Any]],
    top_profit_rows: List[Dict[str, Any]],
    territorial_summary: Dict[str, Any],
    logistics_summary: Dict[str, Any],
) -> Dict[str, Any]:
    out = dict(facts if isinstance(facts, dict) else {})
    out["profit_contribution_summary"] = build_profit_contribution_summary(
        p1_rows=p1_rows if isinstance(p1_rows, list) else [],
        p2_rows=p2_rows if isinstance(p2_rows, list) else [],
        p3_rows=p3_rows if isinstance(p3_rows, list) else [],
        top_profit_rows=top_profit_rows if isinstance(top_profit_rows, list) else [],
    )
    out["territorial_distribution_summary"] = build_territorial_distribution_summary(
        territorial_summary if isinstance(territorial_summary, dict) else {}
    )
    out["logistics_ktr_summary"] = build_logistics_ktr_summary(
        logistics_summary if isinstance(logistics_summary, dict) else {}
    )
    return out


def attach_decision_memory_summary_to_facts(
    facts: Dict[str, Any],
    decision_memory_summary: Dict[str, Any],
) -> Dict[str, Any]:
    out = dict(facts if isinstance(facts, dict) else {})
    out["decision_memory_summary"] = build_decision_memory_summary(
        decision_memory_summary if isinstance(decision_memory_summary, dict) else {}
    )
    return out


def attach_history_summary_to_facts(
    facts: Dict[str, Any],
    history_summary: Dict[str, Any],
    run_date: str,
) -> Dict[str, Any]:
    out = dict(facts if isinstance(facts, dict) else {})
    out["history_summary"] = build_history_summary(
        history_summary if isinstance(history_summary, dict) else {},
        run_date,
    )
    return out
