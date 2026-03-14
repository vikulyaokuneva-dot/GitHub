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
    delta_text = f", О”7d={format_pct_or_unknown(main_delta)}" if main_delta is not None else ""
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
    sales_funnel_summary = data.get("sales_funnel_summary", {})
    if not isinstance(sales_funnel_summary, dict):
        sales_funnel_summary = (
            cabinet_funnel.get("sku_diagnostics", {}).get("summary", {})
            if isinstance(cabinet_funnel.get("sku_diagnostics"), dict)
            else {}
        )
    if not isinstance(sales_funnel_summary, dict):
        sales_funnel_summary = {}
    report_guardrails = data.get("report_guardrails", {})
    if not isinstance(report_guardrails, dict):
        report_guardrails = {}
    sku_attribution_status = str(
        data_quality.get("sku_attribution_status", report_guardrails.get("sku_attribution_status", "ok")) or "ok"
    ).strip().lower()
    financial_finality_status = str(
        data_quality.get("financial_finality_status", report_guardrails.get("financial_finality_status", "unavailable"))
        or "unavailable"
    ).strip().lower()
    territorial_analysis_enabled = bool(
        data_quality.get(
            "territorial_analysis_enabled",
            report_guardrails.get("territorial_analysis_enabled", sku_attribution_status != "broken"),
        )
    )
    profit_contribution_enabled = bool(
        data_quality.get(
            "profit_contribution_enabled",
            report_guardrails.get("profit_contribution_enabled", sku_attribution_status != "broken"),
        )
    )
    ads_analysis_enabled = bool(data_quality.get("ads_analysis_enabled", report_guardrails.get("ads_analysis_enabled", True)))
    sku_level_analytics_enabled = bool(
        territorial_analysis_enabled
        and profit_contribution_enabled
        and int(data_quality.get("valid_sku_count", 0) or 0) > 0
    )

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
        "# WB AI Agent вЂ” РћС‚С‡РµС‚ РїРѕ РєР°Р±РёРЅРµС‚Сѓ",
        f"### РљР°Р±РёРЅРµС‚: {str(data.get('seller_id') or '')}",
        f"### Р”Р°С‚Р° РѕС‚С‡РµС‚Р°: {str(data.get('run_date') or '')}",
        f"### РЈРІРµСЂРµРЅРЅРѕСЃС‚СЊ РґР°РЅРЅС‹С…: {_confidence_ru(str(data.get('confidence') or 'low'))}",
        "",
        "## COMMERCE KPI",
        "РџРѕРєР°Р·Р°С‚РµР»СЊ | Р—РЅР°С‡РµРЅРёРµ",
        f"РљРѕР»РёС‡РµСЃС‚РІРѕ Р·Р°РєР°Р·РѕРІ | {format_int_or_unknown(orders_count_value)}",
        f"РЎСѓРјРјР° Р·Р°РєР°Р·РѕРІ (РјРёРЅСѓСЃ РєРѕРјРёСЃСЃРёСЏ WB) | {format_money_or_unknown(orders_amount_value)}",
        f"Р’С‹РєСѓРїС‹ | {format_int_or_unknown(buyouts_count_value)}",
        f"Рљ РїРµСЂРµС‡РёСЃР»РµРЅРёСЋ РїРѕ РІС‹РєСѓРїР°Рј | {format_money_or_unknown(buyouts_amount_value)}",
        f"РЎСЂРµРґРЅРёР№ С‡РµРє РїРѕ РІС‹РєСѓРїСѓ | {format_money_or_unknown(avg_check_value)}",
        f"РСЃС‚РѕС‡РЅРёРє orders_count | {str(daily_kpi.get('data_source_orders_count') or daily_kpi.get('data_source_orders') or _SOURCE_UNKNOWN)}",
        f"РСЃС‚РѕС‡РЅРёРє orders_amount | {str(daily_kpi.get('data_source_orders_amount') or _SOURCE_UNKNOWN)}",
        f"РСЃС‚РѕС‡РЅРёРє buyouts_count | {str(daily_kpi.get('data_source_buyouts_count') or daily_kpi.get('data_source_buyouts') or _SOURCE_UNKNOWN)}",
        f"РСЃС‚РѕС‡РЅРёРє buyouts_amount | {str(daily_kpi.get('data_source_buyouts_amount') or _SOURCE_UNKNOWN)}",
        f"Orders count РїРѕРґС‚РІРµСЂР¶РґРµРЅ | {'Р”Р°' if bool(daily_kpi.get('orders_count_confirmed', False)) else 'РќРµС‚'}",
        f"Buyouts count РїРѕРґС‚РІРµСЂР¶РґРµРЅ | {'Р”Р°' if bool(daily_kpi.get('buyouts_count_confirmed', False)) else 'РќРµС‚'}",
        f"Orders amount РїРѕРґС‚РІРµСЂР¶РґРµРЅ | {'Р”Р°' if bool(daily_kpi.get('orders_amount_confirmed', False)) else 'РќРµС‚'}",
        f"Buyouts amount РїРѕРґС‚РІРµСЂР¶РґРµРЅ | {'Р”Р°' if bool(daily_kpi.get('buyouts_amount_confirmed', False)) else 'РќРµС‚'}",
        f"Event status matrix | orders={str(daily_status_matrix.get('orders') or 'unknown')}, buyouts={str(daily_status_matrix.get('buyouts') or 'unknown')}, financials={str(daily_status_matrix.get('financials') or 'unknown')}, ads={str(daily_status_matrix.get('ads') or 'unknown')}",
        f"РљРѕР»РёС‡РµСЃС‚РІРѕ SKU | {_format_int(len(sku_metrics))}",
        f"Р Р°СЃС…РѕРґС‹ РЅР° СЂРµРєР»Р°РјСѓ | {_format_money(data.get('ads_spend_total', 0.0))}",
        "",
        "## FINANCIAL KPI",
        "РџРѕРєР°Р·Р°С‚РµР»СЊ | Р—РЅР°С‡РµРЅРёРµ",
        f"Р’С‹СЂСѓС‡РєР° (РїРѕРґС‚РІРµСЂР¶РґРµРЅРЅР°СЏ С„РёРЅР°РЅСЃРѕРІС‹РјРё СЃС‚СЂРѕРєР°РјРё) | {format_money_or_unknown(revenue_value, decimals=0)}",
        f"РЎРµР±РµСЃС‚РѕРёРјРѕСЃС‚СЊ | {_format_money(data.get('cost_price_total', 0.0))}",
        f"РљРѕРјРёСЃСЃРёСЏ WB | {_format_money(data.get('wb_commission', 0.0))}",
        f"Р›РѕРіРёСЃС‚РёРєР° | {_format_money(data.get('logistics_total', 0.0))}",
        f"РҐСЂР°РЅРµРЅРёРµ | {_format_money(data.get('storage_total', 0.0))}",
        f"РЁС‚СЂР°С„С‹ | {_format_money(data.get('penalties_total', 0.0))}",
        f"РЈРґРµСЂР¶Р°РЅРёСЏ | {_format_money(data.get('deductions_total', 0.0))}",
        f"Р РµРєР»Р°РјР° | {_format_money(data.get('ads_spend_total', 0.0))}",
        f"Р’Р°Р»РѕРІР°СЏ РїСЂРёР±С‹Р»СЊ | {_format_money(data.get('gross_profit_total', 0.0))}",
        f"Р§РёСЃС‚Р°СЏ РїСЂРёР±С‹Р»СЊ | {format_money_or_unknown(net_profit_value, decimals=0)}",
        f"РњР°СЂР¶Р° % | {format_pct_or_unknown(margin_pct_value)}",
        f"Р РµРЅС‚Р°Р±РµР»СЊРЅРѕСЃС‚СЊ % | {format_pct_or_unknown(profitability_pct_value)}",
        f"РџРѕР»РЅРѕС‚Р° С„РёРЅР°РЅСЃРѕРІС‹С… РґР°РЅРЅС‹С… | {_format_pct(data.get('financial_completeness_pct', 0.0))}",
        f"Financial contour status | {financial_finality_status}",
        "",
        "## Р Р•РљР›РђРњРђ",
        "РџРѕРєР°Р·Р°С‚РµР»СЊ | Р—РЅР°С‡РµРЅРёРµ",
        f"РџРѕРєР°Р·С‹ | {_format_int(data.get('ads_impressions', 0))}",
        f"РљР»РёРєРё | {_format_int(data.get('ads_clicks', 0))}",
        f"CTR | {_format_pct(data.get('ads_ctr', 0.0))}",
        f"Р Р°СЃС…РѕРґ | {_format_money(data.get('ads_spend_total', 0.0))}",
        f"Р—Р°РєР°Р·С‹ | {_format_int(data.get('ads_orders', 0))}",
        f"Р’С‹СЂСѓС‡РєР° | {_format_money(data.get('ads_revenue', 0.0))}",
        f"ACOS | {_format_pct(data.get('ads_acos', 0.0))}",
        f"ROMI | {_format_pct(data.get('ads_romi', 0.0))}",
        f"Р РµРєР»Р°РјР° СѓС‡С‚РµРЅР° РІ РїСЂРёР±С‹Р»Рё | {'Р”Р°' if _safe_float(data.get('ads_spend_total', 0.0)) > 0 else 'РќРµС‚'}",
        f"РђС‚СЂРёР±СѓС†РёСЏ СЂРµРєР»Р°РјС‹ | {str(data.get('ads_attribution_quality') or 'unknown')}",
        f"РСЃС‚РѕС‡РЅРёРє СЂРµРєР»Р°РјС‹ | {str(data.get('ads_source_file') or ('local_file' if bool(data.get('ads_loaded_from_file', False)) else 'api_or_missing'))}",
        "",
        "## РљР›Р®Р§Р•Р’Р«Р• Р’Р«Р’РћР”Р«",
    ]
    page_1.extend(f"- {line}" for line in data.get("key_insights", []))
    if financial_finality_status != "final":
        page_1.extend(
            [
                "",
                "- Financial metrics are provisional and not interpreted as final day result.",
            ]
        )
    if sku_attribution_status == "broken":
        page_1.extend(
            [
                "",
                "- Technical warning: SKU attribution is broken; SKU-level conclusions are suppressed.",
            ]
        )
    if not ads_analysis_enabled:
        page_1.extend(
            [
                "",
                "- Ads interpretation is suppressed because ads source data is missing.",
            ]
        )

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
    weighted_localization_share = _safe_float(territorial_summary.get("weighted_average_localization_share", 0.0))
    skus_below_60_localization = int(territorial_summary.get("skus_below_60_localization", 0) or 0)
    aggregate_estimated_irp_penalty_total = _safe_float(territorial_summary.get("aggregate_estimated_irp_penalty_total", 0.0))
    top_weak_localization_rows = territorial_summary.get("top_weak_localization_skus", [])
    if not isinstance(top_weak_localization_rows, list):
        top_weak_localization_rows = []
    top_irp_penalty_rows = territorial_summary.get("top_irp_penalty_skus", [])
    if not isinstance(top_irp_penalty_rows, list):
        top_irp_penalty_rows = []
    territorial_signals = territorial_distribution.get("signals", []) if isinstance(territorial_distribution, dict) else []
    if not isinstance(territorial_signals, list):
        territorial_signals = []
    territorial_analysis_mode = str(
        territorial_summary.get("analysis_mode", territorial_distribution.get("analysis_mode", "disabled"))
        if isinstance(territorial_distribution, dict)
        else "disabled"
    ).strip().lower()
    territorial_recommendation_status = str(
        territorial_summary.get("recommendation_status", territorial_distribution.get("recommendation_status", "blocked_by_data"))
        if isinstance(territorial_distribution, dict)
        else "blocked_by_data"
    ).strip().lower()
    territorial_suppressed_due_to_data_quality = bool(
        territorial_summary.get("suppressed_due_to_data_quality", territorial_distribution.get("suppressed_due_to_data_quality", False))
        if isinstance(territorial_distribution, dict)
        else False
    )
    territorial_actionable = bool(
        territorial_analysis_enabled
        and territorial_analysis_mode == "full"
        and territorial_recommendation_status == "actionable"
        and not territorial_suppressed_due_to_data_quality
    )

    top_weak_lines: List[str] = []
    for row in top_weak_localization_rows[:3]:
        if not isinstance(row, dict):
            continue
        sku_code = str(row.get("sku") or "").strip()
        loc_share = _safe_float_local(row.get("localization_share"))
        if sku_code:
            if loc_share is None:
                top_weak_lines.append(sku_code)
            else:
                top_weak_lines.append(f"{sku_code} ({format_pct_or_unknown(loc_share)})")

    top_irp_lines: List[str] = []
    for row in top_irp_penalty_rows[:3]:
        if not isinstance(row, dict):
            continue
        sku_code = str(row.get("sku") or "").strip()
        penalty_value = _safe_float(row.get("estimated_irp_penalty_total", 0.0))
        if sku_code:
            top_irp_lines.append(f"{sku_code} ({_format_money(penalty_value)})")

    page_1.extend(["", "## РўР•Р Р РРўРћР РРђР›Р¬РќРћР• Р РђРЎРџР Р•Р”Р•Р›Р•РќРР•"])
    if (not territorial_actionable) or analyzed_with_ktr <= 0:
        page_1.append("- РќРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РґР°РЅРЅС‹С… РґР»СЏ Р°РЅР°Р»РёР·Р° С‚РµСЂСЂРёС‚РѕСЂРёР°Р»СЊРЅРѕРіРѕ СЂР°СЃРїСЂРµРґРµР»РµРЅРёСЏ")
    else:
        page_1.append(f"- РЎСЂРµРґРЅРёР№ РљРўР  РїРѕ РєР°Р±РёРЅРµС‚Сѓ: {_format_ktr(territorial_summary.get('avg_ktr', 0.0))}")
        page_1.append(f"- РҐРѕСЂРѕС€Рѕ СЂР°СЃРїСЂРµРґРµР»РµРЅС‹: {_format_int(balanced_count)} SKU")
        page_1.append(f"- Р•СЃС‚СЊ РїРµСЂРµРєРѕСЃ: {_format_int(moderate_count + misallocated_count)} SKU")
        if top_misaligned_confident:
            page_1.append(f"- РќР°РёР±РѕР»СЊС€РёР№ РїРµСЂРµРєРѕСЃ (confidence medium/high): {top_misaligned_text}")
        elif top_misaligned_pdf:
            page_1.append("- РќР°РёР±РѕР»СЊС€РёР№ РїРµСЂРµРєРѕСЃ: С‚РѕР»СЊРєРѕ low-confidence SKU (total_buys < 3)")
        else:
            page_1.append("- РќР°РёР±РѕР»СЊС€РёР№ РїРµСЂРµРєРѕСЃ: вЂ”")
        if excluded_low_conf_count > 0:
            page_1.append(f"- РСЃРєР»СЋС‡РµРЅРѕ low-confidence SKU РёР· С‚РѕРїР°: {_format_int(excluded_low_conf_count)}")
        if low_conf_ktr_count > 0:
            page_1.append(f"- Low-confidence KTR (total_buys < 3): {_format_int(low_conf_ktr_count)} SKU, РёРЅС‚РµСЂРїСЂРµС‚РёСЂРѕРІР°С‚СЊ РѕСЃС‚РѕСЂРѕР¶РЅРѕ")

    logistics_top_critical = logistics_summary.get("top_critical_skus", []) if isinstance(logistics_summary, dict) else []

    page_1.extend(["", "## РўРµСЂСЂРёС‚РѕСЂРёР°Р»СЊРЅРѕРµ СЂР°СЃРїСЂРµРґРµР»РµРЅРёРµ Рё Р»РѕРіРёСЃС‚РёС‡РµСЃРєРёР№ СЂРёСЃРє"])
    if (not territorial_actionable) or analyzed_with_ktr <= 0:
        page_1.append("- РќРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РґР°РЅРЅС‹С… РґР»СЏ РѕС†РµРЅРєРё Р»РѕРєР°Р»РёР·Р°С†РёРё Рё IRP-СЂРёСЃРєР°.")
    else:
        page_1.append(f"- Р’Р·РІРµС€РµРЅРЅР°СЏ Р»РѕРєР°Р»РёР·Р°С†РёСЏ РїРѕСЂС‚С„РµР»СЏ: {format_pct_or_unknown(weighted_localization_share)}")
        page_1.append(f"- SKU РЅРёР¶Рµ РїРѕСЂРѕРіР° 60% Р»РѕРєР°Р»РёР·Р°С†РёРё: {_format_int(skus_below_60_localization)}")
        page_1.append(f"- РћС†РµРЅРѕС‡РЅС‹Р№ СЃСѓРјРјР°СЂРЅС‹Р№ IRP exposure: {_format_money(aggregate_estimated_irp_penalty_total)}")
        if top_weak_lines:
            page_1.append("- РўРѕРї SKU СЃ С…СѓРґС€РµР№ Р»РѕРєР°Р»РёР·Р°С†РёРµР№: " + ", ".join(top_weak_lines))
        else:
            page_1.append("- РўРѕРї SKU СЃ С…СѓРґС€РµР№ Р»РѕРєР°Р»РёР·Р°С†РёРµР№: вЂ”")
        if top_irp_lines:
            page_1.append("- РўРѕРї SKU РїРѕ РѕС†РµРЅРѕС‡РЅРѕРјСѓ IRP-СЂРёСЃРєСѓ: " + ", ".join(top_irp_lines))
        else:
            page_1.append("- РўРѕРї SKU РїРѕ РѕС†РµРЅРѕС‡РЅРѕРјСѓ IRP-СЂРёСЃРєСѓ: вЂ”")

        recommendation_lines: List[str] = []
        for signal in territorial_signals:
            if not isinstance(signal, dict):
                continue
            recommendation = str(signal.get("recommendation") or "").strip()
            if not recommendation:
                continue
            if recommendation not in recommendation_lines:
                recommendation_lines.append(recommendation)
            if len(recommendation_lines) >= 2:
                break
        if recommendation_lines:
            page_1.append("- Р РµРєРѕРјРµРЅРґР°С†РёРё: " + "; ".join(recommendation_lines))
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
            page_1.append("- Top critical SKU: вЂ”")

    profit_rows = _top_profit_rows(
        profit_contribution=profit_contribution if isinstance(profit_contribution, dict) else {},
        sku_metrics=sku_metrics,
        abc_rows=abc_rows,
    )
    page_1.extend(["", "## РўРћРџ SKU РџРћ РџР РР‘Р«Р›Р", "SKU | РџСЂРёР±С‹Р»СЊ | Р”РѕР»СЏ РїСЂРёР±С‹Р»Рё (%) | РњР°СЂР¶Р° (%) | РљР»Р°СЃСЃ РїСЂРёР±С‹Р»Рё | ABC"])
    if not sku_level_analytics_enabled:
        page_1.append("SKU-level analytics temporarily unavailable due to attribution quality issues.")
    elif profit_rows:
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
        page_1.append("РќРµС‚ РґР°РЅРЅС‹С… РїРѕ SKU.")

    status_labels = {
        "scale": "РњРђРЎРЁРўРђР‘РР РћР’РђРўР¬ (SCALE)",
        "fix": "РРЎРџР РђР’РРўР¬ (FIX)",
        "watch": "РќРђР‘Р›Р®Р”РђРўР¬ (WATCH)",
        "liquidate": "Р›РРљР’РР”РР РћР’РђРўР¬ (LIQUIDATE)",
    }

    page_2: List[str] = [
        "# РЎРўРђРўРЈРЎ SKU Р Р Р•РЁР•РќРРЇ AI",
        "## РЎРўРђРўРЈРЎ SKU",
        f"- {status_labels['scale']}: {_format_int(len(decision_groups.get('scale', [])))} вЂ” {_compact_sku_list([str(x.get('sku') or '').strip() for x in decision_groups.get('scale', []) if isinstance(x, dict)])}",
        f"- {status_labels['fix']}: {_format_int(len(decision_groups.get('fix', [])))} вЂ” {_compact_sku_list([str(x.get('sku') or '').strip() for x in decision_groups.get('fix', []) if isinstance(x, dict)])}",
        f"- {status_labels['watch']}: {_format_int(len(decision_groups.get('watch', [])))} вЂ” {_compact_sku_list([str(x.get('sku') or '').strip() for x in decision_groups.get('watch', []) if isinstance(x, dict)])}",
        f"- {status_labels['liquidate']}: {_format_int(len(decision_groups.get('liquidate', [])))} вЂ” {_compact_sku_list([str(x.get('sku') or '').strip() for x in decision_groups.get('liquidate', []) if isinstance(x, dict)])}",
        "",
        "## Р Р•РЁР•РќРРЇ AI",
    ]

    if not sku_level_analytics_enabled:
        page_2.extend(["", "SKU-level analytics temporarily unavailable due to attribution quality issues."])

    sku_monitor_lines: List[str] = ["", "## SKU MONITOR вЂ” Р¤РћРљРЈРЎ Р”РќРЇ"]
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
        sku_monitor_lines.append("- РќРµС‚ Р°РєС‚РёРІРЅС‹С… shortlist-РіСЂСѓРїРї РЅР° С‚РµРєСѓС‰РёР№ РґРµРЅСЊ.")
    page_2.extend(sku_monitor_lines)

    def _append_decision_group(page: List[str], group_key: str) -> None:
        page.append(f"### {status_labels[group_key]}")
        rows = decision_groups.get(group_key, [])
        if not isinstance(rows, list) or not rows:
            page.append("- РќРµС‚ SKU РІ СЌС‚РѕР№ РіСЂСѓРїРїРµ.")
            page.append("")
            return
        for row in rows:
            if not isinstance(row, dict):
                continue
            sku = str(row.get("sku") or "n/a")
            action_text = str(row.get("action") or "").strip() or "Р РµС€РµРЅРёРµ РЅРµ Р·Р°РґР°РЅРѕ"
            funnel_reason = str(row.get("funnel_issue_reason") or "").strip()
            funnel_suffix = f" | funnel: {funnel_reason}" if funnel_reason else ""
            page.append(f"- SKU {sku} вЂ” РїСЂРёР±С‹Р»СЊ {_format_money(row.get('profit', 0.0))} вЂ” {action_text.lower()}{funnel_suffix}")
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

    page_2.extend(["## РЎРўР РђРўР•Р“РРЇ AI Р”РР Р•РљРўРћР Рђ"])
    for key in ("scale", "fix", "watch", "liquidate"):
        page_2.append(f"### {status_labels[key]}")
        rows = director_groups.get(key, [])
        if not rows:
            page_2.append("- РќРµС‚ SKU РІ СЌС‚РѕР№ РіСЂСѓРїРїРµ.")
            continue
        default_task = director_default_actions.get(key, "")
        for sku in rows[:10]:
            task = task_by_sku.get(sku) or default_task
            page_2.append(f"- SKU {sku} -> {task}")
    rebalance_rows = [row for row in director_tasks_raw if isinstance(row, dict) and str(row.get("task") or "").strip() == "rebalance_stock"]
    if rebalance_rows:
        page_2.append("### Р›РћР“РРЎРўРР§Р•РЎРљРђРЇ Р‘РђР›РђРќРЎРР РћР’РљРђ")
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
    funnel_total_skus = int(sales_funnel_summary.get("sku_count", 0) or 0)
    funnel_analyzed_skus = int(sales_funnel_summary.get("analyzed_sku_count", 0) or 0)
    funnel_problem_groups = sales_funnel_summary.get("top_problem_groups", [])
    if not isinstance(funnel_problem_groups, list):
        funnel_problem_groups = []
    funnel_problem_groups_text = ", ".join(
        f"{str(item.get('issue_type') or '')}:{int(item.get('count', 0) or 0)}"
        for item in funnel_problem_groups[:3]
        if isinstance(item, dict) and str(item.get("issue_type") or "").strip()
    )

    funnel_section_lines = [
        "",
        "## SALES FUNNEL",
        f"- Views: {format_int_or_unknown(funnel.get('views', funnel.get('impressions')))}",
        f"- Add to cart: {format_int_or_unknown(funnel.get('add_to_cart', funnel.get('cart_count')))}",
        f"- Orders: {format_int_or_unknown(funnel.get('orders'))}",
        f"- Buyouts: {format_int_or_unknown(funnel.get('buyouts'))}",
        f"- View в†’ Order: {format_pct_or_unknown(funnel.get('view_to_order_conversion', funnel.get('click_to_order_conversion_pct')))}",
        f"- Cart в†’ Order: {format_pct_or_unknown(funnel.get('cart_to_order', funnel.get('cart_conversion_pct')))}",
        f"- Order в†’ Buyout: {format_pct_or_unknown(funnel.get('buyout_rate', funnel.get('order_to_buyout_conversion_pct')))}",
        f"- Ads spend: {format_money_or_unknown(funnel.get('ads_spend'))}, CPO: {format_money_or_unknown(funnel.get('cpo', funnel.get('CPO')))}",
        f"- Legacy traffic: impressions={format_int_or_unknown(funnel.get('impressions'))}, clicks={format_int_or_unknown(funnel.get('clicks'))}, CTR={format_pct_or_unknown(funnel.get('ctr'))}",
        f"- О” orders vs yesterday: {format_pct_or_unknown(funnel_orders_prev_delta)}, vs 7d: {format_pct_or_unknown(funnel_orders_7d_delta)}",
        f"- О” buyouts vs yesterday: {format_pct_or_unknown(funnel_buyouts_prev_delta)}, vs 7d: {format_pct_or_unknown(funnel_buyouts_7d_delta)}",
        f"- РЎС‚Р°С‚СѓСЃС‹: traffic={str(funnel_status.get('traffic') or 'unknown')}, conversion={str(funnel_status.get('conversion') or 'unknown')}, buyout_stage={str(funnel_status.get('buyout_stage') or 'unknown')}",
        f"- SKU funnel analyzed: {format_int_or_unknown(funnel_analyzed_skus)} / {format_int_or_unknown(funnel_total_skus)}",
        f"- Top SKU funnel issues: {funnel_problem_groups_text or 'none'}",
        f"- Alert summary: {funnel_alerts_summary}",
    ]
    page_1.extend(funnel_section_lines)

    page_1.extend(["", "## AI Р’Р«Р’РћР” Р”РќРЇ", str(data.get("ai_day_conclusion") or "")])
    page_1.extend(["", "## РљР РђРўРљРР• Р Р•РљРћРњР•РќР”РђР¦РР"])
    page_1.extend(f"- {item}" for item in data.get("short_recommendations", []))

    memory_summary = facts.get("decision_memory_summary", {}) if isinstance(facts, dict) else {}
    important_warnings = _important_warnings(warnings_collector.export_warnings())

    page_3: List[str] = [
        "# РћР‘РЈР§Р•РќРР• AI Р РљРђР§Р•РЎРўР’Рћ Р”РђРќРќР«РҐ",
        "## РџРђРњРЇРўР¬ Р Р•РЁР•РќРР™ AI",
        "РџРѕРєР°Р·Р°С‚РµР»СЊ | Р—РЅР°С‡РµРЅРёРµ",
        f"Р’СЃРµРіРѕ СЂРµС€РµРЅРёР№ | {_format_int(memory_summary.get('total_logged', 0))}",
        f"РћР¶РёРґР°СЋС‚ РѕС†РµРЅРєРё | {_format_int(memory_summary.get('pending', 0))}",
        f"РЈСЃРїРµС€РЅС‹С… | {_format_int(memory_summary.get('success', 0))}",
        f"РќРµСѓРґР°С‡РЅС‹С… | {_format_int(memory_summary.get('fail', 0))}",
        f"РќРµР№С‚СЂР°Р»СЊРЅС‹С… | {_format_int(memory_summary.get('neutral', 0))}",
    ]
    if int(data.get("outcomes_evaluated", 0) or 0) > 0:
        outcome_results = outcomes_payload.get("results", {}) if isinstance(outcomes_payload, dict) else {}
        page_3.append(
            f"- AI РѕС†РµРЅРёР» {_format_int(data.get('outcomes_evaluated', 0))} РїСЂРѕС€Р»С‹С… СЂРµС€РµРЅРёР№: "
            f"{_format_int(outcome_results.get('success', 0))} СѓСЃРїРµС€РЅС‹С…, "
            f"{_format_int(outcome_results.get('neutral', 0))} РЅРµР№С‚СЂР°Р»СЊРЅС‹С…, "
            f"{_format_int(outcome_results.get('fail', 0))} РЅРµСѓРґР°С‡РЅС‹С…."
        )

    page_3.extend(
        [
            "",
            "## РљРђР§Р•РЎРўР’Рћ Р”РђРќРќР«РҐ",
            "РџРѕРєР°Р·Р°С‚РµР»СЊ | Р—РЅР°С‡РµРЅРёРµ",
            f"Р’Р°Р»РёРґРЅС‹Рµ SKU | {_format_int(data_quality.get('valid_sku_count', 0))}",
            f"РќРµРІР°Р»РёРґРЅС‹Рµ СЃС‚СЂРѕРєРё | {_format_int(data_quality.get('invalid_sku_rows', 0))}",
            f"Invalid parser rows | {_format_int(data_quality.get('invalid_sku_rows_parser_error', 0))}",
            f"Missing SKU field rows | {_format_int(data_quality.get('invalid_sku_rows_missing_field', 0))}",
            f"True unassigned rows | {_format_int(data_quality.get('unassigned_rows_true', 0))}",
            f"Р Р°СЃС…РѕРґС‹ Р±РµР· SKU | {'Р”Р°' if bool(data_quality.get('unassigned_costs_present', False)) else 'РќРµС‚'}",
        ]
    )
    if bool(data_quality.get("unassigned_costs_present", False)):
        page_3.append("- Р§Р°СЃС‚СЊ СЂР°СЃС…РѕРґРѕРІ РЅРµ РїСЂРёРІСЏР·Р°РЅР° Рє SKU Рё СѓС‡С‚РµРЅР° РѕС‚РґРµР»СЊРЅРѕ.")

    page_3.extend(
        [
            "",
            "## РљРђР§Р•РЎРўР’Рћ Р¤РРќРђРќРЎРћР’РћР™ РђРўР РР‘РЈР¦РР",
            "РџРѕРєР°Р·Р°С‚РµР»СЊ | Р—РЅР°С‡РµРЅРёРµ",
            f"Р’Р°Р»РёРґРЅС‹С… SKU | {_format_int(data_quality.get('valid_sku_count', 0))}",
            f"SKU attribution status | {sku_attribution_status}",
            f"РќРµСЂР°СЃРїСЂРµРґРµР»РµРЅРЅС‹С… СЃС‚СЂРѕРє | {_format_int(data_quality.get('unassigned_rows', unassigned_costs.get('rows', 0)))}",
            f"РќРµСЂР°СЃРїСЂРµРґРµР»РµРЅРЅС‹Рµ СЂР°СЃС…РѕРґС‹ | {_format_money(unassigned_costs.get('profit', 0.0))}",
            f"РџРѕР»РЅРѕС‚Р° С„РёРЅР°РЅСЃРѕРІС‹С… РґР°РЅРЅС‹С… | {_format_pct(data.get('financial_completeness_pct', 0.0))}",
            f"Financial contour status | {financial_finality_status}",
            f"Report reliability level | {str(data_quality.get('report_reliability_level', 'medium'))}",
            f"Р”РѕСЃС‚РѕРІРµСЂРЅРѕСЃС‚СЊ AI-СЂРµС€РµРЅРёР№ | {_confidence_ru(str(data_quality.get('ai_decision_reliability', 'medium')))}",
        ]
    )

    page_3.extend(["", "## РџР Р•Р”РЈРџР Р•Р–Р”Р•РќРРЇ РЎРРЎРўР•РњР«"])
    if important_warnings:
        for item in important_warnings:
            code = str(item.get("code") or "")
            message = _warning_message_ru(code, str(item.get("message") or ""))
            page_3.append(f"- {message}")
    else:
        page_3.append("- Р’Р°Р¶РЅС‹С… РїСЂРµРґСѓРїСЂРµР¶РґРµРЅРёР№ РЅРµС‚.")

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
            "financial_finality_status": financial_finality_status,
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
        "sales_funnel_summary": sales_funnel_summary if isinstance(sales_funnel_summary, dict) else {},
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











