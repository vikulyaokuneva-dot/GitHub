from __future__ import annotations

import os
import re
from typing import Dict, List

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
    normalized = repair_mojibake(text)
    # Fix common mojibake punctuation that can survive codec repair heuristics.
    normalized = normalized.replace("вЂ”", "—")
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

