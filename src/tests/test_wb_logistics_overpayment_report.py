from pathlib import Path
import sys

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from audit.audit_facts_builder import (
    _build_actions,
    _build_cabinet_logistics_summary,
    _build_regional_logistics_impact_payload,
    _load_logistics_config,
    _parse_localization_pct,
)
from audit.audit_report import build_audit_markdown


def _base_facts() -> dict:
    return {
        "date": "2026-04-05",
        "source": "wb",
        "period": {"label": "2026-04-01_2026-04-05", "days": 5},
        "audit_period": {
            "date_from": "2026-04-01",
            "date_to": "2026-04-05",
            "label_ru": "period",
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
        "local_orders_insights": {"available": False, "message": "no data"},
        "decision_layer": {"reasons_of_loss": [], "unprofitable_sku": []},
        "sku_profit": [],
        "actions": [],
        "region_logistics_summary": {},
        "top_expensive_logistics_regions": [],
        "logistics_potential_risk_regions": [],
        "logistics_regions_over_150": [],
        "logistics_regions_low_coverage": [],
    }


def test_report_contains_logistics_overpayment_section_in_mode_c() -> None:
    facts = _base_facts()
    facts["logistics_formula_model"] = {
        "mode": "C",
        "status": "missing_inputs",
        "missing_inputs": ["volume_liters", "item_price", "warehouse_coef", "localization_share_pct"],
    }

    md = build_audit_markdown(facts)

    assert "## 10." in md
    assert "## 11." in md
    assert "## 12." in md
    assert "## 13." in md
    assert "volume_liters" in md
    assert "---PAGEBREAK---" in md


def test_actions_add_logistics_recommendation_only_for_medium_high() -> None:
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


def test_regional_logistics_impact_payload_full_rub_mode() -> None:
    payload = _build_regional_logistics_impact_payload(
        logistics_payload={
            "region_coefficients": {
                "North-West": {"avg_pct": 203.8, "class": "expensive"},
                "Central": {"avg_pct": 149.3, "class": "expensive"},
            },
            "regions_over_150": ["North-West"],
            "locality_signals": [
                {"logistics_region": "North-West", "orders": 40, "avg_coefficient": 203.8},
                {"logistics_region": "Central", "orders": 25, "avg_coefficient": 149.3},
            ],
        },
        logistics_formula_model={
            "volume_liters": 0.9,
            "item_price": 1200.0,
            "localization_share_pct": 55.0,
        },
        sku_rows=[
            {"sku": 405933491, "abc": "A", "orders": 35, "buyouts": 30, "revenue": 42000.0, "margin": 0.22},
            {"sku": 810239842, "abc": "B", "orders": 18, "buyouts": 16, "revenue": 18000.0, "margin": 0.14},
        ],
        sku_dimensions={
            405933491: {"volume_liters": 1.2, "source": "stocks"},
            810239842: {"volume_liters": 0.8, "source": "stocks"},
        },
        local_orders_insights={"available": True, "by_region": [{"region": "NW", "orders": 65}]},
        localization_loss={"non_local_orders_share": 0.46},
        top5_sku_unit_economics={"items": [{"sku": 405933491, "risk_level": "high"}]},
    )

    assert payload.get("mode") == "full_rub"
    assert payload.get("total_estimated_overpay_rub") is not None
    assert payload.get("high_risk_regions")
    assert payload.get("top_sku_by_regional_risk")


def test_report_renders_regional_logistics_decision_block() -> None:
    facts = _base_facts()
    facts["regional_logistics_impact"] = {
        "mode": "risk_only",
        "status": "partial",
        "routes_available": False,
        "high_risk_regions": ["North-West", "Ural"],
        "top_sku_by_regional_risk": [
            {
                "sku": 405933491,
                "abc": "A",
                "orders": 35,
                "region_risk": "high",
                "sensitivity": "high",
                "conclusion": "SKU is sensitive to expensive destinations.",
            }
        ],
        "recommendations": [
            {
                "action": "Reposition SKU 405933491 closer to demand.",
                "why": "Expensive lanes may eat margin.",
                "expected_effect": "Lower logistics cost per SKU.",
            }
        ],
        "missing_inputs": ["order_geography"],
    }
    facts["localization_loss"] = {"non_local_orders_share": 0.52}

    md = build_audit_markdown(facts)

    assert "## 9." in md
    assert "### SKU" in md
    assert "practically" in md
    assert "order_geography" in md


def test_logistics_section_estimates_irp_when_missing() -> None:
    facts = _base_facts()
    facts["logistics_formula_model"] = {
        "mode": "B",
        "localization_share_pct": 48.0,
        "localization_index": 1.12,
        "item_price": 2300.0,
        "missing_inputs": ["sales_distribution_index_pct"],
    }

    md = build_audit_markdown(facts)
    assert "4.6%" in md
    assert "1.12" in md


def test_parse_localization_pct_handles_supported_formats() -> None:
    assert _parse_localization_pct(40) == 40.0
    assert _parse_localization_pct("40%") == 40.0
    assert _parse_localization_pct("40") == 40.0
    assert _parse_localization_pct(0.40) == 40.0
    assert _parse_localization_pct("0.40") == 40.0


def test_load_logistics_config_reads_localization_from_xlsx(tmp_path: Path) -> None:
    input_dir = tmp_path
    logist_dir = input_dir / "logist"
    logist_dir.mkdir(parents=True, exist_ok=True)
    config_file = logist_dir / "logistics_config.xlsx"

    ru_key = "\u041f\u0440\u043e\u0446\u0435\u043d\u0442 \u043b\u043e\u043a\u0430\u043b\u044c\u043d\u044b\u0445 \u0437\u0430\u043a\u0430\u0437\u043e\u0432"
    df = pd.DataFrame([[ru_key, "40%"]])
    df.to_excel(config_file, index=False, header=False)

    cfg = _load_logistics_config(str(input_dir))
    assert cfg["localization_pct"] == 40.0
    assert cfg["scope"] == "cabinet"
    assert cfg["update_frequency_days"] == 14
    assert cfg["source"].endswith("logist/logistics_config.xlsx")


def test_load_logistics_config_returns_null_when_file_missing(tmp_path: Path) -> None:
    cfg = _load_logistics_config(str(tmp_path))
    assert cfg["localization_pct"] is None
    assert cfg["source"].endswith("logist/logistics_config.xlsx")
    assert cfg["scope"] == "cabinet"


def test_build_cabinet_logistics_summary_uses_config_and_calculates_irp() -> None:
    summary = _build_cabinet_logistics_summary(
        funnel_summary={"orders": 10, "buys": 0, "revenue_orders": 0, "revenue_buyouts": 0},
        financial_summary={
            "gross_revenue": 10000.0,
            "logistics": 0.0,
            "cogs_total": 2000.0,
            "commission": 1000.0,
            "sales_qty": 0,
        },
        logistics_config={"localization_pct": 40.0},
    )

    assert summary["localization_pct"] == 40.0
    assert summary["orders_count"] == 10
    assert summary["avg_logistics_cost_est"] == 92.0
    assert summary["estimated_logistics_total"] == 920.0
    assert summary["target_localization_pct"] == 70.0
    assert summary["potential_overpay_due_localization"] == 210.0
    assert summary["irp"] == 0.608
