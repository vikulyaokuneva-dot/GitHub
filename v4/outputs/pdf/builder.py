"""PDF-ready payload builder over facts + decisions.

Input: FactsBundle and DecisionsBundle.
Output: PdfPayload suitable for renderer.
Does not render PDF and does not recalculate KPI.
"""

from __future__ import annotations

from ...core.contracts import DecisionItem, DecisionsBundle, FactsBundle
from .contracts import PdfBlock, PdfPage, PdfPayload
from .view_model import (
    build_kpi_cards,
    map_ads_section,
    map_finance_section,
    map_funnel_section,
    map_health_section,
    map_stock_section,
)


AUDIT_DISCLAIMER = "Отчет построен в audit_file_mode; выводы ограничены доступными файлами."
ESTIMATE_EXPLANATION_RU = "Оценочный расчет, не основанный на финальной реализации"

_DECISION_TITLE_RU: dict[str, str] = {
    "negative_profit": "Отрицательная прибыль",
    "low_margin": "Низкая маржинальность",
    "ad_inefficiency": "Неэффективная реклама",
    "out_of_stock_risk": "Риск дефицита",
    "weak_conversion": "Слабая конверсия",
    "overstock": "Риск оверстока",
    "dead_sku": "Риск неликвида",
    "low_business_health": "Снижение здоровья бизнеса",
    "partial_data_warning": "Ограниченность данных",
}


def _decision_status_text(item: DecisionItem) -> str:
    return item.status.value if hasattr(item.status, "value") else str(item.status)


def _decision_priority_text(item: DecisionItem) -> str:
    return item.priority.value if hasattr(item.priority, "value") else str(item.priority)


def _decision_status_ru(status: str) -> str:
    token = str(status or "").strip().lower()
    if token == "confirmed":
        return "подтверждено"
    if token == "partial":
        return "частично подтверждено"
    if token == "unavailable":
        return "нет данных"
    return token or "нет данных"


def _financial_estimate_mode(facts_bundle: FactsBundle) -> bool:
    financial = facts_bundle.sections.get("financial")
    diagnostics = financial.diagnostics if financial is not None and isinstance(financial.diagnostics, dict) else {}
    model_mode = str(diagnostics.get("financial_model_mode") or diagnostics.get("financial_mode") or "")
    estimate_used = bool(diagnostics.get("profitability_estimate_used", False))
    return model_mode == "estimated" or estimate_used


def _executive_page(facts_bundle: FactsBundle, decisions_bundle: DecisionsBundle, mode: str) -> PdfPage:
    partial_flag = bool(facts_bundle.data_quality.get("partial_sections") or facts_bundle.data_quality.get("unavailable_sections"))

    kpi_rows = list(build_kpi_cards(facts_bundle))
    summary_rows = [
        {"label": "Режим", "value": mode, "status": "confirmed"},
        {"label": "Продавец", "value": facts_bundle.run_context.seller_id, "status": "confirmed"},
        {"label": "Разделов в отчете", "value": len(facts_bundle.sections), "status": "confirmed"},
        {"label": "Количество рекомендаций", "value": len(decisions_bundle.items), "status": "confirmed"},
        {"label": "Признак неполных данных", "value": "да" if partial_flag else "нет", "status": "confirmed"},
    ]
    if mode == "audit":
        summary_rows.append({"label": "Примечание audit", "value": AUDIT_DISCLAIMER, "status": "confirmed"})

    funnel_rows = map_funnel_section(facts_bundle)

    blocks = [
        PdfBlock(title="Ключевые KPI", rows=kpi_rows, status="confirmed", diagnostics={"mode": mode}),
        PdfBlock(title="Сводка запуска", rows=summary_rows, status="confirmed", diagnostics={"mode": mode}),
        PdfBlock(title="Воронка", rows=funnel_rows, status="confirmed"),
    ]
    return PdfPage(title="Ключевые показатели дня", blocks=blocks)


def _finance_ads_page(facts_bundle: FactsBundle) -> PdfPage:
    section = facts_bundle.sections.get("financial")
    section_diag = section.diagnostics if isinstance(getattr(section, "diagnostics", None), dict) else {}
    model_mode = str(section_diag.get("financial_model_mode") or section_diag.get("financial_mode") or "")
    confidence = str(section_diag.get("financial_confidence") or "none")
    is_estimated = _financial_estimate_mode(facts_bundle)

    finance_rows = map_finance_section(facts_bundle)
    finance_rows.append({"label": "Режим финансовой модели", "value": model_mode or "нет данных", "status": "confirmed"})
    finance_rows.append({"label": "Уверенность модели", "value": confidence, "status": "confirmed"})
    if is_estimated:
        finance_rows.append(
            {
                "label": "Комментарий к прибыли",
                "value": ESTIMATE_EXPLANATION_RU,
                "status": "confirmed",
            }
        )

    ads_map = map_ads_section(facts_bundle)
    ads_rows: list[dict[str, str]]
    if ads_map.get("has_data"):
        ads_rows = list(ads_map.get("rows", []))
    else:
        ads_rows = [
            {
                "label": "Реклама",
                "value": str(ads_map.get("message") or "Данные по рекламе отсутствуют"),
                "status": "unavailable",
            }
        ]

    finance_block = PdfBlock(
        title="Финансовая структура дня",
        rows=finance_rows,
        status=section.status if section is not None else "unavailable",
        diagnostics={"source_quality": section.diagnostics.get("source_quality") if section is not None else None},
    )
    ads_block = PdfBlock(title="Рекламный блок", rows=ads_rows, status="confirmed")
    return PdfPage(title="Финансы и реклама", blocks=[finance_block, ads_block])


