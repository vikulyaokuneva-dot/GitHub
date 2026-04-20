from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from audit.audit_loader import parse_stocks_file_with_diagnostics
from audit.audit_facts_builder import _audit_stock_summary
from audit.audit_stock_parser import parse_audit_stock_history_with_diagnostics


def test_parse_stocks_file_uses_total_stock_priority_column(tmp_path: Path) -> None:
    stock_path = tmp_path / "stocks_priority.xlsx"
    df = pd.DataFrame(
        [
            {
                "Артикул WB": 622909564,
                "Артикул": 111,
                "Артикул продавца": "SKU-622",
                "Название": "Товар 622",
                "Склад": "Тула",
                "Всего находится на складах": 1201,
                "Остатки, шт": 1,
            },
            {
                "Артикул WB": 719734814,
                "Артикул": 222,
                "Артикул продавца": "SKU-719",
                "Название": "Товар 719",
                "Склад": "Казань",
                "Всего находится на складах": 818,
                "Остатки, шт": 2,
            },
            {
                "Артикул WB": 370669127,
                "Артикул": 333,
                "Артикул продавца": "SKU-370",
                "Название": "Товар 370",
                "Склад": "Екатеринбург",
                "Всего находится на складах": 487,
                "Остатки, шт": 3,
            },
        ]
    )
    with pd.ExcelWriter(stock_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Детальная информация", index=False)

    rows, diag = parse_stocks_file_with_diagnostics(str(stock_path))

    assert diag.get("status") == "ok"
    assert str(diag.get("resolved_sku_column") or "") == "Артикул WB"
    assert str(diag.get("resolved_total_stock_column") or "") == "Всего находится на складах"

    by_sku: dict[int, int] = {}
    for row in rows:
        sku = int(row.get("nmId") or 0)
        qty = int(row.get("quantityFull") or 0)
        by_sku[sku] = by_sku.get(sku, 0) + qty

    assert by_sku[622909564] == 1201
    assert by_sku[719734814] == 818
    assert by_sku[370669127] == 487


def test_history_parser_prefers_total_stock_column_over_date_columns(tmp_path: Path) -> None:
    stock_path = tmp_path / "stocks_history_priority.xlsx"
    history_rows = [
        ["Остатки по дням. С учетом удалённых товаров."],
        ["Артикул WB", "Склад", "01.04.2026", "02.04.2026", "Всего находится на складах"],
        [622909564, "Тула", 0, 0, 1201],
        [719734814, "Казань", 0, 0, 818],
        [370669127, "Екатеринбург", 0, 0, 487],
    ]
    with pd.ExcelWriter(stock_path, engine="openpyxl") as writer:
        pd.DataFrame(history_rows).to_excel(writer, sheet_name="Остатки по дням", index=False, header=False)

    payload = parse_audit_stock_history_with_diagnostics(
        str(stock_path),
        preferred_date="2026-04-02",
    )

    assert payload.get("status") == "ok"
    assert str(payload.get("source_stock_column") or "") == "Всего находится на складах"
    assert int((payload.get("sku_total_stocks") or {}).get("622909564") or 0) == 1201
    assert int((payload.get("sku_total_stocks") or {}).get("719734814") or 0) == 818
    assert int((payload.get("sku_total_stocks") or {}).get("370669127") or 0) == 487


def test_stock_summary_downstream_uses_corrected_stock_values() -> None:
    stocks_rows = [
        {"nmId": 622909564, "quantityFull": 1000},
        {"nmId": 622909564, "quantityFull": 201},
        {"nmId": 719734814, "quantityFull": 818},
        {"nmId": 370669127, "quantityFull": 487},
    ]
    summary = _audit_stock_summary(
        stocks_raw=stocks_rows,
        stocks_parse_diag={"status": "ok", "parsed_rows": 4, "mapped_rows": 4},
        stock_history_payload={"status": "history_sheet_not_found", "rows": []},
        avg_daily_sales=100.0,
    )

    assert int(summary.get("stock_units") or 0) == 2506
    totals = summary.get("sku_total_stocks") or {}
    assert int(totals.get("622909564") or 0) == 1201
    assert int(totals.get("719734814") or 0) == 818
    assert int(totals.get("370669127") or 0) == 487
    assert float(summary.get("days_of_cover") or 0.0) > 0.0
    assert bool(summary.get("risk_of_oos")) is False
