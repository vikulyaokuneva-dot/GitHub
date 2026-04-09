from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from audit.audit_report import build_audit_markdown


def _base_facts() -> dict:
    return {
        "date": "2026-04-05",
        "source": "wb",
        "period": {"label": "2026-04-01_2026-04-05", "days": 5},
        "audit_period": {
            "date_from": "2026-04-01",
            "date_to": "2026-04-05",
            "label_ru": "с 01.04.2026 по 05.04.2026",
        },
        "inputs": {
            "selected_files": {},
            "found_files": [],
            "blocks_collected": [],
            "blocks_skipped": [],
            "missing_required": [],
            "missing_optional": [],
        },
        "financial_summary": {
            "gross_revenue": 0,
            "commission": 0,
            "logistics": 0,
            "storage": 0,
            "tax": 0,
            "cogs_total": 0,
            "rows_count": 0,
        },
        "funnel_summary": {"orders": 0, "buys": 0, "revenue_orders": 0, "views": 0, "add_to_cart": 0},
        "ads_summary": {"spend": 0, "roas": None, "impressions": 0, "clicks": 0, "drr": None},
        "stock_summary": {"stock_units": 0, "sku_count": 0, "days_of_cover": 0, "risk_of_oos": False},
        "search_insights": {"status": "missing"},
        "local_orders_insights": {"available": False, "message": "нет данных"},
        "decision_layer": {"reasons_of_loss": [], "unprofitable_sku": []},
        "sku_profit": [],
        "actions": [],
        "region_logistics_summary": {},
        "top_expensive_logistics_regions": [],
        "logistics_potential_risk_regions": [],
        "logistics_regions_over_150": [],
        "logistics_regions_low_coverage": [],
        "logistics_formula_model": {},
        "localization_loss": {"status": "insufficient_data", "estimation_mode": "insufficient_data"},
    }


def _efficiency_section(md: str) -> str:
    assert "## Эффективность товаров" in md
    after = md.split("## Эффективность товаров", 1)[1]
    if "## 7. ТОП-5 SKU" in after:
        return after.split("## 7. ТОП-5 SKU", 1)[0]
    return after


def test_sku_efficiency_block_uses_ab_only_and_formats_metrics() -> None:
    facts = _base_facts()
    facts["sku_profit"] = [
        {"sku": 111, "profit": 300.0, "revenue": 1000.0, "orders": 1, "buyouts": 1, "ad_spend": 100.0, "abc": "A"},
        {"sku": 222, "profit": 200.0, "revenue": 500.0, "orders": 2, "buyouts": 1, "ad_spend": 50.0, "abc": "B"},
        {"sku": 333, "profit": 1000.0, "revenue": 2000.0, "orders": 4, "buyouts": 4, "ad_spend": 100.0, "abc": "C"},
    ]
    facts["search_insights"] = {
        "status": "ok",
        "base_rows": [
            {"nmId": 111, "impressions": 100, "clicks": 10, "add_to_cart": 2, "orders": 1, "buyouts": 1},
            {"nmId": 222, "impressions": 200, "clicks": 20, "add_to_cart": 6, "orders": 2, "buyouts": 1},
            {"nmId": 333, "impressions": 500, "clicks": 70, "add_to_cart": 20, "orders": 4, "buyouts": 4},
        ],
    }

    md = build_audit_markdown(facts)
    section = _efficiency_section(md)

    assert "| Артикул | Показы | Клики | CTR |" in section
    assert "| 111 |" in section
    assert "| 222 |" in section
    assert "| 333 |" not in section
    assert "| 111 | 100 | 10 | 10.0% | 2 | 20.0% | 1 | 50.0% | 1 | 100.0% | 10.0% | 300 ₽ | 3 |" in section


def test_sku_efficiency_fallback_to_top_profit_when_abc_missing_and_limit_20() -> None:
    facts = _base_facts()
    facts["sku_profit"] = [
        {
            "sku": 1000 + i,
            "profit": float(1000 - i),
            "revenue": 3000.0,
            "orders": 5,
            "buyouts": 4,
            "ad_spend": 150.0,
            "abc": "N/A",
        }
        for i in range(25)
    ]

    md = build_audit_markdown(facts)
    section = _efficiency_section(md)

    assert "ABC-анализ недоступен: выбраны TOP SKU по прибыли." in section
    sku_rows = [line for line in section.splitlines() if line.startswith("| 10") and line.endswith("|")]
    assert len(sku_rows) == 20
    assert "| 1000 |" in section
    assert "| 1020 |" not in section
    assert " | - | - | - |" in section
