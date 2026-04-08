from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from audit.audit_facts_builder import _build_search_insights
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
        "logistics_formula_model": {},
        "localization_loss": {"status": "insufficient_data", "estimation_mode": "insufficient_data"},
    }


def test_report_search_tables_include_sku_grouping_and_no_text_decode_block() -> None:
    facts = _base_facts()
    facts["search_insights"] = {
        "status": "ok",
        "base_rows": [
            {"query": "growth-1", "nmId": 12345, "impressions": 120, "clicks": 30, "spend": 0.0},
            {"query": "growth-2", "nmId": 12345, "impressions": 90, "clicks": 18, "spend": 0.0},
        ],
        "unprofitable": [
            {"query": "loss-q1", "nmId": 12345, "impressions": 1000, "clicks": 40, "ctr": 4.0, "spend": 700.0, "orders": 0, "revenue": 0.0, "action": "Отключить"},
            {"query": "loss-q2", "nmId": 12345, "impressions": 800, "clicks": 30, "ctr": 3.75, "spend": 500.0, "orders": 0, "revenue": 0.0, "action": "Отключить"},
        ],
        "weak": [
            {"query": "weak-q1", "nmId": 55555, "impressions": 900, "clicks": 60, "ctr": 6.67, "spend": 800.0, "orders": 2, "revenue": 2400.0, "drr": 0.33, "action": "Снизить ставку"},
        ],
        "effective": [
            {"query": "eff-q1", "nmId": 66666, "impressions": 1100, "clicks": 70, "ctr": 6.36, "spend": 600.0, "orders": 8, "revenue": 5000.0, "drr": 0.12, "action": "Масштабировать"},
        ],
        "growth_hypotheses": [
            {"query": "growth-1", "impressions": 120, "clicks": 30, "ctr": 25.0, "spend": 0.0},
            {"query": "growth-2", "impressions": 90, "clicks": 18, "ctr": 20.0, "spend": 0.0},
        ],
        "orders_data": {"available": True, "source": "search", "message": "ok"},
    }

    md = build_audit_markdown(facts)

    assert "## 12. Поисковые запросы" in md
    assert "Слабые запросы — есть заказы, но высокая стоимость привлечения (высокий ДРР)" in md
    assert "| Артикул | Запрос | Показы | Клики | CTR | Расход | Заказы | Действие |" in md
    assert "| Артикул | Запрос | Показы | Клики | CTR | Расход | Заказы | ДРР | Действие |" in md
    assert "| Артикул | Запрос | Показы | Клики | CTR | Реклама | Действие |" in md
    assert "| 12345 | loss-q1 |" in md
    assert "|  | loss-q2 |" in md
    assert "### Что делать" not in md


def test_report_search_tables_show_rk_column_when_present() -> None:
    facts = _base_facts()
    facts["search_insights"] = {
        "status": "ok",
        "base_rows": [{"query": "q1", "nmId": 123, "rk": "RK-01", "impressions": 100, "clicks": 10, "spend": 0.0}],
        "unprofitable": [{"query": "q1", "nmId": 123, "rk": "RK-01", "impressions": 100, "clicks": 10, "ctr": 10.0, "spend": 100.0, "orders": 0, "revenue": 0.0}],
        "weak": [{"query": "q2", "nmId": 124, "rk": "RK-02", "impressions": 100, "clicks": 20, "ctr": 20.0, "spend": 200.0, "orders": 1, "revenue": 500.0, "drr": 0.4}],
        "effective": [{"query": "q3", "nmId": 125, "rk": "RK-03", "impressions": 100, "clicks": 30, "ctr": 30.0, "spend": 100.0, "orders": 5, "revenue": 1000.0, "drr": 0.1}],
        "growth_hypotheses": [{"query": "q1", "impressions": 100, "clicks": 20, "ctr": 20.0, "spend": 0.0, "rk": "RK-01"}],
        "orders_data": {"available": True, "source": "search", "message": "ok"},
    }

    md = build_audit_markdown(facts)
    assert "| Артикул | Запрос | РК | Показы | Клики | CTR | Расход | Заказы | Действие |" in md
    assert "| Артикул | Запрос | РК | Показы | Клики | CTR | Расход | Заказы | ДРР | Действие |" in md
    assert "| Артикул | Запрос | РК | Показы | Клики | CTR | Реклама | Действие |" in md


def test_search_weak_bucket_uses_drr_threshold_25pct() -> None:
    insights = _build_search_insights(
        selected_search_files=["search.xlsx"],
        search_rows=[
            {
                "query": "weak-26",
                "nmId": 111,
                "seller_article": "",
                "impressions": 100,
                "clicks": 20,
                "add_to_cart": 5,
                "orders": 2,
                "buyouts": 0,
                "spend": 260.0,
                "revenue": 1000.0,
            },
            {
                "query": "effective-18",
                "nmId": 222,
                "seller_article": "",
                "impressions": 100,
                "clicks": 20,
                "add_to_cart": 5,
                "orders": 2,
                "buyouts": 0,
                "spend": 180.0,
                "revenue": 1000.0,
            },
        ],
        search_parse_diag={"status": "ok", "recognized_columns": {"orders": True}},
        ads_rows=[],
        orders_rows=[],
    )

    weak_queries = {str(x.get("query")) for x in (insights.get("weak") or []) if isinstance(x, dict)}
    effective_queries = {str(x.get("query")) for x in (insights.get("effective") or []) if isinstance(x, dict)}

    assert "weak-26" in weak_queries
    assert "effective-18" in effective_queries
