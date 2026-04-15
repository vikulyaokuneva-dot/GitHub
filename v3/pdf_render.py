from __future__ import annotations

import math
import os
import re
import unicodedata
from typing import Any, Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont

from .outputs.render_policy import (
    SECTION_STATE_COMPACT_NOTE,
    SECTION_STATE_FULL,
    SECTION_STATE_HIDDEN,
    SECTION_STATE_PARTIAL,
    normalize_section_state,
)


def _font_dirs() -> List[str]:
    here = os.path.dirname(__file__)
    repo_root = os.path.dirname(here)
    dirs = [
        os.path.join(repo_root, "assets", "fonts"),
        os.path.join(here, "fonts"),
    ]

    win_dir = os.environ.get("WINDIR", "")
    if win_dir:
        dirs.append(os.path.join(win_dir, "Fonts"))

    dirs.extend(
        [
            "/usr/share/fonts/truetype/dejavu",
            "/usr/share/fonts/truetype",
            "/usr/share/fonts",
        ]
    )
    return dirs


def _resolve_font_family() -> Dict[str, str]:
    # Keep one font family for all PDF text to avoid glyph fallback issues.
    families = [("DejaVuSans.ttf", "DejaVuSans.ttf")]
    for directory in _font_dirs():
        for regular_name, bold_name in families:
            regular = os.path.join(directory, regular_name)
            if not os.path.isfile(regular):
                continue
            bold = os.path.join(directory, bold_name)
            return {
                "regular": regular,
                "bold": bold if os.path.isfile(bold) else regular,
                "family": "DejaVuSans",
            }
    raise FileNotFoundError(
        "DejaVuSans.ttf was not found. Put it into assets/fonts/DejaVuSans.ttf."
    )


def get_registered_pdf_font() -> Dict[str, str]:
    return _resolve_font_family()


def _contains_cyrillic(text: str) -> bool:
    for ch in text:
        code = ord(ch)
        if 0x0400 <= code <= 0x04FF:
            return True
    return False


def _bad_marker_count(text: str) -> int:
    markers = ("Ð", "Ñ", "Â", "Ã", "â", "�", "Р ")
    count = 0
    for marker in markers:
        count += text.count(marker)
    return count


def _looks_like_mojibake(text: str) -> bool:
    if not text:
        return False
    if _bad_marker_count(text) > 0:
        return True
    cyrillic_letters = len(re.findall(r"[А-Яа-яЁё]", text))
    if cyrillic_letters < 6:
        return False
    # Typical cp1251 mojibake has an abnormal amount of uppercase "Р"/"С".
    upper_rs = text.count("Р") + text.count("С")
    return upper_rs >= 4 and (upper_rs / max(cyrillic_letters, 1)) >= 0.22


def _try_repair_once(text: str) -> str:
    if not _looks_like_mojibake(text):
        return text

    best = text
    best_bad = _bad_marker_count(text)
    for source_codec in ("cp1251", "latin1", "cp1252"):
        try:
            candidate = text.encode(source_codec, errors="strict").decode("utf-8", errors="strict")
        except Exception:
            continue
        if candidate == text:
            continue
        candidate_bad = _bad_marker_count(candidate)
        if candidate_bad < best_bad:
            best = candidate
            best_bad = candidate_bad
            continue
        if _contains_cyrillic(candidate) and _looks_like_mojibake(text) and not _looks_like_mojibake(candidate):
            best = candidate
            best_bad = candidate_bad
    return best


def _strip_unsafe_controls(text: str) -> str:
    if not text:
        return ""
    # Preserve \f for explicit page breaks handled in renderer.
    allowed = {"\n", "\r", "\t", "\f"}
    return "".join(ch for ch in text if ord(ch) >= 32 or ch in allowed)


def repair_mojibake(text: str) -> str:
    if not isinstance(text, str):
        return str(text)
    if not text or text.isascii():
        return text
    repaired = text
    # Two passes are enough for most double-decoding artifacts.
    for _ in range(2):
        updated = _try_repair_once(repaired)
        if updated == repaired:
            break
        repaired = updated
    return repaired


def normalize_pdf_text(text: str) -> str:
    source = str(text or "")
    normalized = repair_mojibake(source).replace("﻿", "")
    normalized = unicodedata.normalize("NFC", normalized)
    # Fix common mojibake punctuation that can survive codec repair heuristics.
    for bad_dash in ("â€”", "РІР‚вЂќ", "â€“", "РІР‚вЂ“", "вЂ”"):
        normalized = normalized.replace(bad_dash, "—")
    return _strip_unsafe_controls(normalized)



def _line_style(line: str) -> tuple[str, str]:
    if line == "\f":
        return "page_break", ""
    if line.startswith("# "):
        return "title", line[2:].strip()
    if line.startswith("## "):
        return "section", line[3:].strip()
    if line.startswith("### "):
        return "subsection", line[4:].strip()
    if line.startswith("- "):
        return "bullet", line
    if line.strip() == "":
        return "space", ""
    return "body", line


