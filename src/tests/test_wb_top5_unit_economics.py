from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from audit.audit_facts_builder import _build_top5_sku_unit_economics_payload
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


def test_top5_unit_economics_payload_filters_and_computes_risk() -> None:
    sku_rows = [
        {
            "sku": 405933491,
            "abc": "A",
            "orders": 38,
            "buyouts": 38,
            "profit": 15752,
            "revenue": 20814,
            "ad_spend": 1800,
        },
        {
            "sku": 222,
            "abc": "B",
            "orders": 10,
            "buyouts": 10,
            "profit": 5200,
            "revenue": 12000,
            "ad_spend": 300,
        },
        {
            "sku": 333,
            "abc": "C",
            "orders": 5,
            "buyouts": 5,
            "profit": -10,
            "revenue": 5000,
            "ad_spend": 0,
        },
        {
            "sku": 444,
            "abc": "C",
            "orders": 6,
            "buyouts": 6,
            "profit": 100,
            "revenue": 0,
            "ad_spend": 0,
        },
    ]
    financial_summary = {
        "sku_financials": {
            405933491: {
                "profit": 15752,
                "net_revenue": 20814,
                "sales_qty": 38,
                "logistics": 2300,
            },
            222: {
                "profit": 5200,
                "net_revenue": 12000,
                "sales_qty": 10,
                "logistics": 800,
            },
        }
    }
    sku_dimensions = {
        405933491: {"volume_liters": 1.3, "source": "stocks"},
        222: {"volume_liters": 0.9, "source": "stocks"},
    }
    wb_logistics_estimate = {"warehouse_coef": 1.55, "localization_share_pct": 35.0}

    payload = _build_top5_sku_unit_economics_payload(
        sku_rows=sku_rows,
        financial_summary=financial_summary,
        sku_dimensions=sku_dimensions,
        wb_logistics_estimate=wb_logistics_estimate,
        local_orders_insights={},
        localization_loss={},
    )

    items = payload.get("items") or []
    assert payload.get("available") is True
    assert len(items) == 2
    assert all(float(x.get("profit") or 0) > 0 for x in items)
    assert all(float(x.get("revenue") or 0) > 0 for x in items)

    first = items[0]
    assert first.get("sku") == 405933491
    assert first.get("risk_level") in {"low", "medium", "high"}
    assert first.get("logistics_new") is not None
    assert first.get("logistics_base") is not None
    assert first.get("overpay_per_order") is not None


def test_report_renders_top5_unit_economics_block() -> None:
    facts = _base_facts()
    facts["top5_sku_unit_economics"] = {
        "available": True,
        "items": [
            {
                "sku": 405933491,
                "category": "A",
                "revenue": 20814,
                "profit": 15752,
                "orders": 38,
                "buyouts": 38,
                "price_avg": 547.74,
                "profit_per_order": 414.53,
                "logistics_per_order": 60,
                "logistics_new": 62,
                "logistics_base": 30,
                "overpay_per_order": 32,
                "total_overpay": 1216,
                "ads_per_order": 15,
                "risk_level": "high",
                "comment": "Высокая логистика из-за слабой локализации.",
                "recommendation": "Перераспределить товар по складам для снижения ИЛ.",
            }
        ],
    }

    md = build_audit_markdown(facts)

    assert "## ТОП-5 SKU: где зарабатываете и где теряете" in md
    assert "### SKU: 405933491 (A)" in md
    assert "Риск: ВЫСОКИЙ" in md
    assert "Рекомендация: Перераспределить товар по складам для снижения ИЛ." in md