def _decisions_page(decisions_bundle: DecisionsBundle) -> PdfPage:
    rows: list[dict[str, str]] = []
    for item in decisions_bundle.items:
        title_ru = _DECISION_TITLE_RU.get(item.code, item.title)
        status_ru = _decision_status_ru(_decision_status_text(item))
        rows.append(
            {
                "label": f"{_decision_priority_text(item)} {title_ru}",
                "value": f"{item.summary}. Причина: {item.reason}",
                "status": "confirmed",
            }
        )
        rows.append({"label": "Статус рекомендации", "value": status_ru, "status": "confirmed"})
    if not rows:
        rows.append({"label": "Рекомендации", "value": "нет данных", "status": "unavailable"})

    status = "confirmed"
    if any(_decision_status_text(item) in {"partial", "unavailable"} for item in decisions_bundle.items):
        status = "partial"
    if not decisions_bundle.items:
        status = "unavailable"

    block = PdfBlock(
        title="Рекомендации по действиям",
        rows=rows,
        status=status,
        diagnostics={"decision_codes": [item.code for item in decisions_bundle.items]},
    )
    return PdfPage(title="Рекомендации", blocks=[block])


def _stock_page(facts_bundle: FactsBundle) -> PdfPage | None:
    if "stock" not in facts_bundle.sections:
        return None
    rows = map_stock_section(facts_bundle)
    section = facts_bundle.sections["stock"]
    block = PdfBlock(
        title="Складская ситуация",
        rows=rows,
        status=section.status,
        diagnostics={"source_quality": section.diagnostics.get("source_quality")},
    )
    return PdfPage(title="Остатки", blocks=[block])


def _health_page(facts_bundle: FactsBundle) -> PdfPage | None:
    health_section = facts_bundle.sections.get("health")
    if health_section is None:
        return None

    rows = map_health_section(facts_bundle)

    block = PdfBlock(
        title="Состояние товарного портфеля",
        rows=rows,
        status=health_section.status,
        diagnostics={
            "source_quality": health_section.diagnostics.get("source_quality"),
            "policy_version": health_section.diagnostics.get("policy_version"),
            "component_statuses": health_section.diagnostics.get("component_statuses"),
        },
    )
    return PdfPage(title="Оценка товаров", blocks=[block])


def _data_quality_page(facts_bundle: FactsBundle, decisions_bundle: DecisionsBundle, mode: str) -> PdfPage | None:
    warnings_count = len(facts_bundle.warnings) + len(decisions_bundle.warnings)
    partial_sections = list(facts_bundle.data_quality.get("partial_sections", []))
    unavailable_sections = list(facts_bundle.data_quality.get("unavailable_sections", []))
    if not partial_sections and not unavailable_sections and warnings_count == 0 and mode != "audit":
        return None

    rows = [
        {"label": "Частично заполненные разделы", "value": str(partial_sections or []), "status": "partial" if partial_sections else "confirmed"},
        {
            "label": "Недоступные разделы",
            "value": str(unavailable_sections or []),
            "status": "partial" if unavailable_sections else "confirmed",
        },
        {"label": "Количество предупреждений", "value": str(warnings_count), "status": "confirmed"},
    ]
    if mode == "audit":
        rows.append({"label": "Примечание audit", "value": AUDIT_DISCLAIMER, "status": "confirmed"})

    block = PdfBlock(
        title="Диагностика источников",
        rows=rows,
        status="partial" if partial_sections or unavailable_sections else "info",
        diagnostics={
            "facts_warnings": len(facts_bundle.warnings),
            "decisions_warnings": len(decisions_bundle.warnings),
            "mode": mode,
        },
    )
    return PdfPage(title="Качество данных", blocks=[block])


def build_pdf_payload(
    facts_bundle: FactsBundle,
    decisions_bundle: DecisionsBundle,
    mode: str = "daily",
) -> PdfPayload:
    normalized_mode = "audit" if str(mode).strip().lower() == "audit" else "daily"
    pages: list[PdfPage] = [
        _executive_page(facts_bundle, decisions_bundle, normalized_mode),
        _finance_ads_page(facts_bundle),
        _decisions_page(decisions_bundle),
    ]

    stock_page = _stock_page(facts_bundle)
    if stock_page is not None:
        pages.append(stock_page)

    health_page = _health_page(facts_bundle)
    if health_page is not None:
        pages.append(health_page)

    quality_page = _data_quality_page(facts_bundle, decisions_bundle, normalized_mode)
    if quality_page is not None:
        pages.append(quality_page)

    warnings = list(facts_bundle.warnings) + list(decisions_bundle.warnings)
    diagnostics = {
        "pages_count": len(pages),
        "mode": normalized_mode,
        "facts_sections_available": list(facts_bundle.sections.keys()),
        "decisions_count": len(decisions_bundle.items),
        "audit_disclaimer_included": normalized_mode == "audit",
    }
    return PdfPayload(
        mode=normalized_mode,
        pages=pages,
        warnings=warnings,
        diagnostics=diagnostics,
    )

