"""Email payload builder over facts + decisions (+ optional diagnostics).

Input: FactsBundle + DecisionsBundle + optional diagnostics.
Output: EmailPayload (plain text friendly).
Does not send email and does not recalculate KPI.
"""

from __future__ import annotations

from typing import Any

from ...core.contracts import DecisionItem, DecisionsBundle, FactItem, FactsBundle
from ...warnings_utils import dedupe_warnings
from .contracts import EmailPayload, EmailSection


AUDIT_DISCLAIMER = "Отчет построен в audit_file_mode; выводы ограничены доступными файлами."
WB_API_LIMITED_MODE_NOTE = "Данные WB API отсутствуют -> отчет сформирован в ограниченном режиме."

_DECISION_CATALOG: list[tuple[str, str, str]] = [
    ("negative_profit", "Negative profit", "P1"),
    ("low_margin", "Low margin risk", "P2"),
    ("ad_inefficiency", "Ad inefficiency", "P2"),
    ("out_of_stock_risk", "Out-of-stock risk", "P1"),
    ("weak_conversion", "Weak conversion", "P2"),
    ("overstock", "Overstock risk", "P2"),
    ("dead_sku", "Dead SKU risk", "P2"),
    ("low_business_health", "Low business health", "P2"),
    ("partial_data_warning", "Partial data warning", "P3"),
]


def _priority_value(item: DecisionItem) -> int:
    raw = item.priority.value if hasattr(item.priority, "value") else str(item.priority)
    return {"P1": 1, "P2": 2, "P3": 3}.get(raw, 9)


def _priority_text(item: DecisionItem) -> str:
    return item.priority.value if hasattr(item.priority, "value") else str(item.priority)


def _decision_status_text(item: DecisionItem) -> str:
    return item.status.value if hasattr(item.status, "value") else str(item.status)


def _decision_full_debug_status(raw_status: str) -> str:
    if raw_status == "confirmed":
        return "triggered"
    if raw_status == "partial":
        return "triggered_partial"
    if raw_status == "unavailable":
        return "unavailable"
    return "unavailable"


def _find_fact_item(section_name: str, key: str, facts_bundle: FactsBundle) -> FactItem | None:
    section = facts_bundle.sections.get(section_name)
    if section is None:
        return None
    for item in section.items:
        if item.key == key:
            return item
    return None


def _display_fact_value(fact_item: FactItem | None) -> str:
    if fact_item is None:
        return "нет данных"
    status = str(fact_item.value.status)
    value = fact_item.value.value
    if status == "unavailable":
        return "нет данных"
    if status == "partial":
        if value is None:
            return "нет данных (частично)"
        return f"{value} (частично)"
    if value is None:
        return "нет данных"
    return str(value)


def _has_partial_data(facts_bundle: FactsBundle) -> bool:
    return bool(facts_bundle.data_quality.get("partial_sections") or facts_bundle.data_quality.get("unavailable_sections"))


def _normalize_mode(mode: object) -> str:
    return "audit" if str(mode).strip().lower() == "audit" else "daily"


def _section_status(facts_bundle: FactsBundle, section_name: str) -> str:
    section = facts_bundle.sections.get(section_name)
    if section is None:
        return "unavailable"
    return str(section.status)


def _diagnostics_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _source_status_text(raw: object) -> str:
    token = str(raw or "").strip().lower()
    if token == "ok":
        return "available"
    if token == "partial":
        return "partial"
    if token in {"not_implemented", "skipped"}:
        return "skipped"
    return "missing"


