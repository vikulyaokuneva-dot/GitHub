from __future__ import annotations

from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


FONT_NAME = "ReportV2DejaVu"


def _ensure_font_registered() -> dict[str, str]:
    font_path = Path(__file__).resolve().parents[2] / "assets" / "fonts" / "DejaVuSans.ttf"
    if font_path.is_file():
        try:
            pdfmetrics.getFont(FONT_NAME)
        except KeyError:
            pdfmetrics.registerFont(TTFont(FONT_NAME, str(font_path)))
        return {"font_name": FONT_NAME, "font_path": str(font_path)}
    return {"font_name": "Helvetica", "font_path": ""}


def _styles(font_name: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ReportV2Title",
            parent=base["Heading1"],
            fontName=font_name,
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#1F2937"),
            spaceAfter=8,
        ),
        "meta": ParagraphStyle(
            "ReportV2Meta",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#374151"),
        ),
        "section": ParagraphStyle(
            "ReportV2Section",
            parent=base["Heading2"],
            fontName=font_name,
            fontSize=13,
            leading=16,
            textColor=colors.HexColor("#111827"),
            spaceAfter=6,
            spaceBefore=8,
        ),
        "body": ParagraphStyle(
            "ReportV2Body",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#111827"),
        ),
        "warning": ParagraphStyle(
            "ReportV2Warning",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#7C2D12"),
        ),
        "hero_card": ParagraphStyle(
            "ReportV2HeroCard",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#111827"),
        ),
    }


def _format_count(value: Any) -> str:
    if value is None:
        return "unavailable"
    return f"{int(value)}"


def _format_money(value: Any) -> str:
    if value is None:
        return "unavailable"
    return f"{float(value):,.2f}".replace(",", " ")


def _format_text(value: Any) -> str:
    text = str(value or "").strip()
    return text or "unavailable"


