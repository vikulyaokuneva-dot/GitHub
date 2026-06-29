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
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Circle
from reportlab.graphics.charts.barcharts import VerticalBarChart


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
    safe_cards = [item if isinstance(item, dict) else {} for item in cards]
    if not safe_cards:
        safe_cards = [{}]
    column_count = min(max(len(safe_cards), 1), 5)
    table_rows: list[list[Paragraph]] = []
    for start in range(0, len(safe_cards), column_count):
        row: list[Paragraph] = []
        for card in safe_cards[start : start + column_count]:
            row.append(
                Paragraph(
                    (
                        f"<font size=\"8\">{_format_text(card.get('label'))}</font><br/>"
                        f"<font size=\"15\"><b>{_format_text(card.get('value'))}</b></font>"
                    ),
                    style,
                )
            )
        while len(row) < column_count:
            row.append(Paragraph("", style))
        table_rows.append(row)

    table = Table(table_rows, colWidths=[width / column_count] * column_count)
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
        ]
    ]
    for item in rows:
        row = item if isinstance(item, dict) else {}
        table_rows.append(
            [
                Paragraph(_format_text(row.get("label")), style),
                Paragraph(_format_text(row.get("value")), style),
            ]
        )

    table = Table(table_rows, colWidths=[width * 0.45, width * 0.55])
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


def _parse_pct(val: str | None) -> float | None:
    if not val or val in ("н/д", "нет данных", ""):
        return None
    cleaned = val.replace("%", "").replace("+", "").replace(" ", "").replace(",", ".").strip()
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _calc_delta_from_values(today_str: str, yesterday_str: str) -> float | None:
    def _to_num(s: str) -> float | None:
        if not s or s in ("н/д", "нет данных", ""):
            return None
        cleaned = s.replace("₽", "").replace("шт", "").replace("%", "").replace("+", "").replace(" ", "").replace(",", ".").strip()
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return None
    t = _to_num(today_str)
    y = _to_num(yesterday_str)
    if t is None or y is None:
        return None
    if y == 0:
        return None
    return round((t - y) / abs(y) * 100, 1)


def _table_with_comparison(
    rows_data: list[dict[str, Any]],
    *,
    width: float,
    font_name: str,
    style: ParagraphStyle,
    key_map: dict[str, str] | None = None,
    headers: list[str] | None = None,
    label_key: str = "label",
    value_key: str = "value",
) -> Table:
    sd_map: dict[str, dict[str, Any]] = {}
    if key_map:
        sd_map = key_map
    hdrs = headers or ["Показатель", "Вчера", "Позавчера", "Изменение"]
    table_rows: list[list[Paragraph]] = [[Paragraph(h, style) for h in hdrs]]
    delta_list: list[float | None] = []
    for item in rows_data:
        row = item if isinstance(item, dict) else {}
        label = _format_text(row.get(label_key, ""))
        value = _format_text(row.get(value_key, ""))
        match = sd_map.get(label, {})
        today_val = _format_text(match.get("today", "")) if match else ""
        prev_val = _format_text(match.get("yesterday", "н/д")) if match else "н/д"
        delta_pct = _calc_delta_from_values(today_val, prev_val)
        if delta_pct is not None and delta_pct > 0:
            delta_cell = Paragraph(f'<font color="#166534">+{abs(delta_pct):.1f}%</font>', style)
        elif delta_pct is not None and delta_pct < 0:
            delta_cell = Paragraph(f'<font color="#991B1B">{delta_pct:.1f}%</font>', style)
        else:
            delta_cell = Paragraph("н/д", style)
        delta_list.append(delta_pct)
        table_rows.append([
            Paragraph(label, style),
            Paragraph(value, style),
            Paragraph(prev_val, style),
            delta_cell,
        ])

    col_w = [width * 0.30, width * 0.25, width * 0.25, width * 0.20]
    table = Table(table_rows, colWidths=col_w)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16A34A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    for idx, dp in enumerate(delta_list):
        row_idx = idx + 1
        if dp is not None and dp > 0:
            style_cmds.append(("BACKGROUND", (3, row_idx), (3, row_idx), colors.HexColor("#DCFCE7")))
        elif dp is not None and dp < 0:
            style_cmds.append(("BACKGROUND", (3, row_idx), (3, row_idx), colors.HexColor("#FEE2E2")))
    table.setStyle(TableStyle(style_cmds))
    return table


def _funnel_rows_table(rows: list[dict[str, Any]], *, width: float, font_name: str, style: ParagraphStyle) -> Table:
    table_rows: list[list[Paragraph]] = [
        [
            Paragraph("Этап", style),
            Paragraph("Значение", style),
        ]
    ]
    for item in rows:
        row = item if isinstance(item, dict) else {}
        table_rows.append(
            [
                Paragraph(_format_text(row.get("stage")), style),
                Paragraph(_format_text(row.get("value")), style),
            ]
        )

    table = Table(table_rows, colWidths=[width * 0.45, width * 0.55])
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
        ]
    ]
    for item in rows:
        row = item if isinstance(item, dict) else {}
        table_rows.append(
            [
                Paragraph(_format_text(row.get("label")), style),
                Paragraph(_format_text(row.get("value")), style),
            ]
        )

    table = Table(table_rows, colWidths=[width * 0.45, width * 0.55])
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


