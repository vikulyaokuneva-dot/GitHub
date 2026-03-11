from __future__ import annotations

import os
from typing import Any, Dict, List

from ..pipeline.daily_stage_support import sync_from_entry


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

    page_1: List[str] = [
        "# WB AI Agent вЂ” РћС‚С‡РµС‚ РїРѕ РєР°Р±РёРЅРµС‚Сѓ",
        f"### РљР°Р±РёРЅРµС‚: {str(data.get('seller_id') or '')}",
        f"### Р”Р°С‚Р° РѕС‚С‡РµС‚Р°: {str(data.get('run_date') or '')}",
        f"### РЈРІРµСЂРµРЅРЅРѕСЃС‚СЊ РґР°РЅРЅС‹С…: {_confidence_ru(str(data.get('confidence') or 'low'))}",
        "",
        "## COMMERCE KPI",
        "РџРѕРєР°Р·Р°С‚РµР»СЊ | Р—РЅР°С‡РµРЅРёРµ",
        f"РљРѕР»РёС‡РµСЃС‚РІРѕ Р·Р°РєР°Р·РѕРІ | {_format_int(data.get('daily_orders_count', 0))}",
        f"РЎСѓРјРјР° Р·Р°РєР°Р·РѕРІ (РјРёРЅСѓСЃ РєРѕРјРёСЃСЃРёСЏ WB) | {_format_money_2(data.get('daily_orders_amount', 0.0))}",
        f"Р’С‹РєСѓРїС‹ | {_format_int(data.get('daily_buyouts_count', 0))}",
        f"Рљ РїРµСЂРµС‡РёСЃР»РµРЅРёСЋ РїРѕ РІС‹РєСѓРїР°Рј | {_format_money_2(data.get('daily_buyouts_amount', 0.0))}",
        f"РЎСЂРµРґРЅРёР№ С‡РµРє РїРѕ РІС‹РєСѓРїСѓ | {_format_money_2(data.get('avg_check', 0.0))}",
        f"РСЃС‚РѕС‡РЅРёРє orders_count | {str(daily_kpi.get('data_source_orders_count') or daily_kpi.get('data_source_orders') or _SOURCE_UNKNOWN)}",
        f"РСЃС‚РѕС‡РЅРёРє orders_amount | {str(daily_kpi.get('data_source_orders_amount') or _SOURCE_UNKNOWN)}",
        f"РСЃС‚РѕС‡РЅРёРє buyouts_count | {str(daily_kpi.get('data_source_buyouts_count') or daily_kpi.get('data_source_buyouts') or _SOURCE_UNKNOWN)}",
        f"РСЃС‚РѕС‡РЅРёРє buyouts_amount | {str(daily_kpi.get('data_source_buyouts_amount') or _SOURCE_UNKNOWN)}",
        f"Orders count РїРѕРґС‚РІРµСЂР¶РґРµРЅ | {'Р”Р°' if bool(daily_kpi.get('orders_count_confirmed', False)) else 'РќРµС‚'}",
        f"Buyouts count РїРѕРґС‚РІРµСЂР¶РґРµРЅ | {'Р”Р°' if bool(daily_kpi.get('buyouts_count_confirmed', False)) else 'РќРµС‚'}",
        f"Orders amount РїРѕРґС‚РІРµСЂР¶РґРµРЅ | {'Р”Р°' if bool(daily_kpi.get('orders_amount_confirmed', False)) else 'РќРµС‚'}",
        f"Buyouts amount РїРѕРґС‚РІРµСЂР¶РґРµРЅ | {'Р”Р°' if bool(daily_kpi.get('buyouts_amount_confirmed', False)) else 'РќРµС‚'}",
        f"РљРѕР»РёС‡РµСЃС‚РІРѕ SKU | {_format_int(len(sku_metrics))}",
        f"Р Р°СЃС…РѕРґС‹ РЅР° СЂРµРєР»Р°РјСѓ | {_format_money(data.get('ads_spend_total', 0.0))}",
        "",
        "## FINANCIAL KPI",
        "РџРѕРєР°Р·Р°С‚РµР»СЊ | Р—РЅР°С‡РµРЅРёРµ",
        f"Р’С‹СЂСѓС‡РєР° (РїРѕРґС‚РІРµСЂР¶РґРµРЅРЅР°СЏ С„РёРЅР°РЅСЃРѕРІС‹РјРё СЃС‚СЂРѕРєР°РјРё) | {_format_money(data.get('revenue_total', 0.0))}",
        f"РЎРµР±РµСЃС‚РѕРёРјРѕСЃС‚СЊ | {_format_money(data.get('cost_price_total', 0.0))}",
        f"РљРѕРјРёСЃСЃРёСЏ WB | {_format_money(data.get('wb_commission', 0.0))}",
        f"Р›РѕРіРёСЃС‚РёРєР° | {_format_money(data.get('logistics_total', 0.0))}",
        f"РҐСЂР°РЅРµРЅРёРµ | {_format_money(data.get('storage_total', 0.0))}",
        f"РЁС‚СЂР°С„С‹ | {_format_money(data.get('penalties_total', 0.0))}",
        f"РЈРґРµСЂР¶Р°РЅРёСЏ | {_format_money(data.get('deductions_total', 0.0))}",
        f"Р РµРєР»Р°РјР° | {_format_money(data.get('ads_spend_total', 0.0))}",
        f"Р’Р°Р»РѕРІР°СЏ РїСЂРёР±С‹Р»СЊ | {_format_money(data.get('gross_profit_total', 0.0))}",
        f"Р§РёСЃС‚Р°СЏ РїСЂРёР±С‹Р»СЊ | {_format_money(data.get('net_profit', 0.0))}",
        f"РњР°СЂР¶Р° % | {_format_pct(data.get('margin_pct_total', 0.0))}",
        f"Р РµРЅС‚Р°Р±РµР»СЊРЅРѕСЃС‚СЊ % | {_format_pct(data.get('profitability_pct_total', 0.0))}",
        f"РџРѕР»РЅРѕС‚Р° С„РёРЅР°РЅСЃРѕРІС‹С… РґР°РЅРЅС‹С… | {_format_pct(data.get('financial_completeness_pct', 0.0))}",
        f"РЎС‚Р°С‚СѓСЃ С„РёРЅР°РЅСЃРѕРІРѕРіРѕ РєРѕРЅС‚СѓСЂР° | {'С‡Р°СЃС‚РёС‡РЅС‹Р№' if bool(data.get('financial_partial', False)) else 'С„РёРЅР°Р»СЊРЅС‹Р№'}",
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
        f"Р РµРєР»Р°РјР° СѓС‡С‚РµРЅР° РІ РїСЂРёР±С‹Р»Рё | {'Р”Р°' if float(data.get('ads_spend_total', 0.0) or 0.0) > 0 else 'РќРµС‚'}",
        f"РђС‚СЂРёР±СѓС†РёСЏ СЂРµРєР»Р°РјС‹ | {str(data.get('ads_attribution_quality') or 'unknown')}",
        f"РСЃС‚РѕС‡РЅРёРє СЂРµРєР»Р°РјС‹ | {str(data.get('ads_source_file') or ('local_file' if bool(data.get('ads_loaded_from_file', False)) else 'api_or_missing'))}",
        "",
        "## РљР›Р®Р§Р•Р’Р«Р• Р’Р«Р’РћР”Р«",
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

    page_1.extend(["", "## РўР•Р Р РРўРћР РРђР›Р¬РќРћР• Р РђРЎРџР Р•Р”Р•Р›Р•РќРР•"])
    if analyzed_with_ktr <= 0:
        page_1.append("- РќРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РґР°РЅРЅС‹С… РґР»СЏ Р°РЅР°Р»РёР·Р° С‚РµСЂСЂРёС‚РѕСЂРёР°Р»СЊРЅРѕРіРѕ СЂР°СЃРїСЂРµРґРµР»РµРЅРёСЏ")
    else:
        page_1.append(f"- РЎСЂРµРґРЅРёР№ РљРўР  РїРѕ РєР°Р±РёРЅРµС‚Сѓ: {_format_ktr(territorial_summary.get('avg_ktr', 0.0))}")
        page_1.append(f"- РҐСЂРѕС€Рѕ СЂР°СЃРїСЂРµРґРµР»РµРЅС‹: {_format_int(balanced_count)} SKU")
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
            page.append(f"- SKU {sku} вЂ” РїСЂРёР±С‹Р»СЊ {_format_money(row.get('profit', 0.0))} вЂ” {action_text.lower()}")
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
            f"РќРµСЂР°СЃРїСЂРµРґРµР»РµРЅРЅС‹С… СЃС‚СЂРѕРє | {_format_int(data_quality.get('unassigned_rows', unassigned_costs.get('rows', 0)))}",
            f"РќРµСЂР°СЃРїСЂРµРґРµР»РµРЅРЅС‹Рµ СЂР°СЃС…РѕРґС‹ | {_format_money(unassigned_costs.get('profit', 0.0))}",
            f"РџРѕР»РЅРѕС‚Р° С„РёРЅР°РЅСЃРѕРІС‹С… РґР°РЅРЅС‹С… | {_format_pct(data.get('financial_completeness_pct', 0.0))}",
            f"Р¤РёРЅР°РЅСЃРѕРІС‹Р№ РєРѕРЅС‚СѓСЂ С„РёРЅР°Р»СЊРЅС‹Р№ | {'РќРµС‚' if bool(data.get('financial_partial', False)) else 'Р”Р°'}",
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
            "daily_orders_count": int(data.get("daily_orders_count", 0) or 0),
            "daily_orders_amount": round(float(data.get("daily_orders_amount", 0.0) or 0.0), 2),
            "daily_buyouts_count": int(data.get("daily_buyouts_count", 0) or 0),
            "daily_buyouts_amount": round(float(data.get("daily_buyouts_amount", 0.0) or 0.0), 2),
            "avg_check": round(float(data.get("avg_check", 0.0) or 0.0), 2),
            "data_source_orders": str(daily_kpi.get("data_source_orders") or _SOURCE_UNKNOWN),
            "data_source_orders_count": str(daily_kpi.get("data_source_orders_count") or daily_kpi.get("data_source_orders") or _SOURCE_UNKNOWN),
            "data_source_orders_amount": str(daily_kpi.get("data_source_orders_amount") or _SOURCE_UNKNOWN),
            "data_source_buyouts": str(daily_kpi.get("data_source_buyouts") or _SOURCE_UNKNOWN),
            "data_source_buyouts_count": str(daily_kpi.get("data_source_buyouts_count") or daily_kpi.get("data_source_buyouts") or _SOURCE_UNKNOWN),
            "data_source_buyouts_amount": str(daily_kpi.get("data_source_buyouts_amount") or _SOURCE_UNKNOWN),
            "orders_count_confirmed": bool(daily_kpi.get("orders_count_confirmed", False)),
            "buyouts_count_confirmed": bool(daily_kpi.get("buyouts_count_confirmed", False)),
        },
        "daily_financial_kpi": {
            "revenue": round(float(data.get("revenue_total", 0.0) or 0.0), 2),
            "cost_price": round(float(data.get("cost_price_total", 0.0) or 0.0), 2),
            "wb_commission": round(float(data.get("wb_commission", 0.0) or 0.0), 2),
            "ads_spend": round(float(data.get("ads_spend_total", 0.0) or 0.0), 2),
            "ads_impressions": int(data.get("ads_impressions", 0) or 0),
            "ads_clicks": int(data.get("ads_clicks", 0) or 0),
            "ads_orders": int(data.get("ads_orders", 0) or 0),
            "ads_rows": int(data.get("ads_rows_count", 0) or 0),
            "ads_source_file": str(data.get("ads_source_file") or ""),
            "ads_loaded_from_file": bool(data.get("ads_loaded_from_file", False)),
            "ads_attribution_quality": str(data.get("ads_attribution_quality") or "unknown"),
            "gross_profit": round(float(data.get("gross_profit_total", 0.0) or 0.0), 2),
            "net_profit": round(float(data.get("net_profit", 0.0) or 0.0), 2),
            "margin_pct": round(float(data.get("margin_pct_total", 0.0) or 0.0), 2),
            "profitability_pct": round(float(data.get("profitability_pct_total", 0.0) or 0.0), 2),
            "financial_completeness_pct": round(float(data.get("financial_completeness_pct", 0.0) or 0.0), 2),
            "financial_partial": bool(data.get("financial_partial", False)),
        },
    }
    report_meta["page_previews"] = [{"page": page_idx + 1, "lines": page[:30]} for page_idx, page in enumerate(report_pages)]

    write_report_meta(out_dir=out_dir, report_meta=report_meta)
    data.update({"job": job, "report_meta": report_meta})
    return data
