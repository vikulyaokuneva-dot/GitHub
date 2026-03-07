# src/pdf_report.py
import os
import re
from typing import List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)

# ---------------------------
# Font (Cyrillic) — robust
# ---------------------------

def _find_font_file() -> str | None:
    """
    Try to find DejaVuSans.ttf in:
    - repo paths (relative to this file and CWD)
    - common Linux system locations (GitHub Actions)
    """
    base_dir = os.path.dirname(__file__)  # .../src
    candidates = [
        # recommended: src/fonts/DejaVuSans.ttf
        os.path.join(base_dir, "fonts", "DejaVuSans.ttf"),
        # sometimes fonts folder is at repo root: fonts/DejaVuSans.ttf
        os.path.join(os.getcwd(), "fonts", "DejaVuSans.ttf"),
        # sometimes you placed it at src/DejaVuSans.ttf
        os.path.join(base_dir, "DejaVuSans.ttf"),
        # sometimes at repo root
        os.path.join(os.getcwd(), "DejaVuSans.ttf"),
        # common paths in Ubuntu runners
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf",
    ]
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


_FONT_PATH = _find_font_file()
if not _FONT_PATH:
    # IMPORTANT: fail loudly so we don't silently produce ■■■■
    raise FileNotFoundError(
        "Не найден кириллический шрифт DejaVuSans.ttf.\n"
        "Ожидаемый путь: src/fonts/DejaVuSans.ttf (в репозитории, закоммичен!).\n"
        "Либо установи шрифт в системе runner.\n"
        f"CWD={os.getcwd()}, __file__={__file__}"
    )

pdfmetrics.registerFont(TTFont("DejaVuSans", _FONT_PATH))
BASE_FONT = "DejaVuSans"


# ---------------------------
# Markdown helpers
# ---------------------------

def _normalize_markdown(md: str) -> str:
    """Normalize markdown coming from LLM/JSON."""
    if md is None:
        return ""
    s = str(md)

    # Convert escaped newlines/tabs
    s = s.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "    ")

    # Remove odd chars
    s = s.replace("\ufeff", "").replace("\uFFFE", "").replace("\u0000", "")

    # Collapse too many blank lines
    s = re.sub(r"\n{4,}", "\n\n\n", s)

    # Ensure headings are separated
    s = re.sub(r"(?m)^(#{1,6}\s+.*)$", r"\n\1\n", s)

    return s.strip() + "\n"


def _split_blocks(md: str) -> List[str]:
    """Split markdown into blocks: tables and text."""
    lines = md.splitlines()
    blocks: List[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Table block
        if line.strip().startswith("|"):
            tbl_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                tbl_lines.append(lines[i])
                i += 1
            blocks.append("\n".join(tbl_lines).strip())
            continue

        # Text block
        text_lines = []
        while i < len(lines) and (not lines[i].strip().startswith("|")):
            text_lines.append(lines[i])
            i += 1
            if len(text_lines) >= 2 and text_lines[-1].strip() == "" and text_lines[-2].strip() == "":
                break

        block = "\n".join(text_lines).strip()
        if block:
            blocks.append(block)

    return blocks


def _parse_md_table(block: str) -> List[List[str]]:
    """Parse markdown table rows."""
    rows: List[List[str]] = []
    for ln in block.splitlines():
        ln = ln.strip()
        if not ln.startswith("|"):
            continue
        # separator row like |---|---|
        if re.match(r"^\|\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$", ln):
            continue
        parts = [p.strip() for p in ln.strip("|").split("|")]
        rows.append(parts)

    if not rows:
        return []

    w = max(len(r) for r in rows)
    for r in rows:
        while len(r) < w:
            r.append("")
    return rows


def _esc(text: str) -> str:
    """Escape for reportlab Paragraph."""
    if text is None:
        return ""
    s = str(text)
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = s.replace("\n", "<br/>")
    return s


# ---------------------------
# Main PDF render
# ---------------------------

def markdown_to_simple_pdf(markdown_text: str, pdf_path: str, title: str = "Report") -> None:
    md = _normalize_markdown(markdown_text)

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=title,
    )

    styles = getSampleStyleSheet()

    h1 = ParagraphStyle(
        "H1",
        parent=styles["Heading1"],
        fontName=BASE_FONT,
        fontSize=16,
        leading=20,
        spaceBefore=6,
        spaceAfter=10,
    )
    h2 = ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        fontName=BASE_FONT,
        fontSize=13,
        leading=16,
        spaceBefore=10,
        spaceAfter=6,
    )
    h3 = ParagraphStyle(
        "H3",
        parent=styles["Heading3"],
        fontName=BASE_FONT,
        fontSize=11.5,
        leading=14,
        spaceBefore=8,
        spaceAfter=4,
    )
    body = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontName=BASE_FONT,
        fontSize=10.5,
        leading=14,
        spaceBefore=0,
        spaceAfter=3,
    )

    story = []
    blocks = _split_blocks(md)

    for block in blocks:
        if block.strip() == "---PAGEBREAK---":
            story.append(PageBreak())
            continue

        # Table
        if block.splitlines() and block.splitlines()[0].strip().startswith("|"):
            rows = _parse_md_table(block)
            if rows:
                tbl_data = [[Paragraph(_esc(cell), body) for cell in r] for r in rows]
                col_count = len(tbl_data[0])
                col_w = (A4[0] - doc.leftMargin - doc.rightMargin) / col_count
                table = Table(tbl_data, hAlign="LEFT", colWidths=[col_w] * col_count)

                ts = TableStyle([
                    ("FONT", (0, 0), (-1, -1), BASE_FONT, 9.5),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                    ("LINEBELOW", (0, 0), (-1, 0), 1, colors.grey),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ])
                for r in range(1, len(tbl_data)):
                    if r % 2 == 0:
                        ts.add("BACKGROUND", (0, r), (-1, r), colors.HexColor("#FAFAFA"))
                table.setStyle(ts)

                story.append(table)
                story.append(Spacer(1, 8))
                continue

        # Regular text
        for ln in block.splitlines():
            line = ln.rstrip()
            if not line.strip():
                story.append(Spacer(1, 6))
                continue

            if line.startswith("# "):
                story.append(Paragraph(_esc(line[2:].strip()), h1))
                continue
            if line.startswith("## "):
                story.append(Paragraph(_esc(line[3:].strip()), h2))
                continue
            if line.startswith("### "):
                story.append(Paragraph(_esc(line[4:].strip()), h3))
                continue

            m = re.match(r"^\s*[-•]\s+(.*)$", line)
            if m:
                story.append(Paragraph(f"• {_esc(m.group(1).strip())}", body))
                continue

            story.append(Paragraph(_esc(line), body))

        story.append(Spacer(1, 4))

    doc.build(story)