def _abc_section_sku_rows_table(rows: list[dict[str, Any]], *, width: float, font_name: str, style: ParagraphStyle, limit: int = 8) -> Table:
    table_rows: list[list[Paragraph]] = [
        [
            Paragraph("SKU", style),
            Paragraph("Название", style),
            Paragraph("ABC", style),
            Paragraph("Выручка", style),
            Paragraph("Прибыль / маржа", style),
            Paragraph("Реклама", style),
            Paragraph("Причина / действие", style),
        ]
    ]
    for item in rows[:limit]:
        row = item if isinstance(item, dict) else {}
        profit_margin = _format_share_percent(row.get("profit_margin"))
        reason = _format_text(row.get("reason"))
        action = _format_text(row.get("recommended_action"))
        reason_action = reason if action == "нет данных" else f"{reason}<br/>{action}"
        table_rows.append(
            [
                Paragraph(_format_text(row.get("sku") or row.get("nm_id")), style),
                Paragraph(_format_text(row.get("name")), style),
                Paragraph(_format_text(row.get("abc_class")), style),
                Paragraph(_format_query_money(row.get("revenue")), style),
                Paragraph(f"{_format_query_money(row.get('profit'))}<br/>{profit_margin}", style),
                Paragraph(_format_query_money(row.get("ad_spend")), style),
                Paragraph(reason_action, style),
            ]
        )

    table = Table(
        table_rows,
        colWidths=[
            width * 0.12,
            width * 0.17,
            width * 0.07,
            width * 0.13,
            width * 0.16,
            width * 0.12,
            width * 0.23,
        ],
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




def _sku_detail_table(sku: dict[str, Any], *, width: float, font_name: str, style: ParagraphStyle) -> Table:
    rows_data = [
        ("Заказы", f"{sku.get('orders_count', 0)} шт"),
        ("Выкупы", f"{sku.get('buyouts_count', 0)} шт"),
        ("Выручка", _format_money(sku.get("revenue"))),
        ("Себестоимость", _format_money(-sku.get("cogs", 0)) if sku.get("cogs") else None),
        ("Комиссия WB", _format_money(-sku.get("commission", 0)) if sku.get("commission") else None),
        ("Логистика", _format_money(-sku.get("logistics", 0))),
        ("Эквайринг", _format_money(-sku.get("acquiring", 0)) if sku.get("acquiring") else None),
        ("Хранение", _format_money(-sku.get("storage_share", 0)) if sku.get("storage_share") else None),
        ("Удержания", _format_money(-sku.get("deductions_share", 0)) if sku.get("deductions_share") else None),
        ("Реклама", _format_money(-sku.get("ads_spend", 0)) if sku.get("ads_spend") else None),
        ("Чистая прибыль", _format_money(sku.get("profit"))),
        ("Маржа", f"{sku.get('margin_pct', 0)}%"),
        ("Доля выручки", f"{sku.get('share_pct', 0)}%"),
    ]
    table_rows = [[Paragraph("Метрика", style), Paragraph("Значение", style)]]
    for label, value in rows_data:
        if value is None:
            continue
        table_rows.append([Paragraph(label, style), Paragraph(str(value), style)])
    table = Table(table_rows, colWidths=[width * 0.5, width * 0.5])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16A34A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, -2), (-1, -2), colors.HexColor("#e8f5e9")),
    ]))
    return table


def _sku_funnel_table(funnel: dict[str, Any], *, width: float, font_name: str, style: ParagraphStyle) -> Table:
    impressions = funnel.get("impressions", 0)
    views = funnel.get("views", 0)
    cart = funnel.get("cart", 0)
    orders = funnel.get("orders", 0)
    buyouts = funnel.get("buyouts", 0)
    ctr = funnel.get("ctr_pct", 0)
    cr_cart = funnel.get("cr_cart_pct", 0)
    cr_order = funnel.get("cr_order_pct", 0)
    imp_to_click = round(views / impressions * 100, 1) if impressions else 0
    rows_data = [
        ("Показы", str(impressions) if impressions else "—", f"{imp_to_click}%" if impressions else "—"),
        ("Клики", str(views), "—"),
        ("Корзина", str(cart), f"{ctr}% CTR" if views else "—"),
        ("Заказы", str(orders), f"{cr_cart}%" if cart else "—"),
        ("Выкупы", str(buyouts), f"{cr_order}%" if orders else "—"),
    ]
    table_rows = [[Paragraph("Этап", style), Paragraph("Значение", style), Paragraph("Конверсия", style)]]
    for label, value, conv in rows_data:
        table_rows.append([Paragraph(label, style), Paragraph(value, style), Paragraph(conv, style)])
    table = Table(table_rows, colWidths=[width * 0.33, width * 0.33, width * 0.34])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4a90e2")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#e3f2fd"), colors.HexColor("#bbdefb")]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return table


def _render_sku_block(story: list[Any], rank: int, sku: dict[str, Any], styles: dict[str, ParagraphStyle], content_width: float, font_name: str) -> None:
    nm_id = sku.get("nm_id", "")
    seller_article = sku.get("seller_article", "")
    title = sku.get("title", "")
    header_text = f"ТОП-{rank}: {nm_id}"
    if seller_article:
        header_text += f" | {seller_article}"
    story.append(Paragraph(header_text, styles["section"]))
    if title:
        story.append(Paragraph(_format_text(title), styles["meta"]))
    half_width = content_width / 2 - 2 * mm
    unit_table = _sku_detail_table(sku, width=half_width, font_name=font_name, style=styles["hero_card"])
    funnel = sku.get("funnel", {})
    has_funnel = any(v for k, v in funnel.items() if k not in ("ctr_pct", "cr_cart_pct", "cr_order_pct") and v)
    if has_funnel:
        funnel_table = _sku_funnel_table(funnel, width=half_width, font_name=font_name, style=styles["hero_card"])
        outer = Table([[unit_table, funnel_table]], colWidths=[half_width + 2 * mm, half_width + 2 * mm])
        outer.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        story.append(outer)
    else:
        story.append(unit_table)
    story.append(Spacer(1, 8))