def _section_table(rows: list[tuple[str, str]], *, width: float, font_name: str) -> Table:
    table = Table(rows, colWidths=[width * 0.48, width * 0.52])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E7EB")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#111827")),
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("LEADING", (0, 0), (-1, -1), 11),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _hero_cards_table(cards: list[dict[str, Any]], *, width: float, font_name: str, style: ParagraphStyle) -> Table:
    row: list[Paragraph] = []
    for item in cards[:4]:
        card = item if isinstance(item, dict) else {}
        row.append(
            Paragraph(
                (
                    f"{_format_text(card.get('label'))}<br/>"
                    f"<b>{_format_text(card.get('value'))}</b><br/>"
                    f"{_format_text(card.get('subvalue'))}<br/>"
                    f"status: {_format_text(card.get('status'))}"
                ),
                style,
            )
        )
    while len(row) < 4:
        row.append(Paragraph("", style))

    table = Table([row], colWidths=[width * 0.25] * 4)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F9FAFB")),
                ("BOX", (0, 0), (-1, -1), 0.35, colors.HexColor("#D1D5DB")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E7EB")),
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def _display_rows_table(rows: list[dict[str, Any]], *, width: float, font_name: str, style: ParagraphStyle) -> Table:
    table_rows: list[list[Paragraph]] = [
        [
            Paragraph("Показатель", style),
            Paragraph("Значение", style),
            Paragraph("Комментарий", style),
            Paragraph("Статус", style),
        ]
    ]
    for item in rows:
        row = item if isinstance(item, dict) else {}
        table_rows.append(
            [
                Paragraph(_format_text(row.get("label")), style),
                Paragraph(_format_text(row.get("value")), style),
                Paragraph(_format_text(row.get("note")), style),
                Paragraph(_format_text(row.get("status")), style),
            ]
        )

    table = Table(table_rows, colWidths=[width * 0.28, width * 0.22, width * 0.34, width * 0.16])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E7EB")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#111827")),
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def _source_flags_table(rows: list[tuple[str, str, str]], *, width: float, font_name: str) -> Table:
    table = Table(rows, colWidths=[width * 0.42, width * 0.36, width * 0.22])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E7EB")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#111827")),
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("LEADING", (0, 0), (-1, -1), 10),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def write_report_pdf_v2(path: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
    font_info = _ensure_font_registered()
    styles = _styles(font_info["font_name"])

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
    hero = payload.get("hero", {}) if isinstance(payload, dict) else {}
    if not isinstance(hero, dict):
        hero = {}
    commerce_section = payload.get("commerce_section", {}) if isinstance(payload, dict) else {}
    if not isinstance(commerce_section, dict):
        commerce_section = {}
    finance_section = payload.get("finance_section", {}) if isinstance(payload, dict) else {}
    if not isinstance(finance_section, dict):
        finance_section = {}
    finance_notice = payload.get("finance_alignment_notice", {}) if isinstance(payload, dict) else {}
    if not isinstance(finance_notice, dict):
        finance_notice = {}
    live_section = payload.get("live_section", {}) if isinstance(payload, dict) else {}
    if not isinstance(live_section, dict):
        live_section = {}
    diagnostics = payload.get("diagnostics", {}) if isinstance(payload, dict) else {}
    if not isinstance(diagnostics, dict):
        diagnostics = {}

    doc = SimpleDocTemplate(
        str(target),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )
    content_width = A4[0] - doc.leftMargin - doc.rightMargin

    story: list[Any] = []
    hero_cards = hero.get("cards", [])
    if not isinstance(hero_cards, list):
        hero_cards = []
    story.append(Paragraph(_format_text(hero.get("title") or "WB Core Report v2"), styles["title"]))
    story.append(Paragraph(_format_text(hero.get("subtitle")), styles["meta"]))
    if hero_cards:
        story.append(Spacer(1, 6))
        story.append(_hero_cards_table(hero_cards, width=content_width, font_name=font_info["font_name"], style=styles["hero_card"]))
    story.append(
        Paragraph(
            (
                f"data_status: {_format_text(hero.get('data_status'))}<br/>"
                f"{_format_text(hero.get('data_status_message'))}<br/>"
                f"snapshot_source_mode: {_format_text(meta.get('snapshot_source_mode'))}"
            ),
            styles["meta"],
        )
    )
    story.append(Spacer(1, 8))

    commerce_rows = commerce_section.get("rows", [])
    if not isinstance(commerce_rows, list):
        commerce_rows = []
    story.append(Paragraph(_format_text(commerce_section.get("title")), styles["section"]))
    story.append(Paragraph(_format_text(commerce_section.get("subtitle")), styles["meta"]))
    story.append(_display_rows_table(commerce_rows, width=content_width, font_name=font_info["font_name"], style=styles["hero_card"]))
    story.append(Spacer(1, 8))

    finance_notice_state = str(finance_notice.get("state") or "ok").strip().lower()
    if finance_notice_state != "ok":
        title = _format_text(finance_notice.get("title"))
        lines = finance_notice.get("lines", [])
        if not isinstance(lines, list):
            lines = []
        story.append(Paragraph(title, styles["warning"]))
        for line in lines:
            story.append(Paragraph(f"- {_format_text(line)}", styles["warning"]))
        story.append(Spacer(1, 4))

    finance_rows = finance_section.get("rows", [])
    if not isinstance(finance_rows, list):
        finance_rows = []
    story.append(Paragraph(_format_text(finance_section.get("title")), styles["section"]))
    story.append(Paragraph(_format_text(finance_section.get("subtitle")), styles["meta"]))
    story.append(_display_rows_table(finance_rows, width=content_width, font_name=font_info["font_name"], style=styles["hero_card"]))
    story.append(Spacer(1, 8))

    live_rows = live_section.get("rows", [])
    if not isinstance(live_rows, list):
        live_rows = []
    story.append(Paragraph(_format_text(live_section.get("title")), styles["section"]))
    story.append(Paragraph(_format_text(live_section.get("subtitle")), styles["meta"]))
    story.append(_display_rows_table(live_rows, width=content_width, font_name=font_info["font_name"], style=styles["hero_card"]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Диагностика источников", styles["section"]))
    diagnostic_warnings = diagnostics.get("warnings", [])
    if not isinstance(diagnostic_warnings, list):
        diagnostic_warnings = []
    if diagnostic_warnings:
        story.append(Paragraph("Warnings", styles["body"]))
        for item in diagnostic_warnings:
            if not isinstance(item, dict):
                story.append(Paragraph(f"- {_format_text(item)}", styles["warning"]))
                continue
            code = _format_text(item.get("code"))
            message = _format_text(item.get("message"))
            block = _format_text(item.get("block"))
            level = _format_text(item.get("level"))
            story.append(Paragraph(f"- [{level}/{block}] {code}: {message}", styles["warning"]))
    else:
        story.append(Paragraph("No diagnostics warnings.", styles["body"]))

    source_flags = diagnostics.get("source_flags", [])
    if not isinstance(source_flags, list):
        source_flags = []
    if source_flags:
        story.append(Spacer(1, 6))
        rows: list[tuple[str, str, str]] = [("Name", "Value", "Status")]
        for item in source_flags:
            if not isinstance(item, dict):
                continue
            rows.append(
                (
                    _format_text(item.get("name")),
                    _format_text(item.get("value")),
                    _format_text(item.get("status")),
                )
            )
        story.append(_source_flags_table(rows, width=content_width, font_name=font_info["font_name"]))

    doc.build(story)
    return {
        "pdf_path": str(target),
        "font_name": font_info["font_name"],
        "font_path": font_info["font_path"],
        "finance_section_state": finance_notice_state or "ok",
        "finance_notice_state": finance_notice_state or "ok",
        "hero_cards_count": len(hero_cards),
        "hero_data_status": _format_text(hero.get("data_status")),
        "commerce_section_rows_count": len(commerce_rows),
        "finance_section_rows_count": len(finance_rows),
        "live_section_rows_count": len(live_rows),
        "diagnostics_warnings_count": len(diagnostic_warnings),
        "diagnostics_source_flags_count": len(source_flags),
    }
