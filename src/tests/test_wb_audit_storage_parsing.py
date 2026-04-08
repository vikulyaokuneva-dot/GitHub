from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from audit.audit_loader import parse_finance_file_with_diagnostics
from src.metrics import calc_financial_metrics


def _write_finance_file(path: Path, rows: list[dict]) -> None:
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Sheet1", index=False)


def test_parse_finance_keeps_storage_rows_and_builds_storage_debug(tmp_path: Path) -> None:
    finance_path = tmp_path / "finance_storage_rub.xlsx"
    _write_finance_file(
        finance_path,
        [
            {
                "Тип документа": "",
                "Обоснование для оплаты": "Хранение",
                "Код номенклатуры": 0,
                "Кол-во": 0,
                "Вайлдберриз реализовал Товар (Пр)": 0,
                "К перечислению Продавцу за реализованный Товар": 0,
                "Хранение, руб": 100.50,
                "Название": "",
                "Артикул поставщика": "",
            },
            {
                "Тип документа": "",
                "Обоснование для оплаты": "Хранение",
                "Код номенклатуры": 0,
                "Кол-во": 0,
                "Вайлдберриз реализовал Товар (Пр)": 0,
                "К перечислению Продавцу за реализованный Товар": 0,
                "Хранение, руб": 50.00,
                "Название": "",
                "Артикул поставщика": "",
            },
            {
                "Тип документа": "Продажа",
                "Обоснование для оплаты": "Продажа",
                "Код номенклатуры": 123456,
                "Кол-во": 1,
                "Вайлдберриз реализовал Товар (Пр)": 1000.00,
                "К перечислению Продавцу за реализованный Товар": 800.00,
                "Хранение, руб": 0.00,
                "Название": "Товар",
                "Артикул поставщика": "SKU-1",
            },
        ],
    )

    rows, diag = parse_finance_file_with_diagnostics(str(finance_path))

    assert diag.get("status") == "ok"
    assert bool(diag.get("storage_column_found")) is True
    assert str(diag.get("storage_source_column") or "") == "Хранение, руб"
    assert int(diag.get("storage_rows_nonzero") or 0) == 2
    assert round(float(diag.get("storage_total") or 0.0), 2) == 150.50
    assert len(rows) == 3

    summary = calc_financial_metrics(rows, tax_rate=0.0, cogs_rows=[], cogs_file_found=False)
    storage_debug = summary.get("storage_debug") or {}

    assert round(float(summary.get("storage") or 0.0), 2) == 150.50
    assert str(storage_debug.get("source_column") or "") == "Хранение, руб"
    assert int(storage_debug.get("rows_with_storage") or 0) == 2
    assert round(float(storage_debug.get("storage_total") or 0.0), 2) == 150.50


def test_parse_finance_uses_primary_storage_column_without_double_count(tmp_path: Path) -> None:
    finance_path = tmp_path / "finance_storage_two_columns.xlsx"
    _write_finance_file(
        finance_path,
        [
            {
                "Тип документа": "",
                "Обоснование для оплаты": "Хранение",
                "Код номенклатуры": 0,
                "Кол-во": 0,
                "Вайлдберриз реализовал Товар (Пр)": 0,
                "К перечислению Продавцу за реализованный Товар": 0,
                "Хранение, руб": 10.0,
                "Стоимость хранения": 999.0,
            }
        ],
    )

    rows, diag = parse_finance_file_with_diagnostics(str(finance_path))
    summary = calc_financial_metrics(rows, tax_rate=0.0, cogs_rows=[], cogs_file_found=False)
    storage_debug = summary.get("storage_debug") or {}

    assert bool(diag.get("storage_column_found")) is True
    assert str(diag.get("storage_source_column") or "") == "Хранение, руб"
    assert round(float(summary.get("storage") or 0.0), 2) == 10.0
    assert str(storage_debug.get("source_column") or "") == "Хранение, руб"
