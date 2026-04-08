from __future__ import annotations

from pathlib import Path

import pytest

import src.pdf_report as pdf_report


def test_markdown_to_simple_pdf_renders_unicode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pdf_report, "_REGISTERED_FONTS", None)
    pdf_path = tmp_path / "report.pdf"
    markdown = "# АУДИТ WB КАБИНЕТА\n\n- Прибыль без учета себестоимости\n- Рекомендации\n"

    pdf_report.markdown_to_simple_pdf(markdown, pdf_path, title="WB отчёт")

    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0


def test_font_resolution_error_is_explicit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pdf_report, "_REGISTERED_FONTS", None)
    monkeypatch.setenv("WB_PDF_FONT_REGULAR", str(tmp_path / "missing.ttf"))
    monkeypatch.delenv("WB_PDF_FONT_BOLD", raising=False)

    with pytest.raises(FileNotFoundError) as exc:
        pdf_report.get_pdf_font_diagnostics()

    assert "Unicode PDF font with Cyrillic support was not found" in str(exc.value)


def test_explicit_regular_font_works_without_bold(monkeypatch: pytest.MonkeyPatch) -> None:
    regular = (Path(__file__).resolve().parents[2] / "assets" / "fonts" / "DejaVuSans.ttf").resolve()
    assert regular.exists(), f"Expected test font to exist: {regular}"

    monkeypatch.setattr(pdf_report, "_REGISTERED_FONTS", None)
    monkeypatch.setenv("WB_PDF_FONT_REGULAR", str(regular))
    monkeypatch.delenv("WB_PDF_FONT_BOLD", raising=False)

    info = pdf_report.get_pdf_font_diagnostics()

    assert info["regular_path"] == str(regular)
    assert info["bold_path"] == str(regular)


def test_markdown_to_simple_pdf_supports_page_number_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pdf_report, "_REGISTERED_FONTS", None)
    pdf_path = tmp_path / "report_with_numbers.pdf"
    markdown = "# Титул\n\n---PAGEBREAK---\n\n## Страница 2\n\nТекст"

    pdf_report.markdown_to_simple_pdf(
        markdown,
        pdf_path,
        title="WB отчет",
        page_number_format="{page} / {total}",
        page_number_align="right",
        skip_first_page_numbering=True,
    )

    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0


def test_toc_helpers_resolve_pages() -> None:
    section_pages = {
        pdf_report._normalize_heading_key("1. KPI и инсайты"): 3,
        pdf_report._normalize_heading_key("Краткий итог по кабинету"): 1,
    }

    assert pdf_report._resolve_toc_page("1. KPI и инсайты", section_pages) == 3
    assert pdf_report._resolve_toc_page("Executive Summary: краткий итог по кабинету", section_pages) == 1


def test_toc_entry_format_contains_dots_and_page() -> None:
    line = pdf_report._format_toc_entry("1. KPI и инсайты", 3)
    assert "1. KPI и инсайты" in line
    assert "3" in line
    assert "...." in line


def test_logical_page_number_respects_title_page_skip() -> None:
    assert pdf_report._logical_page_number(1, skip_first_page_numbering=True) is None
    assert pdf_report._logical_page_number(2, skip_first_page_numbering=True) == 1
    assert pdf_report._logical_page_number(4, skip_first_page_numbering=False) == 4


def test_toc_leader_uses_width_and_truncates() -> None:
    leader = pdf_report._build_toc_leader(
        "Очень длинное название раздела для проверки усечения в оглавлении",
        leader_width=180.0,
        font_name="Helvetica",
        font_size=10.0,
        min_dots=8,
    )

    assert leader.endswith(" ")
    assert "." in leader
    assert "..." in leader


def test_fit_text_to_width_shortens_when_needed() -> None:
    fitted = pdf_report._fit_text_to_width(
        "Супердлинная строка для проверки",
        max_width=40.0,
        font_name="Helvetica",
        font_size=10.0,
    )
    assert fitted.endswith("...")
