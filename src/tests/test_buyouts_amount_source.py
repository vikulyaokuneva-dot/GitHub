from src.main import build_local_report_from_facts


def _base_facts() -> dict:
    return {
        "date": "2026-04-01",
        "account_summary": {
            "orders": 10,
            "buyouts": 5,
        },
        "funnel_summary": {
            "orders": 10,
            "buys": 5,
            "views": 100,
            "add_to_cart": 20,
            "revenue_orders": 10000,
            "revenue_buyouts": 10000,
        },
        "financial_summary": {
            "rows_count": 3,
            "gross_revenue": 5000,
            "commission": 500,
            "logistics": 200,
            "storage": 50,
            "sales_qty": 5,
        },
        "ads_summary": {
            "spend": 100,
            "revenue_attr": 0,
        },
        "stock_summary": {
            "stock_units": 10,
            "sku_count": 1,
        },
        "sku_summary": {
            "no_sales_with_stock": [],
        },
    }


def test_buyouts_amount_prefers_financial_gross_revenue_when_finance_available():
    facts = _base_facts()
    report = build_local_report_from_facts("2026-04-01", facts)
    markdown = report["pdf_markdown"]

    assert "Сумма заказов: 10000 RUB" in markdown
    assert "Сумма выкупов: 5000 RUB" in markdown


def test_buyouts_amount_falls_back_to_funnel_when_finance_unavailable():
    facts = _base_facts()
    facts["financial_summary"]["rows_count"] = 0
    facts["financial_summary"]["gross_revenue"] = 0
    report = build_local_report_from_facts("2026-04-01", facts)
    markdown = report["pdf_markdown"]

    assert "Сумма заказов: 10000 RUB" in markdown
    assert "Сумма выкупов: 10000 RUB" in markdown

