from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

LOGGER = logging.getLogger(__name__)

FONT_FAMILY_NAME = "WBUnicodeSans"
FONT_REGULAR_NAME = f"{FONT_FAMILY_NAME}-Regular"
FONT_BOLD_NAME = f"{FONT_FAMILY_NAME}-Bold"

_REGISTERED_FONTS: Dict[str, str] | None = None

# Preferred unicode font families with Cyrillic support.
_FONT_FILE_CANDIDATES: tuple[tuple[str, str], ...] = (
    ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
    ("NotoSans-Regular.ttf", "NotoSans-Bold.ttf"),
    ("NotoSans.ttf", "NotoSans-Bold.ttf"),
    ("LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf"),
    ("arial.ttf", "arialbd.ttf"),
)


def _candidate_font_dirs() -> list[Path]:
    base_dir = Path(__file__).resolve().parent
    repo_root = base_dir.parent

    dirs: list[Path] = [
        repo_root / "assets" / "fonts",
        base_dir / "fonts",
        repo_root / "fonts",
        base_dir,
        repo_root,
    ]

    env_dir = str(os.getenv("WB_PDF_FONT_DIR", "")).strip()
    if env_dir:
        dirs.insert(0, Path(env_dir))

    windir = str(os.getenv("WINDIR", "")).strip()
    if windir:
        dirs.append(Path(windir) / "Fonts")

    dirs.extend(
        [
            Path("/usr/share/fonts/truetype/dejavu"),
            Path("/usr/share/fonts/truetype/noto"),
            Path("/usr/share/fonts/truetype/liberation"),
            Path("/usr/share/fonts/truetype"),
            Path("/usr/share/fonts"),
        ]
    )

    unique_dirs: list[Path] = []
    seen: set[str] = set()
    for item in dirs:
        key = str(item.resolve()) if item.exists() else str(item)
        if key in seen:
            continue
        seen.add(key)
        unique_dirs.append(item)
    return unique_dirs


def _font_not_found_error(attempted: list[Path]) -> FileNotFoundError:
    attempted_lines = "\n".join(f"  - {path}" for path in attempted[:60]) or "  - no paths tried"
    message = (
        "Unicode PDF font with Cyrillic support was not found.\n"
        "Tried to locate one of the following: "
        "DejaVuSans, NotoSans, LiberationSans, Arial.\n"
        "Set WB_PDF_FONT_REGULAR/WB_PDF_FONT_BOLD env vars or place fonts in assets/fonts/.\n"
        f"Attempted paths:\n{attempted_lines}"
    )
    return FileNotFoundError(message)


def _find_font_files() -> tuple[Path, Path, list[Path]]:
    attempted: list[Path] = []
    search_dirs = _candidate_font_dirs()

    env_regular = str(os.getenv("WB_PDF_FONT_REGULAR", "")).strip()
    env_bold = str(os.getenv("WB_PDF_FONT_BOLD", "")).strip()
    if env_regular:
        regular = Path(env_regular)
        attempted.append(regular)
        if not regular.is_file():
            raise _font_not_found_error(attempted)

        if env_bold:
            bold = Path(env_bold)
            attempted.append(bold)
            if not bold.is_file():
                raise _font_not_found_error(attempted)
        else:
            bold = None
            for regular_name, bold_name in _FONT_FILE_CANDIDATES:
                if regular.name.lower() == regular_name.lower():
                    sibling = regular.parent / bold_name
                    attempted.append(sibling)
                    if sibling.is_file():
                        bold = sibling
                        break
            if bold is None:
                # Fallback to regular for bold to keep rendering deterministic.
                bold = regular
                LOGGER.warning("WB_PDF_FONT_BOLD is not set; using regular font for bold style: %s", regular)
        return regular, bold, attempted

    for directory in search_dirs:
        for regular_name, bold_name in _FONT_FILE_CANDIDATES:
            regular = directory / regular_name
            attempted.append(regular)
            if not regular.is_file():
                continue

            bold = directory / bold_name
            attempted.append(bold)
            if not bold.is_file():
                for alt_dir in search_dirs:
                    alt_bold = alt_dir / bold_name
                    attempted.append(alt_bold)
                    if alt_bold.is_file():
                        bold = alt_bold
                        break
                else:
                    LOGGER.warning(
                        "Bold font '%s' not found next to '%s'; using regular font for bold style.",
                        bold_name,
                        regular,
                    )
                    bold = regular
            return regular, bold, attempted

    raise _font_not_found_error(attempted)


