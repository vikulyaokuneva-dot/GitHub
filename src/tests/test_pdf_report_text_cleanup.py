from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src import pdf_report  # noqa: E402


def test_clean_pdf_text_removes_markers_markdown_and_formats_values() -> None:
    raw = "■ ДРР SKU:** 0.22%  Прибыль:** 2 971.66 RUB"
    cleaned = pdf_report._clean_pdf_text(raw)

    assert "■" not in cleaned
    assert "**" not in cleaned
    assert "ДРР: 0.2%" in cleaned
    assert "Прибыль: 2 972 ₽" in cleaned


def test_clean_pdf_text_simplifies_losses_phrase() -> None:
    raw = "Реклама без заказов: 26 связок, потери: 4 047.24 RUB"
    cleaned = pdf_report._clean_pdf_text(raw)
    assert cleaned == "Реклама без заказов: 26 связок, потери 4 047 ₽"


def test_clean_toc_entries_match_business_format() -> None:
    assert pdf_report.TOC_CLEAN_ENTRIES[0] == "KPI и инсайты"
    assert pdf_report.TOC_CLEAN_ENTRIES[-1] == "План действий"
    assert len(pdf_report.TOC_CLEAN_ENTRIES) == 10
