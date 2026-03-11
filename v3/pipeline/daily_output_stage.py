from __future__ import annotations

import os
from typing import Any, Dict, List

from .daily_stage_support import sync_from_entry


def run_daily_output_stage(context: Dict[str, Any]) -> Dict[str, Any]:
    sync_from_entry(globals())

    ctx: Dict[str, Any] = dict(context or {})
    seller_id = str(ctx.get("seller_id") or "")
    run_date = str(ctx.get("run_date") or "")
    out_dir = str(ctx.get("out_dir") or "")

    warnings_collector = ctx.get("warnings_collector")
    if not isinstance(warnings_collector, WarningsCollector):
        warnings_collector = WarningsCollector()

    facts = ctx.get("facts", {})
    if not isinstance(facts, dict):
        facts = {}
    job = ctx.get("job", {})
    if not isinstance(job, dict):
        job = {}
    metrics = ctx.get("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}
    data_quality = ctx.get("data_quality", {})
    if not isinstance(data_quality, dict):
        data_quality = {}
    daily_kpi = ctx.get("daily_kpi", {})
    if not isinstance(daily_kpi, dict):
        daily_kpi = {}
    ads_summary = ctx.get("ads_summary", {})
    if not isinstance(ads_summary, dict):
        ads_summary = {}
    decisions_summary = ctx.get("decisions_summary", {})
    if not isinstance(decisions_summary, dict):
        decisions_summary = {}
    director_strategy = ctx.get("director_strategy", {})
    if not isinstance(director_strategy, dict):
        director_strategy = {}
    health_summary = ctx.get("health_summary", {})
    if not isinstance(health_summary, dict):
        health_summary = {}
    outcomes_payload = ctx.get("outcomes_payload", {})
    if not isinstance(outcomes_payload, dict):
        outcomes_payload = {}

    decision_rows_added = int(ctx.get("decision_rows_added", 0) or 0)
    outcomes_evaluated = int(ctx.get("outcomes_evaluated", 0) or 0)
    source_mode = str(ctx.get("source_mode") or "local_reports")
    confidence = str(ctx.get("confidence") or "low")

    sku_metrics = ctx.get("sku_metrics", [])
    if not isinstance(sku_metrics, list):
        sku_metrics = []
    abc_rows = ctx.get("abc_rows", [])
    if not isinstance(abc_rows, list):
        abc_rows = []
    profit_contribution = ctx.get("profit_contribution", {})
    if not isinstance(profit_contribution, dict):
        profit_contribution = {}
    territorial_distribution = ctx.get("territorial_distribution", {})
    if not isinstance(territorial_distribution, dict):
        territorial_distribution = {}
    territorial_summary = ctx.get("territorial_summary", {})
    if not isinstance(territorial_summary, dict):
        territorial_summary = {}
    logistics_summary = ctx.get("logistics_summary", {})
    if not isinstance(logistics_summary, dict):
        logistics_summary = {}
    unassigned_costs = ctx.get("unassigned_costs", {})
    if not isinstance(unassigned_costs, dict):
        unassigned_costs = {}

    financial_kpi = ctx.get("financial_kpi", {})
    if not isinstance(financial_kpi, dict):
        financial_kpi = {}
    totals = metrics.get("totals", {}) if isinstance(metrics, dict) else {}
    if not isinstance(totals, dict):
        totals = {}

    ads_rows_count = int(ctx.get("ads_rows_count", 0) or 0)
    ads_loaded_from_file = bool(ctx.get("ads_loaded_from_file", False))
    ads_source_file = str(ctx.get("ads_source_file") or "")
    ads_attribution_quality = str(ctx.get("ads_attribution_quality") or "unknown")

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

    page_1: List[str] = [
        "# WB AI Agent — Отчет по кабинету",
        f"### Кабинет: {seller_id}",
        f"### Дата отчета: {run_date}",
        f"### Уверенность данных: {_confidence_ru(confidence)}",
        "",
        "## COMMERCE KPI",
        "Показатель | Значение",
        f"Количество заказов | {_format_int(daily_orders_count)}",
        f"Сумма заказов (минус комиссия WB) | {_format_money_2(daily_orders_amount)}",
        f"Выкупы | {_format_int(daily_buyouts_count)}",
        f"К перечислению по выкупам | {_format_money_2(daily_buyouts_amount)}",
        f"Средний чек по выкупу | {_format_money_2(avg_check)}",
        f"Источник orders_count | {str(daily_kpi.get('data_source_orders_count') or daily_kpi.get('data_source_orders') or _SOURCE_UNKNOWN)}",
        f"Источник orders_amount | {str(daily_kpi.get('data_source_orders_amount') or _SOURCE_UNKNOWN)}",
        f"Источник buyouts_count | {str(daily_kpi.get('data_source_buyouts_count') or daily_kpi.get('data_source_buyouts') or _SOURCE_UNKNOWN)}",
        f"Источник buyouts_amount | {str(daily_kpi.get('data_source_buyouts_amount') or _SOURCE_UNKNOWN)}",
        f"Orders count подтвержден | {'Да' if bool(daily_kpi.get('orders_count_confirmed', False)) else 'Нет'}",
        f"Buyouts count подтвержден | {'Да' if bool(daily_kpi.get('buyouts_count_confirmed', False)) else 'Нет'}",
        f"Orders amount подтвержден | {'Да' if bool(daily_kpi.get('orders_amount_confirmed', False)) else 'Нет'}",
        f"Buyouts amount подтвержден | {'Да' if bool(daily_kpi.get('buyouts_amount_confirmed', False)) else 'Нет'}",
        f"Количество SKU | {_format_int(len(sku_metrics))}",
        f"Расходы на рекламу | {_format_money(ads_spend_total)}",
        "",
        "## FINANCIAL KPI",
        "Показатель | Значение",
        f"Выручка (подтвержденная финансовыми строками) | {_format_money(revenue_total)}",
        f"Себестоимость | {_format_money(cost_price_total)}",
        f"Комиссия WB | {_format_money(wb_commission)}",
        f"Логистика | {_format_money(logistics_total)}",
        f"Хранение | {_format_money(storage_total)}",
        f"Штрафы | {_format_money(penalties_total)}",
        f"Удержания | {_format_money(deductions_total)}",
        f"Реклама | {_format_money(ads_spend_total)}",
        f"Валовая прибыль | {_format_money(gross_profit_total)}",
        f"Чистая прибыль | {_format_money(net_profit)}",
        f"Маржа % | {_format_pct(margin_pct_total)}",
        f"Рентабельность % | {_format_pct(profitability_pct_total)}",
        f"Полнота финансовых данных | {_format_pct(financial_completeness_pct)}",
        f"Статус финансового контура | {'частичный' if financial_partial else 'финальный'}",
        "",
        "## РЕКЛАМА",
        "Показатель | Значение",
        f"Показы | {_format_int(ads_impressions)}",
        f"Клики | {_format_int(ads_clicks)}",
        f"CTR | {_format_pct(ads_ctr)}",
        f"Расход | {_format_money(ads_spend_total)}",
        f"Заказы | {_format_int(ads_orders)}",
        f"Выручка | {_format_money(ads_revenue)}",
        f"ACOS | {_format_pct(ads_acos)}",
        f"ROMI | {_format_pct(ads_romi)}",
        f"Реклама учтена в прибыли | {'Да' if ads_spend_total > 0 else 'Нет'}",
        f"Атрибуция рекламы | {ads_attribution_quality}",
        f"Источник рекламы | {ads_source_file or ('local_file' if ads_loaded_from_file else 'api_or_missing')}",
        "",
        "## КЛЮЧЕВЫЕ ВЫВОДЫ",
    ]
    page_1.extend(f"- {line}" for line in key_insights)
    balanced_count = int(territorial_summary.get("balanced_count", 0) or 0)
    moderate_count = int(territorial_summary.get("moderate_mismatch_count", 0) or 0)
    misallocated_count = int(territorial_summary.get("misallocated_count", 0) or 0)
    analyzed_with_ktr = int(
        territorial_summary.get("sku_with_ktr", balanced_count + moderate_count + misallocated_count) or 0
    )
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

    page_1.extend(["", "## ТЕРРИТОРИАЛЬНОЕ РАСПРЕДЕЛЕНИЕ"])
    if analyzed_with_ktr <= 0:
        page_1.append("- Недостаточно данных для анализа территориального распределения")
    else:
        page_1.append(f"- Средний КТР по кабинету: {_format_ktr(territorial_summary.get('avg_ktr', 0.0))}")
        page_1.append(f"- Хорошо распределены: {_format_int(balanced_count)} SKU")
        page_1.append(f"- Есть перекос: {_format_int(moderate_count + misallocated_count)} SKU")
        if top_misaligned_confident:
            page_1.append(f"- Наибольший перекос (confidence medium/high): {top_misaligned_text}")
        elif top_misaligned_pdf:
            page_1.append("- Наибольший перекос: только low-confidence SKU (total_buys < 3)")
        else:
            page_1.append("- Наибольший перекос: —")
        if excluded_low_conf_count > 0:
            page_1.append(f"- Исключено low-confidence SKU из топа: {_format_int(excluded_low_conf_count)}")
        if low_conf_ktr_count > 0:
            page_1.append(
                f"- Low-confidence KTR (total_buys < 3): {_format_int(low_conf_ktr_count)} SKU, интерпретировать осторожно"
            )

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
            page_1.append("- Top critical SKU: —")

    profit_rows = _top_profit_rows(
        profit_contribution=profit_contribution if isinstance(profit_contribution, dict) else {},
        sku_metrics=sku_metrics,
        abc_rows=abc_rows,
    )
    page_1.extend(
        [
            "",
            "## ТОП SKU ПО ПРИБЫЛИ",
            "SKU | Прибыль | Доля прибыли (%) | Маржа (%) | Класс прибыли | ABC",
        ]
    )
    if profit_rows:
        for row in profit_rows[:5]:
            profit_value = _safe_float(row.get("profit", 0.0))
            profit_share_pct = (profit_value / profit_total * 100.0) if abs(profit_total) > 1e-9 else 0.0
            page_1.append(
                f"{row.get('sku', 'n/a')} | "
                f"{_format_money(profit_value)} | "
                f"{_format_pct(profit_share_pct)} | "
                f"{_format_pct(row.get('margin_pct', 0.0))} | "
                f"{str(row.get('profit_class', '-') or '-')} | "
                f"{str(row.get('abc_class', '-') or '-')}"
            )
    else:
        page_1.append("Нет данных по SKU.")

    decision_groups: Dict[str, List[Dict[str, Any]]] = {}
    if isinstance(decisions_summary, dict):
        for key in ("scale", "fix", "watch", "liquidate"):
            rows = decisions_summary.get(key, [])
            decision_groups[key] = [x for x in rows if isinstance(x, dict)] if isinstance(rows, list) else []
    else:
        decision_groups = {"scale": [], "fix": [], "watch": [], "liquidate": []}

    status_labels = {
        "scale": "МАСШТАБИРОВАТЬ (SCALE)",
        "fix": "ИСПРАВИТЬ (FIX)",
        "watch": "НАБЛЮДАТЬ (WATCH)",
        "liquidate": "ЛИКВИДИРОВАТЬ (LIQUIDATE)",
    }

    page_2: List[str] = [
        "# СТАТУС SKU И РЕШЕНИЯ AI",
        "## СТАТУС SKU",
        f"- {status_labels['scale']}: {_format_int(len(decision_groups['scale']))} — "
        f"{_compact_sku_list([str(x.get('sku') or '').strip() for x in decision_groups['scale']])}",
        f"- {status_labels['fix']}: {_format_int(len(decision_groups['fix']))} — "
        f"{_compact_sku_list([str(x.get('sku') or '').strip() for x in decision_groups['fix']])}",
        f"- {status_labels['watch']}: {_format_int(len(decision_groups['watch']))} — "
        f"{_compact_sku_list([str(x.get('sku') or '').strip() for x in decision_groups['watch']])}",
        f"- {status_labels['liquidate']}: {_format_int(len(decision_groups['liquidate']))} — "
        f"{_compact_sku_list([str(x.get('sku') or '').strip() for x in decision_groups['liquidate']])}",
        "",
        "## РЕШЕНИЯ AI",
    ]

    def _append_decision_group(page: List[str], group_key: str) -> None:
        page.append(f"### {status_labels[group_key]}")
        rows = decision_groups.get(group_key, [])
        if not rows:
            page.append("- Нет SKU в этой группе.")
            page.append("")
            return
        for row in rows:
            sku = str(row.get("sku") or "n/a")
            action_text = str(row.get("action") or "").strip() or "Решение не задано"
            page.append(f"- SKU {sku} — прибыль {_format_money(row.get('profit', 0.0))} — {action_text.lower()}")
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

    page_2.extend(["## СТРАТЕГИЯ AI ДИРЕКТОРА"])
    for key in ("scale", "fix", "watch", "liquidate"):
        page_2.append(f"### {status_labels[key]}")
        rows = director_groups.get(key, [])
        if not rows:
            page_2.append("- Нет SKU в этой группе.")
            continue
        default_task = director_default_actions.get(key, "")
        for sku in rows[:10]:
            task = task_by_sku.get(sku) or default_task
            page_2.append(f"- SKU {sku} -> {task}")
    rebalance_rows = [
        row
        for row in director_tasks_raw
        if isinstance(row, dict) and str(row.get("task") or "").strip() == "rebalance_stock"
    ]
    if rebalance_rows:
        page_2.append("### ЛОГИСТИЧЕСКАЯ БАЛАНСИРОВКА")
        for row in rebalance_rows[:10]:
            sku = str(row.get("sku") or "").strip()
            if sku:
                page_2.append(f"- SKU {sku} -> rebalance_stock")

    short_recommendations = _build_short_recommendations(
        decision_groups=decision_groups,
        logistics_summary=logistics_summary if isinstance(logistics_summary, dict) else {},
    )
    ai_day_conclusion = _build_ai_day_conclusion(
        run_date=run_date,
        totals=totals if isinstance(totals, dict) else {},
        daily_kpi=daily_kpi if isinstance(daily_kpi, dict) else {},
        data_quality=data_quality if isinstance(data_quality, dict) else {},
        key_insights=key_insights,
        recommendations=short_recommendations,
    )
    page_1.extend(["", "## AI ВЫВОД ДНЯ", ai_day_conclusion])
    page_1.extend(["", "## КРАТКИЕ РЕКОМЕНДАЦИИ"])
    page_1.extend(f"- {item}" for item in short_recommendations)

    job["email_summary"] = build_email_summary(
        daily_kpi=daily_kpi if isinstance(daily_kpi, dict) else {},
        ads_summary=ads_summary if isinstance(ads_summary, dict) else {},
        net_profit=net_profit,
        gross_profit=gross_profit_total,
        cost_price=cost_price_total,
        wb_commission=wb_commission,
        logistics=logistics_total,
        storage=storage_total,
        penalties=penalties_total,
        deductions=deductions_total,
        ads_spend_total=ads_spend_total,
        margin_pct=margin_pct_total,
        profitability_pct=profitability_pct_total,
        financial_completeness_pct=financial_completeness_pct,
        financial_partial=financial_partial,
        ads_rows=ads_rows_count,
        ads_impressions=ads_impressions,
        ads_clicks=ads_clicks,
        ads_orders=ads_orders,
        ads_loaded_from_file=bool(ads_loaded_from_file),
        ads_source_file=ads_source_file,
        ads_attribution_quality=ads_attribution_quality,
        daily_revenue=daily_buyouts_amount,
        financial_revenue=revenue_total,
        daily_orders_count=daily_orders_count,
        avg_check=avg_check,
        daily_orders_amount=daily_orders_amount,
        daily_buyouts_count=daily_buyouts_count,
        daily_buyouts_amount=daily_buyouts_amount,
        key_insights=key_insights,
        recommendations=short_recommendations,
        ai_day_conclusion=ai_day_conclusion,
    )

    memory_summary = facts.get("decision_memory_summary", {}) if isinstance(facts, dict) else {}
    important_warnings = _important_warnings(warnings_collector.export_warnings())

    page_3: List[str] = [
        "# ОБУЧЕНИЕ AI И КАЧЕСТВО ДАННЫХ",
        "## ПАМЯТЬ РЕШЕНИЙ AI",
        "Показатель | Значение",
        f"Всего решений | {_format_int(memory_summary.get('total_logged', 0))}",
        f"Ожидают оценки | {_format_int(memory_summary.get('pending', 0))}",
        f"Успешных | {_format_int(memory_summary.get('success', 0))}",
        f"Неудачных | {_format_int(memory_summary.get('fail', 0))}",
        f"Нейтральных | {_format_int(memory_summary.get('neutral', 0))}",
    ]
    if outcomes_evaluated > 0:
        outcome_results = outcomes_payload.get("results", {}) if isinstance(outcomes_payload, dict) else {}
        page_3.append(
            f"- AI оценил {_format_int(outcomes_evaluated)} прошлых решений: "
            f"{_format_int(outcome_results.get('success', 0))} успешных, "
            f"{_format_int(outcome_results.get('neutral', 0))} нейтральных, "
            f"{_format_int(outcome_results.get('fail', 0))} неудачных."
        )

    page_3.extend(
        [
            "",
            "## КАЧЕСТВО ДАННЫХ",
            "Показатель | Значение",
            f"Валидные SKU | {_format_int(data_quality.get('valid_sku_count', 0))}",
            f"Невалидные строки | {_format_int(data_quality.get('invalid_sku_rows', 0))}",
            f"Расходы без SKU | {'Да' if bool(data_quality.get('unassigned_costs_present', False)) else 'Нет'}",
        ]
    )
    if bool(data_quality.get("unassigned_costs_present", False)):
        page_3.append("- Часть расходов не привязана к SKU и учтена отдельно.")

    page_3.extend(
        [
            "",
            "## КАЧЕСТВО ФИНАНСОВОЙ АТРИБУЦИИ",
            "Показатель | Значение",
            f"Валидных SKU | {_format_int(data_quality.get('valid_sku_count', 0))}",
            f"Нераспределенных строк | {_format_int(data_quality.get('unassigned_rows', unassigned_costs.get('rows', 0)))}",
            f"Нераспределенные расходы | {_format_money(unassigned_costs.get('profit', 0.0))}",
            f"Полнота финансовых данных | {_format_pct(financial_completeness_pct)}",
            f"Финансовый контур финальный | {'Нет' if financial_partial else 'Да'}",
            f"Достоверность AI-решений | {_confidence_ru(str(data_quality.get('ai_decision_reliability', 'medium')))}",
        ]
    )

    page_3.extend(["", "## ПРЕДУПРЕЖДЕНИЯ СИСТЕМЫ"])
    if important_warnings:
        for item in important_warnings:
            code = str(item.get("code") or "")
            message = _warning_message_ru(code, str(item.get("message") or ""))
            page_3.append(f"- {message}")
    else:
        page_3.append("- Важных предупреждений нет.")

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
            "daily_orders_count": daily_orders_count,
            "daily_orders_amount": round(daily_orders_amount, 2),
            "daily_buyouts_count": daily_buyouts_count,
            "daily_buyouts_amount": round(daily_buyouts_amount, 2),
            "avg_check": round(avg_check, 2),
            "data_source_orders": str(daily_kpi.get("data_source_orders") or _SOURCE_UNKNOWN),
            "data_source_orders_count": str(
                daily_kpi.get("data_source_orders_count")
                or daily_kpi.get("data_source_orders")
                or _SOURCE_UNKNOWN
            ),
            "data_source_orders_amount": str(daily_kpi.get("data_source_orders_amount") or _SOURCE_UNKNOWN),
            "data_source_buyouts": str(daily_kpi.get("data_source_buyouts") or _SOURCE_UNKNOWN),
            "data_source_buyouts_count": str(
                daily_kpi.get("data_source_buyouts_count")
                or daily_kpi.get("data_source_buyouts")
                or _SOURCE_UNKNOWN
            ),
            "data_source_buyouts_amount": str(daily_kpi.get("data_source_buyouts_amount") or _SOURCE_UNKNOWN),
            "orders_count_confirmed": bool(daily_kpi.get("orders_count_confirmed", False)),
            "buyouts_count_confirmed": bool(daily_kpi.get("buyouts_count_confirmed", False)),
        },
        "daily_financial_kpi": {
            "revenue": round(revenue_total, 2),
            "cost_price": round(cost_price_total, 2),
            "wb_commission": round(wb_commission, 2),
            "ads_spend": round(ads_spend_total, 2),
            "ads_impressions": ads_impressions,
            "ads_clicks": ads_clicks,
            "ads_orders": ads_orders,
            "ads_rows": ads_rows_count,
            "ads_source_file": ads_source_file,
            "ads_loaded_from_file": bool(ads_loaded_from_file),
            "ads_attribution_quality": ads_attribution_quality,
            "gross_profit": round(gross_profit_total, 2),
            "net_profit": round(net_profit, 2),
            "margin_pct": round(margin_pct_total, 2),
            "profitability_pct": round(profitability_pct_total, 2),
            "financial_completeness_pct": round(financial_completeness_pct, 2),
            "financial_partial": financial_partial,
        },
    }
    report_meta["page_previews"] = [
        {"page": page_idx + 1, "lines": page[:30]} for page_idx, page in enumerate(report_pages)
    ]

    write_report_meta(out_dir=out_dir, report_meta=report_meta)
    history_bundle = write_daily_history_snapshot_and_build_patches(
        seller_id=seller_id,
        run_date=run_date,
        out_dir=out_dir,
        facts=facts if isinstance(facts, dict) else {},
        warnings=warnings_collector.export_warnings(),
    )
    facts = history_bundle.get("facts", {}) if isinstance(history_bundle, dict) else {}
    if not isinstance(facts, dict):
        facts = {}
    warnings_after_history = history_bundle.get("warnings", []) if isinstance(history_bundle, dict) else []
    if not isinstance(warnings_after_history, list):
        warnings_after_history = warnings_collector.export_warnings()
    write_facts_and_warnings(
        out_dir=out_dir,
        facts=facts if isinstance(facts, dict) else {},
        warnings=warnings_after_history,
    )
    job = attach_daily_job_history(
        job if isinstance(job, dict) else {},
        run_date=run_date,
        history_snapshot_final=(
            history_bundle.get("history_snapshot_final", {})
            if isinstance(history_bundle, dict)
            else {}
        ),
    )
    job = attach_job_warnings(
        job if isinstance(job, dict) else {},
        warnings=warnings_after_history,
    )
    write_job(out_dir=out_dir, job=job)
    return job