def _build_summary_lines(facts_bundle: FactsBundle, decisions_bundle: DecisionsBundle, mode: str) -> list[str]:
    lines: list[str] = []
    decision_items = sorted(decisions_bundle.items, key=_priority_value)
    for decision in decision_items:
        if decision.code == "partial_data_warning":
            continue
        if len(lines) >= 3:
            break
        lines.append(f"{_priority_text(decision)} {decision.title}: {decision.summary}")

    if not lines:
        lines.append("Критичные сигналы по доступным фактам не выявлены.")

    health_line = _build_health_summary_line(facts_bundle)
    if health_line is not None:
        lines.append(health_line)

    if _has_partial_data(facts_bundle):
        partial_sections = list(facts_bundle.data_quality.get("partial_sections", []))
        unavailable_sections = list(facts_bundle.data_quality.get("unavailable_sections", []))
        lines.append(
            "Качество данных: частично."
            f" partial={partial_sections or []}, unavailable={unavailable_sections or []}"
        )

    if mode == "audit":
        lines.append(AUDIT_DISCLAIMER)

    return lines


def _build_health_summary_line(facts_bundle: FactsBundle) -> str | None:
    if "health" not in facts_bundle.sections:
        return None

    score_item = _find_fact_item("health", "business_health_score", facts_bundle)
    status_item = _find_fact_item("health", "score_status", facts_bundle)
    score_text = _display_fact_value(score_item)

    raw_status = None
    if status_item is not None:
        raw_status = status_item.value.value
    elif score_item is not None:
        raw_status = score_item.value.status
    status = str(raw_status or "unavailable").strip().lower()

    if status == "partial":
        return f"Health score: {score_text} (частично)"
    if status == "unavailable":
        return "Health score: нет данных"
    return f"Health score: {score_text}"


def _build_finance_section(facts_bundle: FactsBundle) -> EmailSection:
    section = facts_bundle.sections.get("financial")
    diagnostics = section.diagnostics if isinstance(getattr(section, "diagnostics", None), dict) else {}
    model_mode = str(
        diagnostics.get("financial_model_mode")
        or diagnostics.get("financial_mode")
        or "unavailable"
    )
    confidence = str(diagnostics.get("financial_confidence") or "none")
    profitability_method = str(diagnostics.get("profitability_method") or "unavailable")
    estimate_used = bool(diagnostics.get("profitability_estimate_used", False))
    estimate_warning = str(diagnostics.get("profitability_estimate_warning") or "").strip()
    blockers = diagnostics.get("profitability_blockers")
    blocker_list = list(blockers) if isinstance(blockers, list) else []

    net_label = "Чистая прибыль-like"
    margin_label = "Margin-like"
    if estimate_used:
        net_label = "Чистая прибыль-like (оценка)"
        margin_label = "Margin-like (оценка)"

    lines = [
        f"Выручка (gross): {_display_fact_value(_find_fact_item('financial', 'revenue_gross', facts_bundle))}",
        f"Выплата продавцу: {_display_fact_value(_find_fact_item('financial', 'seller_payout', facts_bundle))}",
        f"{net_label}: {_display_fact_value(_find_fact_item('financial', 'net_profit_like', facts_bundle))}",
        f"{margin_label}: {_display_fact_value(_find_fact_item('financial', 'margin', facts_bundle))}",
        f"Модель: {model_mode}; confidence={confidence}",
        f"Метод profitability: {profitability_method}",
    ]
    if estimate_warning:
        lines.append(f"Note: {estimate_warning}")
    elif estimate_used:
        lines.append("Note: рассчитано без realization components, на основе seller_payout.")
    if blocker_list:
        lines.append(f"Blockers: {blocker_list}")
    return EmailSection(title="Финансы", lines=lines, status=_section_status(facts_bundle, "financial"))


def _build_decisions_section(decisions_bundle: DecisionsBundle) -> EmailSection:
    if not decisions_bundle.items:
        return EmailSection(
            title="Ключевые решения",
            lines=["Решений по правилам не выявлено."],
            status="info",
        )
    lines: list[str] = []
    for item in sorted(decisions_bundle.items, key=_priority_value):
        lines.append(f"{_priority_text(item)} | {_decision_status_text(item)} | {item.title}: {item.summary}")
    section_status = "confirmed"
    if any(_decision_status_text(item) in {"partial", "unavailable"} for item in decisions_bundle.items):
        section_status = "partial"
    return EmailSection(title="Ключевые решения", lines=lines, status=section_status)


