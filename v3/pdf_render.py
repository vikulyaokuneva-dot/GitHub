from __future__ import annotations

import math
import os
import re
import unicodedata
from typing import Any, Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont


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
    normalized = repair_mojibake(source).replace("\ufeff", "")
    normalized = unicodedata.normalize("NFC", normalized)
    # Fix common mojibake punctuation that can survive codec repair heuristics.
    for bad_dash in ("\u00e2\u20ac\u201d", "\u0420\u0406\u0420\u201a\u0432\u0402\u045c", "\u00e2\u20ac\u201c", "\u0420\u0406\u0420\u201a\u0432\u0402\u201c", "\u0432\u0402\u201d"):
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

    not_enough = normalize_pdf_text("Недостаточно данных для визуализации")

    # Page 1: KPI cards
    page_1, draw_1 = _new_page()
    seller_id = normalize_pdf_text(str(payload.get("seller_id") or ""))
    run_date = normalize_pdf_text(str(payload.get("run_date") or ""))
    operational_day = normalize_pdf_text(str(payload.get("operational_day") or run_date))
    draw_1.text((margin, margin), normalize_pdf_text("WB AI Agent v3"), font=fonts["h1"], fill=colors["title"])
    draw_1.text(
        (margin, margin + 64),
        normalize_pdf_text(f"Кабинет: {seller_id}    Отчетная дата: {run_date}    Операционный день: {operational_day}"),
        font=fonts["body"],
        fill=colors["muted"],
    )
    draw_1.text((margin, margin + 126), normalize_pdf_text("Ключевые показатели дня"), font=fonts["h2"], fill=colors["title"])

    kpi_cards = payload.get("kpi_cards", [])
    if not isinstance(kpi_cards, list):
        kpi_cards = []

    card_y = margin + 182
    card_gap = 18
    card_w = int((width_px - margin * 2 - card_gap * 3) / 4)
    card_h = 320
    for idx, card in enumerate(kpi_cards[:4]):
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
        if value == "??? ??????" or len(value) >= 10:
            value_font = fonts["h2"]
        elif len(value) >= 8:
            value_font = fonts["h3"]
        _draw_centered_text(draw_1, (x + 12, y + 40, x + card_w - 12, y + 120), label, fonts["kpi_label"], colors["muted"])
        _draw_centered_text(
            draw_1,
            (x + 12, y + 128, x + card_w - 12, y + card_h - 48),
            normalize_pdf_text(value),
            value_font,
            colors["dark_blue"],
        )

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
    top_content = _draw_panel(
        draw_2,
        margin,
        margin + 84,
        width_px - margin * 2,
        top_panel_h,
        "Структура расходов",
    )
    left, top, right, bottom = top_content

    expenses = payload.get("expense_structure", {})
    if not isinstance(expenses, dict):
        expenses = {}
    expense_rows = [
        ("Комиссия WB", _as_number(expenses.get("commission")), colors["gray"]),
        ("Логистика", _as_number(expenses.get("logistics")), colors["orange"]),
        ("Хранение", _as_number(expenses.get("storage")), colors["gray"]),
        ("Реклама", _as_number(expenses.get("ads")), colors["red"]),
        ("Себестоимость", _as_number(expenses.get("cost_price")), colors["blue"]),
        ("Налог", _as_number(expenses.get("tax")), colors["dark_gray"]),
    ]
    numeric_values = [abs(v) for _, v, _ in expense_rows if v is not None]
    if not numeric_values:
        draw_2.text((left, top + 18), not_enough, font=fonts["body"], fill=colors["muted"])
    else:
        max_value = max(max(numeric_values), 1.0)
        row_h = int((bottom - top - 24) / max(len(expense_rows), 1))
        label_w = 245
        value_w = 110
        bar_max_w = max(60, (right - left - label_w - value_w - 32))
        for idx, (label, value, color) in enumerate(expense_rows):
            y = top + idx * row_h + 6
            draw_2.text((left, y + 6), normalize_pdf_text(label), font=fonts["body"], fill=colors["text"])
            bar_x = left + label_w
            bar_y = y + 14
            draw_2.rounded_rectangle(
                (bar_x, bar_y, bar_x + bar_max_w, bar_y + 24),
                radius=8,
                fill=(237, 240, 246),
                outline=(228, 232, 240),
            )
            if value is not None:
                bar_w = int((abs(value) / max_value) * bar_max_w)
                draw_2.rounded_rectangle(
                    (bar_x, bar_y, bar_x + max(2, bar_w), bar_y + 24),
                    radius=8,
                    fill=color,
                    outline=color,
                )
                val_text = _format_money(abs(value))
            else:
                val_text = "нет данных"
            draw_2.text((bar_x + bar_max_w + 12, y + 6), normalize_pdf_text(val_text), font=fonts["body"], fill=colors["text"])

    bottom_panel_y = margin + 84 + top_panel_h + panel_gap
    bottom_panel_h = height_px - bottom_panel_y - margin
    ad_content = _draw_panel(
        draw_2,
        margin,
        bottom_panel_y,
        width_px - margin * 2,
        bottom_panel_h,
        "Эффективность рекламы",
    )
    left, top, right, bottom = ad_content
    ads = payload.get("ads_efficiency", {})
    if not isinstance(ads, dict):
        ads = {}
    ad_spend = _as_number(ads.get("ad_spend"))
    ad_revenue = _as_number(ads.get("ad_revenue"))
    if ad_spend is None and ad_revenue is None:
        draw_2.text((left, top + 18), not_enough, font=fonts["body"], fill=colors["muted"])
    else:
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
    pages.append(page_2)

    # Page 3: Funnel + SKU donut
    page_3, draw_3 = _new_page()
    draw_3.text((margin, margin), normalize_pdf_text("Воронка и статус ассортимента"), font=fonts["h1"], fill=colors["title"])

    funnel_panel_h = 900
    funnel_content = _draw_panel(
        draw_3,
        margin,
        margin + 84,
        width_px - margin * 2,
        funnel_panel_h,
        "Воронка продаж",
    )
    left, top, right, bottom = funnel_content
    funnel = payload.get("funnel", {})
    if not isinstance(funnel, dict):
        funnel = {}
    funnel_stages = [
        ("Просмотры", _as_number(funnel.get("views"))),
        ("Добавления в корзину", _as_number(funnel.get("add_to_cart"))),
        ("Заказы", _as_number(funnel.get("orders"))),
        ("Выкупы", _as_number(funnel.get("buyouts"))),
    ]
    positive_values = [v for _, v in funnel_stages if v is not None and v > 0]
    if len(positive_values) < 2:
        draw_3.text((left, top + 18), not_enough, font=fonts["body"], fill=colors["muted"])
    else:
        max_val = max(positive_values)
        min_w = 280
        max_w = right - left - 280
        if max_w < min_w:
            max_w = min_w + 60
        heights = [130, 130, 130, 130]
        stage_y = top + 24
        cx = left + (max_w // 2) + 40
        widths: List[int] = []
        for _, value in funnel_stages:
            if value is None or value <= 0:
                widths.append(min_w)
            else:
                ratio = (value / max_val) ** 0.65
                widths.append(int(min_w + (max_w - min_w) * ratio))
        stage_colors = [(119, 153, 194), (97, 136, 183), (73, 114, 166), (48, 90, 146)]
        for idx, (label, value) in enumerate(funnel_stages):
            top_w = widths[idx]
            bottom_w = widths[idx + 1] if idx < len(widths) - 1 else max(int(widths[idx] * 0.88), min_w - 10)
            h = heights[idx]
            y1 = stage_y
            y2 = stage_y + h
            polygon = [
                (cx - top_w // 2, y1),
                (cx + top_w // 2, y1),
                (cx + bottom_w // 2, y2),
                (cx - bottom_w // 2, y2),
            ]
            draw_3.polygon(polygon, fill=stage_colors[idx], outline=(255, 255, 255))
            value_text = _format_int(value) if value is not None else "нет данных"
            draw_3.text((cx - top_w // 2 + 22, y1 + 42), normalize_pdf_text(f"{label}: {value_text}"), font=fonts["body"], fill=(255, 255, 255))
            if idx < len(funnel_stages) - 1:
                next_val = funnel_stages[idx + 1][1]
                conversion = None
                if value is not None and value > 0 and next_val is not None:
                    conversion = (next_val / value) * 100.0
                draw_3.text(
                    (cx + max_w // 2 + 26, y1 + 44),
                    normalize_pdf_text(f"Конверсия: {_format_pct(conversion)}"),
                    font=fonts["small"],
                    fill=colors["text"],
                )
            stage_y = y2 + 18

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

    os.makedirs(os.path.dirname(path), exist_ok=True)
    preview_paths: List[str] = []
    preview_dir = str(payload.get("preview_dir") or os.path.dirname(path))
    if preview_dir:
        os.makedirs(preview_dir, exist_ok=True)
        for idx, image in enumerate(pages[:3], start=1):
            preview_path = os.path.join(preview_dir, f"report_preview_page_{idx}.png")
            image.save(preview_path, "PNG")
            preview_paths.append(preview_path)

    pages[0].save(path, "PDF", save_all=True, append_images=pages[1:], resolution=150.0)
    font_info["pages"] = str(len(pages))
    font_info["preview_images"] = preview_paths
    return font_info
