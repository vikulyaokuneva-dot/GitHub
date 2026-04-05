from __future__ import annotations

from pathlib import Path

import pandas as pd

from audit.audit_ozon.facts_builder import build_ozon_facts
from audit.audit_ozon.loader import load_ozon_excel
from audit.audit_ozon.report import build_ozon_report


def test_ozon_consistency_top_vs_zero_orders() -> None:
    data = {
        "columns": [
            "Артикул",
            "Заказы",
            "Выручка",
            "Остаток",
            "Расход рекламы",
            "ДРР",
        ],
        "rows": [
            {"Артикул": "SKU-A", "Заказы": 10, "Выручка": 1000, "Остаток": 5, "Расход рекламы": 200, "ДРР": 30},
            {"Артикул": "SKU-B", "Заказы": 0, "Выручка": 500, "Остаток": 3, "Расход рекламы": 0, "ДРР": 40},
            {"Артикул": "SKU-C", "Заказы": 1, "Выручка": 100, "Остаток": 2, "Расход рекламы": None, "ДРР": 50},
        ],
        "row_count": 3,
        "diagnostics": {
            "period_hint": {
                "status": "ok",
                "date_from": "2026-04-01",
                "date_to": "2026-04-07",
                "label_ru": "с 01.04.2026 по 07.04.2026",
                "fallback_used": False,
                "message": "Период распознан автоматически.",
            }
        },
    }

    facts = build_ozon_facts(data)

    top_labels = [x.get("label") for x in (facts.get("top_sku") or [])]
    assert "SKU-B" not in top_labels
    assert "SKU-A" in top_labels

    suspicious = (facts.get("consistency_checks") or {}).get("suspicious_revenue_without_orders") or []
    assert any(x.get("label") == "SKU-B" for x in suspicious)

    promo = facts.get("promotion_summary") or {}
    assert promo.get("sku_with_ads_count") == 1
    assert promo.get("sku_with_drr_count") == 1
    assert promo.get("avg_drr_active") == 0.3


def test_ozon_loader_detects_sheet_header_and_period(tmp_path: Path) -> None:
    path = tmp_path / "analytics_report_2026-04-02_16_46 (1).xlsx"

    with pd.ExcelWriter(path) as writer:
        pd.DataFrame([["meta", "x"], ["empty", "y"]]).to_excel(writer, sheet_name="Лист1", index=False, header=False)
        rows = [
            ["Период: с 01-04-2026 по 07-04-2026", "", "", ""],
            ["", "", "", ""],
            ["Артикул", "Заказы", "Выручка", "Остаток"],
            ["SKU-1", 5, 1000, 3],
            ["SKU-2", 0, 0, 7],
            ["SKU-3", 2, 500, 1],
        ]
        pd.DataFrame(rows).to_excel(writer, sheet_name="Данные", index=False, header=False)

    loaded = load_ozon_excel(str(path))
    diagnostics = loaded.get("diagnostics") or {}
    period = diagnostics.get("period_hint") or {}

    assert diagnostics.get("chosen_sheet") == "Данные"
    assert diagnostics.get("chosen_header_row") == 2
    assert loaded.get("row_count") == 3
    assert period.get("date_from") == "2026-04-01"
    assert period.get("date_to") == "2026-04-07"


def test_ozon_report_has_4_page_structure_and_actions() -> None:
    data = {
        "columns": ["Артикул", "Заказы", "Выручка", "Остаток", "Расход", "ДРР"],
        "rows": [
            {"Артикул": "SKU-A", "Заказы": 12, "Выручка": 2000, "Остаток": 4, "Расход": 800, "ДРР": 40},
            {"Артикул": "SKU-B", "Заказы": 0, "Выручка": 300, "Остаток": 9, "Расход": 0, "ДРР": 20},
            {"Артикул": "SKU-C", "Заказы": 3, "Выручка": 700, "Остаток": 1, "Расход": 100, "ДРР": 15},
        ],
        "row_count": 3,
        "diagnostics": {
            "chosen_sheet": "Данные",
            "chosen_header_row": 0,
            "period_hint": {
                "status": "ok",
                "date_from": "2026-04-01",
                "date_to": "2026-04-07",
                "label_ru": "с 01.04.2026 по 07.04.2026",
                "fallback_used": False,
                "message": "Период распознан автоматически.",
            },
        },
    }
    facts = build_ozon_facts(data)
    report = build_ozon_report(facts)
    markdown = report.get("pdf_markdown") or ""

    assert markdown.count("---PAGEBREAK---") == 3
    assert "## Топ SKU" in markdown
    assert "## Структура ассортимента (ABC)" in markdown
    assert "## Проблемные SKU" in markdown
    assert "## Продвижение и ДРР" in markdown
    assert "## Рекомендации (Action-Level)" in markdown

    actions = report.get("actions") or []
    assert len(actions) > 0
    assert all(action.get("priority") in {"P0", "P1", "P2"} for action in actions)