def _build_stock_section(facts_bundle: FactsBundle) -> EmailSection:
    lines = [
        f"Всего остатков, шт: {_display_fact_value(_find_fact_item('stock', 'total_stock_units', facts_bundle))}",
        f"In-stock SKU entities: {_display_fact_value(_find_fact_item('stock', 'in_stock_items_count', facts_bundle))}",
        f"Out-of-stock SKU entities: {_display_fact_value(_find_fact_item('stock', 'out_of_stock_items_count', facts_bundle))}",
    ]
    return EmailSection(title="Остатки / stock", lines=lines, status=_section_status(facts_bundle, "stock"))


def _build_health_section(facts_bundle: FactsBundle) -> EmailSection:
    health_section = facts_bundle.sections.get("health")
    if health_section is None:
        return EmailSection(title="Health", lines=["нет данных"], status="unavailable")

    lines = [
        f"Business health score: {_display_fact_value(_find_fact_item('health', 'business_health_score', facts_bundle))}",
        f"Score status: {_display_fact_value(_find_fact_item('health', 'score_status', facts_bundle))}",
        f"SKU health signals: {_display_fact_value(_find_fact_item('health', 'sku_health_signals_count', facts_bundle))}",
        f"Problematic SKU count: {_display_fact_value(_find_fact_item('health', 'problematic_sku_count', facts_bundle))}",
        f"Dead stock risk count: {_display_fact_value(_find_fact_item('health', 'dead_stock_risk_count', facts_bundle))}",
        f"Overstock risk count: {_display_fact_value(_find_fact_item('health', 'overstock_risk_count', facts_bundle))}",
    ]

    status_note = _find_fact_item("health", "business_health_status_note", facts_bundle)
    if status_note is not None:
        lines.append(f"Health note: {_display_fact_value(status_note)}")

    component_items = sorted(
        [item for item in health_section.items if item.key.startswith("component_") and item.key.endswith("_score")],
        key=lambda item: item.key,
    )
    for item in component_items:
        component_name = item.key[len("component_") : -len("_score")]
        lines.append(f"Component {component_name}: {_display_fact_value(item)}")

    return EmailSection(title="Health", lines=lines, status=health_section.status)


def _build_quality_section(facts_bundle: FactsBundle, mode: str) -> EmailSection:
    warnings = dedupe_warnings(facts_bundle.warnings)
    partial_sections = list(facts_bundle.data_quality.get("partial_sections", []))
    unavailable_sections = list(facts_bundle.data_quality.get("unavailable_sections", []))
    source_flags = facts_bundle.data_quality.get("source_flags")
    source_map = dict(source_flags) if isinstance(source_flags, dict) else {}
    source_reason_map = facts_bundle.diagnostics.get("source_reason_map")
    reason_map = dict(source_reason_map) if isinstance(source_reason_map, dict) else {}
    missing_sources = [name for name, status in source_map.items() if str(status) not in {"ok", "partial"}]
    partial_sources = [
        name
        for name, status in source_map.items()
        if str(status) == "partial" or str(reason_map.get(name, "")).strip().lower() in {"parse_failed", "normalized_empty"}
    ]
    lines = [
        f"Partial sections: {partial_sections or []}",
        f"Unavailable sections: {unavailable_sections or []}",
        f"Missing sources: {missing_sources}",
        f"Partial sources: {partial_sources}",
        f"Warnings count: {len(warnings)}",
    ]
    if reason_map:
        lines.append("Source reasons:")
        for source_name in sorted(reason_map.keys()):
            lines.append(f"- {source_name}: {reason_map[source_name]}")
    if mode == "audit":
        lines.append(AUDIT_DISCLAIMER)
    status = "partial" if partial_sections or unavailable_sections else "info"
    return EmailSection(title="Качество данных", lines=lines, status=status)


