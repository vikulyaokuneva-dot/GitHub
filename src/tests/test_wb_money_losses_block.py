from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from audit.audit_facts_builder import _build_money_losses
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
            "gross_revenue": 200000,
            "commission": 20000,
            "logistics": 10000,
            "storage": 3000,
            "tax": 12000,
            "cogs_total": 90000,
            "rows_count": 10,
            "sales_qty": 100,
            "profit": 15000,
            "profit_without_cogs": False,
        },
        "funnel_summary": {"orders": 120, "buys": 100, "revenue_orders": 210000, "views": 10000, "add_to_cart": 600},
        "ads_summary": {"spend": 25000, "roas": 4.2, "impressions": 200000, "clicks": 5000, "drr": 0.12},
        "stock_summary": {"stock_units": 1000, "sku_count": 50, "days_of_cover": 35, "risk_of_oos": False},
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


def test_build_money_losses_uses_query_level_waste_and_separates_risks() -> None:
    payload = _build_money_losses(
        ads_summary={"spend": 999.0, "revenue_attr": 0.0},
        decision_layer={
            "ads_leaks": [
                {"level": "query", "spend": 100.0, "orders": 0},
                {"level": "query", "spend": 50.0, "orders": 0},
                {"level": "query", "spend": 60.0, "orders": 1},
                {"level": "cabinet", "spend": 500.0, "orders": 0},
            ]
        },
        financial_summary={
            "sku_financials": {
                "111": {"cogs": 1000.0, "sales_qty": 10},
            }
        },
        sku_rows=[
            {"sku": 111, "profit": -230.0, "stock_qty": 100, "orders": 0, "buyouts": 0, "turnover_days": 90},
            {"sku": 222, "profit": 150.0, "stock_qty": 60, "orders": 2, "buyouts": 1, "turnover_days": 70},
            {"sku": 444, "profit": 10.0, "stock_qty": 55, "orders": 0, "buyouts": 0},
        ],
        stock_summary={"source": "xlsx_history", "source_date": "2026-04-05"},
    )

    assert round(float(payload.get("ads_waste_rub") or 0.0), 2) == 150.0
    assert int(payload.get("ads_waste_count") or 0) == 2
    assert str(payload.get("ads_waste_source") or "") == "query"

    assert round(float(payload.get("negative_profit_rub") or 0.0), 2) == 230.0
    assert int(payload.get("negative_profit_sku_count") or 0) == 1

    assert int(payload.get("frozen_stock_sku_count") or 0) == 3
    assert int(payload.get("frozen_stock_qty_units") or 0) == 215
    assert round(float(payload.get("frozen_stock_value_rub") or 0.0), 2) == 10000.0

    assert int(payload.get("storage_risk_sku_count") or 0) == 3
    assert round(float(payload.get("total_direct_losses_rub") or 0.0), 2) == 380.0


def test_build_money_losses_falls_back_to_ads_summary_when_no_leaks() -> None:
    payload = _build_money_losses(
        ads_summary={"spend": 700.0, "revenue_attr": 0.0},
        decision_layer={"ads_leaks": []},
        financial_summary={},
        sku_rows=[],
        stock_summary={},
    )

    assert round(float(payload.get("ads_waste_rub") or 0.0), 2) == 700.0
    assert int(payload.get("ads_waste_count") or 0) == 1
    assert str(payload.get("ads_waste_source") or "") == "ads_summary_fallback"
    assert round(float(payload.get("total_direct_losses_rub") or 0.0), 2) == 700.0


def test_report_renders_money_losses_block_with_direct_and_risk_parts() -> None:
    facts = _base_facts()
    facts["money_losses"] = {
        "ads_waste_rub": 12540.0,
        "ads_waste_count": 7,
        "negative_profit_rub": 8230.0,
        "negative_profit_sku_count": 3,
        "frozen_stock_value_rub": 54000.0,
        "frozen_stock_sku_count": 5,
        "frozen_stock_qty_units": 700,
        "storage_risk_sku_count": 8,
        "total_direct_losses_rub": 20770.0,
    }

    md = build_audit_markdown(facts)

    idx_ads = md.find("12 540.00 RUB")
    idx_negative = md.find("8 230.00 RUB")
    idx_frozen = md.find("54 000.00 RUB")
    idx_total = md.find("20 770.00 RUB")

    assert idx_ads >= 0
    assert idx_negative > idx_ads
    assert idx_frozen > idx_negative
    assert idx_total > idx_frozen

    assert "3 SKU" in md
    assert "5 SKU" in md
    assert "8 SKU" in md


def test_report_renders_unprofitable_sku_section_after_kpi() -> None:
    facts = _base_facts()
    facts["financial_summary"]["sku_financials"] = {
        "111": {
            "net_revenue": 1000.0,
            "cogs": 400.0,
            "commission": 350.0,  # 35% -> Высокая комиссия
            "logistics": 50.0,
            "profit": -120.0,
            "margin": -0.12,
        },
        "222": {
            "net_revenue": 1200.0,
            "cogs": 600.0,
            "commission": 120.0,
            "logistics": 360.0,  # 30% -> Дорогая логистика
            "profit": -200.0,
            "margin": -0.1667,
        },
        "333": {
            "net_revenue": 1400.0,
            "cogs": 600.0,
            "commission": 150.0,
            "logistics": 100.0,
            "profit": -80.0,
            "margin": -0.0571,  # fallback -> Низкая цена
        },
        "444": {
            "net_revenue": 1000.0,
            "cogs": 400.0,
            "commission": 120.0,
            "logistics": 100.0,
            "profit": 10.0,
            "margin": 0.01,
        },
    }

    md = build_audit_markdown(facts)

    kpi_pos = md.index("# 📊 KPI и инсайты")
    unprofitable_pos = md.index("## 🚨 Убыточные SKU")
    finance_pos = md.index("## 2. 💰 Финансы: сколько реально зарабатываете")
    assert kpi_pos < unprofitable_pos < finance_pos

    assert "| SKU | Выручка | Себестоимость | Комиссии WB | Логистика | Прибыль | Причина убытка |" in md
    assert "| 222 | 1 200 ₽ | 600 ₽ | 120 ₽ | 360 ₽ | -200 ₽ | Дорогая логистика |" in md
    assert "| 111 | 1 000 ₽ | 400 ₽ | 350 ₽ | 50 ₽ | -120 ₽ | Высокая комиссия |" in md
    assert "| 333 | 1 400 ₽ | 600 ₽ | 150 ₽ | 100 ₽ | -80 ₽ | Низкая цена |" in md
    assert "| 444 |" not in md

    assert md.index("| 222 |") < md.index("| 111 |") < md.index("| 333 |")


def test_report_unprofitable_sku_section_shows_empty_message() -> None:
    facts = _base_facts()
    facts["financial_summary"]["sku_financials"] = {
        "111": {"net_revenue": 1000.0, "profit": 100.0},
        "222": {"net_revenue": 500.0, "profit": 0.0},
    }

    md = build_audit_markdown(facts)
    assert "## 🚨 Убыточные SKU" in md
    assert "Убыточных SKU не выявлено" in md
