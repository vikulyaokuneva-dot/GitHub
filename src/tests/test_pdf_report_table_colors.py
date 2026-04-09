from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.pdf_report import (  # noqa: E402
    COLOR_DANGER_RED,
    COLOR_SUCCESS_GREEN,
    _table_cell_metric_color,
)


def test_table_metric_colors_for_ctr_cr_drr_profit_roi() -> None:
    headers = [
        "CTR",
        "CR (клик->корзина)",
        "ДРР",
        "Чистая прибыль (руб)",
        "ROI",
    ]

    assert _table_cell_metric_color(headers, col_index=0, value="5.0%") == COLOR_SUCCESS_GREEN
    assert _table_cell_metric_color(headers, col_index=0, value="0.8%") == COLOR_DANGER_RED

    assert _table_cell_metric_color(headers, col_index=1, value="15.0%") == COLOR_SUCCESS_GREEN
    assert _table_cell_metric_color(headers, col_index=1, value="2.0%") == COLOR_DANGER_RED

    assert _table_cell_metric_color(headers, col_index=2, value="8.0%") == COLOR_SUCCESS_GREEN
    assert _table_cell_metric_color(headers, col_index=2, value="30.0%") == COLOR_DANGER_RED

    assert _table_cell_metric_color(headers, col_index=3, value="12 500 ₽") == COLOR_SUCCESS_GREEN
    assert _table_cell_metric_color(headers, col_index=3, value="-500 ₽") == COLOR_DANGER_RED

    assert _table_cell_metric_color(headers, col_index=4, value="1.25") == COLOR_SUCCESS_GREEN
    assert _table_cell_metric_color(headers, col_index=4, value="-0.10") == COLOR_DANGER_RED