def _build_subject(facts_bundle: FactsBundle, decisions_bundle: DecisionsBundle, mode: str) -> str:
    seller_id = facts_bundle.run_context.seller_id
    p1_count = sum(1 for item in decisions_bundle.items if _priority_text(item) == "P1")
    mode_prefix = "AUDIT" if mode == "audit" else "DAILY"
    if p1_count > 0:
        return f"WB v4 {mode_prefix}: P1={p1_count} | {seller_id}"
    if decisions_bundle.items:
        return f"WB v4 {mode_prefix}: decisions={len(decisions_bundle.items)} | {seller_id}"
    return f"WB v4 {mode_prefix}: no critical decisions | {seller_id}"


def _build_header_section(
    facts_bundle: FactsBundle,
    mode: str,
    diagnostics: dict[str, Any],
) -> EmailSection:
    summary = _diagnostics_dict(diagnostics.get("summary"))
    production = _diagnostics_dict(diagnostics.get("production"))
    operator = _diagnostics_dict(diagnostics.get("operator"))
    selected_mode = (
        production.get("selected_mode")
        or summary.get("selected_production_mode")
        or operator.get("selected_production_mode")
        or mode
    )
    run_date = (
        summary.get("resolved_date")
        or summary.get("requested_date")
        or facts_bundle.run_context.resolved_date_iso
        or facts_bundle.run_context.requested_date_iso
        or "нет данных"
    )
    run_id = diagnostics.get("run_id")
    job_id = diagnostics.get("job_id")
    lines = [
        f"seller: {facts_bundle.run_context.seller_id}",
        f"date: {run_date}",
        f"production_mode: {selected_mode}",
        f"dry_run: {str(bool(facts_bundle.run_context.dry_run)).lower()}",
        f"run_id: {run_id if run_id is not None else 'нет данных'}",
        f"job_id: {job_id if job_id is not None else 'нет данных'}",
    ]
    return EmailSection(title="HEADER", lines=lines, status="confirmed")


def _build_data_availability_section(facts_bundle: FactsBundle, diagnostics: dict[str, Any]) -> EmailSection:
    job = _diagnostics_dict(diagnostics.get("job"))
    source_availability = job.get("source_availability")
    source_map = source_availability if isinstance(source_availability, dict) else {}
    reason_payload = job.get("source_reason_map")
    reason_map = reason_payload if isinstance(reason_payload, dict) else {}
    source_order = ["orders", "sales", "realization", "ads", "stocks", "funnel"]

    lines = [f"wb_api_token_present: {str(bool(facts_bundle.run_context.wb_api_token_present)).lower()}"]
    if not facts_bundle.run_context.wb_api_token_present:
        lines.append(WB_API_LIMITED_MODE_NOTE)
    for source_name in source_order:
        raw = source_map.get(source_name, "missing")
        reason = reason_map.get(source_name)
        if str(reason or "").strip():
            lines.append(f"{source_name}: {_source_status_text(raw)} (raw={raw}, reason={reason})")
        else:
            lines.append(f"{source_name}: {_source_status_text(raw)} (raw={raw})")
    return EmailSection(title="DATA AVAILABILITY", lines=lines, status="partial")


