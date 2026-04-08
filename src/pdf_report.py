from __future__ import annotations

import logging
import os
import re
from io import BytesIO
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


def _normalize_heading_key(text: str) -> str:
    key = _coerce_text(text).strip().lower().replace("\u0451", "\u0435")
    key = re.sub(r"^\s*[-*•]+\s*", "", key)
    key = re.sub(r"^\s*\d+\.\s*", "", key)
    key = re.sub(r"\s*\.+\s*(\d+|\u043d/\u0434)\s*$", "", key)
    key = key.replace("—", "-")
    key = re.sub(r"\s+", " ", key).strip(" .:-")
    return key


def _is_toc_heading(title: str) -> bool:
    key = _normalize_heading_key(title)
    return key in {"\u043e\u0433\u043b\u0430\u0432\u043b\u0435\u043d\u0438\u0435", "\u0441\u043e\u0434\u0435\u0440\u0436\u0430\u043d\u0438\u0435"}


def _extract_toc_entry_title(line: str) -> str | None:
    match = re.match(r"^\s*[-*•]\s+(.*)$", line)
    if not match:
        return None
    title = _coerce_text(match.group(1)).strip()
    title = re.sub(r"\s*\.+\s*(\d+|\u043d/\u0434)\s*$", "", title)
    return title.strip()


def _format_toc_entry(title: str, page: int | None) -> str:
    clean_title = _coerce_text(title).strip()
    page_token = "\u043d/\u0434" if page is None else str(page)
    target_width = 62
    dots_count = max(6, target_width - len(clean_title) - len(page_token))
    return f"{clean_title} {'.' * dots_count} {page_token}"


def _fit_text_to_width(
    text: str,
    max_width: float,
    *,
    font_name: str,
    font_size: float,
    suffix: str = "...",
) -> str:
    clean = _coerce_text(text).strip()
    if max_width <= 0:
        return ""
    if pdfmetrics.stringWidth(clean, font_name, font_size) <= max_width:
        return clean

    suffix_width = pdfmetrics.stringWidth(suffix, font_name, font_size)
    if suffix_width >= max_width:
        return ""

    low = 0
    high = len(clean)
    while low < high:
        mid = (low + high + 1) // 2
        candidate = clean[:mid].rstrip()
        width = pdfmetrics.stringWidth(candidate, font_name, font_size) + suffix_width
        if width <= max_width:
            low = mid
        else:
            high = mid - 1

    fitted = clean[:low].rstrip()
    if not fitted:
        return ""
    return f"{fitted}{suffix}"


def _build_toc_leader(
    title: str,
    *,
    leader_width: float,
    font_name: str,
    font_size: float,
    min_dots: int = 8,
) -> str:
    clean_title = _coerce_text(title).strip()
    dot_width = pdfmetrics.stringWidth(".", font_name, font_size)
    space_width = pdfmetrics.stringWidth(" ", font_name, font_size)
    if dot_width <= 0:
        return clean_title

    # Keep at least a short dotted trail and one space before the page number column.
    required_for_min_dots = (min_dots * dot_width) + (2 * space_width)
    title_max_width = max(0.0, leader_width - required_for_min_dots)
    safe_title = _fit_text_to_width(
        clean_title,
        title_max_width,
        font_name=font_name,
        font_size=font_size,
        suffix="...",
    )

    title_width = pdfmetrics.stringWidth(safe_title, font_name, font_size)
    remaining = max(0.0, leader_width - title_width - (2 * space_width))
    dots_count = max(min_dots, int(remaining / dot_width))

    leader = f"{safe_title} {'.' * dots_count} "
    while dots_count > min_dots and pdfmetrics.stringWidth(leader, font_name, font_size) > leader_width:
        dots_count -= 1
        leader = f"{safe_title} {'.' * dots_count} "
    return leader


def _resolve_toc_page(entry_title: str, section_pages: dict[str, int]) -> int | None:
    entry_key = _normalize_heading_key(entry_title)
    if not entry_key:
        return None

    direct = section_pages.get(entry_key)
    if direct is not None:
        return direct

    best_match_key = ""
    best_match_page: int | None = None
    for section_key, page in section_pages.items():
        if entry_key in section_key or section_key in entry_key:
            if len(section_key) > len(best_match_key):
                best_match_key = section_key
                best_match_page = page
    return best_match_page


def _logical_page_number(physical_page: int, *, skip_first_page_numbering: bool) -> int | None:
    if skip_first_page_numbering:
        if physical_page <= 1:
            return None
        return physical_page - 1
    if physical_page <= 0:
        return None
    return physical_page


