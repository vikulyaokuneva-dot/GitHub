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


def test_report_search_block_renders_categories_and_actions() -> None:
    facts = _base_facts()
    facts["search_insights"] = {
        "status": "ok",
        "base_rows": [
            {
                "query": "платье женское",
                "nmId": 405933491,
                "clicks": 80,
                "add_to_cart": 14,
                "orders": 9,
                "buyouts": 7,
                "spend": 1200.0,
                "revenue": 18000.0,
            },
            {
                "query": "платье в офис",
                "nmId": 810239842,
                "clicks": 120,
                "add_to_cart": 0,
                "orders": 0,
                "buyouts": 0,
                "spend": 2100.0,
                "revenue": 0.0,
            },
            {
                "query": "платье миди",
                "nmId": 0,
                "seller_article": "ART-55",
                "clicks": 55,
                "add_to_cart": 11,
                "orders": 0,
                "buyouts": 0,
                "spend": 900.0,
                "revenue": 0.0,
            },
        ],
    }

    md = build_audit_markdown(facts)

    assert "## 12. Поисковые запросы" in md
    assert "эффективных запросов (дают заказы)" in md
    assert "неэффективных (сливают бюджет)" in md
    assert "с потенциалом" in md
    assert "### Эффективные запросы (оставить и масштабировать)" in md
    assert "### Неэффективные запросы (отключить / снизить ставки)" in md
    assert "### Запросы с потенциалом (доработать карточку)" in md
    assert "| Запрос | SKU | Клики | CTR | В корзину | Заказы | CR | Расход | Выручка | Прибыль (оценка) | ДРР | Вывод |" in md
    assert "### Деньги в поиске" in md
    assert "Потери на неэффективных запросах" in md
    assert "работает" in md
    assert "сливает бюджет" in md
    assert "нужно улучшить карточку" in md
    assert "ART-55" in md
    assert "### Что делать с поиском" in md
    assert "### Связь с SKU" in md
    assert "SKU 405933491:" in md
    assert "SKU 810239842:" in md
    assert "5. Поиск: отключить / снизить ставки:" in md
    assert "6. Поиск: масштабировать:" in md


def test_search_ignores_zero_spend_rows_for_ineffective_bucket() -> None:
    facts = _base_facts()
    facts["search_insights"] = {
        "status": "ok",
        "base_rows": [
            {
                "query": "без рекламы",
                "nmId": 111,
                "clicks": 50,
                "add_to_cart": 0,
                "orders": 0,
                "buyouts": 0,
                "spend": 0.0,
                "revenue": 0.0,
            },
            {
                "query": "с рекламой",
                "nmId": 222,
                "clicks": 40,
                "add_to_cart": 0,
                "orders": 0,
                "buyouts": 0,
                "spend": 500.0,
                "revenue": 0.0,
            },
        ],
    }

    md = build_audit_markdown(facts)
    assert "Найдено (только запросы с рекламой, spend > 0):" in md
    assert "пропущено 1 строк без рекламного расхода (spend = 0)" in md
    assert "| Строк с рекламой (spend > 0) | 1 |" in md
