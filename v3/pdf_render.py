from __future__ import annotations

import os
from typing import Dict, List

from PIL import Image, ImageDraw, ImageFont


def _font_dirs() -> List[str]:
    here = os.path.dirname(__file__)
    dirs = [
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
    families = [
        ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
        ("arial.ttf", "arialbd.ttf"),
        ("tahoma.ttf", "tahomabd.ttf"),
    ]
    for directory in _font_dirs():
        for regular_name, bold_name in families:
            regular = os.path.join(directory, regular_name)
            if not os.path.isfile(regular):
                continue
            bold = os.path.join(directory, bold_name)
            return {
                "regular": regular,
                "bold": bold if os.path.isfile(bold) else regular,
                "family": os.path.splitext(os.path.basename(regular))[0],
            }
    raise FileNotFoundError(
        "No Cyrillic-capable TTF font found. Put DejaVuSans.ttf into v3/fonts/ or install Arial/Tahoma."
    )


def get_registered_pdf_font() -> Dict[str, str]:
    return _resolve_font_family()


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
        "title": ImageFont.truetype(font_info["bold"], size=46),
        "section": ImageFont.truetype(font_info["bold"], size=32),
        "subsection": ImageFont.truetype(font_info["bold"], size=26),
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
        line = str(raw)
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
