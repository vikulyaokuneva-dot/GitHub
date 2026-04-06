from __future__ import annotations

from pathlib import Path

import pandas as pd

from audit.ozon_facts_builder import build_ozon_audit_facts
from audit.ozon_loader import parse_ozon_products_file
from audit.ozon_report import build_ozon_audit_markdown


def _write_products_with_offer_id_header(path: Path) -> None:
    rows = [
        ["Отчет Ozon", "", "", "", ""],
        ["Период: 2026-04-01 - 2026-04-03", "", "", "", ""],
        ["", "", "", "", ""],
        ["ID предложения", "Наименование товара", "Количество заказов", "Сумма продаж", "Остаток"],
        ["OF-1", "Товар 1", 4, 12000, 8],
        ["OF-2", "Товар 2", 0, 0, 3],
        ["Итого", "", 4, 12000, 11],
    ]
    df = pd.DataFrame(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(path, index=False, header=False)


def _write_products_revenue_only(path: Path) -> None:
    rows = [
        ["ID предложения", "Наименование товара", "Заказы", "Выручка", "Остаток"],
        ["OF-10", "Товар 10", 10, 15000, 2],
        ["OF-20", "Товар 20", 2, 2500, 5],
        ["OF-30", "Товар 30", 0, 0, 9],
    ]
    df = pd.DataFrame(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(path, index=False, header=False)


def _write_products_without_revenue(path: Path) -> None:
    rows = [
        ["ID предложения", "Наименование товара", "Заказы", "Остаток"],
        ["OF-100", "Товар 100", 5, 3],
        ["OF-200", "Товар 200", 0, 1],
    ]
    df = pd.DataFrame(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(path, index=False, header=False)


def test_ozon_products_parser_maps_aliases_and_falls_back_to_offer_id(tmp_path: Path) -> None:
    file_path = tmp_path / "products_aliases.xlsx"
    _write_products_with_offer_id_header(file_path)

    rows, diagnostics = parse_ozon_products_file(str(file_path))

    assert len(rows) == 2
    assert rows[0]["sku"] == "OF-1"
    assert rows[0]["id_source"] == "offer_id_fallback"
    assert rows[0]["orders"] == 4
    assert rows[0]["revenue"] == 12000.0
    assert rows[0]["stock"] == 8.0

    assert diagnostics.get("resolved_columns", {}).get("offer_id") == "ID предложения"
    assert diagnostics.get("resolved_columns", {}).get("revenue") == "Сумма продаж"
    assert "sku" in (diagnostics.get("missing_columns") or [])
    assert diagnostics.get("source_columns")
    assert diagnostics.get("unresolved_columns") is not None
    assert diagnostics.get("sku_fallback_to_offer_id_count") == 2


def test_ozon_products_parser_reports_missing_revenue(tmp_path: Path) -> None:
    file_path = tmp_path / "products_without_revenue.xlsx"
    _write_products_without_revenue(file_path)

    rows, diagnostics = parse_ozon_products_file(str(file_path))
    assert len(rows) == 2
    assert "revenue" in (diagnostics.get("missing_columns") or [])
    assert "revenue column missing caused empty revenue metrics" in (diagnostics.get("warnings") or [])

    input_root = tmp_path / "input" / "ozon"
    _write_products_without_revenue(input_root / "products" / "ozon_products_report.xlsx")
    facts = build_ozon_audit_facts(input_dir=str(input_root))
    gap_types = [x.get("type") for x in ((facts.get("decision_layer") or {}).get("data_gaps") or [])]
    assert "products_revenue_missing" in gap_types


def test_ozon_audit_uses_revenue_fallback_abc_without_cogs(tmp_path: Path) -> None:
    input_root = tmp_path / "input" / "ozon"
    _write_products_revenue_only(input_root / "products" / "ozon_products_report.xlsx")

    facts = build_ozon_audit_facts(input_dir=str(input_root), period_label="2026-04-01_2026-04-03")
    abc_summary = (facts.get("abc_analysis") or {}).get("summary") or {}

    assert abc_summary.get("status") == "fallback_revenue_no_cogs"
    assert "fallback" in str(abc_summary.get("basis_note") or "").lower()
    assert len(facts.get("top_sku_by_revenue") or []) > 0
    assert len(facts.get("top_sku_by_orders") or []) > 0
    assert len(facts.get("sku_with_stock") or []) > 0

    markdown = build_ozon_audit_markdown(facts)
    assert "ABC по выручке (fallback, т.к. нет COGS)" in markdown
    assert "SKU unknown" not in markdown
