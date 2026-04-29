from __future__ import annotations

from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


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
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#1F2937"),
            spaceAfter=6,
        ),
        "meta": ParagraphStyle(
            "ReportV2Meta",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#374151"),
            spaceAfter=4,
        ),
        "section": ParagraphStyle(
            "ReportV2Section",
            parent=base["Heading2"],
            fontName=font_name,
            fontSize=12,
            leading=15,
            textColor=colors.HexColor("#111827"),
            spaceAfter=4,
            spaceBefore=6,
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
            leading=10,
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
    return text or "нет данных"


def _status_label(value: Any) -> str:
    status = str(value or "").strip().lower()
    labels = {
        "ok": "Готово",
        "warning": "Внимание",
        "partial": "Частично",
        "lagged": "С лагом",
        "unavailable": "Нет данных",
        "no_data": "Нет данных",
        "disabled": "Отключено",
        "insufficient_data": "Недостаточно данных",
        "missing": "Нет данных",
        "true": "Да",
        "false": "Нет",
    }
    return labels.get(status, _format_text(value))


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
        badge = _status_label(card.get("status"))
        row.append(
            Paragraph(
                (
                    f"<font size=\"8\">{_format_text(card.get('label'))}</font><br/>"
                    f"<font size=\"15\"><b>{_format_text(card.get('value'))}</b></font><br/>"
                    f"<font size=\"8\">{_format_text(card.get('subvalue'))}</font><br/>"
                    f"<font size=\"7\">{badge}</font>"
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
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("BOX", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
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
                Paragraph(_status_label(row.get("status")), style),
            ]
        )

    table = Table(table_rows, colWidths=[width * 0.30, width * 0.22, width * 0.33, width * 0.15])
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


def _funnel_rows_table(rows: list[dict[str, Any]], *, width: float, font_name: str, style: ParagraphStyle) -> Table:
    table_rows: list[list[Paragraph]] = [
        [
            Paragraph("Этап", style),
            Paragraph("Значение", style),
            Paragraph("Источник", style),
            Paragraph("Статус", style),
            Paragraph("Комментарий", style),
        ]
    ]
    for item in rows:
        row = item if isinstance(item, dict) else {}
        table_rows.append(
            [
                Paragraph(_format_text(row.get("stage")), style),
                Paragraph(_format_text(row.get("value")), style),
                Paragraph(_format_text(row.get("source")), style),
                Paragraph(_status_label(row.get("status")), style),
                Paragraph(_format_text(row.get("note")), style),
            ]
        )

    table = Table(table_rows, colWidths=[width * 0.20, width * 0.16, width * 0.22, width * 0.14, width * 0.28])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E7EB")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#111827")),
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def _ads_rows_table(rows: list[dict[str, Any]], *, width: float, font_name: str, style: ParagraphStyle) -> Table:
    table_rows: list[list[Paragraph]] = [
        [
            Paragraph("Показатель", style),
            Paragraph("Значение", style),
            Paragraph("Источник", style),
            Paragraph("Статус", style),
            Paragraph("Комментарий", style),
        ]
    ]
    for item in rows:
        row = item if isinstance(item, dict) else {}
        table_rows.append(
            [
                Paragraph(_format_text(row.get("label")), style),
                Paragraph(_format_text(row.get("value")), style),
                Paragraph(_format_text(row.get("source")), style),
                Paragraph(_status_label(row.get("status")), style),
                Paragraph(_format_text(row.get("note")), style),
            ]
        )

    table = Table(table_rows, colWidths=[width * 0.22, width * 0.18, width * 0.22, width * 0.14, width * 0.24])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E7EB")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#111827")),
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def _format_query_money(value: Any) -> str:
    try:
        if value is None or value == "":
            return "нет данных"
        numeric = float(value)
    except (TypeError, ValueError):
        return "нет данных"
    if numeric.is_integer():
        formatted = f"{int(numeric):,}".replace(",", " ")
    else:
        formatted = f"{numeric:,.2f}".replace(",", " ").replace(".", ",")
    return f"{formatted} ₽"