class _TrackingDocTemplate(SimpleDocTemplate):
    def __init__(self, *args: Any, heading_pages: dict[str, int], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._heading_pages = heading_pages

    def afterFlowable(self, flowable: Any) -> None:  # noqa: N802
        section_key = getattr(flowable, "_wb_heading_key", "")
        if not section_key:
            return
        if section_key in self._heading_pages:
            return
        self._heading_pages[section_key] = int(self.canv.getPageNumber())


def _build_story(
    *,
    doc: SimpleDocTemplate,
    markdown_text: str,
    h1: ParagraphStyle,
    h2: ParagraphStyle,
    h3: ParagraphStyle,
    body: ParagraphStyle,
    font_info: dict[str, str],
    toc_pages: dict[str, int] | None = None,
    capture_headings: bool = False,
) -> list[Any]:
    story: list[Any] = []
    in_toc_section = False

    def _append_page_break() -> None:
        if not story:
            return
        if isinstance(story[-1], PageBreak):
            return
        story.append(PageBreak())

    def _attach_heading_key(paragraph: Paragraph, heading_text: str) -> Paragraph:
        if capture_headings:
            paragraph._wb_heading_key = _normalize_heading_key(heading_text)  # type: ignore[attr-defined]
        return paragraph

    for block in _split_blocks(markdown_text):
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
                heading_text = line[2:].strip()
                in_toc_section = False
                para = Paragraph(_esc(heading_text), h1)
                story.append(_attach_heading_key(para, heading_text))
                continue

            if line.startswith("## "):
                heading_text = line[3:].strip()
                in_toc_section = _is_toc_heading(heading_text)
                para = Paragraph(_esc(heading_text), h2)
                story.append(_attach_heading_key(para, heading_text))
                continue

            if line.startswith("### "):
                story.append(Paragraph(_esc(line[4:].strip()), h3))
                continue

            if in_toc_section:
                toc_title = _extract_toc_entry_title(line)
                if toc_title:
                    page = _resolve_toc_page(toc_title, toc_pages or {}) if toc_pages else None
                    page_token = "\u043d/\u0434" if page is None else str(page)
                    page_col_width = max(
                        12 * mm,
                        pdfmetrics.stringWidth(page_token, body.fontName, body.fontSize) + (2 * mm),
                    )
                    leader_col_width = max(24 * mm, doc.width - page_col_width)
                    leader = _build_toc_leader(
                        toc_title,
                        leader_width=leader_col_width,
                        font_name=body.fontName,
                        font_size=body.fontSize,
                        min_dots=8,
                    )
                    toc_table = Table(
                        [[Paragraph(_esc(leader), body), Paragraph(_esc(page_token), body)]],
                        colWidths=[leader_col_width, page_col_width],
                        hAlign="LEFT",
                    )
                    toc_table.setStyle(
                        TableStyle(
                            [
                                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                ("TOPPADDING", (0, 0), (-1, -1), 0),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                            ]
                        )
                    )
                    story.append(toc_table)
                    story.append(Spacer(1, 1))
                    continue

            bullet_match = re.match(r"^\s*[-*•]\s+(.*)$", line)
            if bullet_match:
                story.append(Paragraph(f"• {_esc(bullet_match.group(1).strip())}", body))
                continue

            story.append(Paragraph(_esc(line), body))

        story.append(Spacer(1, 4))

    return story


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

    base_doc_args = dict(
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

    toc_pages: dict[str, int] = {}
    previous_snapshot: tuple[tuple[str, int], ...] | None = None

    # Two-pass stabilization:
    # 1) collect section start pages;
    # 2) rebuild TOC with real numbers;
    # if TOC text slightly shifts pages, one extra probe pass updates mapping.
    for _ in range(2):
        heading_pages_physical: dict[str, int] = {}
        probe_doc = _TrackingDocTemplate(
            BytesIO(),
            heading_pages=heading_pages_physical,
            **base_doc_args,
        )
        probe_story = _build_story(
            doc=probe_doc,
            markdown_text=md,
            h1=h1,
            h2=h2,
            h3=h3,
            body=body,
            font_info=font_info,
            toc_pages=toc_pages if toc_pages else None,
            capture_headings=True,
        )
        probe_doc.build(probe_story)

        computed_toc_pages: dict[str, int] = {}
        for section_key, physical_page in heading_pages_physical.items():
            logical_page = _logical_page_number(
                physical_page,
                skip_first_page_numbering=skip_first_page_numbering,
            )
            if logical_page is not None:
                computed_toc_pages[section_key] = logical_page

        snapshot = tuple(sorted(computed_toc_pages.items()))
        toc_pages = computed_toc_pages
        if snapshot == previous_snapshot:
            break
        previous_snapshot = snapshot

    doc = SimpleDocTemplate(str(target), **base_doc_args)
    story = _build_story(
        doc=doc,
        markdown_text=md,
        h1=h1,
        h2=h2,
        h3=h3,
        body=body,
        font_info=font_info,
        toc_pages=toc_pages,
        capture_headings=False,
    )

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
