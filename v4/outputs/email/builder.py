"""Email payload builder over facts + decisions.

Input: FactsBundle and DecisionsBundle.
Output: EmailPayload (plain text friendly).
Does not send email and does not recalculate KPI.
"""

from __future__ import annotations

from ...core.contracts import DecisionItem, DecisionsBundle, FactItem, FactsBundle
from .contracts import EmailPayload, EmailSection


def _priority_value(item: DecisionItem) -> int:
    raw = item.priority.value if hasattr(item.priority, "value") else str(item.priority)
    return {"P1": 1, "P2": 2, "P3": 3}.get(raw, 9)


def _priority_text(item: DecisionItem) -> str:
    return item.priority.value if hasattr(item.priority, "value") else str(item.priority)


def _decision_status_text(item: DecisionItem) -> str:
    return item.status.value if hasattr(item.status, "value") else str(item.status)


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

    if _has_partial_data(facts_bundle):
        partial_sections = list(facts_bundle.data_quality.get("partial_sections", []))
        unavailable_sections = list(facts_bundle.data_quality.get("unavailable_sections", []))
        lines.append(
            "Качество данных: частично."
            f" partial={partial_sections or []}, unavailable={unavailable_sections or []}"
        )

    if mode == "audit":
        lines.append("Отчет построен в audit_file_mode; выводы ограничены доступными файлами.")

    return lines


def _build_finance_section(facts_bundle: FactsBundle) -> EmailSection:
    lines = [
        f"Выручка (gross): {_display_fact_value(_find_fact_item('financial', 'revenue_gross', facts_bundle))}",
        f"Выплата продавцу: {_display_fact_value(_find_fact_item('financial', 'seller_payout', facts_bundle))}",
        f"Чистая прибыль-like: {_display_fact_value(_find_fact_item('financial', 'net_profit_like', facts_bundle))}",
    ]
    status = facts_bundle.sections.get("financial").status if "financial" in facts_bundle.sections else "unavailable"
    return EmailSection(title="Финансы", lines=lines, status=status)


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


def _build_stock_section(facts_bundle: FactsBundle) -> EmailSection | None:
    if "stock" not in facts_bundle.sections:
        return None
    lines = [
        f"Всего остатков, шт: {_display_fact_value(_find_fact_item('stock', 'total_stock_units', facts_bundle))}",
        f"In-stock SKU entities: {_display_fact_value(_find_fact_item('stock', 'in_stock_items_count', facts_bundle))}",
        f"Out-of-stock SKU entities: {_display_fact_value(_find_fact_item('stock', 'out_of_stock_items_count', facts_bundle))}",
    ]
    status = facts_bundle.sections["stock"].status
    return EmailSection(title="Остатки / stock", lines=lines, status=status)


def _build_quality_section(facts_bundle: FactsBundle, mode: str) -> EmailSection | None:
    warnings = list(facts_bundle.warnings)
    partial_sections = list(facts_bundle.data_quality.get("partial_sections", []))
    unavailable_sections = list(facts_bundle.data_quality.get("unavailable_sections", []))
    if not warnings and not partial_sections and not unavailable_sections and mode != "audit":
        return None

    lines = [
        f"Partial sections: {partial_sections or []}",
        f"Unavailable sections: {unavailable_sections or []}",
        f"Warnings count: {len(warnings)}",
    ]
    if mode == "audit":
        lines.append("Отчет построен в audit_file_mode; выводы ограничены доступными файлами.")
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


def build_email_payload(
    facts_bundle: FactsBundle,
    decisions_bundle: DecisionsBundle,
    mode: str = "daily",
) -> EmailPayload:
    normalized_mode = "audit" if str(mode).strip().lower() == "audit" else "daily"

    summary_lines = _build_summary_lines(facts_bundle, decisions_bundle, normalized_mode)
    sections: list[EmailSection] = [
        _build_finance_section(facts_bundle),
        _build_decisions_section(decisions_bundle),
    ]

    stock_section = _build_stock_section(facts_bundle)
    if stock_section is not None:
        sections.append(stock_section)

    quality_section = _build_quality_section(facts_bundle, normalized_mode)
    if quality_section is not None:
        sections.append(quality_section)

    warnings = list(facts_bundle.warnings) + list(decisions_bundle.warnings)
    diagnostics = {
        "sections_count": len(sections),
        "summary_lines_count": len(summary_lines),
        "decisions_count": len(decisions_bundle.items),
        "facts_sections_available": list(facts_bundle.sections.keys()),
    }

    return EmailPayload(
        subject=_build_subject(facts_bundle, decisions_bundle, normalized_mode),
        preheader=f"sections={len(sections)}, decisions={len(decisions_bundle.items)}",
        mode=normalized_mode,
        summary_lines=summary_lines,
        sections=sections,
        warnings=warnings,
        diagnostics=diagnostics,
    )