def _wrap_line(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
    if not text:
        return [""]

    if draw.textlength(text, font=font) <= max_width:
        return [text]

    indent_len = len(text) - len(text.lstrip(" "))
    indent = " " * indent_len
    words = text.strip().split()
    if not words:
        return [text]

    wrapped: List[str] = []
    current = indent + words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            wrapped.append(current)
            current = indent + word
    wrapped.append(current)
    return wrapped


def write_text_pdf(path: str, lines: List[str]) -> Dict[str, str]:
    font_info = get_registered_pdf_font()

    # Render A4 pages as images and store as multi-page PDF to keep Unicode text stable.
    width_px, height_px = 1240, 1754
    margin_x, margin_y = 64, 64
    max_text_width = width_px - margin_x * 2

    fonts = {
        "title": ImageFont.truetype(font_info["regular"], size=46),
        "section": ImageFont.truetype(font_info["regular"], size=32),
        "subsection": ImageFont.truetype(font_info["regular"], size=26),
        "body": ImageFont.truetype(font_info["regular"], size=23),
        "bullet": ImageFont.truetype(font_info["regular"], size=23),
    }

    spacing = {
        "title": (8, 22),
        "section": (16, 10),
        "subsection": (10, 6),
        "body": (2, 2),
        "bullet": (1, 2),
        "space": (12, 0),
    }
    line_steps = {
        "title": 56,
        "section": 40,
        "subsection": 33,
        "body": 30,
        "bullet": 31,
    }

    pages: List[Image.Image] = []

    def _new_page() -> tuple[Image.Image, ImageDraw.ImageDraw, int]:
        img = Image.new("RGB", (width_px, height_px), "white")
        return img, ImageDraw.Draw(img), margin_y

    image, draw, y = _new_page()

    for raw in lines:
        line = normalize_pdf_text(str(raw))
        style, text = _line_style(line)
        if style == "page_break":
            pages.append(image)
            image, draw, y = _new_page()
            continue
        if style == "space":
            y += spacing["space"][0]
            continue

        before, after = spacing.get(style, (2, 2))
        y += before

        font = fonts.get(style, fonts["body"])
        line_step = line_steps.get(style, 30)
        for chunk in _wrap_line(draw, text, font, max_text_width):
            if y + line_step > height_px - margin_y:
                pages.append(image)
                image, draw, y = _new_page()
            draw.text((margin_x, y), chunk, fill="black", font=font)
            y += line_step

        if style in {"section", "subsection"}:
            rule_y = y + 2
            draw.line((margin_x, rule_y, width_px - margin_x, rule_y), fill=(210, 210, 210), width=1)
            y += 6
        y += after

    pages.append(image)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    pages[0].save(path, "PDF", save_all=True, append_images=pages[1:], resolution=150.0)
    font_info["pages"] = str(len(pages))
    return font_info


def _as_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _format_money(value: float | None) -> str:
    if value is None:
        return "нет данных"
    return f"{int(round(value)):,}".replace(",", " ") + " ₽"


def _format_int(value: float | None) -> str:
    if value is None:
        return "нет данных"
    return f"{int(round(value)):,}".replace(",", " ")


def _format_pct(value: float | None) -> str:
    if value is None:
        return "недостаточно данных"
    return f"{value:.1f} %"


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> Tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return max(0, int(box[2] - box[0])), max(0, int(box[3] - box[1]))


def _draw_centered_text(
    draw: ImageDraw.ImageDraw,
    box: Tuple[int, int, int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: Tuple[int, int, int],
) -> None:
    x1, y1, x2, y2 = box
    tw, th = _text_size(draw, text, font)
    tx = x1 + max(0, (x2 - x1 - tw) // 2)
    ty = y1 + max(0, (y2 - y1 - th) // 2)
    draw.text((tx, ty), text, font=font, fill=fill)


def write_daily_bi_pdf(path: str, payload: Dict[str, Any]) -> Dict[str, str]:
    font_info = get_registered_pdf_font()

    width_px, height_px = 1240, 1754
    margin = 56
    panel_gap = 26

    colors = {
        "bg": (246, 248, 252),
        "panel": (255, 255, 255),
        "border": (216, 223, 234),
        "warning_bg": (255, 244, 226),
        "warning_border": (230, 189, 128),
        "warning_text": (123, 83, 22),
        "title": (28, 52, 84),
        "text": (55, 66, 82),
        "muted": (116, 127, 142),
        "dark_blue": (33, 70, 115),
        "gray": (128, 138, 152),
        "orange": (221, 145, 71),
        "red": (191, 83, 83),
        "blue": (75, 126, 184),
        "dark_gray": (81, 88, 98),
    }

    fonts = {
        "h1": ImageFont.truetype(font_info["regular"], size=46),
        "h2": ImageFont.truetype(font_info["regular"], size=32),
        "h3": ImageFont.truetype(font_info["regular"], size=25),
        "body": ImageFont.truetype(font_info["regular"], size=22),
        "small": ImageFont.truetype(font_info["regular"], size=19),
        "kpi_value": ImageFont.truetype(font_info["regular"], size=54),
        "kpi_label": ImageFont.truetype(font_info["regular"], size=24),
    }

    pages: List[Image.Image] = []

    def _new_page() -> tuple[Image.Image, ImageDraw.ImageDraw]:
        image = Image.new("RGB", (width_px, height_px), colors["bg"])
        return image, ImageDraw.Draw(image)

    def _draw_panel(
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        w: int,
        h: int,
        title: str,
    ) -> Tuple[int, int, int, int]:
        draw.rounded_rectangle(
            (x, y, x + w, y + h),
            radius=20,
            fill=colors["panel"],
            outline=colors["border"],
            width=2,
        )
        draw.text((x + 24, y + 18), normalize_pdf_text(title), font=fonts["h3"], fill=colors["title"])
        line_y = y + 62
        draw.line((x + 20, line_y, x + w - 20, line_y), fill=colors["border"], width=1)
        return (x + 24, y + 78, x + w - 24, y + h - 22)

    def _fit_text(draw_obj: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: int) -> str:
        prepared = normalize_pdf_text(str(text or "")).strip()
        if not prepared:
            return ""
        if draw_obj.textlength(prepared, font=font) <= max_w:
            return prepared
        dots = "..."
        candidate = prepared
        while candidate and draw_obj.textlength(candidate + dots, font=font) > max_w:
            candidate = candidate[:-1]
        return (candidate + dots) if candidate else dots

    def _draw_table(
        draw_obj: ImageDraw.ImageDraw,
        box: Tuple[int, int, int, int],
        columns: List[Tuple[str, str, int]],
        rows: List[Dict[str, Any]],
        empty_text: str,
    ) -> None:
        x1, y1, x2, y2 = box
        if not rows:
            draw_obj.text((x1, y1 + 10), normalize_pdf_text(empty_text), font=fonts["body"], fill=colors["muted"])
            return

        header_h = 42
        row_h = 36
        width = x2 - x1
        total_ratio = sum(max(1, ratio) for _, _, ratio in columns)

        x_positions: List[int] = [x1]
        consumed = 0
        for idx, (_, _, ratio) in enumerate(columns):
            if idx == len(columns) - 1:
                col_w = width - consumed
            else:
                col_w = int(width * (max(1, ratio) / total_ratio))
            consumed += col_w
            x_positions.append(x_positions[-1] + col_w)

        draw_obj.rectangle((x1, y1, x2, y1 + header_h), fill=(242, 245, 250), outline=colors["border"], width=1)

        for idx, (title, _, _) in enumerate(columns):
            cx1, cx2 = x_positions[idx], x_positions[idx + 1]
            text = _fit_text(draw_obj, title, fonts["small"], max(16, cx2 - cx1 - 14))
            draw_obj.text((cx1 + 8, y1 + 10), text, font=fonts["small"], fill=colors["title"])
            if idx > 0:
                draw_obj.line((cx1, y1, cx1, y2), fill=colors["border"], width=1)

        max_rows = max(1, int((y2 - y1 - header_h) / row_h))
        visible = rows[:max_rows]
        y = y1 + header_h
        for row in visible:
            draw_obj.rectangle((x1, y, x2, y + row_h), fill=colors["panel"], outline=colors["border"], width=1)
            for idx, (_, key, _) in enumerate(columns):
                cx1, cx2 = x_positions[idx], x_positions[idx + 1]
                value = _fit_text(draw_obj, str(row.get(key, "")), fonts["small"], max(16, cx2 - cx1 - 14))
                draw_obj.text((cx1 + 8, y + 8), value, font=fonts["small"], fill=colors["text"])
            y += row_h

    def _section_state(name: str, fallback: str = SECTION_STATE_FULL) -> str:
        states = payload.get("section_states", {})
        if isinstance(states, dict):
            return normalize_section_state(states.get(name), default=fallback)
        return fallback

    def _draw_compact_note(
        draw_obj: ImageDraw.ImageDraw,
        box: Tuple[int, int, int, int],
        title: str,
        note: str,
    ) -> None:
        x1, y1, x2, y2 = box
        text = normalize_pdf_text(note.strip() or title.strip())
        draw_obj.text((x1, y1 + 8), _fit_text(draw_obj, text, fonts["body"], max(40, x2 - x1 - 8)), font=fonts["body"], fill=colors["muted"])

    not_enough = normalize_pdf_text("Недостаточно данных для визуализации")

    # Page 1: KPI cards
    page_1, draw_1 = _new_page()
    seller_id = normalize_pdf_text(str(payload.get("seller_id") or ""))
    run_date = normalize_pdf_text(str(payload.get("run_date") or ""))
    operational_day = normalize_pdf_text(str(payload.get("operational_day") or run_date))
    financial_alignment = payload.get("financial_alignment", {})
    if not isinstance(financial_alignment, dict):
        financial_alignment = {}
    financial_alignment_status = str(financial_alignment.get("financial_alignment_status") or "").strip().lower()
    financial_lagged = bool(
        financial_alignment.get("financial_lagged", False)
        or financial_alignment.get("financial_date_misaligned", False)
        or financial_alignment_status in {"lagged", "lagged_fallback"}
    )
    financial_actual_date = normalize_pdf_text(str(financial_alignment.get("financial_actual_date") or ""))
    financial_target_date = normalize_pdf_text(str(financial_alignment.get("financial_target_date") or operational_day))
    lag_warning_text = normalize_pdf_text(str(financial_alignment.get("warning_text") or "").strip())
    if financial_lagged and not lag_warning_text:
        lag_warning_text = normalize_pdf_text(
            "Финансовые данные WB доступны только за "
            f"{financial_actual_date or 'более раннюю дату'} и не относятся к операционному дню "
            f"{financial_target_date or operational_day}. Показан лаговый финансовый срез."
        )

    draw_1.text((margin, margin), normalize_pdf_text("WB AI Agent v3"), font=fonts["h1"], fill=colors["title"])
    draw_1.text(
        (margin, margin + 64),
        normalize_pdf_text(f"Кабинет: {seller_id}    Отчетная дата: {run_date}    Операционный день: {operational_day}"),
        font=fonts["body"],
        fill=colors["muted"],
    )
    draw_1.text((margin, margin + 126), normalize_pdf_text("Ключевые показатели дня"), font=fonts["h2"], fill=colors["title"])
    card_y = margin + 182
    if financial_lagged:
        warning_top = margin + 170
        warning_bottom = warning_top + 74
        draw_1.rounded_rectangle(
            (margin, warning_top, width_px - margin, warning_bottom),
            radius=14,
            fill=colors["warning_bg"],
            outline=colors["warning_border"],
            width=2,
        )
        draw_1.text(
            (margin + 12, warning_top + 10),
            _fit_text(draw_1, lag_warning_text, fonts["small"], width_px - margin * 2 - 24),
            font=fonts["small"],
            fill=colors["warning_text"],
        )
        card_y = warning_bottom + 16

    kpi_cards = payload.get("kpi_cards", [])
    if not isinstance(kpi_cards, list):
        kpi_cards = []
    visible_kpi_cards = [
        card
        for card in kpi_cards
        if isinstance(card, dict) and normalize_section_state(card.get("state"), default=SECTION_STATE_FULL) != SECTION_STATE_HIDDEN
    ][:4]
    if not visible_kpi_cards:
        visible_kpi_cards = [{"label": "Ключевые показатели", "value": None, "value_type": "text"}]

    card_gap = 18
    card_count = max(1, len(visible_kpi_cards))
    card_w = int((width_px - margin * 2 - card_gap * (card_count - 1)) / card_count)
    card_h = 320
    for idx, card in enumerate(visible_kpi_cards):
        if not isinstance(card, dict):
            continue
        x = margin + idx * (card_w + card_gap)
        y = card_y
        draw_1.rounded_rectangle(
            (x, y, x + card_w, y + card_h),
            radius=18,
            fill=colors["panel"],
            outline=colors["border"],
            width=2,
        )
        label = normalize_pdf_text(str(card.get("label") or ""))
        value_type = str(card.get("value_type") or "int").strip().lower()
        value_num = _as_number(card.get("value"))
        if value_type == "money":
            value = _format_money(value_num)
        elif value_type == "pct":
            value = _format_pct(value_num)
        else:
            value = _format_int(value_num)
        value_font = fonts["kpi_value"]
        if value == "нет данных" or len(value) >= 10:
            value_font = fonts["h2"]
        elif len(value) >= 8:
            value_font = fonts["h3"]
        _draw_centered_text(draw_1, (x + 12, y + 40, x + card_w - 12, y + 120), label, fonts["kpi_label"], colors["muted"])
        _draw_centered_text(
            draw_1,
            (x + 12, y + 128, x + card_w - 12, y + card_h - 86),
            normalize_pdf_text(value),
            value_font,
            colors["dark_blue"],
        )
        reason = normalize_pdf_text(str(card.get("reason") or "").strip())
        if reason:
            draw_1.text((x + 12, y + card_h - 58), _fit_text(draw_1, reason, fonts["small"], card_w - 24), font=fonts["small"], fill=colors["muted"])

    draw_1.text(
        (margin, height_px - margin - 24),
        normalize_pdf_text("Формат: BI-резюме | WB AI Agent v3"),
        font=fonts["small"],
        fill=colors["muted"],
    )
    pages.append(page_1)

    # Page 2: Expense structure + ad efficiency
    page_2, draw_2 = _new_page()
    draw_2.text((margin, margin), normalize_pdf_text("Финансы и реклама"), font=fonts["h1"], fill=colors["title"])

    top_panel_h = 930
    finance_panel_title = "Финансовая структура (лаговый срез WB)" if financial_lagged else "Финансовая структура дня"
    top_content = _draw_panel(
        draw_2,
        margin,
        margin + 84,
        width_px - margin * 2,
        top_panel_h,
        finance_panel_title,
    )
    left, top, right, bottom = top_content
    finance_table_box: Tuple[int, int, int, int] = top_content
    if financial_lagged:
        banner_h = 86
        banner_bottom = min(bottom - 16, top + banner_h)
        draw_2.rounded_rectangle(
            (left, top, right, banner_bottom),
            radius=12,
            fill=colors["warning_bg"],
            outline=colors["warning_border"],
            width=2,
        )
        draw_2.text(
            (left + 12, top + 10),
            _fit_text(draw_2, lag_warning_text, fonts["small"], max(80, right - left - 24)),
            font=fonts["small"],
            fill=colors["warning_text"],
        )
        finance_table_box = (left, banner_bottom + 12, right, bottom)
    financial_structure = payload.get("financial_structure_day", {})
    if not isinstance(financial_structure, dict):
        financial_structure = {}
    seller_payout_value = _as_number(
        financial_structure.get("seller_payout")
        if financial_structure.get("seller_payout") is not None
        else financial_structure.get("revenue")
    )
    gross_revenue_value = _as_number(financial_structure.get("gross_revenue"))
    wb_realized_revenue_value = _as_number(financial_structure.get("wb_realized_revenue"))
    loyalty_total_value = _as_number(financial_structure.get("loyalty_total"))
    if loyalty_total_value is None:
        loyalty_program_value = _as_number(financial_structure.get("loyalty_program"))
        loyalty_points_value = _as_number(financial_structure.get("loyalty_points_withheld"))
        if loyalty_program_value is not None or loyalty_points_value is not None:
            loyalty_total_value = float(loyalty_program_value or 0.0) + float(loyalty_points_value or 0.0)

    fs_rows_raw = [
        ("Валовая выручка", gross_revenue_value),
        ("WB реализовал", wb_realized_revenue_value),
        ("К перечислению продавцу", seller_payout_value),
        ("Комиссия WB", _as_number(financial_structure.get("commission"))),
        ("Эквайринг", _as_number(financial_structure.get("acquiring"))),
        ("ПВЗ / выдача-возврат", _as_number(financial_structure.get("pvz_service"))),
        ("Логистика", _as_number(financial_structure.get("logistics"))),
        ("Хранение", _as_number(financial_structure.get("storage"))),
        ("Штрафы", _as_number(financial_structure.get("penalties"))),
        ("Удержания", _as_number(financial_structure.get("deductions"))),
        ("Лояльность / бонусные удержания", loyalty_total_value),
        ("Прочие корректировки", _as_number(financial_structure.get("other_adjustments"))),
        ("Себестоимость", _as_number(financial_structure.get("cost_price"))),
        ("Налог", _as_number(financial_structure.get("tax"))),
        ("Расход на рекламу", _as_number(financial_structure.get("ads_spend"))),
        ("Чистая прибыль", _as_number(financial_structure.get("net_profit"))),
        ("Проверка прибыли (по компонентам)", _as_number(financial_structure.get("explained_net_profit"))),
        ("Дельта расчета прибыли", _as_number(financial_structure.get("net_profit_explain_delta"))),
    ]
    fs_rows = [
        {
            "metric": normalize_pdf_text(label),
            "value": normalize_pdf_text(_format_money(value) if value is not None else "нет данных"),
        }
        for label, value in fs_rows_raw
    ]
    _draw_table(
        draw_2,
        finance_table_box,
        [
            ("Показатель", "metric", 58),
            ("Значение", "value", 42),
        ],
        fs_rows,
        "Недостаточно данных для визуализации",
    )

    ads = payload.get("ads_efficiency", {})
    if not isinstance(ads, dict):
        ads = {}
    ads_state = normalize_section_state(ads.get("state"), default=_section_state("ads_efficiency", SECTION_STATE_FULL))
    if ads_state == SECTION_STATE_HIDDEN:
        ads_state = SECTION_STATE_COMPACT_NOTE
    bottom_panel_y = margin + 84 + top_panel_h + panel_gap
    available_bottom_h = height_px - bottom_panel_y - margin
    target_bottom_h = 640 if ads_state == SECTION_STATE_FULL else (360 if ads_state == SECTION_STATE_PARTIAL else 230)
    bottom_panel_h = max(200, min(available_bottom_h, target_bottom_h))
    ad_content = _draw_panel(
        draw_2,
        margin,
        bottom_panel_y,
        width_px - margin * 2,
        bottom_panel_h,
        "Эффективность рекламы",
    )
    left, top, right, bottom = ad_content
    ad_spend = _as_number(ads.get("ad_spend"))
    ad_revenue = _as_number(ads.get("ad_revenue"))
    ads_note = normalize_pdf_text(str(ads.get("note") or "").strip())
    summary_rows = ads.get("summary_rows", [])
    if not isinstance(summary_rows, list):
        summary_rows = []
    table_rows = ads.get("table_rows", [])
    if not isinstance(table_rows, list):
        table_rows = []
    if ads_state == SECTION_STATE_FULL and (ad_spend is not None or ad_revenue is not None):
        bars = [
            ("Расход на рекламу", abs(ad_spend) if ad_spend is not None else None, colors["red"]),
            ("Выручка от рекламы", abs(ad_revenue) if ad_revenue is not None else None, colors["dark_blue"]),
        ]
        vals = [v for _, v, _ in bars if v is not None]
        max_value = max(max(vals), 1.0) if vals else 1.0
        base_y = bottom - 16
        draw_2.line((left + 20, base_y, right - 20, base_y), fill=colors["border"], width=2)
        column_w = 220
        gap = 140
        start_x = left + 90
        for idx, (label, value, color) in enumerate(bars):
            x = start_x + idx * (column_w + gap)
            if value is not None:
                bar_h = int((value / max_value) * max(40, bottom - top - 72))
                draw_2.rounded_rectangle(
                    (x, base_y - bar_h, x + column_w, base_y),
                    radius=12,
                    fill=color,
                    outline=color,
                )
                draw_2.text((x, base_y - bar_h - 34), _format_money(value), font=fonts["body"], fill=colors["text"])
            else:
                draw_2.rounded_rectangle(
                    (x, base_y - 2, x + column_w, base_y),
                    radius=6,
                    fill=(230, 233, 240),
                    outline=(230, 233, 240),
                )
                draw_2.text((x, base_y - 40), "нет данных", font=fonts["body"], fill=colors["muted"])
            draw_2.text((x, base_y + 10), normalize_pdf_text(label), font=fonts["small"], fill=colors["text"])
    elif table_rows:
        ads_table: List[Dict[str, Any]] = []
        for row in table_rows:
            if not isinstance(row, dict):
                continue
            ads_table.append(
                {
                    "query": normalize_pdf_text(str(row.get("query") or "")),
                    "spend": normalize_pdf_text(_format_money(_as_number(row.get("spend")))),
                    "orders": normalize_pdf_text(_format_int(_as_number(row.get("orders")))),
                    "revenue": normalize_pdf_text(_format_money(_as_number(row.get("revenue")))),
                }
            )
        _draw_table(
            draw_2,
            ad_content,
            [
                ("Запрос", "query", 40),
                ("Расход", "spend", 20),
                ("Заказы", "orders", 16),
                ("Выручка", "revenue", 24),
            ],
            ads_table,
            ads_note or not_enough,
        )
    elif summary_rows:
        summary_table: List[Dict[str, Any]] = []
        for row in summary_rows:
            if not isinstance(row, dict):
                continue
            value_type = str(row.get("value_type") or "text").strip().lower()
            raw_value = row.get("value")
            if value_type == "money":
                value_text = _format_money(_as_number(raw_value))
            elif value_type == "pct":
                value_text = _format_pct(_as_number(raw_value))
            elif value_type == "int":
                value_text = _format_int(_as_number(raw_value))
            else:
                value_text = str(raw_value or "нет данных")
            summary_table.append(
                {
                    "metric": normalize_pdf_text(str(row.get("metric") or "")),
                    "value": normalize_pdf_text(value_text),
                }
            )
        _draw_table(
            draw_2,
            ad_content,
            [
                ("Показатель", "metric", 62),
                ("Значение", "value", 38),
            ],
            summary_table,
            ads_note or not_enough,
        )
        if ads_note:
            draw_2.text((left, bottom - 26), _fit_text(draw_2, ads_note, fonts["small"], right - left), font=fonts["small"], fill=colors["muted"])
    else:
        _draw_compact_note(draw_2, ad_content, "Нет данных для оценки рекламы", ads_note or "Нет данных для оценки рекламы")
    pages.append(page_2)

    # Page 3: Funnel + SKU donut
    page_3, draw_3 = _new_page()
    draw_3.text((margin, margin), normalize_pdf_text("Воронка и статус ассортимента"), font=fonts["h1"], fill=colors["title"])

    funnel = payload.get("funnel", {})
    if not isinstance(funnel, dict):
        funnel = {}
    funnel_state = normalize_section_state(funnel.get("state"), default=_section_state("funnel", SECTION_STATE_FULL))
    funnel_note = normalize_pdf_text(str(funnel.get("note") or "").strip())
    funnel_stages_raw = funnel.get("stages", [])
    if not isinstance(funnel_stages_raw, list) or not funnel_stages_raw:
        funnel_stages_raw = [
            {"label": "Показы", "value": funnel.get("views")},
            {"label": "Корзина", "value": funnel.get("add_to_cart")},
            {"label": "Заказы", "value": funnel.get("orders")},
            {"label": "Выкупы", "value": funnel.get("buyouts")},
        ]
    funnel_stages: List[Dict[str, Any]] = []
    for row in funnel_stages_raw:
        if not isinstance(row, dict):
            continue
        numeric_value = _as_number(row.get("value"))
        status_token = str(row.get("status") or ("missing" if numeric_value is None else "confirmed")).strip().lower()
        raw_display_value = str(row.get("display_value") or "").strip()
        display_value = normalize_pdf_text(raw_display_value) if raw_display_value else normalize_pdf_text(_format_int(numeric_value))
        funnel_stages.append(
            {
                "label": normalize_pdf_text(str(row.get("label") or "")),
                "value": numeric_value,
                "status": status_token,
                "display_value": display_value,
            }
        )
    funnel_present_rows = [row for row in funnel_stages if row.get("value") is not None]
    positive_values = [float(row.get("value")) for row in funnel_present_rows if row.get("value") is not None and float(row.get("value")) > 0]
    should_draw_funnel_graph = len(positive_values) >= 2 and funnel_state in {SECTION_STATE_FULL, SECTION_STATE_PARTIAL}
    funnel_panel_h = 900 if should_draw_funnel_graph else (420 if funnel_stages else 260)
    funnel_content = _draw_panel(
        draw_3,
        margin,
        margin + 84,
        width_px - margin * 2,
        funnel_panel_h,
        "Воронка продаж",
    )
    left, top, right, bottom = funnel_content
    if should_draw_funnel_graph:
        graph_rows = [
            (str(row.get("label") or ""), float(row.get("value")))
            for row in funnel_present_rows
            if row.get("value") is not None
        ]
        max_val = max(max(positive_values), 1.0)
        min_w = 240
        max_w = right - left - 280
        if max_w < min_w:
            max_w = min_w + 60
        rows_count = max(2, len(graph_rows))
        stage_gap = 12
        stage_h = max(64, int((bottom - top - 20 - stage_gap * (rows_count - 1)) / rows_count))
        stage_y = top + 12
        cx = left + (max_w // 2) + 40
        widths: List[int] = []
        for _, value in graph_rows:
            if value is None or value <= 0:
                widths.append(min_w)
            else:
                ratio = (value / max_val) ** 0.65
                widths.append(int(min_w + (max_w - min_w) * ratio))
        palette = [(119, 153, 194), (97, 136, 183), (73, 114, 166), (48, 90, 146), (44, 79, 130)]
        for idx, (label, value) in enumerate(graph_rows):
            top_w = widths[idx]
            next_w_base = widths[idx + 1] if idx < len(widths) - 1 else widths[idx]
            bottom_w = max(int(next_w_base * 0.92), min_w - 10)
            y1 = stage_y
            y2 = stage_y + stage_h
            polygon = [
                (cx - top_w // 2, y1),
                (cx + top_w // 2, y1),
                (cx + bottom_w // 2, y2),
                (cx - bottom_w // 2, y2),
            ]
            draw_3.polygon(polygon, fill=palette[idx % len(palette)], outline=(255, 255, 255))
            value_text = _format_int(value)
            draw_3.text((cx - top_w // 2 + 22, y1 + max(14, stage_h // 3)), normalize_pdf_text(f"{label}: {value_text}"), font=fonts["body"], fill=(255, 255, 255))
            if idx < len(graph_rows) - 1:
                next_val = graph_rows[idx + 1][1]
                conversion = None
                if value is not None and value > 0 and next_val is not None:
                    conversion = (next_val / value) * 100.0
                conversion_text = _format_pct(conversion)
                if idx == len(graph_rows) - 2 and bool(funnel.get("order_to_buyout_over_100", False)):
                    conversion_text = "недостаточно данных (возможен лаг выкупа)"
                draw_3.text(
                    (cx + max_w // 2 + 26, y1 + max(14, stage_h // 3)),
                    normalize_pdf_text(f"Конверсия: {conversion_text}"),
                    font=fonts["small"],
                    fill=colors["text"],
                )
            stage_y = y2 + stage_gap
        if funnel_note:
            draw_3.text((left, bottom - 22), _fit_text(draw_3, funnel_note, fonts["small"], right - left), font=fonts["small"], fill=colors["muted"])
    elif funnel_stages:
        table_rows = [
            {
                "stage": normalize_pdf_text(str(row.get("label") or "")),
                "value": normalize_pdf_text(str(row.get("display_value") or _format_int(_as_number(row.get("value"))))),
            }
            for row in funnel_stages
        ]
        _draw_table(
            draw_3,
            funnel_content,
            [
                ("Этап", "stage", 62),
                ("Значение", "value", 38),
            ],
            table_rows,
            funnel_note or not_enough,
        )
        if funnel_note:
            draw_3.text((left, bottom - 22), _fit_text(draw_3, funnel_note, fonts["small"], right - left), font=fonts["small"], fill=colors["muted"])
    else:
        _draw_compact_note(draw_3, funnel_content, "Нет данных по воронке", funnel_note or "Нет полной воронки за период")

    donut_panel_y = margin + 84 + funnel_panel_h + panel_gap
    donut_panel_h = height_px - donut_panel_y - margin
    donut_content = _draw_panel(
        draw_3,
        margin,
        donut_panel_y,
        width_px - margin * 2,
        donut_panel_h,
        "Статус товаров",
    )
    left, top, right, bottom = donut_content
    sku_status = payload.get("sku_status", {})
    if not isinstance(sku_status, dict):
        sku_status = {}
    status_rows = [
        ("Рост", int(_as_number(sku_status.get("growth")) or 0), colors["blue"]),
        ("Нормально", int(_as_number(sku_status.get("normal")) or 0), colors["gray"]),
        ("Риск", int(_as_number(sku_status.get("risk")) or 0), colors["orange"]),
        ("Ликвидация", int(_as_number(sku_status.get("liquidation")) or 0), colors["red"]),
    ]
    total_status = sum(max(0, item[1]) for item in status_rows)
    if total_status <= 0:
        draw_3.text((left, top + 18), not_enough, font=fonts["body"], fill=colors["muted"])
    else:
        center_x = left + 210
        center_y = top + (bottom - top) // 2 + 4
        outer_r = min(128, (bottom - top) // 2 - 8)
        bbox = (center_x - outer_r, center_y - outer_r, center_x + outer_r, center_y + outer_r)
        start = -90.0
        for _, count, color in status_rows:
            if count <= 0:
                continue
            sweep = 360.0 * (count / total_status)
            draw_3.pieslice(bbox, start=start, end=start + sweep, fill=color, outline=colors["panel"])
            start += sweep
        inner_r = int(outer_r * 0.58)
        draw_3.ellipse(
            (center_x - inner_r, center_y - inner_r, center_x + inner_r, center_y + inner_r),
            fill=colors["panel"],
            outline=colors["panel"],
        )
        draw_3.text((center_x - 54, center_y - 20), "SKU", font=fonts["body"], fill=colors["muted"])
        draw_3.text((center_x - 28, center_y + 10), str(total_status), font=fonts["h3"], fill=colors["title"])

        legend_x = left + 430
        legend_y = top + 18
        for label, count, color in status_rows:
            draw_3.rounded_rectangle(
                (legend_x, legend_y + 6, legend_x + 22, legend_y + 28),
                radius=4,
                fill=color,
                outline=color,
            )
            pct = (count / total_status) * 100 if total_status > 0 else 0.0
            text = normalize_pdf_text(f"{label}: {count} ({pct:.1f}%)")
            draw_3.text((legend_x + 34, legend_y), text, font=fonts["body"], fill=colors["text"])
            legend_y += 54
    pages.append(page_3)

    # Page 4: SKU health score
    page_4, draw_4 = _new_page()
    draw_4.text((margin, margin), normalize_pdf_text("Оценка товаров"), font=fonts["h1"], fill=colors["title"])
    health_content = _draw_panel(
        draw_4,
        margin,
        margin + 84,
        width_px - margin * 2,
        height_px - (margin + 84) - margin,
        "Оценка здоровья SKU",
    )
    health_rows_raw = payload.get("sku_health_rows", [])
    if not isinstance(health_rows_raw, list):
        health_rows_raw = []
    health_rows: List[Dict[str, Any]] = []
    for row in health_rows_raw:
        if not isinstance(row, dict):
            continue
        sku = normalize_pdf_text(str(row.get("sku") or "").strip())
        if not sku:
            continue
        score_value = _as_number(row.get("health_score"))
        score_text = "нет данных"
        if score_value is not None:
            score_text = str(int(max(0, min(100, round(score_value)))))
        health_rows.append(
            {
                "sku": sku,
                "score": score_text,
                "status": normalize_pdf_text(str(row.get("status") or "Нормально")),
                "reason": normalize_pdf_text(str(row.get("reason") or "Без критичных сигналов")),
            }
        )
    _draw_table(
        draw_4,
        health_content,
        [
            ("SKU", "sku", 20),
            ("Health Score", "score", 17),
            ("Статус", "status", 19),
            ("Причина", "reason", 44),
        ],
        health_rows,
        "Недостаточно данных для визуализации",
    )
    pages.append(page_4)

    # Page 5: Key problems by SKU
    page_5, draw_5 = _new_page()
    draw_5.text((margin, margin), normalize_pdf_text("Ключевые проблемы"), font=fonts["h1"], fill=colors["title"])
    key_problem_cards = payload.get("key_problem_cards", [])
    if not isinstance(key_problem_cards, list):
        key_problem_cards = []
    key_problems = payload.get("key_problems", {})
    if not isinstance(key_problems, dict):
        key_problems = {}
    key_problem_reasons = payload.get("key_problem_reasons", {})
    if not isinstance(key_problem_reasons, dict):
        key_problem_reasons = {}

    def _problem_skus(key: str) -> List[str]:
        rows = key_problems.get(key, [])
        if not isinstance(rows, list):
            return []
        result: List[str] = []
        seen: set[str] = set()
        for item in rows:
            sku = normalize_pdf_text(str(item or "").strip())
            if not sku or sku in seen:
                continue
            seen.add(sku)
            result.append(sku)
            if len(result) >= 8:
                break
        return result

    def _problem_reason(key: str) -> str:
        reason = normalize_pdf_text(str(key_problem_reasons.get(key) or "").strip())
        return reason or normalize_pdf_text("нет данных")

    if not key_problem_cards:
        key_problem_cards = []
        for title, key in (
            ("Низкий трафик", "low_traffic"),
            ("Падение конверсии", "conversion_drop"),
            ("Неэффективная реклама", "inefficient_ads"),
            ("SKU в зоне ликвидации", "liquidation_skus"),
        ):
            skus = _problem_skus(key)
            reason = _problem_reason(key)
            if not skus and not reason:
                continue
            key_problem_cards.append(
                {
                    "title": title,
                    "key": key,
                    "state": SECTION_STATE_FULL if skus else SECTION_STATE_COMPACT_NOTE,
                    "skus": skus,
                    "reason": reason,
                }
            )

    box_top = margin + 92
    area_h = height_px - box_top - margin
    visible_problem_cards = [card for card in key_problem_cards if isinstance(card, dict)][:4]
    if not visible_problem_cards:
        visible_problem_cards = [
            {
                "title": "Что не удалось проверить",
                "state": SECTION_STATE_COMPACT_NOTE,
                "skus": [],
                "reason": "Нет достаточных сигналов по ключевым проблемам",
                "notes": [],
            }
        ]
    cols = 1 if len(visible_problem_cards) == 1 else 2
    rows = int(math.ceil(len(visible_problem_cards) / cols))
    box_h = int((area_h - panel_gap * max(0, rows - 1)) / rows)
    box_w = int((width_px - margin * 2 - panel_gap * max(0, cols - 1)) / cols)

    for idx, card in enumerate(visible_problem_cards):
        row_idx = idx // cols
        col_idx = idx % cols
        x = margin + col_idx * (box_w + panel_gap)
        y = box_top + row_idx * (box_h + panel_gap)
        title = normalize_pdf_text(str(card.get("title") or "Проблема"))
        content = _draw_panel(draw_5, x, y, box_w, box_h, title)
        cx1, cy1, cx2, cy2 = content
        skus = card.get("skus", [])
        if not isinstance(skus, list):
            skus = []
        notes = card.get("notes", [])
        if not isinstance(notes, list):
            notes = []
        reason = normalize_pdf_text(str(card.get("reason") or "").strip())
        if reason:
            draw_5.text((cx1, cy1 + 2), _fit_text(draw_5, reason, fonts["small"], cx2 - cx1 - 8), font=fonts["small"], fill=colors["muted"])
        y_cursor = cy1 + 4
        if reason:
            y_cursor += 30
        for sku in skus:
            line = normalize_pdf_text(f"- SKU {sku}")
            draw_5.text((cx1, y_cursor), _fit_text(draw_5, line, fonts["body"], cx2 - cx1 - 8), font=fonts["body"], fill=colors["text"])
            y_cursor += 34
            if y_cursor > cy2 - 28:
                break
        for note in notes:
            if y_cursor > cy2 - 28:
                break
            note_line = normalize_pdf_text(f"- {note}")
            draw_5.text((cx1, y_cursor), _fit_text(draw_5, note_line, fonts["small"], cx2 - cx1 - 8), font=fonts["small"], fill=colors["text"])
            y_cursor += 30
    pages.append(page_5)

    # Page 6: AI recommendations by priority
    page_6, draw_6 = _new_page()
    draw_6.text((margin, margin), normalize_pdf_text("Рекомендации AI"), font=fonts["h1"], fill=colors["title"])
    rec_payload = payload.get("ai_recommendations", {})
    if not isinstance(rec_payload, dict):
        rec_payload = {}

    rec_sections = [
        ("P1 — срочные действия", rec_payload.get("p1", [])),
        ("P2 — оптимизация", rec_payload.get("p2", [])),
        ("P3 — наблюдение", rec_payload.get("p3", [])),
    ]
    visible_rec_sections: List[Tuple[str, List[Any]]] = []
    for title, rows_raw in rec_sections:
        rows = rows_raw if isinstance(rows_raw, list) else []
        if rows:
            visible_rec_sections.append((title, rows))

    section_top = margin + 92
    if not visible_rec_sections:
        fallback_note = normalize_pdf_text(str(payload.get("recommendations_note") or "Нет рекомендаций с достаточным уровнем сигнала").strip())
        content = _draw_panel(
            draw_6,
            margin,
            section_top,
            width_px - margin * 2,
            260,
            "Рекомендации",
        )
        _draw_compact_note(draw_6, content, "Рекомендации", fallback_note)
        pages.append(page_6)
    else:
        section_h = int((height_px - section_top - margin - panel_gap * max(0, len(visible_rec_sections) - 1)) / len(visible_rec_sections))
        for idx, (title, rows_raw) in enumerate(visible_rec_sections):
            y = section_top + idx * (section_h + panel_gap)
            content = _draw_panel(draw_6, margin, y, width_px - margin * 2, section_h, title)
            cx1, cy1, cx2, cy2 = content
            rows_formatted: List[Dict[str, Any]] = []
            if isinstance(rows_raw, list):
                for item in rows_raw:
                    if not isinstance(item, dict):
                        continue
                    rows_formatted.append(
                        {
                            "action": normalize_pdf_text(str(item.get("action") or "")),
                            "reason": normalize_pdf_text(str(item.get("reason") or "")),
                            "sku": normalize_pdf_text(str(item.get("sku") or "")),
                        }
                    )
            _draw_table(
                draw_6,
                (cx1, cy1, cx2, cy2),
                [
                    ("Действие", "action", 33),
                    ("Причина", "reason", 47),
                    ("SKU", "sku", 20),
                ],
                rows_formatted,
                "Нет рекомендаций",
            )
        pages.append(page_6)

    # Page 7: Profit by SKU
    page_7, draw_7 = _new_page()
    draw_7.text((margin, margin), normalize_pdf_text("Прибыль по SKU"), font=fonts["h1"], fill=colors["title"])
    profit_content = _draw_panel(
        draw_7,
        margin,
        margin + 84,
        width_px - margin * 2,
        height_px - (margin + 84) - margin,
        "Товарная прибыль",
    )
    sku_profit_rows_raw = payload.get("sku_profit_rows", [])
    if not isinstance(sku_profit_rows_raw, list):
        sku_profit_rows_raw = []
    sku_profit_rows: List[Dict[str, Any]] = []
    for row in sku_profit_rows_raw:
        if not isinstance(row, dict):
            continue
        sku = normalize_pdf_text(str(row.get("sku") or "").strip())
        if not sku:
            continue
        sku_profit_rows.append(
            {
                "sku": sku,
                "revenue": normalize_pdf_text(str(row.get("revenue") or "нет данных")),
                "ads": normalize_pdf_text(str(row.get("ads_spend") or "нет данных")),
                "profit": normalize_pdf_text(str(row.get("profit") or "нет данных")),
            }
        )
    _draw_table(
        draw_7,
        profit_content,
        [
            ("SKU", "sku", 21),
            ("К перечислению продавцу", "revenue", 26),
            ("Расход на рекламу", "ads", 27),
            ("Прибыль", "profit", 26),
        ],
        sku_profit_rows,
        "Недостаточно данных для визуализации",
    )
    pages.append(page_7)

    territorial = payload.get("territorial_localization", {})
    if not isinstance(territorial, dict):
        territorial = {}
    territorial_show = bool(territorial.get("show")) or bool(territorial)
    if territorial_show:
        # Page 8: Territorial status, data quality and recommendations
        page_8, draw_8 = _new_page()
        draw_8.text((margin, margin), normalize_pdf_text("Локализация спроса и размещение остатков"), font=fonts["h1"], fill=colors["title"])

        top_panel_h = 620
        status_content = _draw_panel(
            draw_8,
            margin,
            margin + 84,
            width_px - margin * 2,
            top_panel_h,
            "Статус анализа и качество данных",
        )
        sx1, sy1, sx2, sy2 = status_content
        analysis_status_label = normalize_pdf_text(str(territorial.get("analysis_status_label") or "").strip())
        summary_lines = territorial.get("summary_lines", [])
        if not isinstance(summary_lines, list):
            summary_lines = []
        note_line = normalize_pdf_text(str(territorial.get("note") or "").strip())

        y_cursor = sy1 + 2
        if analysis_status_label:
            draw_8.text(
                (sx1, y_cursor),
                _fit_text(draw_8, f"Статус: {analysis_status_label}", fonts["body"], sx2 - sx1 - 8),
                font=fonts["body"],
                fill=colors["text"],
            )
            y_cursor += 34
        for line in summary_lines[:4]:
            prepared = normalize_pdf_text(str(line or "").strip())
            if not prepared:
                continue
            draw_8.text((sx1, y_cursor), _fit_text(draw_8, prepared, fonts["small"], sx2 - sx1 - 8), font=fonts["small"], fill=colors["text"])
            y_cursor += 28
        if note_line:
            draw_8.text((sx1, y_cursor), _fit_text(draw_8, note_line, fonts["small"], sx2 - sx1 - 8), font=fonts["small"], fill=colors["muted"])
            y_cursor += 28

        quality_rows = territorial.get("quality_rows", [])
        if not isinstance(quality_rows, list):
            quality_rows = []
        quality_box = (sx1, min(y_cursor + 10, sy2 - 260), sx2, sy2)
        _draw_table(
            draw_8,
            quality_box,
            [
                ("Показатель", "metric", 60),
                ("Значение", "value", 40),
            ],
            quality_rows,
            "Нет доступных данных по качеству территориального анализа",
        )

        bottom_panel_y = margin + 84 + top_panel_h + panel_gap
        bottom_panel_h = height_px - bottom_panel_y - margin
        insights_content = _draw_panel(
            draw_8,
            margin,
            bottom_panel_y,
            width_px - margin * 2,
            bottom_panel_h,
            "Что удалось понять и куда смотреть дальше",
        )
        ix1, iy1, ix2, iy2 = insights_content
        insight_counts = territorial.get("insight_counts", {})
        if not isinstance(insight_counts, dict):
            insight_counts = {}
        counts_line = normalize_pdf_text(
            "SKU с non-local спросом: "
            f"{int(insight_counts.get('non_local_skus', 0) or 0)} | "
            "SKU с признаками mismatch: "
            f"{int(insight_counts.get('mismatch_skus', 0) or 0)} | "
            "SKU-кандидаты: "
            f"{int(insight_counts.get('candidate_skus', 0) or 0)}"
        )
        draw_8.text((ix1, iy1 + 2), _fit_text(draw_8, counts_line, fonts["small"], ix2 - ix1 - 8), font=fonts["small"], fill=colors["text"])

        split_mid = ix1 + int((ix2 - ix1) / 2)
        upper_start = iy1 + 40
        upper_end = min(iy1 + 300, iy2 - 210)

        blocked_reason_rows = territorial.get("blocked_reason_rows", [])
        if not isinstance(blocked_reason_rows, list):
            blocked_reason_rows = []
        _draw_table(
            draw_8,
            (ix1, upper_start, split_mid - 8, upper_end),
            [
                ("Причина ограничения", "reason", 74),
                ("SKU", "count", 26),
            ],
            blocked_reason_rows,
            "Критичные ограничения по данным не выявлены",
        )

        top_region_rows = territorial.get("top_demand_regions_rows", [])
        if not isinstance(top_region_rows, list):
            top_region_rows = []
        _draw_table(
            draw_8,
            (split_mid + 8, upper_start, ix2, upper_end),
            [
                ("Регион", "region", 46),
                ("Заказы", "orders", 24),
                ("Доля", "share", 30),
            ],
            top_region_rows,
            "Нет полной картины по регионам спроса",
        )

        recommendation_rows = territorial.get("recommendation_rows", [])
        if not isinstance(recommendation_rows, list):
            recommendation_rows = []
        _draw_table(
            draw_8,
            (ix1, upper_end + 16, ix2, iy2),
            [
                ("SKU", "sku", 10),
                ("Регион спроса", "region", 18),
                ("Доля спроса", "demand_share", 13),
                ("Доля остатков", "stock_share", 13),
                ("Разрыв", "gap", 12),
                ("Приоритет", "priority", 10),
                ("Комментарий", "comment", 24),
            ],
            recommendation_rows,
            "Кандидаты для перераспределения в этот день не выделены",
        )
        pages.append(page_8)

        # Page 9: SKU-level territorial table
        page_9, draw_9 = _new_page()
        draw_9.text((margin, margin), normalize_pdf_text("Локализация по SKU"), font=fonts["h1"], fill=colors["title"])
        sku_content = _draw_panel(
            draw_9,
            margin,
            margin + 84,
            width_px - margin * 2,
            height_px - (margin + 84) - margin,
            "SKU-профиль: спрос против размещения",
        )
        sku_rows = territorial.get("sku_rows", [])
        if not isinstance(sku_rows, list):
            sku_rows = []
        _draw_table(
            draw_9,
            sku_content,
            [
                ("SKU", "sku", 14),
                ("Статус", "status", 19),
                ("Локализация", "local_share", 14),
                ("Non-local заказы", "non_local_orders", 14),
                ("Топ-регион", "top_region", 16),
                ("Рекомендация", "recommendation", 23),
            ],
            sku_rows,
            "Нет доступных SKU-строк для территориальной таблицы",
        )
        pages.append(page_9)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    preview_paths: List[str] = []
    preview_dir = str(payload.get("preview_dir") or os.path.dirname(path))
    if preview_dir:
        os.makedirs(preview_dir, exist_ok=True)
        for idx, image in enumerate(pages, start=1):
            preview_path = os.path.join(preview_dir, f"report_preview_page_{idx}.png")
            image.save(preview_path, "PNG")
            preview_paths.append(preview_path)

    pages[0].save(path, "PDF", save_all=True, append_images=pages[1:], resolution=150.0)
    font_info["pages"] = str(len(pages))
    font_info["preview_images"] = preview_paths
    return font_info
