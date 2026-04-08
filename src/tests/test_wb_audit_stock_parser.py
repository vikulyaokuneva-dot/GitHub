from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from audit.audit_stock_parser import parse_audit_stock_history_with_diagnostics


def _build_stock_history_file(path: Path, *, detail_total_override: int | None = None) -> None:
    history_rows = [
        ["Остатки по дням. С учетом удалённых товаров."],
        [
            "Артикул продавца",
            "Название",
            "Артикул WB",
            "Склад",
            "04.04.2026",
            "05.04.2026",
        ],
        ["SKU-405", "Товар 405", 405933491, "Тула", 80, 91],
        ["SKU-405", "Товар 405", 405933491, "Екатеринбург", 55, 60],
        ["SKU-405", "Товар 405", 405933491, "Электросталь", 42, 50],
        ["SKU-405", "Товар 405", 405933491, "Остальные", 310, 322],
        ["SKU-810", "Товар 810", 810239842, "Казань", 5, 10],
        ["SKU-810", "Товар 810", 810239842, "Краснодар", 3, -7],
    ]

    detail_total_405 = 523 if detail_total_override is None else int(detail_total_override)
    detail_rows = [
        ["Остатки по КТ по размерам. С учетом удалённых товаров."],
        [
            "Артикул продавца",
            "Название",
            "Артикул WB",
            "Регион",
            "Склад",
            "Остатки на текущий день, шт",
        ],
        ["SKU-405", "Товар 405", 405933491, "Центральный", "Тула", 91],
        ["SKU-405", "Товар 405", 405933491, "Уральский", "Екатеринбург", 60],
        ["SKU-405", "Товар 405", 405933491, "Центральный", "Электросталь", 50],
        ["SKU-405", "Товар 405", 405933491, "Остальные", "Остальные", max(detail_total_405 - 201, 0)],
        ["SKU-810", "Товар 810", 810239842, "Приволжский", "Казань", 10],
    ]

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(history_rows).to_excel(writer, sheet_name="Остатки по дням", index=False, header=False)
        pd.DataFrame(detail_rows).to_excel(writer, sheet_name="Детальная информация", index=False, header=False)
        pd.DataFrame([["meta", "value"]]).to_excel(writer, sheet_name="Общая информация", index=False, header=False)


def test_audit_stock_parser_sums_all_warehouses_for_selected_date(tmp_path: Path) -> None:
    stock_path = tmp_path / "stocks.xlsx"
    _build_stock_history_file(stock_path)

    payload = parse_audit_stock_history_with_diagnostics(
        str(stock_path),
        preferred_date="2026-04-05",
    )

    assert payload.get("status") == "ok"
    assert payload.get("source_sheet") == "Остатки по дням"
    assert payload.get("source_date") == "2026-04-05"
    assert payload.get("control_totals_match") is True
    assert int((payload.get("sku_total_stocks") or {}).get("405933491") or 0) == 523
    assert int((payload.get("sku_total_stocks") or {}).get("810239842") or 0) == 10

    by_warehouse = (payload.get("sku_stocks_by_warehouse") or {}).get("405933491") or []
    assert any((item or {}).get("warehouse") == "Остальные" for item in by_warehouse)
    assert len(by_warehouse) >= 4


def test_audit_stock_parser_warns_when_history_and_detail_totals_mismatch(tmp_path: Path) -> None:
    stock_path = tmp_path / "stocks_mismatch.xlsx"
    _build_stock_history_file(stock_path, detail_total_override=500)

    payload = parse_audit_stock_history_with_diagnostics(
        str(stock_path),
        preferred_date="2026-04-05",
    )

    assert payload.get("status") == "ok"
    assert payload.get("control_totals_match") is False
    warnings = payload.get("warnings") or []
    assert warnings
    assert "history_total" in str(warnings[0])