def write_report_pdf_v2(path: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
    font_info = _ensure_font_registered()
    styles = _styles(font_info["font_name"])

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
    hero = payload.get("hero", {}) if isinstance(payload, dict) else {}
    if not isinstance(hero, dict):
        hero = {}
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

    hero_section = payload.get("hero_section", {})
    if not isinstance(hero_section, dict):
        hero_section = {}
    hero_rows = hero_section.get("rows", [])

    sales_dynamics_raw = payload.get("sales_dynamics_section", {}) if isinstance(payload, dict) else {}
    if not isinstance(sales_dynamics_raw, dict):
        sales_dynamics_raw = {}
    sd_rows_raw = sales_dynamics_raw.get("rows", [])
    sd_map: dict[str, dict[str, Any]] = {}
    if isinstance(sd_rows_raw, list):
        for _r in sd_rows_raw:
            if isinstance(_r, dict):
                sd_map[_r.get("label", "")] = _r
    sd_label_aliases = {
        "Сумма выкупов": "Выручка",
        "Сумма заказов": "Заказы",
    }
    for alias, target in sd_label_aliases.items():
        if target in sd_map and alias not in sd_map:
            sd_map[alias] = sd_map[target]
    for _key in ("Реклама",):
        if _key in sd_map:
            for _fld in ("today", "yesterday", "week_ago"):
                _v = sd_map[_key].get(_fld, "")
                if _v and _v not in ("н/д", "нет данных") and not _v.startswith("-"):
                    sd_map[_key][_fld] = f"-{_v}"
    if isinstance(hero_rows, list):
        for _hr in hero_rows:
            if not isinstance(_hr, dict):
                continue
            _hl = _hr.get("label", "")
            _hv = _hr.get("value", "")
            if _hl in sd_map and sd_map[_hl].get("today") in ("нет данных", "", None):
                sd_map[_hl]["today"] = _hv
    funnel_comparison: dict[str, dict[str, Any]] = {}
    _meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
    _seller_id = _meta.get("seller_id", "")
    _op_date = _meta.get("operational_date", "")
    if _seller_id and _op_date:
        import json as _json_mod
        from pathlib import Path as _Path
        _hist_path = _Path("cabinets") / _seller_id / "history" / "history_index.json"
        if not _hist_path.is_file():
            _hist_path = _Path(__file__).resolve().parents[2] / "cabinets" / _seller_id / "history" / "history_index.json"
        if not _hist_path.is_file():
            _hist_path = _Path(r"D:\WB\Бот ИИ менеджер\GitHub\cabinets") / _seller_id / "history" / "history_index.json"
        if _hist_path.is_file():
            try:
                _hist = _json_mod.load(open(_hist_path, encoding="utf-8"))
                _snaps = _hist.get("snapshots", []) if isinstance(_hist, dict) else []
                _today_funnel = {}
                _yesterday_funnel = {}
                for _s in _snaps:
                    if not isinstance(_s, dict):
                        continue
                    if _s.get("date") == _op_date:
                        _today_funnel = _s.get("kpi", {}).get("funnel", {})
                    _y_date = ""
                    try:
                        from datetime import datetime as _dt, timedelta as _td
                        _y_date = (_dt.strptime(_op_date, "%Y-%m-%d") - _td(days=1)).strftime("%Y-%m-%d")
                    except Exception:
                        pass
                    if _s.get("date") == _y_date:
                        _yesterday_funnel = _s.get("kpi", {}).get("funnel", {})
                _funnel_stage_map = {
                    "Показы": "impressions", "Клики": "clicks", "Корзина": "cart",
                    "Заказы": "orders", "Выкупы": "buyouts",
                }
                _fmt_funnel = lambda v: f"{int(v)} шт" if v and v == int(v) else f"{v} шт" if v else "н/д"
                for _stage, _key in _funnel_stage_map.items():
                    _t = _today_funnel.get(_key)
                    _y = _yesterday_funnel.get(_key)
                    _vs = None
                    if _t is not None and _y is not None and _y != 0:
                        _vs = round((_t - _y) / abs(_y) * 100, 1)
                    _vs_str = f"{_vs:+.1f}%" if _vs is not None else "н/д"
                    funnel_comparison[_stage] = {
                        "today": _fmt_funnel(_t) if _t is not None else "н/д",
                        "yesterday": _fmt_funnel(_y) if _y is not None else "н/д",
                        "vs_yesterday": _vs_str,
                    }
                _conv_pairs = [
                    ("Показы → Клики", "clicks", "impressions"),
                    ("Клики → Корзина", "cart", "clicks"),
                    ("Корзина → Заказ", "orders", "cart"),
                    ("Заказ → Выкуп", "buyouts", "orders"),
                ]
                for _cstage, _num_key, _den_key in _conv_pairs:
                    _tn = _today_funnel.get(_num_key)
                    _td = _today_funnel.get(_den_key)
                    _yn = _yesterday_funnel.get(_num_key)
                    _yd = _yesterday_funnel.get(_den_key)
                    _t_pct = round(_tn / _td * 100, 1) if _tn is not None and _td and _td > 0 else None
                    _y_pct = round(_yn / _yd * 100, 1) if _yn is not None and _yd and _yd > 0 else None
                    _cv = None
                    if _t_pct is not None and _y_pct is not None and _y_pct != 0:
                        _cv = round((_t_pct - _y_pct) / abs(_y_pct) * 100, 1)
                    _cv_str = f"{_cv:+.1f}%" if _cv is not None else "н/д"
                    funnel_comparison[_cstage] = {
                        "today": f"{_t_pct:.1f}%" if _t_pct is not None else "нет данных",
                        "yesterday": f"{_y_pct:.1f}%" if _y_pct is not None else "нет данных",
                        "vs_yesterday": _cv_str,
                    }
            except Exception:
                pass
    if isinstance(hero_rows, list) and hero_rows:
        story.append(Paragraph(_format_text(hero_section.get("title") or "Ежедневный отчёт WB"), styles["title"]))
        story.append(Paragraph(_format_text(hero_section.get("subtitle")), styles["meta"]))
        story.append(Spacer(1, 6))

        alert_boxes = hero_section.get("alert_boxes", [])
        if isinstance(alert_boxes, list) and alert_boxes and len(alert_boxes) >= 3:
            box_colors = {"critical": colors.HexColor("#DC2626"), "warning": colors.HexColor("#D97706"), "ok": colors.HexColor("#16A34A")}
            box_bg = {"critical": colors.HexColor("#FEF2F2"), "warning": colors.HexColor("#FFFBEB"), "ok": colors.HexColor("#F0FDF4")}
            box_style = ParagraphStyle("BoxText", parent=styles["hero_card"], fontSize=8, leading=10, alignment=1)
            box_label_style = ParagraphStyle("BoxLabel", parent=styles["hero_card"], fontSize=7, leading=9, alignment=1, textColor=colors.HexColor("#6B7280"))
            box_cells = []
            for box in alert_boxes[:3]:
                if not isinstance(box, dict):
                    continue
                status = box.get("status", "ok")
                cell_color = box_colors.get(status, colors.black)
                cell_bg = box_bg.get(status, colors.white)
                label_p = Paragraph(f"<font color='#6B7280'>{_format_text(box.get('label', ''))}</font>", box_label_style)
                value_p = Paragraph(f"<b><font color='{cell_color.hexval()}'>{_format_text(box.get('value', ''))}</font></b>", box_style)
                detail_p = Paragraph(f"<font color='#6B7280'>{_format_text(box.get('detail', ''))}</font>", box_label_style)
                cell_content = Table([[label_p], [value_p], [detail_p]], colWidths=[content_width / 3 - 4 * mm])
                cell_content.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), cell_bg),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
                ]))
                box_cells.append(cell_content)
            if len(box_cells) >= 3:
                boxes_row = Table([box_cells], colWidths=[content_width / 3 - 2 * mm] * 3)
                boxes_row.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ]))
                story.append(boxes_row)
                story.append(Spacer(1, 6))

        story.append(_table_with_comparison(hero_rows, width=content_width, font_name=font_info["font_name"], style=styles["hero_card"], key_map=sd_map))
        story.append(Spacer(1, 4))

        hero_actions = hero_section.get("actions", [])
        if isinstance(hero_actions, list) and hero_actions:
            action_header_style = ParagraphStyle("ActionHeader", parent=styles["section"], textColor=colors.HexColor("#1a1a2e"))
            story.append(Paragraph("Что делать сегодня:", action_header_style))
            act_header_style = ParagraphStyle("ActHeader", parent=styles["hero_card"], textColor=colors.white)
            act_table_rows = [[Paragraph(h, act_header_style) for h in ['#', 'Действие', 'Эффект']]]
            for idx, act in enumerate(hero_actions[:5]):
                if not isinstance(act, dict):
                    continue
                priority = act.get("priority", "info")
                effect = act.get("effect", "")
                act_table_rows.append([
                    Paragraph(str(idx + 1), styles["hero_card"]),
                    Paragraph(_format_text(act.get("text", "")), styles["hero_card"]),
                    Paragraph(_format_text(effect), styles["hero_card"]),
                ])
            act_table = Table(act_table_rows, colWidths=[content_width * 0.05, content_width * 0.55, content_width * 0.40])
            act_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16A34A")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
            ]))
            story.append(act_table)
            story.append(Spacer(1, 6))

    losses = payload.get("losses_of_the_day", {}) if isinstance(payload, dict) else {}
    if not isinstance(losses, dict):
        losses = {}
    loss_items = losses.get("items", [])
    if isinstance(loss_items, list) and loss_items:
        story.append(Paragraph(_format_text(losses.get("title") or "Потери дня"), styles["section"]))
        loss_header_style = ParagraphStyle("LossHeader", parent=styles["hero_card"], textColor=colors.white)
        loss_table_rows = [[Paragraph(h, loss_header_style) for h in ['Статья', 'Сумма']]]
        for item in loss_items:
            if not isinstance(item, dict):
                continue
            loss_table_rows.append([
                Paragraph(_format_text(item.get("label", "")), styles["hero_card"]),
                Paragraph(_format_text(item.get("value", "")), styles["hero_card"]),
            ])
        total_loss = losses.get("total", "0 ₽")
        loss_table_rows.append([
            Paragraph("Итого", styles["hero_card"]),
            Paragraph(_format_text(total_loss), styles["hero_card"]),
        ])
        loss_table = Table(loss_table_rows, colWidths=[content_width * 0.6, content_width * 0.4])
        loss_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7C2D12")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#FEF2F2")),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
        ]))
        story.append(loss_table)
        story.append(Spacer(1, 6))

    profit_section = payload.get("profit_section", {})
    if not isinstance(profit_section, dict):
        profit_section = {}
    profit_rows = profit_section.get("rows", [])
    if isinstance(profit_rows, list) and profit_rows:
        story.append(Paragraph(_format_text(profit_section.get("title") or "Прибыль"), styles["section"]))
        profit_header_style = ParagraphStyle("ProfitHeader", parent=styles["hero_card"], textColor=colors.white)
        p_table_rows = [[Paragraph("Показатель", profit_header_style), Paragraph("Значение", profit_header_style)]]
        for row in profit_rows:
            if not isinstance(row, dict):
                continue
            label = _format_text(row.get("label", ""))
            value = _format_text(row.get("value", ""))
            val_str = value.replace("₽", "").replace(" ", "").replace(",", ".").strip()
            try:
                val_num = float(val_str)
            except (ValueError, TypeError):
                val_num = 0
            is_negative = "-" in value and val_num < 0
            is_positive_profit = "прибыль" in label.lower() and val_num > 0
            if is_negative:
                row_bg = colors.HexColor("#FEF2F2")
                val_color = colors.HexColor("#DC2626")
            elif is_positive_profit:
                row_bg = colors.HexColor("#F0FDF4")
                val_color = colors.HexColor("#16A34A")
            else:
                row_bg = colors.white
                val_color = colors.black
            val_style = ParagraphStyle("ValColor", parent=styles["hero_card"], textColor=val_color)
            p_table_rows.append([
                Paragraph(label, styles["hero_card"]),
                Paragraph(value, val_style),
            ])
        profit_table = Table(p_table_rows, colWidths=[content_width * 0.5, content_width * 0.5])
        profit_style_list = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]
        for idx, row in enumerate(profit_rows):
            if not isinstance(row, dict):
                continue
            label = _format_text(row.get("label", ""))
            value = _format_text(row.get("value", ""))
            val_str = value.replace("₽", "").replace(" ", "").replace(",", ".").strip()
            try:
                val_num = float(val_str)
            except (ValueError, TypeError):
                val_num = 0
            is_negative = "-" in value and val_num < 0
            is_positive_profit = "прибыль" in label.lower() and val_num > 0
            if is_negative:
                profit_style_list.append(("BACKGROUND", (0, idx + 1), (-1, idx + 1), colors.HexColor("#FEF2F2")))
            elif is_positive_profit:
                profit_style_list.append(("BACKGROUND", (0, idx + 1), (-1, idx + 1), colors.HexColor("#F0FDF4")))
        profit_table.setStyle(TableStyle(profit_style_list))
        story.append(profit_table)
        story.append(Spacer(1, 6))

    story.append(PageBreak())

    funnel_section = payload.get("funnel_section", {}) if isinstance(payload, dict) else {}
    if not isinstance(funnel_section, dict):
        funnel_section = {}
    funnel_rows = funnel_section.get("rows", [])
    if not isinstance(funnel_rows, list):
        funnel_rows = []
    funnel_sd: dict[str, dict[str, Any]] = {}
    for fr in funnel_rows:
        if isinstance(fr, dict):
            stage = fr.get("stage", "")
            if stage in sd_map:
                funnel_sd[stage] = sd_map[stage]
    story.append(Paragraph(_format_text(funnel_section.get("title")), styles["section"]))
    story.append(_table_with_comparison(funnel_rows, width=content_width, font_name=font_info["font_name"], style=styles["hero_card"], key_map=funnel_comparison, label_key="stage", value_key="value"))
    story.append(Spacer(1, 6))

    ads_section = payload.get("ads_section", {}) if isinstance(payload, dict) else {}
    if not isinstance(ads_section, dict):
        ads_section = {}
    ads_efficiency_section = payload.get("ads_efficiency_section", {}) if isinstance(payload, dict) else {}
    if not isinstance(ads_efficiency_section, dict):
        ads_efficiency_section = {}
    ads_rows = ads_efficiency_section.get("metric_rows") or ads_section.get("rows", [])
    if not isinstance(ads_rows, list):
        ads_rows = []
    ads_sd: dict[str, dict[str, Any]] = {}
    ads_label_map = {"Spend": "Реклама", "Расход": "Реклама"}
    for ar in ads_rows:
        if isinstance(ar, dict):
            lbl = ar.get("label", "")
            mapped = ads_label_map.get(lbl, lbl)
            if mapped in sd_map:
                ads_sd[lbl] = sd_map[mapped]
    story.append(Paragraph(_format_text(ads_efficiency_section.get("title") or ads_section.get("title")), styles["section"]))
    story.append(_ads_rows_table(ads_rows, width=content_width, font_name=font_info["font_name"], style=styles["hero_card"]))
    story.append(Spacer(1, 6))

    _ads_history = {}
    _orders_history = {}
    _meta_ads = payload.get("meta", {}) if isinstance(payload, dict) else {}
    _sid_ads = _meta_ads.get("seller_id", "")
    _opd_ads = _meta_ads.get("operational_date", "")
    _hi = {}
    if _sid_ads and _opd_ads:
        import json as _ja
        from pathlib import Path as _Pa
        from datetime import datetime as _dta, timedelta as _tda
        _hp = _Pa(r"D:\WB\Бот ИИ менеджер\GitHub\cabinets") / _sid_ads / "history" / "history_index.json"
        if not _hp.is_file():
            _hp = _Pa("cabinets") / _sid_ads / "history" / "history_index.json"
        if _hp.is_file():
            try:
                _hi = _ja.load(open(_hp, encoding="utf-8"))
                for _s in _hi.get("snapshots", []):
                    if isinstance(_s, dict):
                        _d = _s.get("date", "")
                        _a = _s.get("kpi", {}).get("ads_spend")
                        _ov = _s.get("kpi", {}).get("orders_amount")
                        if _d:
                            if _a is not None:
                                _ads_history[_d] = float(_a)
                            if _ov is not None:
                                _orders_history[_d] = float(_ov)
            except Exception:
                pass
    if _ads_history:
        _today_d = _opd_ads
        _dates = []
        try:
            _base_d = _dta.strptime(_today_d, "%Y-%m-%d")
            for _i in range(6, -1, -1):
                _dd = (_base_d - _tda(days=_i)).strftime("%Y-%m-%d")
                _dates.append(_dd)
        except Exception:
            pass
        if _dates:
            _spend_vals = [_ads_history.get(d, 0) for d in _dates]
            _orders_vals = [_orders_history.get(d, 0) for d in _dates]
            _labels = [d[-5:] for d in _dates]
            _drawing = Drawing(content_width, 160)
            _drawing.add(String(content_width / 2, 145, "Расходы на рекламу и сумма заказов за 7 дней (₽)", fontName=font_info["font_name"], fontSize=9, textAnchor="middle", fillColor=colors.HexColor("#374151")))
            _chart_left = 50
            _chart_right = content_width - 30
            _chart_top = 125
            _chart_bottom = 30
            _chart_w = _chart_right - _chart_left
            _chart_h = _chart_top - _chart_bottom
            _all_vals = _spend_vals + _orders_vals
            _max_val = max(_all_vals) if _all_vals and max(_all_vals) > 0 else 1
            _n = len(_spend_vals)
            _step = _chart_w / max(_n - 1, 1)
            _pts_spend = []
            _pts_orders = []
            for _i in range(_n):
                _x = _chart_left + _i * _step
                _ys = _chart_bottom + (_spend_vals[_i] / _max_val) * _chart_h if _max_val > 0 else _chart_bottom
                _yo = _chart_bottom + (_orders_vals[_i] / _max_val) * _chart_h if _max_val > 0 else _chart_bottom
                _pts_spend.append((_x, _ys, _spend_vals[_i]))
                _pts_orders.append((_x, _yo, _orders_vals[_i]))
            for _j in range(len(_pts_spend) - 1):
                _drawing.add(Line(_pts_spend[_j][0], _pts_spend[_j][1], _pts_spend[_j + 1][0], _pts_spend[_j + 1][1], strokeColor=colors.HexColor("#DC2626"), strokeWidth=2))
                _drawing.add(Line(_pts_orders[_j][0], _pts_orders[_j][1], _pts_orders[_j + 1][0], _pts_orders[_j + 1][1], strokeColor=colors.HexColor("#2563EB"), strokeWidth=2))
            for _x, _y, _v in _pts_spend:
                _drawing.add(Circle(_x, _y, 3, fillColor=colors.HexColor("#DC2626"), strokeColor=colors.white, strokeWidth=1))
                _vt = f"{_v:.0f}" if _v == int(_v) else f"{_v:.1f}"
                if _v > 0:
                    _drawing.add(String(_x, _y + 8, _vt, fontName=font_info["font_name"], fontSize=7, textAnchor="middle", fillColor=colors.HexColor("#DC2626")))
            for _x, _y, _v in _pts_orders:
                _drawing.add(Circle(_x, _y, 3, fillColor=colors.HexColor("#2563EB"), strokeColor=colors.white, strokeWidth=1))
                if _v > 0:
                    _drawing.add(String(_x, _y - 12, f"{_v:.0f}", fontName=font_info["font_name"], fontSize=7, textAnchor="middle", fillColor=colors.HexColor("#2563EB")))
            for _i, _lb in enumerate(_labels):
                _drawing.add(String(_chart_left + _i * _step, _chart_bottom - 12, _lb, fontName=font_info["font_name"], fontSize=7, textAnchor="middle", fillColor=colors.HexColor("#6B7280")))
            _drawing.add(Line(_chart_left, _chart_bottom, _chart_right, _chart_bottom, strokeColor=colors.HexColor("#D1D5DB"), strokeWidth=0.5))
            _legend_y = 5
            _drawing.add(Line(_chart_left, _legend_y, _chart_left + 15, _legend_y, strokeColor=colors.HexColor("#DC2626"), strokeWidth=2))
            _drawing.add(String(_chart_left + 18, _legend_y - 3, "Расходы на рекламу", fontName=font_info["font_name"], fontSize=7, fillColor=colors.HexColor("#374151")))
            _drawing.add(Line(_chart_left + 130, _legend_y, _chart_left + 145, _legend_y, strokeColor=colors.HexColor("#2563EB"), strokeWidth=2))
            _drawing.add(String(_chart_left + 148, _legend_y - 3, "Сумма заказов", fontName=font_info["font_name"], fontSize=7, fillColor=colors.HexColor("#374151")))
            story.append(_drawing)
            story.append(Spacer(1, 6))

    search_section = payload.get("search_section", {})
    if not isinstance(search_section, dict):
        search_section = {}
    search_available = search_section.get("available", False)
    search_sections = search_section.get("sections", [])
    search_summary = search_section.get("summary", [])

    if search_available and (search_sections or search_summary):
        story.append(PageBreak())
        story.append(Paragraph(_format_text(search_section.get("title") or "Поисковые запросы"), styles["section"]))
        story.append(Spacer(1, 4))

        header_style = ParagraphStyle("SearchHeader", parent=styles["hero_card"], textColor=colors.white)
        summary_table_rows = [[Paragraph(h, header_style) for h in ['Категория', 'Кол-во', 'Действие', 'Приоритет', 'Детали']]]
        for s in search_summary:
            if not isinstance(s, dict):
                continue
            summary_table_rows.append([
                Paragraph(_format_text(s.get("category", "")), styles["hero_card"]),
                Paragraph(str(s.get("count", 0)), styles["hero_card"]),
                Paragraph(_format_text(s.get("action", "")), styles["hero_card"]),
                Paragraph(_format_text(s.get("priority", "")), styles["hero_card"]),
                Paragraph(_format_text(s.get("detail", "")), styles["hero_card"]),
            ])
        total_actions = search_section.get("total_actions", 0)
        summary_table_rows.append([
            Paragraph("Итого к действию", styles["hero_card"]),
            Paragraph(str(total_actions), styles["hero_card"]),
            Paragraph("", styles["hero_card"]),
            Paragraph("", styles["hero_card"]),
            Paragraph("", styles["hero_card"]),
        ])
        summary_table = Table(summary_table_rows, colWidths=[content_width * 0.25, content_width * 0.10, content_width * 0.20, content_width * 0.12, content_width * 0.33])
        summary_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 6))

        for section in search_sections:
            if not isinstance(section, dict):
                continue
            sec_title = section.get("title", "")
            sec_criterion = section.get("criterion", "")
            sec_rows = section.get("rows", [])

            story.append(Paragraph(f"<b>{_format_text(sec_title)}</b>", styles["section"]))
            if sec_criterion:
                story.append(Paragraph(f"Критерий: {_format_text(sec_criterion)}", styles["meta"]))
            story.append(Spacer(1, 2))

            if sec_rows:
                sec_title_lower = sec_title.lower()
                if "убыточн" in sec_title_lower:
                    sec_bg = colors.HexColor("#DC2626")
                    sec_text = colors.black
                elif "эффективн" in sec_title_lower:
                    sec_bg = colors.HexColor("#16A34A")
                    sec_text = colors.black
                elif "гипотез" in sec_title_lower:
                    sec_bg = colors.HexColor("#D97706")
                    sec_text = colors.black
                else:
                    sec_bg = colors.HexColor("#1a1a2e")
                    sec_text = colors.white
                sec_header_style = ParagraphStyle("SecHeader", parent=styles["hero_card"], textColor=sec_text)
                sec_header = [Paragraph(h, sec_header_style) for h in ['Запрос', 'Показы', 'Клики', 'CTR', 'Расход', 'Заказы', 'Выручка', 'ДРР', 'Действие']]
                table_rows = [sec_header]
                for r in sec_rows:
                    if not isinstance(r, dict):
                        continue
                    drr_val = r.get("drr")
                    drr_text = f"{drr_val}%" if drr_val is not None else "н/д"
                    table_rows.append([
                        Paragraph(_format_text(r.get("query", "")), styles["hero_card"]),
                        Paragraph(str(r.get("impressions", 0)), styles["hero_card"]),
                        Paragraph(str(r.get("clicks", 0)), styles["hero_card"]),
                        Paragraph(f"{r.get('ctr', 0)}%", styles["hero_card"]),
                        Paragraph(_format_money(r.get("spend")) if r.get("spend") else "0 ₽", styles["hero_card"]),
                        Paragraph(str(r.get("orders", 0)), styles["hero_card"]),
                        Paragraph(_format_money(r.get("revenue")) if r.get("revenue") else "0 ₽", styles["hero_card"]),
                        Paragraph(drr_text, styles["hero_card"]),
                        Paragraph(_format_text(r.get("action", "")), styles["hero_card"]),
                    ])
                show_total = section.get("show_total", False)
                if show_total:
                    total_label = section.get("total_label", "Итого")
                    total_spend = section.get("total_spend", 0)
                    total_revenue = section.get("total_revenue", 0)
                    total_orders = section.get("total_orders", 0)
                    total_style = ParagraphStyle("TotalHeader", parent=styles["hero_card"], textColor=sec_text, fontName=styles["hero_card"].fontName)
                    table_rows.append([
                        Paragraph(f"<b>{total_label}</b>", total_style),
                        Paragraph("", styles["hero_card"]),
                        Paragraph("", styles["hero_card"]),
                        Paragraph("", styles["hero_card"]),
                        Paragraph(f"<b>{_format_money(total_spend) if total_spend else ''}</b>" if total_spend else "", total_style),
                        Paragraph(f"<b>{total_orders}</b>" if total_orders else "", total_style),
                        Paragraph(f"<b>{_format_money(total_revenue) if total_revenue else ''}</b>" if total_revenue else "", total_style),
                        Paragraph("", styles["hero_card"]),
                        Paragraph("", styles["hero_card"]),
                    ])
                sec_table = Table(table_rows, colWidths=[content_width * 0.22, content_width * 0.07, content_width * 0.07, content_width * 0.07, content_width * 0.11, content_width * 0.07, content_width * 0.12, content_width * 0.07, content_width * 0.12])
                sec_table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), sec_bg),
                    ("TEXTCOLOR", (0, 0), (-1, 0), sec_text),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                ]))
                story.append(sec_table)
            story.append(Spacer(1, 6))
        story.append(PageBreak())

    abc_section = payload.get("abc_section", {}) if isinstance(payload, dict) else {}
    if not isinstance(abc_section, dict):
        abc_section = {}
    abc_summary_rows = abc_section.get("summary_rows", [])
    sku_detail = payload.get("sku_detail_section", {}) if isinstance(payload, dict) else {}
    if not isinstance(sku_detail, dict):
        sku_detail = {}
    abc_analysis = payload.get("abc_analysis_section", {}) if isinstance(payload, dict) else {}
    if not isinstance(abc_analysis, dict):
        abc_analysis = {}

    if isinstance(abc_summary_rows, list) and abc_summary_rows:
        story.append(Paragraph(_format_text(abc_section.get("title") or "Ассортимент / ABC"), styles["section"]))
        subtitle = abc_section.get("subtitle", "")
        if subtitle:
            story.append(Paragraph(_format_text(subtitle), styles["meta"]))
        story.append(_display_rows_table(abc_summary_rows, width=content_width, font_name=font_info["font_name"], style=styles["hero_card"]))
        story.append(Spacer(1, 6))

        c_analysis_cats = abc_analysis.get("categories", {})
        c_from_analysis_raw = c_analysis_cats.get("C", []) if isinstance(c_analysis_cats, dict) else []
        c_from_analysis = []
        for item in c_from_analysis_raw:
            if isinstance(item, dict):
                c_from_analysis.append({
                    "sku": item.get("sku") or item.get("nm_id"),
                    "nm_id": item.get("nm_id") or item.get("sku"),
                    "abc_class": item.get("category") or item.get("abc_class"),
                    "revenue": item.get("metric_value") or item.get("revenue") or 0,
                    "profit": item.get("profit") or 0,
                    "profit_margin": item.get("profit_margin"),
                    "ad_spend": item.get("ad_spend"),
                })
        all_abc_skus = abc_section.get("top_a_skus", []) + abc_section.get("critical_a_skus", []) + abc_section.get("c_skus_with_ads", []) + abc_section.get("low_margin_skus", []) + c_from_analysis
        seen_skus = set()
        unique_abc_skus = []
        for s in all_abc_skus:
            sku_id = s.get("sku") or s.get("nm_id") or ""
            if sku_id and sku_id not in seen_skus:
                seen_skus.add(sku_id)
                unique_abc_skus.append(s)

        a_skus = [s for s in unique_abc_skus if (s.get("abc_class") or "").upper() == "A"]
        c_negative_skus = [s for s in unique_abc_skus if (s.get("abc_class") or "").upper() == "C" and (s.get("profit") or 0) < 0]

        if a_skus:
            story.append(Paragraph("Товары категории А — основные драйверы", styles["section"]))
            story.append(Spacer(1, 4))
            top_skus_map = {str(s.get("nm_id") or ""): s for s in (sku_detail.get("top_skus", []) + sku_detail.get("loss_skus", [])) if isinstance(s, dict)}
            for idx, s in enumerate(a_skus):
                sku_id = s.get("sku") or s.get("nm_id") or ""
                detail = top_skus_map.get(str(sku_id), {})
                nm_id = detail.get("nm_id") or sku_id
                seller_article = detail.get("seller_article", "")
                header_text = f"А-{idx+1}: {nm_id}"
                if seller_article:
                    header_text += f" | {seller_article}"
                story.append(Paragraph(header_text, styles["section"]))
                half_width = content_width / 2 - 2 * mm
                unit_table = _sku_detail_table(detail if detail else {
                    "nm_id": sku_id,
                    "orders_count": 0,
                    "buyouts_count": 0,
                    "revenue": s.get("revenue"),
                    "profit": s.get("profit"),
                }, width=half_width, font_name=font_info["font_name"], style=styles["hero_card"])
                funnel = detail.get("funnel", {})
                has_funnel = any(v for k, v in funnel.items() if k not in ("ctr_pct", "cr_cart_pct", "cr_order_pct") and v)
                if has_funnel:
                    funnel_table = _sku_funnel_table(funnel, width=half_width, font_name=font_info["font_name"], style=styles["hero_card"])
                    outer = Table([[unit_table, funnel_table]], colWidths=[half_width + 2 * mm, half_width + 2 * mm])
                    outer.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
                    story.append(outer)
                else:
                    story.append(unit_table)
                story.append(Spacer(1, 8))

        if c_negative_skus:
            story.append(Paragraph("Товары с отрицательной прибылью", styles["section"]))
            story.append(Spacer(1, 4))
            header_style = ParagraphStyle("AbcNegHeader", parent=styles["hero_card"], textColor=colors.white)
            neg_header = [Paragraph(h, header_style) for h in ['SKU', 'Выручка', 'Прибыль', 'Причина', 'Рекомендация']]
            neg_rows = [neg_header]
            for s in c_negative_skus:
                neg_rows.append([
                    Paragraph(_format_text(s.get("sku") or s.get("nm_id") or ""), styles["hero_card"]),
                    Paragraph(_format_query_money(s.get("revenue")), styles["hero_card"]),
                    Paragraph(_format_query_money(s.get("profit")), styles["hero_card"]),
                    Paragraph(_format_text(s.get("reason") or "низкая маржинальность"), styles["hero_card"]),
                    Paragraph(_format_text(s.get("recommended_action") or "пересмотреть цену, скидки и себестоимость"), styles["hero_card"]),
                ])
            neg_table = Table(neg_rows, colWidths=[content_width * 0.12, content_width * 0.14, content_width * 0.14, content_width * 0.30, content_width * 0.30])
            neg_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7C2D12")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#FEF2F2"), colors.HexColor("#FEE2E2")]),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
            ]))
            story.append(neg_table)
            story.append(Spacer(1, 6))

        c_all_skus = [s for s in unique_abc_skus if (s.get("abc_class") or "").upper() == "C" and (s.get("profit") or 0) >= 0]
        if c_all_skus:
            story.append(Paragraph("Товары категории C", styles["section"]))
            story.append(Spacer(1, 4))
            c_header = [Paragraph(h, styles["hero_card"]) for h in ['SKU', 'Выручка', 'Прибыль', 'Маржа', 'Реклама']]
            c_rows = [c_header]
            for s in c_all_skus:
                margin_val = s.get("profit_margin")
                margin_str = f"{round(margin_val * 100, 1)}%" if margin_val is not None else "—"
                c_rows.append([
                    Paragraph(_format_text(s.get("sku") or s.get("nm_id") or ""), styles["hero_card"]),
                    Paragraph(_format_query_money(s.get("revenue")), styles["hero_card"]),
                    Paragraph(_format_query_money(s.get("profit")), styles["hero_card"]),
                    Paragraph(margin_str, styles["hero_card"]),
                    Paragraph(_format_query_money(s.get("ad_spend")), styles["hero_card"]),
                ])
            c_table = Table(c_rows, colWidths=[content_width * 0.18, content_width * 0.20, content_width * 0.20, content_width * 0.20, content_width * 0.22])
            c_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#9CA3AF")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
            ]))
            story.append(c_table)
            story.append(Spacer(1, 6))

    doc.build(story)
    return {
        "pdf_path": str(target),
        "font_name": font_info["font_name"],
        "font_path": font_info["font_path"],
        "hero_rows_count": len(hero_rows),
        "top_skus_count": len(a_skus) if isinstance(abc_summary_rows, list) and abc_summary_rows else 0,
        "loss_skus_count": len(c_negative_skus) if isinstance(abc_summary_rows, list) and abc_summary_rows else 0,
    }
