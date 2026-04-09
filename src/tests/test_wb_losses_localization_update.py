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
            "cogs_total": 25000.0,
            "rows_count": 0,
            "sales_qty": 0,
        },
        "funnel_summary": {"orders": 100, "buys": 50, "revenue_orders": 0, "views": 0, "add_to_cart": 0},
        "ads_summary": {"spend": 0, "roas": None, "impressions": 0, "clicks": 0, "drr": None},
        "stock_summary": {"stock_units": 0, "sku_count": 0, "days_of_cover": 0, "risk_of_oos": False},
        "search_insights": {"status": "ok", "total_leak_spend": 1000.0, "effective": [], "growth_hypotheses": []},
        "money_losses": {"ads_waste_rub": 0.0, "frozen_stock_value_rub": 45000.0},
        "local_orders_insights": {"available": False, "message": "нет данных"},
        "decision_layer": {"reasons_of_loss": [], "unprofitable_sku": [], "ads_leaks": []},
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


def test_losses_block_has_only_ads_and_logistics_without_cogs() -> None:
    facts = _base_facts()
    md = build_audit_markdown(facts)

    losses_section = md[md.index("## 💸 Потери") : md.index("## 📈 Точки роста")]
    assert "• Неэффективная реклама:" in losses_section
    assert "• Переплата за логистику:" in losses_section
    assert "Себестоимость" not in losses_section
    assert "заморожено в остатках" not in losses_section

    where_money_lost_section = md[md.index("### 🚨 Где теряются деньги") : md.index("---PAGEBREAK---", md.index("### 🚨 Где теряются деньги"))]
    assert "Себестоимость" not in where_money_lost_section


def test_localization_block_explains_buyouts_formula() -> None:
    facts = _base_facts()
    facts["local_orders_insights"] = {
        "available": True,
        "total_buyouts": 25,
        "by_region": [
            {"region": "Москва", "orders": 100, "buyouts": 20, "stock_qty": 10},
            {"region": "Казань", "orders": 10, "buyouts": 5, "stock_qty": 5},
        ],
        "recommendations": [],
    }

    md = build_audit_markdown(facts)
    section_8 = md[md.index("## 8. Локальные заказы и размещение товара") : md.index("## 9. Логистика: где переплачиваете")]

    assert "Распределение по регионам рассчитывается от выкупов." in section_8
    assert "Если товар отсутствует на складе региона, но есть выкуп — заказ считается не локальным." in section_8
    assert "Всего выкупов: 25" in section_8
    assert "| Регион/город | Выкупы, шт | Доля | Остаток, шт |" in section_8
    assert "| Москва | 20 | 80% | 10 |" in section_8
    assert "| Казань | 5 | 20% | 5 |" in section_8
    assert "При небольшом количестве выкупов доли по регионам могут выглядеть завышенными." in section_8