def _build_full_financial_section(facts_bundle: FactsBundle) -> EmailSection:
    section = facts_bundle.sections.get("financial")
    diagnostics = section.diagnostics if isinstance(getattr(section, "diagnostics", None), dict) else {}
    model_mode = str(
        diagnostics.get("financial_model_mode")
        or diagnostics.get("financial_mode")
        or "unavailable"
    )
    confidence = str(diagnostics.get("financial_confidence") or "none")
    profitability_method = str(diagnostics.get("profitability_method") or "unavailable")
    estimate_used = bool(diagnostics.get("profitability_estimate_used", False))
    estimate_formula = str(diagnostics.get("profitability_estimate_formula") or "").strip()
    estimate_warning = str(diagnostics.get("profitability_estimate_warning") or "").strip()
    dependencies = diagnostics.get("profitability_dependencies")
    dependencies_list = list(dependencies) if isinstance(dependencies, list) else []
    blockers = diagnostics.get("profitability_blockers")
    blockers_list = list(blockers) if isinstance(blockers, list) else []

    lines = [
        f"revenue: {_display_fact_value(_find_fact_item('financial', 'revenue_gross', facts_bundle))}",
        f"seller_payout: {_display_fact_value(_find_fact_item('financial', 'seller_payout', facts_bundle))}",
        f"commission: {_display_fact_value(_find_fact_item('financial', 'commission_amount', facts_bundle))}",
        f"logistics: {_display_fact_value(_find_fact_item('financial', 'logistics_cost', facts_bundle))}",
        f"storage: {_display_fact_value(_find_fact_item('financial', 'storage_cost', facts_bundle))}",
        f"acceptance: {_display_fact_value(_find_fact_item('financial', 'acceptance_amount', facts_bundle))}",
        f"paid_acceptance: {_display_fact_value(_find_fact_item('financial', 'paid_acceptance_amount', facts_bundle))}",
        f"net_profit: {_display_fact_value(_find_fact_item('financial', 'net_profit_like', facts_bundle))}",
        f"margin: {_display_fact_value(_find_fact_item('financial', 'margin', facts_bundle))}",
        f"financial_model_mode: {model_mode}",
        f"financial_confidence: {confidence}",
        f"profitability_method: {profitability_method}",
        f"profitability_estimate_used: {str(estimate_used).lower()}",
    ]
    if estimate_formula:
        lines.append(f"profitability_estimate_formula: {estimate_formula}")
    if dependencies_list:
        lines.append(f"profitability_dependencies: {dependencies_list}")
    if blockers_list:
        lines.append(f"profitability_blockers: {blockers_list}")
    if estimate_warning:
        lines.append(f"profitability_estimate_warning: {estimate_warning}")
    return EmailSection(title="FINANCIAL SUMMARY", lines=lines, status=_section_status(facts_bundle, "financial"))


def _build_daily_kpi_section(facts_bundle: FactsBundle) -> EmailSection:
    lines = [
        f"orders: {_display_fact_value(_find_fact_item('daily', 'orders_count', facts_bundle) or _find_fact_item('financial', 'orders_count', facts_bundle))}",
        f"buyouts: {_display_fact_value(_find_fact_item('daily', 'sales_count', facts_bundle) or _find_fact_item('financial', 'sales_count', facts_bundle))}",
        f"conversion: {_display_fact_value(_find_fact_item('funnel', 'cr_orders_from_cart', facts_bundle))}",
        f"avg_check: {_display_fact_value(_find_fact_item('daily', 'avg_check', facts_bundle))}",
    ]
    status = _section_status(facts_bundle, "daily")
    if status == "unavailable" and _section_status(facts_bundle, "financial") != "unavailable":
        status = "partial"
    return EmailSection(title="DAILY KPI", lines=lines, status=status)


def _build_funnel_section(facts_bundle: FactsBundle) -> EmailSection:
    lines = [
        f"views: {_display_fact_value(_find_fact_item('funnel', 'impressions', facts_bundle))}",
        f"add_to_cart: {_display_fact_value(_find_fact_item('funnel', 'cart_adds', facts_bundle))}",
        f"order_rate: {_display_fact_value(_find_fact_item('funnel', 'cr_orders_from_cart', facts_bundle))}",
        f"buyout_rate: {_display_fact_value(_find_fact_item('funnel', 'cr_buys_from_orders', facts_bundle))}",
    ]
    return EmailSection(title="FUNNEL", lines=lines, status=_section_status(facts_bundle, "funnel"))