def _format_query_number(value: Any) -> str:
    try:
        if value is None or value == "":
            return "нет данных"
        numeric = float(value)
    except (TypeError, ValueError):
        return "нет данных"
    if numeric.is_integer():
        return f"{int(numeric):,}".replace(",", " ")
    return f"{numeric:,.2f}".replace(",", " ").replace(".", ",")


def _format_share_percent(value: Any) -> str:
    try:
        if value is None or value == "":
            return "нет данных"
        numeric = float(value)
    except (TypeError, ValueError):
        return "нет данных"
    display_value = numeric * 100.0 if abs(numeric) <= 1.0 else numeric
    if float(display_value).is_integer():
        formatted = f"{int(display_value):,}".replace(",", " ")
    else:
        formatted = f"{display_value:,.2f}".replace(",", " ").replace(".", ",")
    return f"{formatted}%"


def _format_query_status_label(value: Any) -> str:
    status = str(value or "").strip().lower()
    labels = {
        "profitable": "эффективный",
        "unprofitable": "убыточный",
        "neutral": "нейтральный",
        "winner": "эффективный",
        "growth_opportunity": "гипотеза роста",
        "low_conversion": "слабая конверсия",
        "low_relevance": "низкая релевантность",
        "traffic_only": "трафик без продаж",
        "no_orders": "нет заказов",
        "costly": "дорогой запрос",
        "insufficient_data": "недостаточно данных",
    }
    return labels.get(status, _format_text(value))


