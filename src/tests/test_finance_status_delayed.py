from src.main import build_local_report_from_facts
from src.portfolio_strategy_engine import analyze_portfolio_strategy
from src.report_metrics import derive_finance_status
from src.sku_performance_analyzer import analyze_sku_performance


def test_derive_finance_status_delayed_when_orders_present_and_finance_rows_empty():
    status, message, orders, rows = derive_finance_status(orders=5, financial_rows_count=0)
    assert status == "delayed"
    assert orders == 5
    assert rows == 0
    assert "WB ещё не отдал финансовые строки" in message


def test_local_report_contains_delayed_finance_warning_and_metadata():
    facts = {
        "date": "2026-04-02",
        "report_date": "2026-04-02",
        "account_summary": {"orders": 3, "buyouts": 0},
        "funnel_summary": {
            "orders": 3,
            "buys": 0,
            "views": 100,
            "add_to_cart": 10,
            "revenue_orders": 1200,
            "revenue_buyouts": 0,
        },
        "financial_summary": {"rows_count": 0, "gross_revenue": 0},
        "ads_summary": {"spend": 0, "revenue_attr": 0},
        "stock_summary": {"stock_units": 10, "sku_count": 1},
        "sku_summary": {"no_sales_with_stock": [{"sku": 111, "stock_qty": 5}]},
    }

    report = build_local_report_from_facts("2026-04-02", facts)
    markdown = report["pdf_markdown"]

    assert report["finance_status"] == "delayed"
    assert report["financial_rows_count"] == 0
    assert "WB ещё не отдал финансовые строки/выкупы за эту дату" in markdown
    assert "SKU без продаж, но с остатками (top-5):" not in markdown


def test_profit_abc_is_disabled_when_finance_is_delayed():
    sku_perf = analyze_sku_performance(
        finance_summary={
            "sku_financials": {
                "1": {"net_revenue": 1000, "profit": 300, "margin": 0.3},
                "2": {"net_revenue": 1000, "profit": -100, "margin": -0.1},
            }
        },
        funnel_raw=[],
        stocks_raw=[],
        ads_raw=[],
        period_days=1,
        finance_status="delayed",
    )
    assert sku_perf["abc_summary"] == {}
    assert sku_perf["top_profit"] == []
    assert sku_perf["worst_profit"] == []


def test_portfolio_does_not_mark_dead_when_finance_is_delayed():
    portfolio = analyze_portfolio_strategy(
        sku_performance={
            "rows": [
                {
                    "sku": 111,
                    "revenue": 0,
                    "profit": 0,
                    "margin": 0,
                    "orders": 0,
                    "buyouts": 0,
                    "ad_spend": 100,
                    "ad_roi": -1,
                    "stock_qty": 20,
                    "turnover_days": 999,
                    "abc": "N/A",
                }
            ]
        },
        finance_status="delayed",
    )

    assert portfolio["top_dead"] == []
    assert portfolio["summary"]["counts"]["Dead"] == 0

