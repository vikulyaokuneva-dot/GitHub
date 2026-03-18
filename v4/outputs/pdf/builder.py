"""PDF-ready payload builder over facts + decisions.

Input: FactsBundle and DecisionsBundle.
Output: PdfPayload suitable for future renderer.
Does not render PDF and does not recalculate KPI.
"""

from __future__ import annotations

from ...core.contracts import DecisionItem, DecisionsBundle, FactItem, FactsBundle
from .contracts import PdfBlock, PdfPage, PdfPayload


def _decision_status_text(item: DecisionItem) -> str:
    return item.status.value if hasattr(item.status, "value") else str(item.status)


def _decision_priority_text(item: DecisionItem) -> str:
    return item.priority.value if hasattr(item.priority, "value") else str(item.priority)


def _find_fact_item(facts_bundle: FactsBundle, section_name: str, key: str) -> FactItem | None:
    section = facts_bundle.sections.get(section_name)
    if section is None:
        return None
    for item in section.items:
        if item.key == key:
            return item
    return None


def _render_fact_value(fact_item: FactItem | None) -> str:
    if fact_item is None:
        return "нет данных"
    status = str(fact_item.value.status)
    value = fact_item.value.value
    if status == "unavailable":
        return "нет данных"
    if status == "partial":
        if value is None:
            return "частично"
        return f"{value} (частично)"
    if status == "confirmed":
        return "нет данных" if value is None else str(value)
    if status == "info":
        return "нет данных" if value is None else str(value)
    return "нет данных" if value is None else str(value)


def _executive_page(facts_bundle: FactsBundle, decisions_bundle: DecisionsBundle, mode: str) -> PdfPage:
    partial_flag = bool(facts_bundle.data_quality.get("partial_sections") or facts_bundle.data_quality.get("unavailable_sections"))
    rows = [
        {"label": "Mode", "value": mode, "status": "info"},
        {"label": "Seller", "value": facts_bundle.run_context.seller_id, "status": "info"},
        {"label": "Sections present", "value": list(facts_bundle.sections.keys()), "status": "info"},
        {"label": "Decisions count", "value": len(decisions_bundle.items), "status": "info"},
        {"label": "Partial flag", "value": partial_flag, "status": "info"},
    ]
    block = PdfBlock(title="Executive Summary", rows=rows, status="info", diagnostics={})
    return PdfPage(title="Executive Summary", blocks=[block])


def _finance_page(facts_bundle: FactsBundle) -> PdfPage:
    keys = [
        ("orders_count", "Orders count"),
        ("sales_amount", "Sales amount"),
        ("seller_payout", "Seller payout"),
        ("revenue_gross", "Revenue gross"),
        ("net_profit_like", "Net profit-like"),
    ]
    rows: list[dict[str, str]] = []
    for key, title in keys:
        fact_item = _find_fact_item(facts_bundle, "financial", key)
        rows.append(
            {
                "label": title,
                "value": _render_fact_value(fact_item),
                "status": fact_item.value.status if fact_item is not None else "unavailable",
            }
        )
    section = facts_bundle.sections.get("financial")
    status = section.status if section is not None else "unavailable"
    block = PdfBlock(
        title="Finance Metrics",
        rows=rows,
        status=status,
        diagnostics={"source_quality": section.diagnostics.get("source_quality") if section is not None else None},
    )
    return PdfPage(title="Finance", blocks=[block])


def _decisions_page(decisions_bundle: DecisionsBundle) -> PdfPage:
    rows: list[dict[str, str]] = []
    for item in decisions_bundle.items:
        rows.append(
            {
                "label": f"{_decision_priority_text(item)} {item.title}",
                "value": item.summary,
                "status": _decision_status_text(item),
            }
        )
    if not rows:
        rows.append({"label": "Decisions", "value": "нет данных", "status": "unavailable"})

    status = "confirmed"
    if any(_decision_status_text(item) in {"partial", "unavailable"} for item in decisions_bundle.items):
        status = "partial"
    if not decisions_bundle.items:
        status = "unavailable"

    block = PdfBlock(
        title="Decisions",
        rows=rows,
        status=status,
        diagnostics={"decision_codes": [item.code for item in decisions_bundle.items]},
    )
    return PdfPage(title="Decisions", blocks=[block])


def _stock_page(facts_bundle: FactsBundle) -> PdfPage | None:
    if "stock" not in facts_bundle.sections:
        return None
    keys = [
        ("total_stock_units", "Stock units"),
        ("in_stock_items_count", "In-stock items"),
        ("out_of_stock_items_count", "Out-of-stock items"),
        ("distinct_nm_ids_count", "Distinct nm_id"),
        ("distinct_warehouses_count", "Distinct warehouses"),
    ]
    rows: list[dict[str, str]] = []
    for key, title in keys:
        fact_item = _find_fact_item(facts_bundle, "stock", key)
        rows.append(
            {
                "label": title,
                "value": _render_fact_value(fact_item),
                "status": fact_item.value.status if fact_item is not None else "unavailable",
            }
        )
    section = facts_bundle.sections["stock"]
    block = PdfBlock(
        title="Stock Metrics",
        rows=rows,
        status=section.status,
        diagnostics={"source_quality": section.diagnostics.get("source_quality")},
    )
    return PdfPage(title="Stock", blocks=[block])


def _data_quality_page(facts_bundle: FactsBundle, decisions_bundle: DecisionsBundle) -> PdfPage | None:
    warnings_count = len(facts_bundle.warnings) + len(decisions_bundle.warnings)
    partial_sections = list(facts_bundle.data_quality.get("partial_sections", []))
    unavailable_sections = list(facts_bundle.data_quality.get("unavailable_sections", []))
    if not partial_sections and not unavailable_sections and warnings_count == 0:
        return None

    rows = [
        {"label": "Partial sections", "value": str(partial_sections or []), "status": "partial" if partial_sections else "info"},
        {
            "label": "Unavailable sections",
            "value": str(unavailable_sections or []),
            "status": "partial" if unavailable_sections else "info",
        },
        {"label": "Warnings count", "value": str(warnings_count), "status": "info"},
    ]
    block = PdfBlock(
        title="Data Quality",
        rows=rows,
        status="partial" if partial_sections or unavailable_sections else "info",
        diagnostics={"facts_warnings": len(facts_bundle.warnings), "decisions_warnings": len(decisions_bundle.warnings)},
    )
    return PdfPage(title="Data Quality", blocks=[block])


def build_pdf_payload(
    facts_bundle: FactsBundle,
    decisions_bundle: DecisionsBundle,
    mode: str = "daily",
) -> PdfPayload:
    normalized_mode = "audit" if str(mode).strip().lower() == "audit" else "daily"
    pages: list[PdfPage] = [
        _executive_page(facts_bundle, decisions_bundle, normalized_mode),
        _finance_page(facts_bundle),
        _decisions_page(decisions_bundle),
    ]

    stock_page = _stock_page(facts_bundle)
    if stock_page is not None:
        pages.append(stock_page)

    quality_page = _data_quality_page(facts_bundle, decisions_bundle)
    if quality_page is not None:
        pages.append(quality_page)

    warnings = list(facts_bundle.warnings) + list(decisions_bundle.warnings)
    diagnostics = {
        "pages_count": len(pages),
        "mode": normalized_mode,
        "facts_sections_available": list(facts_bundle.sections.keys()),
        "decisions_count": len(decisions_bundle.items),
    }
    return PdfPayload(
        mode=normalized_mode,
        pages=pages,
        warnings=warnings,
        diagnostics=diagnostics,
    )