def _ads_query_rows_table(rows: list[dict[str, Any]], *, width: float, font_name: str, style: ParagraphStyle) -> Table:
    table_rows: list[list[Paragraph]] = [
        [
            Paragraph("Запрос", style),
            Paragraph("Расход", style),
            Paragraph("Заказы", style),
            Paragraph("Выручка", style),
            Paragraph("Прибыль / ROMI", style),
            Paragraph("Статус", style),
        ]
    ]
    for item in rows[:8]:
        row = item if isinstance(item, dict) else {}
        profit = _format_query_money(row.get("profit"))
        romi = _format_query_number(row.get("ROMI") if row.get("ROMI") is not None else row.get("romi"))
        status_label = str(row.get("status_label") or "").strip() or _format_query_status_label(
            row.get("classification") or row.get("status")
        )
        table_rows.append(
            [
                Paragraph(_format_text(row.get("query")), style),
                Paragraph(_format_query_money(row.get("ad_spend")), style),
                Paragraph(_format_query_number(row.get("orders")), style),
                Paragraph(_format_query_money(row.get("revenue")), style),
                Paragraph(f"{profit} / {romi}%", style),
                Paragraph(_format_text(status_label), style),
            ]
        )

    table = Table(
        table_rows,
        colWidths=[width * 0.24, width * 0.15, width * 0.12, width * 0.16, width * 0.20, width * 0.13],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E7EB")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#111827")),
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def _sku_rows_table(rows: list[dict[str, Any]], *, width: float, font_name: str, style: ParagraphStyle) -> Table:
    table_rows: list[list[Paragraph]] = [
        [
            Paragraph("SKU", style),
            Paragraph("Score", style),
            Paragraph("Attention", style),
            Paragraph("Статус", style),
            Paragraph("Причина", style),
            Paragraph("Действие", style),
        ]
    ]
    for item in rows[:10]:
        row = item if isinstance(item, dict) else {}
        score = row.get("health_score") if row.get("health_score") is not None else row.get("score")
        table_rows.append(
            [
                Paragraph(_format_text(row.get("sku") or row.get("nm_id") or row.get("article")), style),
                Paragraph(_format_query_number(score), style),
                Paragraph(_format_query_number(row.get("attention_score")), style),
                Paragraph(_format_text(row.get("status")), style),
                Paragraph(_format_text(row.get("reason")), style),
                Paragraph(_format_text(row.get("recommended_action")), style),
            ]
        )

    table = Table(
        table_rows,
        colWidths=[width * 0.13, width * 0.10, width * 0.11, width * 0.13, width * 0.27, width * 0.26],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E7EB")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#111827")),
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def _profit_sku_rows_table(rows: list[dict[str, Any]], *, width: float, font_name: str, style: ParagraphStyle, limit: int = 10) -> Table:
    table_rows: list[list[Paragraph]] = [
        [
            Paragraph("SKU", style),
            Paragraph("Название", style),
            Paragraph("Выручка", style),
            Paragraph("Прибыль", style),
            Paragraph("Доля", style),
            Paragraph("Статус / действие", style),
        ]
    ]
    for item in rows[:limit]:
        row = item if isinstance(item, dict) else {}
        action = str(row.get("recommended_action") or "").strip()
        status = _format_text(row.get("status"))
        status_action = f"{status}<br/>{_format_text(action)}" if action else status
        table_rows.append(
            [
                Paragraph(_format_text(row.get("sku") or row.get("nm_id")), style),
                Paragraph(_format_text(row.get("name")), style),
                Paragraph(_format_query_money(row.get("revenue")), style),
                Paragraph(_format_query_money(row.get("profit")), style),
                Paragraph(_format_share_percent(row.get("contribution_share")), style),
                Paragraph(status_action, style),
            ]
        )

    table = Table(
        table_rows,
        colWidths=[width * 0.14, width * 0.20, width * 0.14, width * 0.14, width * 0.12, width * 0.26],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E7EB")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#111827")),
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def _abc_sku_rows_table(rows: list[dict[str, Any]], *, width: float, font_name: str, style: ParagraphStyle, limit: int = 10) -> Table:
    table_rows: list[list[Paragraph]] = [
        [
            Paragraph("SKU", style),
            Paragraph("Название", style),
            Paragraph("Категория", style),
            Paragraph("Значение", style),
            Paragraph("Накопленная доля", style),
            Paragraph("Статус", style),
        ]
    ]
    for item in rows[:limit]:
        row = item if isinstance(item, dict) else {}
        table_rows.append(
            [
                Paragraph(_format_text(row.get("sku") or row.get("nm_id")), style),
                Paragraph(_format_text(row.get("name")), style),
                Paragraph(_format_text(row.get("category")), style),
                Paragraph(_format_query_money(row.get("metric_value")), style),
                Paragraph(_format_share_percent(row.get("cumulative_share")), style),
                Paragraph(_format_text(row.get("status")), style),
            ]
        )

    table = Table(
        table_rows,
        colWidths=[width * 0.16, width * 0.22, width * 0.12, width * 0.16, width * 0.18, width * 0.16],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E7EB")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#111827")),
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
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
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("LEADING", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
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
    funnel_section = payload.get("funnel_section", {}) if isinstance(payload, dict) else {}
    if not isinstance(funnel_section, dict):
        funnel_section = {}
    ads_efficiency_section = payload.get("ads_efficiency_section", {}) if isinstance(payload, dict) else {}
    if not isinstance(ads_efficiency_section, dict):
        ads_efficiency_section = {}
    ads_section = payload.get("ads_section", {}) if isinstance(payload, dict) else {}
    if not isinstance(ads_section, dict):
        ads_section = {}
    query_profitability_section = payload.get("query_profitability_section", {}) if isinstance(payload, dict) else {}
    if not isinstance(query_profitability_section, dict):
        query_profitability_section = {}
    sku_health_section = payload.get("sku_health_section", {}) if isinstance(payload, dict) else {}
    if not isinstance(sku_health_section, dict):
        sku_health_section = {}
    profit_contribution_section = payload.get("profit_contribution_section", {}) if isinstance(payload, dict) else {}
    if not isinstance(profit_contribution_section, dict):
        profit_contribution_section = {}
    abc_analysis_section = payload.get("abc_analysis_section", {}) if isinstance(payload, dict) else {}
    if not isinstance(abc_analysis_section, dict):
        abc_analysis_section = {}
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
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
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
                f"{_format_text(hero.get('data_status_message'))}<br/>"
                f"Источник данных: {_format_text(meta.get('snapshot_source_mode'))}"
            ),
            styles["meta"],
        )
    )
    story.append(Spacer(1, 6))

    commerce_rows = commerce_section.get("rows", [])
    if not isinstance(commerce_rows, list):
        commerce_rows = []
    story.append(Paragraph(_format_text(commerce_section.get("title")), styles["section"]))
    story.append(Paragraph(_format_text(commerce_section.get("subtitle")), styles["meta"]))
    story.append(_display_rows_table(commerce_rows, width=content_width, font_name=font_info["font_name"], style=styles["hero_card"]))
    story.append(Spacer(1, 6))

    funnel_rows = funnel_section.get("rows", [])
    if not isinstance(funnel_rows, list):
        funnel_rows = []
    story.append(Paragraph(_format_text(funnel_section.get("title")), styles["section"]))
    story.append(Paragraph(_format_text(funnel_section.get("subtitle")), styles["meta"]))
    story.append(Paragraph(_format_text(funnel_section.get("message")), styles["warning"]))
    story.append(_funnel_rows_table(funnel_rows, width=content_width, font_name=font_info["font_name"], style=styles["hero_card"]))
    story.append(Spacer(1, 6))

    ads_rows = ads_efficiency_section.get("metric_rows") or ads_section.get("rows", [])
    if not isinstance(ads_rows, list):
        ads_rows = []
    story.append(Paragraph(_format_text(ads_efficiency_section.get("title") or ads_section.get("title")), styles["section"]))
    story.append(Paragraph(_format_text(ads_efficiency_section.get("subtitle") or ads_section.get("subtitle")), styles["meta"]))
    story.append(Paragraph(_format_text(ads_efficiency_section.get("message") or ads_section.get("message")), styles["warning"]))
    story.append(_ads_rows_table(ads_rows, width=content_width, font_name=font_info["font_name"], style=styles["hero_card"]))
    loss_rows = ads_efficiency_section.get("loss_rows", [])
    if not isinstance(loss_rows, list):
        loss_rows = []
    opportunity_rows = ads_efficiency_section.get("opportunity_rows", [])
    if not isinstance(opportunity_rows, list):
        opportunity_rows = []
    recommendations = ads_efficiency_section.get("recommendations", [])
    if not isinstance(recommendations, list):
        recommendations = []
    if loss_rows:
        story.append(Paragraph("Потери рекламы", styles["section"]))
        story.append(_ads_query_rows_table(loss_rows, width=content_width, font_name=font_info["font_name"], style=styles["hero_card"]))
    if opportunity_rows:
        story.append(Paragraph("Прибыльные и перспективные запросы", styles["section"]))
        story.append(_ads_query_rows_table(opportunity_rows, width=content_width, font_name=font_info["font_name"], style=styles["hero_card"]))
    if recommendations:
        story.append(Paragraph("Рекомендации по рекламе", styles["section"]))
        for item in recommendations[:5]:
            story.append(Paragraph(f"- {_format_text(item)}", styles["warning"]))
    story.append(Spacer(1, 6))

    query_loss_rows = query_profitability_section.get("top_loss_queries", [])
    if not isinstance(query_loss_rows, list):
        query_loss_rows = []
    query_weak_rows = query_profitability_section.get("weak_queries", [])
    if not isinstance(query_weak_rows, list):
        query_weak_rows = []
    query_performing_rows = query_profitability_section.get("top_performing_queries", [])
    if not isinstance(query_performing_rows, list):
        query_performing_rows = []
    query_status = str(query_profitability_section.get("status") or "no_data").strip().lower()
    story.append(Paragraph(_format_text(query_profitability_section.get("title") or "Поисковые запросы"), styles["section"]))
    story.append(Paragraph(_format_text(query_profitability_section.get("subtitle") or "Прибыльность и качество поисковых запросов."), styles["meta"]))
    story.append(Paragraph(_format_text(query_profitability_section.get("message") or "Данные query_profitability.json недоступны."), styles["warning"]))
    if query_status != "no_data":
        if query_loss_rows:
            story.append(Paragraph("TOP убыточных запросов", styles["section"]))
            story.append(_ads_query_rows_table(query_loss_rows, width=content_width, font_name=font_info["font_name"], style=styles["hero_card"]))
        if query_weak_rows:
            story.append(Paragraph("Слабые запросы", styles["section"]))
            story.append(_ads_query_rows_table(query_weak_rows, width=content_width, font_name=font_info["font_name"], style=styles["hero_card"]))
        if query_performing_rows:
            story.append(Paragraph("Эффективные запросы", styles["section"]))
            story.append(_ads_query_rows_table(query_performing_rows, width=content_width, font_name=font_info["font_name"], style=styles["hero_card"]))
    story.append(Spacer(1, 6))

    sku_summary_rows = sku_health_section.get("summary_rows", [])
    if not isinstance(sku_summary_rows, list):
        sku_summary_rows = []
    sku_risk_rows = sku_health_section.get("risk_rows", [])
    if not isinstance(sku_risk_rows, list):
        sku_risk_rows = []
    sku_growth_rows = sku_health_section.get("growth_rows", [])
    if not isinstance(sku_growth_rows, list):
        sku_growth_rows = []
    sku_attention_rows = sku_health_section.get("attention_rows", [])
    if not isinstance(sku_attention_rows, list):
        sku_attention_rows = []
    sku_alert_rows = sku_health_section.get("alerts", [])
    if not isinstance(sku_alert_rows, list):
        sku_alert_rows = []
    story.append(Paragraph(_format_text(sku_health_section.get("title")), styles["section"]))
    story.append(Paragraph(_format_text(sku_health_section.get("subtitle")), styles["meta"]))
    story.append(Paragraph(_format_text(sku_health_section.get("message")), styles["warning"]))
    if sku_summary_rows:
        story.append(_display_rows_table(sku_summary_rows, width=content_width, font_name=font_info["font_name"], style=styles["hero_card"]))
    if sku_risk_rows:
        story.append(Paragraph("SKU под риском", styles["section"]))
        story.append(_sku_rows_table(sku_risk_rows, width=content_width, font_name=font_info["font_name"], style=styles["hero_card"]))
    if sku_growth_rows:
        story.append(Paragraph("SKU для роста", styles["section"]))
        story.append(_sku_rows_table(sku_growth_rows, width=content_width, font_name=font_info["font_name"], style=styles["hero_card"]))
    if sku_attention_rows:
        story.append(Paragraph("SKU требуют внимания", styles["section"]))
        story.append(_sku_rows_table(sku_attention_rows, width=content_width, font_name=font_info["font_name"], style=styles["hero_card"]))
    if sku_alert_rows:
        story.append(Paragraph("Alert-ы по SKU", styles["section"]))
        story.append(_sku_rows_table(sku_alert_rows[:10], width=content_width, font_name=font_info["font_name"], style=styles["hero_card"]))
    story.append(Spacer(1, 6))

    profit_summary_rows = profit_contribution_section.get("summary_rows", [])
    if not isinstance(profit_summary_rows, list):
        profit_summary_rows = []
    profit_top_rows = profit_contribution_section.get("top_profit_skus", [])
    if not isinstance(profit_top_rows, list):
        profit_top_rows = []
    profit_loss_rows = profit_contribution_section.get("loss_skus", [])
    if not isinstance(profit_loss_rows, list):
        profit_loss_rows = []
    profit_status = str(profit_contribution_section.get("status") or "no_data").strip().lower()
    story.append(Paragraph(_format_text(profit_contribution_section.get("title") or "Прибыль по товарам"), styles["section"]))
    story.append(Paragraph(_format_text(profit_contribution_section.get("subtitle") or "Вклад SKU в прибыль."), styles["meta"]))
    story.append(Paragraph(_format_text(profit_contribution_section.get("message") or "Данные profit_contribution.json недоступны."), styles["warning"]))
    if profit_status != "no_data":
        if profit_summary_rows:
            story.append(_display_rows_table(profit_summary_rows, width=content_width, font_name=font_info["font_name"], style=styles["hero_card"]))
        if profit_top_rows:
            story.append(Paragraph("Топ прибыльных SKU", styles["section"]))
            story.append(_profit_sku_rows_table(profit_top_rows, width=content_width, font_name=font_info["font_name"], style=styles["hero_card"], limit=10))
        if profit_loss_rows:
            story.append(Paragraph("Убыточные SKU", styles["section"]))
            story.append(_profit_sku_rows_table(profit_loss_rows, width=content_width, font_name=font_info["font_name"], style=styles["hero_card"], limit=10))
    story.append(Spacer(1, 6))

    abc_summary_rows = abc_analysis_section.get("summary_rows", [])
    if not isinstance(abc_summary_rows, list):
        abc_summary_rows = []
    abc_categories = abc_analysis_section.get("categories", {})
    if not isinstance(abc_categories, dict):
        abc_categories = {}
    abc_a_rows = abc_categories.get("A", [])
    if not isinstance(abc_a_rows, list):
        abc_a_rows = []
    abc_b_rows = abc_categories.get("B", [])
    if not isinstance(abc_b_rows, list):
        abc_b_rows = []
    abc_c_rows = abc_categories.get("C", [])
    if not isinstance(abc_c_rows, list):
        abc_c_rows = []
    abc_status = str(abc_analysis_section.get("status") or "no_data").strip().lower()
    story.append(Paragraph(_format_text(abc_analysis_section.get("title") or "ABC-анализ"), styles["section"]))
    story.append(Paragraph(_format_text(abc_analysis_section.get("subtitle") or "ABC-категории SKU."), styles["meta"]))
    story.append(Paragraph(_format_text(abc_analysis_section.get("message") or "Данные abc_analysis.json недоступны."), styles["warning"]))
    if abc_status != "no_data":
        if abc_summary_rows:
            story.append(_display_rows_table(abc_summary_rows, width=content_width, font_name=font_info["font_name"], style=styles["hero_card"]))
        if abc_a_rows:
            story.append(Paragraph("A-SKU: ключевые товары", styles["section"]))
            story.append(_abc_sku_rows_table(abc_a_rows, width=content_width, font_name=font_info["font_name"], style=styles["hero_card"], limit=10))
        if abc_b_rows:
            story.append(Paragraph("B-SKU", styles["section"]))
            story.append(_abc_sku_rows_table(abc_b_rows, width=content_width, font_name=font_info["font_name"], style=styles["hero_card"], limit=5))
        if abc_c_rows:
            story.append(Paragraph("C-SKU", styles["section"]))
            story.append(_abc_sku_rows_table(abc_c_rows, width=content_width, font_name=font_info["font_name"], style=styles["hero_card"], limit=5))
    story.append(Spacer(1, 6))

    finance_notice_state = str(finance_notice.get("state") or "ok").strip().lower()
    if finance_notice_state != "ok":
        title = _format_text(finance_notice.get("title"))
        lines = finance_notice.get("lines", [])
        if not isinstance(lines, list):
            lines = []
        story.append(Paragraph(title, styles["warning"]))
        for line in lines:
            story.append(Paragraph(f"- {_format_text(line)}", styles["warning"]))
        story.append(Spacer(1, 3))

    finance_rows = finance_section.get("rows", [])
    if not isinstance(finance_rows, list):
        finance_rows = []
    story.append(Paragraph(_format_text(finance_section.get("title")), styles["section"]))
    story.append(Paragraph(_format_text(finance_section.get("subtitle")), styles["meta"]))
    story.append(_display_rows_table(finance_rows, width=content_width, font_name=font_info["font_name"], style=styles["hero_card"]))
    story.append(Spacer(1, 6))

    live_rows = live_section.get("rows", [])
    if not isinstance(live_rows, list):
        live_rows = []
    story.append(Paragraph(_format_text(live_section.get("title")), styles["section"]))
    story.append(Paragraph(_format_text(live_section.get("subtitle")), styles["meta"]))
    story.append(_display_rows_table(live_rows, width=content_width, font_name=font_info["font_name"], style=styles["hero_card"]))
    story.append(Spacer(1, 6))

    story.append(PageBreak())
    story.append(Paragraph("Диагностика источников", styles["section"]))
    diagnostic_warnings = diagnostics.get("warnings", [])
    if not isinstance(diagnostic_warnings, list):
        diagnostic_warnings = []
    if diagnostic_warnings:
        story.append(Paragraph("Предупреждения", styles["body"]))
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
        story.append(Paragraph("Предупреждений нет.", styles["body"]))

    source_flags = diagnostics.get("source_flags", [])
    if not isinstance(source_flags, list):
        source_flags = []
    if source_flags:
        story.append(Spacer(1, 6))
        rows: list[tuple[str, str, str]] = [("Флаг", "Значение", "Статус")]
        for item in source_flags:
            if not isinstance(item, dict):
                continue
            rows.append(
                (
                    _format_text(item.get("name")),
                    _format_text(item.get("value")),
                    _status_label(item.get("status")),
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
        "funnel_section_rows_count": len(funnel_rows),
        "funnel_section_status": _format_text(funnel_section.get("status")),
        "ads_section_rows_count": len(ads_rows),
        "ads_section_status": _format_text(ads_efficiency_section.get("status") or ads_section.get("status")),
        "ads_efficiency_section_status": _format_text(ads_efficiency_section.get("status")),
        "ads_efficiency_loss_rows_count": len(loss_rows),
        "ads_efficiency_opportunity_rows_count": len(opportunity_rows),
        "query_profitability_section_status": _format_text(query_profitability_section.get("status")),
        "query_profitability_loss_rows_count": len(query_loss_rows),
        "query_profitability_weak_rows_count": len(query_weak_rows),
        "query_profitability_performing_rows_count": len(query_performing_rows),
        "sku_health_section_status": _format_text(sku_health_section.get("status")),
        "sku_health_summary_rows_count": len(sku_summary_rows),
        "sku_health_risk_rows_count": len(sku_risk_rows),
        "sku_health_growth_rows_count": len(sku_growth_rows),
        "sku_health_attention_rows_count": len(sku_attention_rows),
        "sku_health_alert_rows_count": len(sku_alert_rows),
        "profit_contribution_section_status": _format_text(profit_contribution_section.get("status")),
        "profit_contribution_top_rows_count": len(profit_top_rows),
        "profit_contribution_loss_rows_count": len(profit_loss_rows),
        "abc_analysis_section_status": _format_text(abc_analysis_section.get("status")),
        "abc_analysis_a_rows_count": len(abc_a_rows),
        "abc_analysis_b_rows_count": len(abc_b_rows),
        "abc_analysis_c_rows_count": len(abc_c_rows),
        "finance_section_rows_count": len(finance_rows),
        "live_section_rows_count": len(live_rows),
        "diagnostics_on_new_page": True,
        "diagnostics_warnings_count": len(diagnostic_warnings),
        "diagnostics_source_flags_count": len(source_flags),
    }
