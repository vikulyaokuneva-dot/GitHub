from __future__ import annotations

import os
from typing import Any, Dict, List

from ..pipeline.daily_stage_support import sync_from_entry
from .render_policy import format_int_or_unknown, format_money_or_unknown, format_pct_or_unknown


def _safe_float_local(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _funnel_delta(funnel_alerts: Dict[str, Any], metric: str, field: str) -> float | None:
    if not isinstance(funnel_alerts, dict):
        return None
    for container_key in ("metrics", "comparisons", "deltas"):
        container = funnel_alerts.get(container_key, {})
        if not isinstance(container, dict):
            continue
        payload = container.get(metric, {})
        if isinstance(payload, dict):
            value = _safe_float_local(payload.get(field))
            if value is not None:
                return value
    alerts = funnel_alerts.get("alerts", [])
    if isinstance(alerts, list):
        for row in alerts:
            if not isinstance(row, dict):
                continue
            row_metric = str(row.get("metric") or row.get("type") or "").strip().lower()
            if metric.lower() not in row_metric:
                continue
            value = _safe_float_local(row.get(field))
            if value is not None:
                return value
    return None


def _funnel_alert_summary(funnel_alerts: Dict[str, Any]) -> str:
    if not isinstance(funnel_alerts, dict) or not funnel_alerts:
        return "unknown"
    summary = funnel_alerts.get("summary", {})
    if isinstance(summary, dict):
        warning_count = int(summary.get("warning_count", 0) or 0)
        critical_count = int(summary.get("critical_count", 0) or 0)
        return f"warning={warning_count}, critical={critical_count}"
    alerts = funnel_alerts.get("alerts", [])
    if not isinstance(alerts, list):
        return "unknown"
    warning_count = 0
    critical_count = 0
    for row in alerts:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "").strip().lower()
        if status == "warning":
            warning_count += 1
        elif status == "critical":
            critical_count += 1
    return f"warning={warning_count}, critical={critical_count}"


def _watchlist_groups_for_render() -> List[tuple[str, str]]:
    return [
        ("top_growth", "TOP GROWTH"),
        ("top_risk", "TOP RISK"),
        ("dead_stock", "DEAD STOCK"),
        ("ad_inefficiency", "AD INEFFICIENCY"),
        ("conversion_drop", "CONVERSION DROP"),
        ("logistics_risk", "LOGISTICS RISK"),
    ]


def _watchlist_rows(sku_watchlists: Dict[str, Any], group: str, limit: int = 5) -> List[Dict[str, Any]]:
    watchlists = sku_watchlists.get("watchlists", {}) if isinstance(sku_watchlists, dict) else {}
    rows = watchlists.get(group, []) if isinstance(watchlists, dict) else []
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)][: max(0, int(limit))]


def _watchlist_line(row: Dict[str, Any]) -> str:
    sku = str(row.get("sku") or "").strip() or "n/a"
    attention = int(float(row.get("attention_score", 0) or 0))
    reason = str(row.get("reason") or "").strip()
    deltas = row.get("deltas", {})
    if not isinstance(deltas, dict):
        deltas = {}
    main_delta = _safe_float_local(
        deltas.get("net_profit_vs_7d_pct")
        if deltas.get("net_profit_vs_7d_pct") is not None
        else deltas.get("orders_vs_7d_pct")
    )
    delta_text = f", Δ7d={format_pct_or_unknown(main_delta)}" if main_delta is not None else ""
    reason_text = f", {reason}" if reason else ""
    return f"SKU {sku} | attention {attention}{delta_text}{reason_text}"


