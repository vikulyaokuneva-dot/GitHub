from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from audit.audit_facts_builder import _build_actions
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
    }


def test_report_contains_logistics_overpayment_section_in_mode_c():
    facts = _base_facts()
    facts["logistics_formula_model"] = {
        "mode": "C",
        "status": "missing_inputs",
        "missing_inputs": ["volume_liters", "item_price", "warehouse_coef", "localization_share_pct"],
    }

    md = build_audit_markdown(facts)

    assert "## 9." in md
    assert "## 10." in md
    assert "## 11." in md
    assert "## 12." in md
    assert "Точный расчет переплаты за логистику недоступен" in md
    assert "---PAGEBREAK---" in md


def test_actions_add_logistics_recommendation_only_for_medium_high():
    medium_actions = _build_actions(
        {"profit_state": "breakeven", "kpi": {}},
        {"aggregation_status": "ok"},
        {"risk_level": "medium", "localization_share_pct": 55.0},
    )
    low_actions = _build_actions(
        {"profit_state": "breakeven", "kpi": {}},
        {"aggregation_status": "ok"},
        {"risk_level": "low", "localization_share_pct": 80.0},
    )

    assert any(a.get("area") == "logistics" for a in medium_actions)
    assert not any(a.get("area") == "logistics" for a in low_actions)