def _is_registered(font_name: str) -> bool:
    try:
        pdfmetrics.getFont(font_name)
        return True
    except KeyError:
        return False


def _ensure_pdf_fonts_registered() -> Dict[str, str]:
    global _REGISTERED_FONTS

    if _REGISTERED_FONTS is not None:
        return dict(_REGISTERED_FONTS)

    regular_path, bold_path, _ = _find_font_files()

    try:
        if not _is_registered(FONT_REGULAR_NAME):
            pdfmetrics.registerFont(TTFont(FONT_REGULAR_NAME, str(regular_path)))
        if not _is_registered(FONT_BOLD_NAME):
            pdfmetrics.registerFont(TTFont(FONT_BOLD_NAME, str(bold_path)))
        pdfmetrics.registerFontFamily(
            FONT_FAMILY_NAME,
            normal=FONT_REGULAR_NAME,
            bold=FONT_BOLD_NAME,
            italic=FONT_REGULAR_NAME,
            boldItalic=FONT_BOLD_NAME,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Failed to register PDF Unicode fonts: regular={regular_path}, bold={bold_path}"
        ) from exc

    _REGISTERED_FONTS = {
        "family": FONT_FAMILY_NAME,
        "regular_name": FONT_REGULAR_NAME,
        "bold_name": FONT_BOLD_NAME,
        "regular_path": str(regular_path),
        "bold_path": str(bold_path),
    }

    LOGGER.info("Registered PDF fonts for Unicode rendering: %s", _REGISTERED_FONTS)
    return dict(_REGISTERED_FONTS)


def get_pdf_font_diagnostics() -> Dict[str, str]:
    return _ensure_pdf_fonts_registered()


def _coerce_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if value is None:
        return ""
    return str(value)


def _normalize_markdown(md: str | bytes) -> str:
    text = _coerce_text(md)

    # Convert escaped newlines/tabs coming from JSON.
    text = text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "    ")

    # Remove odd chars.
    text = text.replace("\ufeff", "").replace("\uFFFE", "").replace("\u0000", "")

    # Collapse too many blank lines.
    text = re.sub(r"\n{4,}", "\n\n\n", text)

    # Ensure headings are separated.
    text = re.sub(r"(?m)^(#{1,6}\s+.*)$", r"\n\1\n", text)

    return text.strip() + "\n"


def _split_blocks(md: str) -> List[str]:
    lines = md.splitlines()
    blocks: List[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]

        if line.strip().startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            blocks.append("\n".join(table_lines).strip())
            continue

        text_lines = []
        while i < len(lines) and not lines[i].strip().startswith("|"):
            text_lines.append(lines[i])
            i += 1
            if len(text_lines) >= 2 and text_lines[-1].strip() == "" and text_lines[-2].strip() == "":
                break

        block = "\n".join(text_lines).strip()
        if block:
            blocks.append(block)

    return blocks


def _parse_md_table(block: str) -> List[List[str]]:
    rows: List[List[str]] = []
    for ln in block.splitlines():
        ln = ln.strip()
        if not ln.startswith("|"):
            continue
        if re.match(r"^\|\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$", ln):
            continue
        parts = [part.strip() for part in ln.strip("|").split("|")]
        rows.append(parts)

    if not rows:
        return []

    width = max(len(r) for r in rows)
    for row in rows:
        while len(row) < width:
            row.append("")
    return rows


def _esc(text: str) -> str:
    value = _coerce_text(text)
    value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Minimal inline markdown support for emphasis in generated reports.
    value = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", value)
    value = value.replace("\n", "<br/>")
    return value


