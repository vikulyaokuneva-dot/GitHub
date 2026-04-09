from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sys

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, SimpleDocTemplate, Spacer, Table

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import src.pdf_report as pdf_report  # noqa: E402


def _build_story(markdown_text: str, *, toc_entries: list[tuple[str, int | None]] | None = None):
    font_info = pdf_report._ensure_pdf_fonts_registered()
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontName=font_info["bold_name"])
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontName=font_info["bold_name"])
    h3 = ParagraphStyle("H3", parent=styles["Heading3"], fontName=font_info["bold_name"])
    callout_title = ParagraphStyle("CT", parent=styles["Heading3"], fontName=font_info["bold_name"])
    body = ParagraphStyle("B", parent=styles["BodyText"], fontName=font_info["regular_name"])
    doc = SimpleDocTemplate(
        BytesIO(),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )
    return pdf_report._build_story(
        doc=doc,
        markdown_text=markdown_text,
        h1=h1,
        h2=h2,
        h3=h3,
        callout_title=callout_title,
        body=body,
        font_info=font_info,
        toc_entries=toc_entries,
        capture_headings=False,
    )


def test_main_section_matching_handles_dash_variants_and_business_sections() -> None:
    assert pdf_report._match_main_section("6. Ассортимент / SKU") == "assortment"
    assert pdf_report._match_main_section("ТОП‑5 SKU: где зарабатываете и где теряете") == "top_sku"
    assert pdf_report._match_main_section("10. Потери из-за плохой локализации") == "losses"


def test_toc_renders_provided_titles_with_numeric_pages() -> None:
    markdown = (
        "## Оглавление\n"
        "- разделы\n\n"
        "## 6. Ассортимент / SKU\n"
        "Текст\n"
    )
    story = _build_story(markdown, toc_entries=[("6. Ассортимент / SKU", 12)])

    toc_rows = [
        flowable
        for flowable in story
        if isinstance(flowable, Table)
        and len(getattr(flowable, "_cellvalues", [])) == 1
        and len(flowable._cellvalues[0]) == 2
    ]
    assert toc_rows, "Expected at least one TOC row table to be rendered"

    left_cell = toc_rows[0]._cellvalues[0][0]
    right_cell = toc_rows[0]._cellvalues[0][1]
    assert "SKU" in left_cell.text
    assert "12" in right_cell.text
    assert "н/д" not in right_cell.text


def test_top_sku_and_action_summary_start_with_page_break() -> None:
    markdown = (
        "## 1. KPI и инсайты\n"
        "Текст\n\n"
        "## 6. Ассортимент / SKU\n"
        "Текст\n\n"
        "## ТОП-5 SKU: где зарабатываете и где теряете\n"
        "Текст\n\n"
        "## 12. План действий / рекомендации\n"
        "Текст\n\n"
        "## Итог: что делать\n"
        "Текст\n"
    )
    story = _build_story(markdown)

    has_pagebreak_before_top_sku = False
    has_pagebreak_before_action_summary = False
    for idx, flowable in enumerate(story):
        if not isinstance(flowable, pdf_report._SectionHeaderBar):
            continue
        heading = pdf_report._strip_visual_prefix(flowable._text)
        page_break_before = idx > 0 and isinstance(story[idx - 1], PageBreak)
        if heading == "ТОП-5 SKU: где зарабатываете и где теряете":
            has_pagebreak_before_top_sku = page_break_before
        if heading == "Итог: что делать":
            has_pagebreak_before_action_summary = page_break_before

    assert has_pagebreak_before_top_sku
    assert has_pagebreak_before_action_summary


def test_no_double_pagebreak_and_no_pagebreak_plus_spacer() -> None:
    markdown = (
        "## 1. KPI и инсайты\n"
        "Текст\n\n"
        "---PAGEBREAK---\n\n"
        "\n"
        "## 2. Финансы\n"
        "Текст\n"
    )
    story = _build_story(markdown)

    for idx in range(1, len(story)):
        assert not (isinstance(story[idx - 1], PageBreak) and isinstance(story[idx], PageBreak))
        assert not (isinstance(story[idx - 1], PageBreak) and isinstance(story[idx], Spacer))
