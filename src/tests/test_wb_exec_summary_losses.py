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
        "period": {"label": "2026-03-30_2026-04-05", "days": 7},
        "audit_period": {
            "date_from": "2026-03-30",
            "date_to": "2026-04-05",
            "label_ru": "с 30.03.2026 по 05.04.2026",
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
            "sales_qty": 0,
        },
        "funnel_summary": {"orders": 100, "buys": 50, "revenue_orders": 0, "views": 0, "add_to_cart": 0},
        "ads_summary": {"spend": 0, "roas": None, "impressions": 0, "clicks": 0, "drr": None},
        "stock_summary": {"stock_units": 0, "sku_count": 0, "days_of_cover": 0, "risk_of_oos": False},
        "search_insights": {"status": "ok", "total_leak_spend": 1000.0, "effective": [], "growth_hypotheses": []},
        "money_losses": {"ads_waste_rub": 0.0, "frozen_stock_value_rub": 0.0},
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
        "logistics_summary": {
            "delta_vs_target_per_order": 10.0,
            "avg_logistics_cost_est": 80.0,
            "target_avg_logistics_cost": 70.0,
        },
        "regional_logistics_impact": {"total_estimated_overpay_rub": 999999.0},
        "localization_loss": {"status": "insufficient_data", "estimation_mode": "insufficient_data"},
    }


def test_exec_summary_losses_use_buyouts_and_monthly_normalization() -> None:
    facts = _base_facts()
    md = build_audit_markdown(facts)

    assert "Вы теряете ~6 000 ₽ в месяц" in md
    assert "• Неэффективная реклама: 4 000 ₽" in md
    assert "• Переплата за логистику: 2 000 ₽" in md
    assert "Разница: 10 ₽ на выкуп" in md
    assert "10 × 50 = 500 ₽ за период" in md
    assert "500 × 4 = 2 000 ₽ в месяц" in md