def _build_ads_section(facts_bundle: FactsBundle) -> EmailSection:
    ads_section = facts_bundle.sections.get("ads")
    warnings = list(ads_section.warnings) if ads_section is not None else []
    warning_text = "; ".join(warnings) if warnings else "none"
    lines = [
        f"spend: {_display_fact_value(_find_fact_item('ads', 'spend', facts_bundle))}",
        f"CPC: {_display_fact_value(_find_fact_item('ads', 'cpc', facts_bundle))}",
        f"ROAS: {_display_fact_value(_find_fact_item('ads', 'roas', facts_bundle))}",
        f"warnings: {warning_text}",
    ]
    return EmailSection(title="ADS", lines=lines, status=_section_status(facts_bundle, "ads"))


def _build_stock_full_section(facts_bundle: FactsBundle) -> EmailSection:
    lines = [
        f"total_stock_units: {_display_fact_value(_find_fact_item('stock', 'total_stock_units', facts_bundle))}",
        f"in_stock_items: {_display_fact_value(_find_fact_item('stock', 'in_stock_items_count', facts_bundle))}",
        f"out_of_stock_items: {_display_fact_value(_find_fact_item('stock', 'out_of_stock_items_count', facts_bundle))}",
    ]
    return EmailSection(title="STOCK", lines=lines, status=_section_status(facts_bundle, "stock"))


def _build_health_full_section(facts_bundle: FactsBundle) -> EmailSection:
    health_section = _build_health_section(facts_bundle)
    lines = list(health_section.lines)
    raw_warnings = facts_bundle.sections.get("health").warnings if facts_bundle.sections.get("health") is not None else []
    warning_text = "; ".join(raw_warnings) if raw_warnings else "none"
    lines.append(f"warnings: {warning_text}")
    return EmailSection(title="HEALTH", lines=lines, status=health_section.status)


def _build_decisions_full_section(decisions_bundle: DecisionsBundle) -> EmailSection:
    by_code = {item.code: item for item in decisions_bundle.items}
    lines: list[str] = []
    unavailable_count = 0
    not_triggered_count = 0

    for code, title, priority in _DECISION_CATALOG:
        item = by_code.get(code)
        if item is None:
            not_triggered_count += 1
            lines.append(
                f"{priority} | {code} | status=not_triggered | {title} | reason=rule not triggered on confirmed evidence"
            )
            continue

        raw_status = _decision_status_text(item)
        status = _decision_full_debug_status(raw_status)
        if status == "unavailable":
            unavailable_count += 1
        lines.append(
            f"{_priority_text(item)} | {item.code} | status={status} | {item.summary} | reason={item.reason}"
        )

    known_codes = {code for code, _, _ in _DECISION_CATALOG}
    for item in sorted(decisions_bundle.items, key=_priority_value):
        if item.code in known_codes:
            continue
        raw_status = _decision_status_text(item)
        status = _decision_full_debug_status(raw_status)
        if status == "unavailable":
            unavailable_count += 1
        lines.append(
            f"{_priority_text(item)} | {item.code} | status={status} | {item.summary} | reason={item.reason}"
        )

    if not lines:
        lines.append("нет данных")
    section_status = "partial" if unavailable_count > 0 or not_triggered_count > 0 else "confirmed"
    return EmailSection(title="DECISIONS", lines=lines, status=section_status)