def run_daily_report_stage(payload: Dict[str, Any]) -> Dict[str, Any]:
    sync_from_entry(globals())

    data: Dict[str, Any] = dict(payload or {})
    out_dir = str(data.get("out_dir") or "")
    daily_kpi = data.get("daily_kpi", {})
    if not isinstance(daily_kpi, dict):
        daily_kpi = {}
    territorial_summary = data.get("territorial_summary", {})
    if not isinstance(territorial_summary, dict):
        territorial_summary = {}
    territorial_distribution = data.get("territorial_distribution", {})
    if not isinstance(territorial_distribution, dict):
        territorial_distribution = {}
    logistics_summary = data.get("logistics_summary", {})
    if not isinstance(logistics_summary, dict):
        logistics_summary = {}
    profit_contribution = data.get("profit_contribution", {})
    if not isinstance(profit_contribution, dict):
        profit_contribution = {}
    sku_metrics = data.get("sku_metrics", [])
    if not isinstance(sku_metrics, list):
        sku_metrics = []
    abc_rows = data.get("abc_rows", [])
    if not isinstance(abc_rows, list):
        abc_rows = []
    decision_groups = data.get("decision_groups", {})
    if not isinstance(decision_groups, dict):
        decision_groups = {"scale": [], "fix": [], "watch": [], "liquidate": []}
    director_strategy = data.get("director_strategy", {})
    if not isinstance(director_strategy, dict):
        director_strategy = {}
    job = data.get("job", {})
    if not isinstance(job, dict):
        job = {}
    warnings_collector = data.get("warnings_collector")
    if not isinstance(warnings_collector, WarningsCollector):
        warnings_collector = WarningsCollector()
    facts = data.get("facts", {})
    if not isinstance(facts, dict):
        facts = {}
    data_quality = data.get("data_quality", {})
    if not isinstance(data_quality, dict):
        data_quality = {}
    outcomes_payload = data.get("outcomes_payload", {})
    if not isinstance(outcomes_payload, dict):
        outcomes_payload = {}
    unassigned_costs = data.get("unassigned_costs", {})
    if not isinstance(unassigned_costs, dict):
        unassigned_costs = {}
    render_kpi = data.get("render_kpi", {})
    if not isinstance(render_kpi, dict):
        render_kpi = {}
    daily_status_matrix = data.get("daily_status_matrix", {})
    if not isinstance(daily_status_matrix, dict):
        daily_status_matrix = {}
    order_kpi = data.get("order_kpi", {})
    if not isinstance(order_kpi, dict):
        order_kpi = {}
    buyout_kpi = data.get("buyout_kpi", {})
    if not isinstance(buyout_kpi, dict):
        buyout_kpi = {}
    event_date_model = data.get("event_date_model", {})
    if not isinstance(event_date_model, dict):
        event_date_model = {}
    event_ledger = data.get("event_ledger", {})
    if not isinstance(event_ledger, dict):
        event_ledger = {}
    cabinet_funnel = data.get("cabinet_funnel", {})
    if not isinstance(cabinet_funnel, dict):
        cabinet_funnel = {}
    funnel_alerts = data.get("funnel_alerts", {})
    if not isinstance(funnel_alerts, dict):
        funnel_alerts = {}
    sku_watchlists = data.get("sku_watchlists", {})
    if not isinstance(sku_watchlists, dict):
        sku_watchlists = {}

    def _round_or_none(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return round(float(value), 2)
        except (TypeError, ValueError):
            return None

    def _int_or_none(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    orders_count_value = render_kpi.get("orders_count", data.get("daily_orders_count"))
    orders_amount_value = render_kpi.get("orders_amount", data.get("daily_orders_amount"))
    buyouts_count_value = render_kpi.get("buyouts_count", data.get("daily_buyouts_count"))
    buyouts_amount_value = render_kpi.get("buyouts_amount", data.get("daily_buyouts_amount"))
    avg_check_value = render_kpi.get("avg_check", data.get("avg_check"))
    revenue_value = render_kpi.get("revenue", data.get("revenue_total"))
    net_profit_value = render_kpi.get("net_profit", data.get("net_profit"))
    margin_pct_value = render_kpi.get("margin_pct", data.get("margin_pct_total"))
    profitability_pct_value = render_kpi.get("profitability_pct", data.get("profitability_pct_total"))

    page_1: List[str] = [
        "# WB AI Agent РІР‚вЂќ Р С›РЎвЂљРЎвЂЎР ВµРЎвЂљ Р С—Р С• Р С”Р В°Р В±Р С‘Р Р…Р ВµРЎвЂљРЎС“",
        f"### Р С™Р В°Р В±Р С‘Р Р…Р ВµРЎвЂљ: {str(data.get('seller_id') or '')}",
        f"### Р вЂќР В°РЎвЂљР В° Р С•РЎвЂљРЎвЂЎР ВµРЎвЂљР В°: {str(data.get('run_date') or '')}",
        f"### Р Р€Р Р†Р ВµРЎР‚Р ВµР Р…Р Р…Р С•РЎРѓРЎвЂљРЎРЉ Р Т‘Р В°Р Р…Р Р…РЎвЂ№РЎвЂ¦: {_confidence_ru(str(data.get('confidence') or 'low'))}",
        "",
        "## COMMERCE KPI",
        "Р СџР С•Р С”Р В°Р В·Р В°РЎвЂљР ВµР В»РЎРЉ | Р вЂ”Р Р…Р В°РЎвЂЎР ВµР Р…Р С‘Р Вµ",
        f"Р С™Р С•Р В»Р С‘РЎвЂЎР ВµРЎРѓРЎвЂљР Р†Р С• Р В·Р В°Р С”Р В°Р В·Р С•Р Р† | {format_int_or_unknown(orders_count_value)}",
        f"Р РЋРЎС“Р СР СР В° Р В·Р В°Р С”Р В°Р В·Р С•Р Р† (Р СР С‘Р Р…РЎС“РЎРѓ Р С”Р С•Р СР С‘РЎРѓРЎРѓР С‘РЎРЏ WB) | {format_money_or_unknown(orders_amount_value)}",
        f"Р вЂ™РЎвЂ№Р С”РЎС“Р С—РЎвЂ№ | {format_int_or_unknown(buyouts_count_value)}",
        f"Р С™ Р С—Р ВµРЎР‚Р ВµРЎвЂЎР С‘РЎРѓР В»Р ВµР Р…Р С‘РЎР‹ Р С—Р С• Р Р†РЎвЂ№Р С”РЎС“Р С—Р В°Р С | {format_money_or_unknown(buyouts_amount_value)}",
        f"Р РЋРЎР‚Р ВµР Т‘Р Р…Р С‘Р в„– РЎвЂЎР ВµР С” Р С—Р С• Р Р†РЎвЂ№Р С”РЎС“Р С—РЎС“ | {format_money_or_unknown(avg_check_value)}",
        f"Р ВРЎРѓРЎвЂљР С•РЎвЂЎР Р…Р С‘Р С” orders_count | {str(daily_kpi.get('data_source_orders_count') or daily_kpi.get('data_source_orders') or _SOURCE_UNKNOWN)}",
        f"Р ВРЎРѓРЎвЂљР С•РЎвЂЎР Р…Р С‘Р С” orders_amount | {str(daily_kpi.get('data_source_orders_amount') or _SOURCE_UNKNOWN)}",
        f"Р ВРЎРѓРЎвЂљР С•РЎвЂЎР Р…Р С‘Р С” buyouts_count | {str(daily_kpi.get('data_source_buyouts_count') or daily_kpi.get('data_source_buyouts') or _SOURCE_UNKNOWN)}",
        f"Р ВРЎРѓРЎвЂљР С•РЎвЂЎР Р…Р С‘Р С” buyouts_amount | {str(daily_kpi.get('data_source_buyouts_amount') or _SOURCE_UNKNOWN)}",
        f"Orders count Р С—Р С•Р Т‘РЎвЂљР Р†Р ВµРЎР‚Р В¶Р Т‘Р ВµР Р… | {'Р вЂќР В°' if bool(daily_kpi.get('orders_count_confirmed', False)) else 'Р СњР ВµРЎвЂљ'}",
        f"Buyouts count Р С—Р С•Р Т‘РЎвЂљР Р†Р ВµРЎР‚Р В¶Р Т‘Р ВµР Р… | {'Р вЂќР В°' if bool(daily_kpi.get('buyouts_count_confirmed', False)) else 'Р СњР ВµРЎвЂљ'}",
        f"Orders amount Р С—Р С•Р Т‘РЎвЂљР Р†Р ВµРЎР‚Р В¶Р Т‘Р ВµР Р… | {'Р вЂќР В°' if bool(daily_kpi.get('orders_amount_confirmed', False)) else 'Р СњР ВµРЎвЂљ'}",
        f"Buyouts amount Р С—Р С•Р Т‘РЎвЂљР Р†Р ВµРЎР‚Р В¶Р Т‘Р ВµР Р… | {'Р вЂќР В°' if bool(daily_kpi.get('buyouts_amount_confirmed', False)) else 'Р СњР ВµРЎвЂљ'}",
        f"Event status matrix | orders={str(daily_status_matrix.get('orders') or 'unknown')}, buyouts={str(daily_status_matrix.get('buyouts') or 'unknown')}, financials={str(daily_status_matrix.get('financials') or 'unknown')}, ads={str(daily_status_matrix.get('ads') or 'unknown')}",
        f"Р С™Р С•Р В»Р С‘РЎвЂЎР ВµРЎРѓРЎвЂљР Р†Р С• SKU | {_format_int(len(sku_metrics))}",
        f"Р В Р В°РЎРѓРЎвЂ¦Р С•Р Т‘РЎвЂ№ Р Р…Р В° РЎР‚Р ВµР С”Р В»Р В°Р СРЎС“ | {_format_money(data.get('ads_spend_total', 0.0))}",
        "",
        "## FINANCIAL KPI",
        "Р СџР С•Р С”Р В°Р В·Р В°РЎвЂљР ВµР В»РЎРЉ | Р вЂ”Р Р…Р В°РЎвЂЎР ВµР Р…Р С‘Р Вµ",
        f"Р вЂ™РЎвЂ№РЎР‚РЎС“РЎвЂЎР С”Р В° (Р С—Р С•Р Т‘РЎвЂљР Р†Р ВµРЎР‚Р В¶Р Т‘Р ВµР Р…Р Р…Р В°РЎРЏ РЎвЂћР С‘Р Р…Р В°Р Р…РЎРѓР С•Р Р†РЎвЂ№Р СР С‘ РЎРѓРЎвЂљРЎР‚Р С•Р С”Р В°Р СР С‘) | {format_money_or_unknown(revenue_value, decimals=0)}",
        f"Р РЋР ВµР В±Р ВµРЎРѓРЎвЂљР С•Р С‘Р СР С•РЎРѓРЎвЂљРЎРЉ | {_format_money(data.get('cost_price_total', 0.0))}",
        f"Р С™Р С•Р СР С‘РЎРѓРЎРѓР С‘РЎРЏ WB | {_format_money(data.get('wb_commission', 0.0))}",
        f"Р вЂєР С•Р С–Р С‘РЎРѓРЎвЂљР С‘Р С”Р В° | {_format_money(data.get('logistics_total', 0.0))}",
        f"Р ТђРЎР‚Р В°Р Р…Р ВµР Р…Р С‘Р Вµ | {_format_money(data.get('storage_total', 0.0))}",
        f"Р РЃРЎвЂљРЎР‚Р В°РЎвЂћРЎвЂ№ | {_format_money(data.get('penalties_total', 0.0))}",
        f"Р Р€Р Т‘Р ВµРЎР‚Р В¶Р В°Р Р…Р С‘РЎРЏ | {_format_money(data.get('deductions_total', 0.0))}",
        f"Р В Р ВµР С”Р В»Р В°Р СР В° | {_format_money(data.get('ads_spend_total', 0.0))}",
        f"Р вЂ™Р В°Р В»Р С•Р Р†Р В°РЎРЏ Р С—РЎР‚Р С‘Р В±РЎвЂ№Р В»РЎРЉ | {_format_money(data.get('gross_profit_total', 0.0))}",
        f"Р В§Р С‘РЎРѓРЎвЂљР В°РЎРЏ Р С—РЎР‚Р С‘Р В±РЎвЂ№Р В»РЎРЉ | {format_money_or_unknown(net_profit_value, decimals=0)}",
        f"Р СљР В°РЎР‚Р В¶Р В° % | {format_pct_or_unknown(margin_pct_value)}",
        f"Р В Р ВµР Р…РЎвЂљР В°Р В±Р ВµР В»РЎРЉР Р…Р С•РЎРѓРЎвЂљРЎРЉ % | {format_pct_or_unknown(profitability_pct_value)}",
        f"Р СџР С•Р В»Р Р…Р С•РЎвЂљР В° РЎвЂћР С‘Р Р…Р В°Р Р…РЎРѓР С•Р Р†РЎвЂ№РЎвЂ¦ Р Т‘Р В°Р Р…Р Р…РЎвЂ№РЎвЂ¦ | {_format_pct(data.get('financial_completeness_pct', 0.0))}",
        f"Р РЋРЎвЂљР В°РЎвЂљРЎС“РЎРѓ РЎвЂћР С‘Р Р…Р В°Р Р…РЎРѓР С•Р Р†Р С•Р С–Р С• Р С”Р С•Р Р…РЎвЂљРЎС“РЎР‚Р В° | {'РЎвЂЎР В°РЎРѓРЎвЂљР С‘РЎвЂЎР Р…РЎвЂ№Р в„–' if bool(data.get('financial_partial', False)) else 'РЎвЂћР С‘Р Р…Р В°Р В»РЎРЉР Р…РЎвЂ№Р в„–'}",
        "",
        "## Р В Р вЂўР С™Р вЂєР С’Р СљР С’",
        "Р СџР С•Р С”Р В°Р В·Р В°РЎвЂљР ВµР В»РЎРЉ | Р вЂ”Р Р…Р В°РЎвЂЎР ВµР Р…Р С‘Р Вµ",
        f"Р СџР С•Р С”Р В°Р В·РЎвЂ№ | {_format_int(data.get('ads_impressions', 0))}",
        f"Р С™Р В»Р С‘Р С”Р С‘ | {_format_int(data.get('ads_clicks', 0))}",
        f"CTR | {_format_pct(data.get('ads_ctr', 0.0))}",
        f"Р В Р В°РЎРѓРЎвЂ¦Р С•Р Т‘ | {_format_money(data.get('ads_spend_total', 0.0))}",
        f"Р вЂ”Р В°Р С”Р В°Р В·РЎвЂ№ | {_format_int(data.get('ads_orders', 0))}",
        f"Р вЂ™РЎвЂ№РЎР‚РЎС“РЎвЂЎР С”Р В° | {_format_money(data.get('ads_revenue', 0.0))}",
        f"ACOS | {_format_pct(data.get('ads_acos', 0.0))}",
        f"ROMI | {_format_pct(data.get('ads_romi', 0.0))}",
        f"Р В Р ВµР С”Р В»Р В°Р СР В° РЎС“РЎвЂЎРЎвЂљР ВµР Р…Р В° Р Р† Р С—РЎР‚Р С‘Р В±РЎвЂ№Р В»Р С‘ | {'Р вЂќР В°' if _safe_float(data.get('ads_spend_total', 0.0)) > 0 else 'Р СњР ВµРЎвЂљ'}",
        f"Р С’РЎвЂљРЎР‚Р С‘Р В±РЎС“РЎвЂ Р С‘РЎРЏ РЎР‚Р ВµР С”Р В»Р В°Р СРЎвЂ№ | {str(data.get('ads_attribution_quality') or 'unknown')}",
        f"Р ВРЎРѓРЎвЂљР С•РЎвЂЎР Р…Р С‘Р С” РЎР‚Р ВµР С”Р В»Р В°Р СРЎвЂ№ | {str(data.get('ads_source_file') or ('local_file' if bool(data.get('ads_loaded_from_file', False)) else 'api_or_missing'))}",
        "",
        "## Р С™Р вЂєР В®Р В§Р вЂўР вЂ™Р В«Р вЂў Р вЂ™Р В«Р вЂ™Р С›Р вЂќР В«",
    ]
    page_1.extend(f"- {line}" for line in data.get("key_insights", []))

    balanced_count = int(territorial_summary.get("balanced_count", 0) or 0)
    moderate_count = int(territorial_summary.get("moderate_mismatch_count", 0) or 0)
    misallocated_count = int(territorial_summary.get("misallocated_count", 0) or 0)
    analyzed_with_ktr = int(territorial_summary.get("sku_with_ktr", balanced_count + moderate_count + misallocated_count) or 0)
    top_misaligned_pdf = territorial_summary.get("top_misaligned_skus", [])
    if not isinstance(top_misaligned_pdf, list):
        top_misaligned_pdf = []
    top_misaligned_pdf = [str(x).strip() for x in top_misaligned_pdf if str(x).strip()]
    territorial_items = territorial_distribution.get("skus", []) if isinstance(territorial_distribution, dict) else []
    if not isinstance(territorial_items, list) and isinstance(territorial_distribution, dict):
        territorial_items = territorial_distribution.get("items", [])
    if not isinstance(territorial_items, list):
        territorial_items = []
    confidence_by_sku: Dict[str, str] = {}
    for item in territorial_items:
        if not isinstance(item, dict):
            continue
        sku = str(item.get("sku") or "").strip()
        if not sku:
            continue
        confidence_by_sku[sku] = str(item.get("confidence") or "").strip().lower()
    top_misaligned_confident = [sku for sku in top_misaligned_pdf if confidence_by_sku.get(sku) != "low"]
    excluded_low_conf_count = len([sku for sku in top_misaligned_pdf if confidence_by_sku.get(sku) == "low"])
    low_conf_ktr_count = sum(
        1
        for item in territorial_items
        if isinstance(item, dict)
        and _safe_float(item.get("ktr")) > 0
        and str(item.get("confidence") or "").strip().lower() == "low"
    )
    top_misaligned_text = _compact_sku_list(top_misaligned_confident, limit=3)

    page_1.extend(["", "## Р СћР вЂўР В Р В Р ВР СћР С›Р В Р ВР С’Р вЂєР В¬Р СњР С›Р вЂў Р В Р С’Р РЋР СџР В Р вЂўР вЂќР вЂўР вЂєР вЂўР СњР ВР вЂў"])
    if analyzed_with_ktr <= 0:
        page_1.append("- Р СњР ВµР Т‘Р С•РЎРѓРЎвЂљР В°РЎвЂљР С•РЎвЂЎР Р…Р С• Р Т‘Р В°Р Р…Р Р…РЎвЂ№РЎвЂ¦ Р Т‘Р В»РЎРЏ Р В°Р Р…Р В°Р В»Р С‘Р В·Р В° РЎвЂљР ВµРЎР‚РЎР‚Р С‘РЎвЂљР С•РЎР‚Р С‘Р В°Р В»РЎРЉР Р…Р С•Р С–Р С• РЎР‚Р В°РЎРѓР С—РЎР‚Р ВµР Т‘Р ВµР В»Р ВµР Р…Р С‘РЎРЏ")
    else:
        page_1.append(f"- Р РЋРЎР‚Р ВµР Т‘Р Р…Р С‘Р в„– Р С™Р СћР В  Р С—Р С• Р С”Р В°Р В±Р С‘Р Р…Р ВµРЎвЂљРЎС“: {_format_ktr(territorial_summary.get('avg_ktr', 0.0))}")
        page_1.append(f"- Р ТђРЎР‚Р С•РЎв‚¬Р С• РЎР‚Р В°РЎРѓР С—РЎР‚Р ВµР Т‘Р ВµР В»Р ВµР Р…РЎвЂ№: {_format_int(balanced_count)} SKU")
        page_1.append(f"- Р вЂўРЎРѓРЎвЂљРЎРЉ Р С—Р ВµРЎР‚Р ВµР С”Р С•РЎРѓ: {_format_int(moderate_count + misallocated_count)} SKU")
        if top_misaligned_confident:
            page_1.append(f"- Р СњР В°Р С‘Р В±Р С•Р В»РЎРЉРЎв‚¬Р С‘Р в„– Р С—Р ВµРЎР‚Р ВµР С”Р С•РЎРѓ (confidence medium/high): {top_misaligned_text}")
        elif top_misaligned_pdf:
            page_1.append("- Р СњР В°Р С‘Р В±Р С•Р В»РЎРЉРЎв‚¬Р С‘Р в„– Р С—Р ВµРЎР‚Р ВµР С”Р С•РЎРѓ: РЎвЂљР С•Р В»РЎРЉР С”Р С• low-confidence SKU (total_buys < 3)")
        else:
            page_1.append("- Р СњР В°Р С‘Р В±Р С•Р В»РЎРЉРЎв‚¬Р С‘Р в„– Р С—Р ВµРЎР‚Р ВµР С”Р С•РЎРѓ: РІР‚вЂќ")
        if excluded_low_conf_count > 0:
            page_1.append(f"- Р ВРЎРѓР С”Р В»РЎР‹РЎвЂЎР ВµР Р…Р С• low-confidence SKU Р С‘Р В· РЎвЂљР С•Р С—Р В°: {_format_int(excluded_low_conf_count)}")
        if low_conf_ktr_count > 0:
            page_1.append(f"- Low-confidence KTR (total_buys < 3): {_format_int(low_conf_ktr_count)} SKU, Р С‘Р Р…РЎвЂљР ВµРЎР‚Р С—РЎР‚Р ВµРЎвЂљР С‘РЎР‚Р С•Р Р†Р В°РЎвЂљРЎРЉ Р С•РЎРѓРЎвЂљР С•РЎР‚Р С•Р В¶Р Р…Р С•")

    logistics_top_critical = logistics_summary.get("top_critical_skus", []) if isinstance(logistics_summary, dict) else []
    if not isinstance(logistics_top_critical, list):
        logistics_top_critical = []
    logistics_top_critical = [str(x).strip() for x in logistics_top_critical if str(x).strip()]
    logistics_sku_total = int(logistics_summary.get("sku_total", 0) or 0) if isinstance(logistics_summary, dict) else 0
    if logistics_sku_total > 0:
        page_1.extend(["", "## LOGISTICS KTR"])
        page_1.append(f"- Critical SKU: {_format_int(logistics_summary.get('critical_count', 0))}")
        page_1.append(f"- Inefficient SKU: {_format_int(logistics_summary.get('inefficient_count', 0))}")
        page_1.append(f"- Average locality score: {_format_ktr(logistics_summary.get('avg_locality_score', 0.0))}")
        if logistics_top_critical:
            page_1.append(f"- Top critical SKU: {_compact_sku_list(logistics_top_critical, limit=5)}")
        else:
            page_1.append("- Top critical SKU: РІР‚вЂќ")

    profit_rows = _top_profit_rows(
        profit_contribution=profit_contribution if isinstance(profit_contribution, dict) else {},
        sku_metrics=sku_metrics,
        abc_rows=abc_rows,
    )
    page_1.extend(["", "## Р СћР С›Р Сџ SKU Р СџР С› Р СџР В Р ВР вЂР В«Р вЂєР В", "SKU | Р СџРЎР‚Р С‘Р В±РЎвЂ№Р В»РЎРЉ | Р вЂќР С•Р В»РЎРЏ Р С—РЎР‚Р С‘Р В±РЎвЂ№Р В»Р С‘ (%) | Р СљР В°РЎР‚Р В¶Р В° (%) | Р С™Р В»Р В°РЎРѓРЎРѓ Р С—РЎР‚Р С‘Р В±РЎвЂ№Р В»Р С‘ | ABC"])
    if profit_rows:
        for row in profit_rows[:5]:
            profit_value = _safe_float(row.get("profit", 0.0))
            profit_share_pct = (profit_value / float(data.get("profit_total", 0.0) or 0.0) * 100.0) if abs(float(data.get("profit_total", 0.0) or 0.0)) > 1e-9 else 0.0
            page_1.append(
                f"{row.get('sku', 'n/a')} | "
                f"{_format_money(profit_value)} | "
                f"{_format_pct(profit_share_pct)} | "
                f"{_format_pct(row.get('margin_pct', 0.0))} | "
                f"{str(row.get('profit_class', '-') or '-')} | "
                f"{str(row.get('abc_class', '-') or '-')}"
            )
    else:
        page_1.append("Р СњР ВµРЎвЂљ Р Т‘Р В°Р Р…Р Р…РЎвЂ№РЎвЂ¦ Р С—Р С• SKU.")

    status_labels = {
        "scale": "Р СљР С’Р РЋР РЃР СћР С’Р вЂР ВР В Р С›Р вЂ™Р С’Р СћР В¬ (SCALE)",
        "fix": "Р ВР РЋР СџР В Р С’Р вЂ™Р ВР СћР В¬ (FIX)",
        "watch": "Р СњР С’Р вЂР вЂєР В®Р вЂќР С’Р СћР В¬ (WATCH)",
        "liquidate": "Р вЂєР ВР С™Р вЂ™Р ВР вЂќР ВР В Р С›Р вЂ™Р С’Р СћР В¬ (LIQUIDATE)",
    }

    page_2: List[str] = [
        "# Р РЋР СћР С’Р СћР Р€Р РЋ SKU Р В Р В Р вЂўР РЃР вЂўР СњР ВР Р‡ AI",
        "## Р РЋР СћР С’Р СћР Р€Р РЋ SKU",
        f"- {status_labels['scale']}: {_format_int(len(decision_groups.get('scale', [])))} РІР‚вЂќ {_compact_sku_list([str(x.get('sku') or '').strip() for x in decision_groups.get('scale', []) if isinstance(x, dict)])}",
        f"- {status_labels['fix']}: {_format_int(len(decision_groups.get('fix', [])))} РІР‚вЂќ {_compact_sku_list([str(x.get('sku') or '').strip() for x in decision_groups.get('fix', []) if isinstance(x, dict)])}",
        f"- {status_labels['watch']}: {_format_int(len(decision_groups.get('watch', [])))} РІР‚вЂќ {_compact_sku_list([str(x.get('sku') or '').strip() for x in decision_groups.get('watch', []) if isinstance(x, dict)])}",
        f"- {status_labels['liquidate']}: {_format_int(len(decision_groups.get('liquidate', [])))} РІР‚вЂќ {_compact_sku_list([str(x.get('sku') or '').strip() for x in decision_groups.get('liquidate', []) if isinstance(x, dict)])}",
        "",
        "## Р В Р вЂўР РЃР вЂўР СњР ВР Р‡ AI",
    ]

    sku_monitor_lines: List[str] = ["", "## SKU MONITOR — ФОКУС ДНЯ"]
    rendered_groups = 0
    for group_key, group_title in _watchlist_groups_for_render():
        rows = _watchlist_rows(sku_watchlists, group_key, limit=5)
        if not rows:
            continue
        rendered_groups += 1
        sku_monitor_lines.append(f"### {group_title}")
        for row in rows[:5]:
            sku_monitor_lines.append(f"- {_watchlist_line(row)}")
    if rendered_groups == 0:
        sku_monitor_lines.append("- Нет активных shortlist-групп на текущий день.")
    page_2.extend(sku_monitor_lines)

    def _append_decision_group(page: List[str], group_key: str) -> None:
        page.append(f"### {status_labels[group_key]}")
        rows = decision_groups.get(group_key, [])
        if not isinstance(rows, list) or not rows:
            page.append("- Р СњР ВµРЎвЂљ SKU Р Р† РЎРЊРЎвЂљР С•Р в„– Р С–РЎР‚РЎС“Р С—Р С—Р Вµ.")
            page.append("")
            return
        for row in rows:
            if not isinstance(row, dict):
                continue
            sku = str(row.get("sku") or "n/a")
            action_text = str(row.get("action") or "").strip() or "Р В Р ВµРЎв‚¬Р ВµР Р…Р С‘Р Вµ Р Р…Р Вµ Р В·Р В°Р Т‘Р В°Р Р…Р С•"
            page.append(f"- SKU {sku} РІР‚вЂќ Р С—РЎР‚Р С‘Р В±РЎвЂ№Р В»РЎРЉ {_format_money(row.get('profit', 0.0))} РІР‚вЂќ {action_text.lower()}")
        page.append("")

    _append_decision_group(page_2, "scale")
    _append_decision_group(page_2, "fix")
    _append_decision_group(page_2, "watch")
    _append_decision_group(page_2, "liquidate")

    director_strategy_payload = director_strategy if isinstance(director_strategy, dict) else {}
    director_groups_raw = director_strategy_payload.get("strategy", {})
    if not isinstance(director_groups_raw, dict):
        director_groups_raw = {}
    director_tasks_raw = director_strategy_payload.get("tasks", [])
    if not isinstance(director_tasks_raw, list):
        director_tasks_raw = []

    director_groups: Dict[str, List[str]] = {}
    for key in ("scale", "fix", "watch", "liquidate"):
        raw_rows = director_groups_raw.get(key, [])
        if isinstance(raw_rows, list):
            director_groups[key] = [str(item).strip() for item in raw_rows if str(item).strip()]
        else:
            director_groups[key] = []

    task_by_sku: Dict[str, str] = {}
    for row in director_tasks_raw:
        if not isinstance(row, dict):
            continue
        sku = str(row.get("sku") or "").strip()
        task = str(row.get("task") or "").strip()
        if not sku or not task:
            continue
        task_by_sku.setdefault(sku, task)

    director_default_actions = {
        "scale": "increase_ads",
        "fix": "improve_listing",
        "watch": "monitor",
        "liquidate": "discount_or_remove",
    }

    page_2.extend(["## Р РЋР СћР В Р С’Р СћР вЂўР вЂњР ВР Р‡ AI Р вЂќР ВР В Р вЂўР С™Р СћР С›Р В Р С’"])
    for key in ("scale", "fix", "watch", "liquidate"):
        page_2.append(f"### {status_labels[key]}")
        rows = director_groups.get(key, [])
        if not rows:
            page_2.append("- Р СњР ВµРЎвЂљ SKU Р Р† РЎРЊРЎвЂљР С•Р в„– Р С–РЎР‚РЎС“Р С—Р С—Р Вµ.")
            continue
        default_task = director_default_actions.get(key, "")
        for sku in rows[:10]:
            task = task_by_sku.get(sku) or default_task
            page_2.append(f"- SKU {sku} -> {task}")
    rebalance_rows = [row for row in director_tasks_raw if isinstance(row, dict) and str(row.get("task") or "").strip() == "rebalance_stock"]
    if rebalance_rows:
        page_2.append("### Р вЂєР С›Р вЂњР ВР РЋР СћР ВР В§Р вЂўР РЋР С™Р С’Р Р‡ Р вЂР С’Р вЂєР С’Р СњР РЋР ВР В Р С›Р вЂ™Р С™Р С’")
        for row in rebalance_rows[:10]:
            sku = str(row.get("sku") or "").strip()
            if sku:
                page_2.append(f"- SKU {sku} -> rebalance_stock")

    funnel = cabinet_funnel.get("funnel", {}) if isinstance(cabinet_funnel, dict) else {}
    if not isinstance(funnel, dict):
        funnel = {}
    funnel_status = cabinet_funnel.get("status", {}) if isinstance(cabinet_funnel, dict) else {}
    if not isinstance(funnel_status, dict):
        funnel_status = {}
    funnel_orders_prev_delta = _funnel_delta(funnel_alerts, "orders", "delta_vs_prev_pct")
    funnel_orders_7d_delta = _funnel_delta(funnel_alerts, "orders", "delta_vs_7d_pct")
    funnel_buyouts_prev_delta = _funnel_delta(funnel_alerts, "buyouts", "delta_vs_prev_pct")
    funnel_buyouts_7d_delta = _funnel_delta(funnel_alerts, "buyouts", "delta_vs_7d_pct")
    funnel_alerts_summary = _funnel_alert_summary(funnel_alerts)

    funnel_section_lines = [
        "",
        "## SALES FUNNEL",
        f"- Views: {format_int_or_unknown(funnel.get('views', funnel.get('impressions')))}",
        f"- Add to cart: {format_int_or_unknown(funnel.get('add_to_cart', funnel.get('cart_count')))}",
        f"- Orders: {format_int_or_unknown(funnel.get('orders'))}",
        f"- Buyouts: {format_int_or_unknown(funnel.get('buyouts'))}",
        f"- View → Order: {format_pct_or_unknown(funnel.get('view_to_order_conversion', funnel.get('click_to_order_conversion_pct')))}",
        f"- Cart → Order: {format_pct_or_unknown(funnel.get('cart_to_order', funnel.get('cart_conversion_pct')))}",
        f"- Order → Buyout: {format_pct_or_unknown(funnel.get('buyout_rate', funnel.get('order_to_buyout_conversion_pct')))}",
        f"- Ads spend: {format_money_or_unknown(funnel.get('ads_spend'))}, CPO: {format_money_or_unknown(funnel.get('cpo', funnel.get('CPO')))}",
        f"- Legacy traffic: impressions={format_int_or_unknown(funnel.get('impressions'))}, clicks={format_int_or_unknown(funnel.get('clicks'))}, CTR={format_pct_or_unknown(funnel.get('ctr'))}",
        f"- Δ orders vs yesterday: {format_pct_or_unknown(funnel_orders_prev_delta)}, vs 7d: {format_pct_or_unknown(funnel_orders_7d_delta)}",
        f"- Δ buyouts vs yesterday: {format_pct_or_unknown(funnel_buyouts_prev_delta)}, vs 7d: {format_pct_or_unknown(funnel_buyouts_7d_delta)}",
        f"- Статусы: traffic={str(funnel_status.get('traffic') or 'unknown')}, conversion={str(funnel_status.get('conversion') or 'unknown')}, buyout_stage={str(funnel_status.get('buyout_stage') or 'unknown')}",
        f"- Alert summary: {funnel_alerts_summary}",
    ]
    page_1.extend(funnel_section_lines)

    page_1.extend(["", "## AI Р вЂ™Р В«Р вЂ™Р С›Р вЂќ Р вЂќР СњР Р‡", str(data.get("ai_day_conclusion") or "")])
    page_1.extend(["", "## Р С™Р В Р С’Р СћР С™Р ВР вЂў Р В Р вЂўР С™Р С›Р СљР вЂўР СњР вЂќР С’Р В¦Р ВР В"])
    page_1.extend(f"- {item}" for item in data.get("short_recommendations", []))

    memory_summary = facts.get("decision_memory_summary", {}) if isinstance(facts, dict) else {}
    important_warnings = _important_warnings(warnings_collector.export_warnings())

    page_3: List[str] = [
        "# Р С›Р вЂР Р€Р В§Р вЂўР СњР ВР вЂў AI Р В Р С™Р С’Р В§Р вЂўР РЋР СћР вЂ™Р С› Р вЂќР С’Р СњР СњР В«Р Тђ",
        "## Р СџР С’Р СљР Р‡Р СћР В¬ Р В Р вЂўР РЃР вЂўР СњР ВР в„ў AI",
        "Р СџР С•Р С”Р В°Р В·Р В°РЎвЂљР ВµР В»РЎРЉ | Р вЂ”Р Р…Р В°РЎвЂЎР ВµР Р…Р С‘Р Вµ",
        f"Р вЂ™РЎРѓР ВµР С–Р С• РЎР‚Р ВµРЎв‚¬Р ВµР Р…Р С‘Р в„– | {_format_int(memory_summary.get('total_logged', 0))}",
        f"Р С›Р В¶Р С‘Р Т‘Р В°РЎР‹РЎвЂљ Р С•РЎвЂ Р ВµР Р…Р С”Р С‘ | {_format_int(memory_summary.get('pending', 0))}",
        f"Р Р€РЎРѓР С—Р ВµРЎв‚¬Р Р…РЎвЂ№РЎвЂ¦ | {_format_int(memory_summary.get('success', 0))}",
        f"Р СњР ВµРЎС“Р Т‘Р В°РЎвЂЎР Р…РЎвЂ№РЎвЂ¦ | {_format_int(memory_summary.get('fail', 0))}",
        f"Р СњР ВµР в„–РЎвЂљРЎР‚Р В°Р В»РЎРЉР Р…РЎвЂ№РЎвЂ¦ | {_format_int(memory_summary.get('neutral', 0))}",
    ]
    if int(data.get("outcomes_evaluated", 0) or 0) > 0:
        outcome_results = outcomes_payload.get("results", {}) if isinstance(outcomes_payload, dict) else {}
        page_3.append(
            f"- AI Р С•РЎвЂ Р ВµР Р…Р С‘Р В» {_format_int(data.get('outcomes_evaluated', 0))} Р С—РЎР‚Р С•РЎв‚¬Р В»РЎвЂ№РЎвЂ¦ РЎР‚Р ВµРЎв‚¬Р ВµР Р…Р С‘Р в„–: "
            f"{_format_int(outcome_results.get('success', 0))} РЎС“РЎРѓР С—Р ВµРЎв‚¬Р Р…РЎвЂ№РЎвЂ¦, "
            f"{_format_int(outcome_results.get('neutral', 0))} Р Р…Р ВµР в„–РЎвЂљРЎР‚Р В°Р В»РЎРЉР Р…РЎвЂ№РЎвЂ¦, "
            f"{_format_int(outcome_results.get('fail', 0))} Р Р…Р ВµРЎС“Р Т‘Р В°РЎвЂЎР Р…РЎвЂ№РЎвЂ¦."
        )

    page_3.extend(
        [
            "",
            "## Р С™Р С’Р В§Р вЂўР РЋР СћР вЂ™Р С› Р вЂќР С’Р СњР СњР В«Р Тђ",
            "Р СџР С•Р С”Р В°Р В·Р В°РЎвЂљР ВµР В»РЎРЉ | Р вЂ”Р Р…Р В°РЎвЂЎР ВµР Р…Р С‘Р Вµ",
            f"Р вЂ™Р В°Р В»Р С‘Р Т‘Р Р…РЎвЂ№Р Вµ SKU | {_format_int(data_quality.get('valid_sku_count', 0))}",
            f"Р СњР ВµР Р†Р В°Р В»Р С‘Р Т‘Р Р…РЎвЂ№Р Вµ РЎРѓРЎвЂљРЎР‚Р С•Р С”Р С‘ | {_format_int(data_quality.get('invalid_sku_rows', 0))}",
            f"Р В Р В°РЎРѓРЎвЂ¦Р С•Р Т‘РЎвЂ№ Р В±Р ВµР В· SKU | {'Р вЂќР В°' if bool(data_quality.get('unassigned_costs_present', False)) else 'Р СњР ВµРЎвЂљ'}",
        ]
    )
    if bool(data_quality.get("unassigned_costs_present", False)):
        page_3.append("- Р В§Р В°РЎРѓРЎвЂљРЎРЉ РЎР‚Р В°РЎРѓРЎвЂ¦Р С•Р Т‘Р С•Р Р† Р Р…Р Вµ Р С—РЎР‚Р С‘Р Р†РЎРЏР В·Р В°Р Р…Р В° Р С” SKU Р С‘ РЎС“РЎвЂЎРЎвЂљР ВµР Р…Р В° Р С•РЎвЂљР Т‘Р ВµР В»РЎРЉР Р…Р С•.")

    page_3.extend(
        [
            "",
            "## Р С™Р С’Р В§Р вЂўР РЋР СћР вЂ™Р С› Р В¤Р ВР СњР С’Р СњР РЋР С›Р вЂ™Р С›Р в„ў Р С’Р СћР В Р ВР вЂР Р€Р В¦Р ВР В",
            "Р СџР С•Р С”Р В°Р В·Р В°РЎвЂљР ВµР В»РЎРЉ | Р вЂ”Р Р…Р В°РЎвЂЎР ВµР Р…Р С‘Р Вµ",
            f"Р вЂ™Р В°Р В»Р С‘Р Т‘Р Р…РЎвЂ№РЎвЂ¦ SKU | {_format_int(data_quality.get('valid_sku_count', 0))}",
            f"Р СњР ВµРЎР‚Р В°РЎРѓР С—РЎР‚Р ВµР Т‘Р ВµР В»Р ВµР Р…Р Р…РЎвЂ№РЎвЂ¦ РЎРѓРЎвЂљРЎР‚Р С•Р С” | {_format_int(data_quality.get('unassigned_rows', unassigned_costs.get('rows', 0)))}",
            f"Р СњР ВµРЎР‚Р В°РЎРѓР С—РЎР‚Р ВµР Т‘Р ВµР В»Р ВµР Р…Р Р…РЎвЂ№Р Вµ РЎР‚Р В°РЎРѓРЎвЂ¦Р С•Р Т‘РЎвЂ№ | {_format_money(unassigned_costs.get('profit', 0.0))}",
            f"Р СџР С•Р В»Р Р…Р С•РЎвЂљР В° РЎвЂћР С‘Р Р…Р В°Р Р…РЎРѓР С•Р Р†РЎвЂ№РЎвЂ¦ Р Т‘Р В°Р Р…Р Р…РЎвЂ№РЎвЂ¦ | {_format_pct(data.get('financial_completeness_pct', 0.0))}",
            f"Р В¤Р С‘Р Р…Р В°Р Р…РЎРѓР С•Р Р†РЎвЂ№Р в„– Р С”Р С•Р Р…РЎвЂљРЎС“РЎР‚ РЎвЂћР С‘Р Р…Р В°Р В»РЎРЉР Р…РЎвЂ№Р в„– | {'Р СњР ВµРЎвЂљ' if bool(data.get('financial_partial', False)) else 'Р вЂќР В°'}",
            f"Р вЂќР С•РЎРѓРЎвЂљР С•Р Р†Р ВµРЎР‚Р Р…Р С•РЎРѓРЎвЂљРЎРЉ AI-РЎР‚Р ВµРЎв‚¬Р ВµР Р…Р С‘Р в„– | {_confidence_ru(str(data_quality.get('ai_decision_reliability', 'medium')))}",
        ]
    )

    page_3.extend(["", "## Р СџР В Р вЂўР вЂќР Р€Р СџР В Р вЂўР вЂ“Р вЂќР вЂўР СњР ВР Р‡ Р РЋР ВР РЋР СћР вЂўР СљР В«"])
    if important_warnings:
        for item in important_warnings:
            code = str(item.get("code") or "")
            message = _warning_message_ru(code, str(item.get("message") or ""))
            page_3.append(f"- {message}")
    else:
        page_3.append("- Р вЂ™Р В°Р В¶Р Р…РЎвЂ№РЎвЂ¦ Р С—РЎР‚Р ВµР Т‘РЎС“Р С—РЎР‚Р ВµР В¶Р Т‘Р ВµР Р…Р С‘Р в„– Р Р…Р ВµРЎвЂљ.")

    report_pages: List[List[str]] = [page_1, page_2, page_3]
    pdf_lines: List[str] = []
    for idx, page in enumerate(report_pages):
        if idx > 0:
            pdf_lines.append("\f")
        pdf_lines.extend(page)

    font_info = write_text_pdf(os.path.join(out_dir, "report.pdf"), pdf_lines)
    job["pdf_font"] = {
        "family": font_info.get("family", ""),
        "regular": font_info.get("regular", ""),
        "bold": font_info.get("bold", ""),
    }
    report_meta: Dict[str, Any] = {
        "pdf_path": os.path.join(out_dir, "report.pdf"),
        "font": job["pdf_font"],
        "pages": int(str(font_info.get("pages", "1"))),
        "daily_commerce_kpi": {
            "daily_orders_count": _int_or_none(orders_count_value),
            "daily_orders_amount": _round_or_none(orders_amount_value),
            "daily_buyouts_count": _int_or_none(buyouts_count_value),
            "daily_buyouts_amount": _round_or_none(buyouts_amount_value),
            "avg_check": _round_or_none(avg_check_value),
            "views": _int_or_none(funnel.get("views", funnel.get("impressions"))),
            "add_to_cart": _int_or_none(funnel.get("add_to_cart", funnel.get("cart_count"))),
            "view_to_order_conversion": _round_or_none(
                funnel.get("view_to_order_conversion", funnel.get("click_to_order_conversion_pct"))
            ),
            "cart_rate": _round_or_none(funnel.get("cart_rate", funnel.get("cart_conversion_pct"))),
            "cart_to_order": _round_or_none(funnel.get("cart_to_order")),
            "buyout_rate": _round_or_none(funnel.get("buyout_rate", funnel.get("order_to_buyout_conversion_pct"))),
            "cpo": _round_or_none(funnel.get("cpo", funnel.get("CPO"))),
            "data_source_orders": str(daily_kpi.get("data_source_orders") or _SOURCE_UNKNOWN),
            "data_source_orders_count": str(daily_kpi.get("data_source_orders_count") or daily_kpi.get("data_source_orders") or _SOURCE_UNKNOWN),
            "data_source_orders_amount": str(daily_kpi.get("data_source_orders_amount") or _SOURCE_UNKNOWN),
            "data_source_buyouts": str(daily_kpi.get("data_source_buyouts") or _SOURCE_UNKNOWN),
            "data_source_buyouts_count": str(daily_kpi.get("data_source_buyouts_count") or daily_kpi.get("data_source_buyouts") or _SOURCE_UNKNOWN),
            "data_source_buyouts_amount": str(daily_kpi.get("data_source_buyouts_amount") or _SOURCE_UNKNOWN),
            "orders_count_confirmed": bool(daily_kpi.get("orders_count_confirmed", False)),
            "buyouts_count_confirmed": bool(daily_kpi.get("buyouts_count_confirmed", False)),
            "display": {
                "daily_orders_count": format_int_or_unknown(orders_count_value),
                "daily_orders_amount": format_money_or_unknown(orders_amount_value),
                "daily_buyouts_count": format_int_or_unknown(buyouts_count_value),
                "daily_buyouts_amount": format_money_or_unknown(buyouts_amount_value),
                "avg_check": format_money_or_unknown(avg_check_value),
            },
        },
        "daily_financial_kpi": {
            "revenue": _round_or_none(revenue_value),
            "cost_price": _round_or_none(data.get("cost_price_total")),
            "wb_commission": _round_or_none(data.get("wb_commission")),
            "ads_spend": _round_or_none(data.get("ads_spend_total")),
            "ads_impressions": int(data.get("ads_impressions", 0) or 0),
            "ads_clicks": int(data.get("ads_clicks", 0) or 0),
            "ads_orders": int(data.get("ads_orders", 0) or 0),
            "ads_rows": int(data.get("ads_rows_count", 0) or 0),
            "ads_source_file": str(data.get("ads_source_file") or ""),
            "ads_loaded_from_file": bool(data.get("ads_loaded_from_file", False)),
            "ads_attribution_quality": str(data.get("ads_attribution_quality") or "unknown"),
            "gross_profit": _round_or_none(data.get("gross_profit_total")),
            "net_profit": _round_or_none(net_profit_value),
            "margin_pct": _round_or_none(margin_pct_value),
            "profitability_pct": _round_or_none(profitability_pct_value),
            "financial_completeness_pct": round(float(data.get("financial_completeness_pct", 0.0) or 0.0), 2),
            "financial_partial": bool(data.get("financial_partial", False)),
            "display": {
                "revenue": format_money_or_unknown(revenue_value, decimals=0),
                "net_profit": format_money_or_unknown(net_profit_value, decimals=0),
                "margin_pct": format_pct_or_unknown(margin_pct_value),
                "profitability_pct": format_pct_or_unknown(profitability_pct_value),
            },
        },
        "event_date_model": event_date_model if isinstance(event_date_model, dict) else {},
        "daily_status_matrix": daily_status_matrix if isinstance(daily_status_matrix, dict) else {},
        "order_kpi": order_kpi if isinstance(order_kpi, dict) else {},
        "buyout_kpi": buyout_kpi if isinstance(buyout_kpi, dict) else {},
        "event_ledger_preview": (event_ledger.get("events", [])[:3] if isinstance(event_ledger.get("events"), list) else []),
        "funnel_snapshot": cabinet_funnel if isinstance(cabinet_funnel, dict) else {},
        "sku_watchlists_preview": {
            key: _watchlist_rows(sku_watchlists, key, limit=5)
            for key, _ in _watchlist_groups_for_render()
        },
        "funnel_section_preview": funnel_section_lines,
        "sku_monitor_section_preview": sku_monitor_lines,
    }
    report_meta["page_previews"] = [{"page": page_idx + 1, "lines": page[:30]} for page_idx, page in enumerate(report_pages)]

    write_report_meta(out_dir=out_dir, report_meta=report_meta)
    data.update({"job": job, "report_meta": report_meta})
    return data

