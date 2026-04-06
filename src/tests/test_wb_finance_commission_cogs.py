from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from audit.audit_report import build_audit_markdown
from src.metrics import calc_financial_metrics


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
            "gross_revenue": 1000,
            "commission": 100,
            "commission_breakdown": {
                "base_commission": 60,
                "pvz_compensation": 20,
                "payment_services_compensation": 15,
                "payment_services_compensation_amount": 5,
                "total_commission": 100,
            },
            "logistics": 0,
            "storage": 0,
            "tax": 0,
            "cogs_total": 0,
            "rows_count": 1,
            "cogs_diagnostics": {"cogs_coverage_pct": 0.0},
        },
        "funnel_summary": {"orders": 1, "buys": 1, "revenue_orders": 1000, "views": 0, "add_to_cart": 0},
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


def test_financial_commission_aggregates_required_components() -> None:
    rows = [
        {
            "supplier_oper_name": "Продажа",
            "nm_id": 111,
            "quantity": 1,
            "retail_amount": 1000,
            "wb_reward_before_agent": 100,
            "pvz_compensation": 20,
            "payment_services_compensation": 30,
            "payment_services_compensation_amount": 5,
            "ppvz_sales_commission": 10,
        },
        {
            "supplier_oper_name": "Возврат",
            "nm_id": 111,
            "quantity": 1,
            "retail_amount": 0,
            "wb_reward_before_agent": -10,
            "pvz_compensation": -2,
            "payment_services_compensation": -3,
            "payment_services_compensation_amount": -0.5,
            "ppvz_sales_commission": 0,
        },
    ]

    summary = calc_financial_metrics(rows, tax_rate=0.0, cogs_rows=[], cogs_file_found=False)
    breakdown = summary.get("commission_breakdown") or {}

    assert round(float(breakdown.get("base_commission") or 0.0), 2) == 90.0
    assert round(float(breakdown.get("pvz_compensation") or 0.0), 2) == 18.0
    assert round(float(breakdown.get("payment_services_compensation") or 0.0), 2) == 27.0
    assert round(float(breakdown.get("payment_services_compensation_amount") or 0.0), 2) == 4.5
    assert round(float(summary.get("commission") or 0.0), 2) == 139.5
    assert round(float(breakdown.get("total_commission") or 0.0), 2) == 139.5


def test_cogs_match_handles_int_float_and_string_sku_partial() -> None:
    rows = [
        {"supplier_oper_name": "Продажа", "nm_id": 111, "quantity": 2, "retail_amount": 1000, "_supplier_article": "A-111"},
        {"supplier_oper_name": "Продажа", "nm_id": 222, "quantity": 3, "retail_amount": 1500, "_supplier_article": "B-222"},
        {"supplier_oper_name": "Продажа", "nm_id": 333, "quantity": 1, "retail_amount": 500, "_supplier_article": "C-333"},
        {"supplier_oper_name": "Продажа", "nm_id": 444, "quantity": 1, "retail_amount": 400, "_supplier_article": "D-444"},
    ]
    cogs_rows = [
        {"sku": "111.0", "cogs": 10},
        {"sku": 222, "cogs": 20},
        {"sku": "333", "cogs": 30},
    ]

    summary = calc_financial_metrics(rows, tax_rate=0.0, cogs_rows=cogs_rows, cogs_file_found=True)
    cogs_diag = summary.get("cogs_diagnostics") or {}

    assert summary.get("cogs_status") == "partial_match"
    assert round(float(summary.get("cogs_total") or 0.0), 2) == 110.0
    assert int(cogs_diag.get("cogs_matched_sku") or 0) == 3
    assert 444 in (cogs_diag.get("cogs_unmatched_sku") or [])


def test_toc_has_numbered_top5_and_shifted_sections() -> None:
    facts = _base_facts()
    md = build_audit_markdown(facts)
    assert "- 7. ТОП-5 SKU: где зарабатываете и где теряете" in md
    assert "## 7. ТОП-5 SKU: где зарабатываете и где теряете" in md
    assert "## 8. Локальные заказы и размещение товара" in md
    assert "## 9. Логистика: где переплачиваете" in md
    assert "## 10. Переплата за логистику" in md
    assert "## 11. Потери из-за плохой локализации" in md
    assert "## 12. Поисковые запросы" in md
    assert "## 13. План действий / рекомендации" in md


def test_markdown_is_consistent_with_cogs_status_not_matched() -> None:
    facts = _base_facts()
    facts["financial_summary"]["cogs_status"] = "file_read_not_matched"
    facts["financial_summary"]["profit_without_cogs"] = True
    facts["financial_summary"]["cogs_total"] = 0
    facts["financial_summary"]["profit_note"] = "COGS найден, но не сопоставлен с продажами; прибыль рассчитана без себестоимости."
    md = build_audit_markdown(facts)

    assert "COGS найден, но не сопоставлен с SKU продаж" in md
    assert "не рассчитан (нет данных по себестоимости)" in md