def _build_diagnostics_section(diagnostics: dict[str, Any]) -> EmailSection:
    job = _diagnostics_dict(diagnostics.get("job"))
    summary = _diagnostics_dict(diagnostics.get("summary"))
    operator = _diagnostics_dict(diagnostics.get("operator"))
    production = _diagnostics_dict(diagnostics.get("production"))
    warnings_payload = job.get("warnings")
    warnings_list = [str(item) for item in warnings_payload] if isinstance(warnings_payload, list) else []
    if not warnings_list:
        fallback_warnings = diagnostics.get("warnings")
        if isinstance(fallback_warnings, list):
            warnings_list = [str(item) for item in fallback_warnings]
    warnings_list = dedupe_warnings(warnings_list)

    source_availability = job.get("source_availability")
    source_flags = source_availability if isinstance(source_availability, dict) else {}
    source_reason_payload = job.get("source_reason_map")
    source_reason_map = source_reason_payload if isinstance(source_reason_payload, dict) else {}
    source_coverage_payload = job.get("source_coverage_summary")
    source_coverage_summary = source_coverage_payload if isinstance(source_coverage_payload, dict) else {}
    available_count = sum(1 for value in source_flags.values() if _source_status_text(value) in {"available", "partial"})
    total_count = len(source_flags)
    data_coverage = f"{available_count}/{total_count}" if total_count > 0 else "0/0"

    selected_mode = (
        production.get("selected_mode")
        or summary.get("selected_production_mode")
        or operator.get("selected_production_mode")
        or "нет данных"
    )
    reason = production.get("switch_reason") or operator.get("switch_reason") or "нет данных"
    rollback_happened = bool(production.get("rollback_happened", False))
    fallback_used = bool(production.get("fallback_used", False))
    missing_sources = job.get("missing_sources")
    missing_list = list(missing_sources) if isinstance(missing_sources, list) else []
    partial_sources = job.get("partial_sources")
    partial_list = list(partial_sources) if isinstance(partial_sources, list) else []

    lines = [
        f"production_mode: {selected_mode}",
        f"mode_resolution_reason: {reason}",
        f"rollback_happened: {str(rollback_happened).lower()}",
        f"fallback_used: {str(fallback_used).lower()}",
        f"partial_flag: {str(bool(summary.get('partial_flag', False))).lower()}",
        f"data_coverage: {data_coverage}",
        f"missing_sources: {missing_list}",
        f"partial_sources: {partial_list}",
    ]

    if source_flags:
        lines.append("source_flags:")
        for name in sorted(source_flags.keys()):
            reason_text = source_reason_map.get(name)
            coverage_text = source_coverage_summary.get(name)
            details: list[str] = [f"raw={source_flags[name]}"]
            if str(reason_text or "").strip():
                details.append(f"reason={reason_text}")
            if str(coverage_text or "").strip():
                details.append(f"coverage={coverage_text}")
            lines.append(f"- {name}: {_source_status_text(source_flags[name])} ({', '.join(details)})")
    else:
        lines.append("source_flags: нет данных")

    lines.append("warnings:")
    if warnings_list:
        lines.extend(f"- {warning}" for warning in warnings_list)
    else:
        lines.append("- none")

    return EmailSection(title="DIAGNOSTICS", lines=lines, status="partial")


def _build_footer_section(facts_bundle: FactsBundle, diagnostics: dict[str, Any]) -> EmailSection:
    summary = _diagnostics_dict(diagnostics.get("summary"))
    job = _diagnostics_dict(diagnostics.get("job"))
    artifacts = diagnostics.get("artifacts")
    artifact_map = artifacts if isinstance(artifacts, dict) else {}
    output_dir = diagnostics.get("output_dir") or summary.get("output_dir_label") or facts_bundle.run_context.output_dir or "нет данных"
    timestamp = job.get("build_timestamp")
    timestamp_value = timestamp if timestamp is not None else "нет данных"
    lines = [f"output_dir: {output_dir}", f"timestamp: {timestamp_value}"]
    if artifact_map:
        lines.append("artifacts:")
        for key in sorted(artifact_map.keys()):
            lines.append(f"- {key}: {artifact_map[key]}")
    else:
        lines.append("artifacts: нет данных")
    return EmailSection(title="FOOTER", lines=lines, status="info")