class _PageNumberCanvas(canvas.Canvas):
    def __init__(
        self,
        *args: Any,
        footer_font_name: str,
        footer_font_size: float = 9.0,
        footer_format: str = "Стр. {page} из {total}",
        skip_first_page: bool = True,
        footer_align: str = "center",
        footer_right_margin: float = 16 * mm,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, Any]] = []
        self._footer_font_name = footer_font_name
        self._footer_font_size = footer_font_size
        self._footer_format = footer_format
        self._skip_first_page = skip_first_page
        self._footer_align = footer_align
        self._footer_right_margin = footer_right_margin

    def showPage(self) -> None:  # noqa: N802
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total_physical_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_footer(total_physical_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def _draw_footer(self, total_physical_pages: int) -> None:
        physical_page = int(self._pageNumber)

        if self._skip_first_page:
            if physical_page <= 1:
                return
            page = physical_page - 1
            total = total_physical_pages - 1
        else:
            page = physical_page
            total = total_physical_pages

        if total <= 0:
            return

        text = self._footer_format.format(
            page=page,
            total=total,
            physical_page=physical_page,
            physical_total=total_physical_pages,
        )

        width, _ = self._pagesize
        y = 8 * mm

        self.saveState()
        self.setFont(self._footer_font_name, self._footer_font_size)
        self.setFillColor(colors.grey)

        if self._footer_align == "right":
            self.drawRightString(width - self._footer_right_margin, y, text)
        else:
            self.drawCentredString(width / 2.0, y, text)

        self.restoreState()


def markdown_to_simple_pdf(
    markdown_text: str | bytes,
    pdf_path: str | os.PathLike[str],
    title: str = "Report",
    *,
    page_number_format: str = "Стр. {page} из {total}",
    page_number_align: str = "center",
    skip_first_page_numbering: bool = True,
) -> None:
    font_info = _ensure_pdf_fonts_registered()
    md = _normalize_markdown(markdown_text)

    target = Path(pdf_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(target),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=_coerce_text(title),
    )

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle(
        "H1",
        parent=styles["Heading1"],
        fontName=font_info["bold_name"],
        fontSize=16,
        leading=20,
        spaceBefore=6,
        spaceAfter=10,
        keepWithNext=True,
    )
    h2 = ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        fontName=font_info["bold_name"],
        fontSize=13,
        leading=16,
        spaceBefore=10,
        spaceAfter=6,
        keepWithNext=True,
    )
    h3 = ParagraphStyle(
        "H3",
        parent=styles["Heading3"],
        fontName=font_info["bold_name"],
        fontSize=11.5,
        leading=14,
        spaceBefore=8,
        spaceAfter=4,
        keepWithNext=True,
    )
    body = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontName=font_info["regular_name"],
        fontSize=10.5,
        leading=14,
        spaceBefore=0,
        spaceAfter=3,
    )

    story: list[Any] = []

    def _append_page_break() -> None:
        if not story:
            return
        if isinstance(story[-1], PageBreak):
            return
        story.append(PageBreak())

    for block in _split_blocks(md):
        if block.strip() == "---PAGEBREAK---":
            _append_page_break()
            continue

        if block.splitlines() and block.splitlines()[0].strip().startswith("|"):
            rows = _parse_md_table(block)
            if rows:
                tbl_data = [[Paragraph(_esc(cell), body) for cell in row] for row in rows]
                col_count = len(tbl_data[0])
                col_width = (A4[0] - doc.leftMargin - doc.rightMargin) / col_count
                table = Table(tbl_data, hAlign="LEFT", colWidths=[col_width] * col_count, repeatRows=1)

                table_style = TableStyle(
                    [
                        ("FONTNAME", (0, 0), (-1, 0), font_info["bold_name"]),
                        ("FONTNAME", (0, 1), (-1, -1), font_info["regular_name"]),
                        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                        ("LINEBELOW", (0, 0), (-1, 0), 1, colors.grey),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
                for row_index in range(1, len(tbl_data)):
                    if row_index % 2 == 0:
                        table_style.add("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#FAFAFA"))
                table.setStyle(table_style)

                story.append(table)
                story.append(Spacer(1, 8))
                continue

        for raw_line in block.splitlines():
            line = raw_line.rstrip()
            if line.strip() == "---PAGEBREAK---":
                _append_page_break()
                continue
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

            bullet_match = re.match(r"^\s*[-•]\s+(.*)$", line)
            if bullet_match:
                story.append(Paragraph(f"• {_esc(bullet_match.group(1).strip())}", body))
                continue

            story.append(Paragraph(_esc(line), body))

        story.append(Spacer(1, 4))

    normalized_align = str(page_number_align or "center").strip().lower()
    if normalized_align not in {"center", "right"}:
        normalized_align = "center"

    def _canvas_factory(*args: Any, **kwargs: Any) -> _PageNumberCanvas:
        return _PageNumberCanvas(
            *args,
            footer_font_name=font_info["regular_name"],
            footer_format=page_number_format,
            skip_first_page=skip_first_page_numbering,
            footer_align=normalized_align,
            footer_right_margin=doc.rightMargin,
            **kwargs,
        )

    doc.build(story, canvasmaker=_canvas_factory)


__all__ = ["markdown_to_simple_pdf", "get_pdf_font_diagnostics"]