def _build_full_debug_payload(
    facts_bundle: FactsBundle,
    decisions_bundle: DecisionsBundle,
    mode: str,
    diagnostics: dict[str, Any],
) -> EmailPayload:
    summary = _diagnostics_dict(diagnostics.get("summary"))
    partial_flag = bool(summary.get("partial_flag", _has_partial_data(facts_bundle)))
    summary_lines = [
        "Acceptance / Full Debug Mode: все секции включены, включая unavailable.",
        f"partial_flag={str(partial_flag).lower()}",
    ]
    if not facts_bundle.run_context.wb_api_token_present:
        summary_lines.append(WB_API_LIMITED_MODE_NOTE)
    if mode == "audit":
        summary_lines.append(AUDIT_DISCLAIMER)

    sections = [
        _build_header_section(facts_bundle, mode, diagnostics),
        _build_data_availability_section(facts_bundle, diagnostics),
        _build_full_financial_section(facts_bundle),
        _build_daily_kpi_section(facts_bundle),
        _build_funnel_section(facts_bundle),
        _build_ads_section(facts_bundle),
        _build_stock_full_section(facts_bundle),
        _build_health_full_section(facts_bundle),
        _build_decisions_full_section(decisions_bundle),
        _build_diagnostics_section(diagnostics),
        _build_footer_section(facts_bundle, diagnostics),
    ]

    warnings = [str(item) for item in facts_bundle.warnings] + [str(item) for item in decisions_bundle.warnings]
    diagnostics_warnings = diagnostics.get("warnings")
    if isinstance(diagnostics_warnings, list):
        warnings.extend([str(item) for item in diagnostics_warnings])
    deduped_warnings = dedupe_warnings(warnings)

    subject = f"WB v4 {mode.upper()} FULL DEBUG | {facts_bundle.run_context.seller_id}"
    preheader = (
        f"mode={mode}; dry_run={str(bool(facts_bundle.run_context.dry_run)).lower()}; "
        f"partial={str(partial_flag).lower()}; sections={len(sections)}"
    )
    return EmailPayload(
        subject=subject,
        preheader=preheader,
        mode=mode,
        summary_lines=summary_lines,
        sections=sections,
        warnings=deduped_warnings,
        diagnostics={
            "full_debug": True,
            "sections_count": len(sections),
            "decisions_count": len(decisions_bundle.items),
            "facts_sections_available": list(facts_bundle.sections.keys()),
            "mode": mode,
            "audit_disclaimer_included": mode == "audit",
        },
    )


def build_email_payload(
    facts_bundle: FactsBundle,
    decisions_bundle: DecisionsBundle,
    mode: str = "daily",
    diagnostics: dict[str, Any] | None = None,
    full_debug: bool = False,
) -> EmailPayload:
    normalized_mode = _normalize_mode(mode)
    if full_debug:
        return _build_full_debug_payload(
            facts_bundle=facts_bundle,
            decisions_bundle=decisions_bundle,
            mode=normalized_mode,
            diagnostics=_diagnostics_dict(diagnostics),
        )

    summary_lines = _build_summary_lines(facts_bundle, decisions_bundle, normalized_mode)
    sections: list[EmailSection] = [
        _build_finance_section(facts_bundle),
        _build_decisions_section(decisions_bundle),
        _build_health_section(facts_bundle),
        _build_stock_section(facts_bundle),
        _build_quality_section(facts_bundle, normalized_mode),
    ]

    warnings = dedupe_warnings(list(facts_bundle.warnings) + list(decisions_bundle.warnings))
    payload_diagnostics = {
        "sections_count": len(sections),
        "summary_lines_count": len(summary_lines),
        "decisions_count": len(decisions_bundle.items),
        "facts_sections_available": list(facts_bundle.sections.keys()),
        "mode": normalized_mode,
        "audit_disclaimer_included": normalized_mode == "audit",
    }

    return EmailPayload(
        subject=_build_subject(facts_bundle, decisions_bundle, normalized_mode),
        preheader=f"sections={len(sections)}, decisions={len(decisions_bundle.items)}",
        mode=normalized_mode,
        summary_lines=summary_lines,
        sections=sections,
        warnings=warnings,
        diagnostics=payload_diagnostics,
    )
