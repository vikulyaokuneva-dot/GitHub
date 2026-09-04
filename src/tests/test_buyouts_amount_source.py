from src.main import _enforce_kpi_totals, _extract_buyouts_from_daily_detailed_facts, build_local_report_from_facts


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

    assert "10000 RUB" in markdown
    assert "5000 RUB" in markdown


def test_buyouts_amount_falls_back_to_funnel_when_finance_unavailable():
    facts = _base_facts()
    facts["financial_summary"]["rows_count"] = 0
    facts["financial_summary"]["gross_revenue"] = 0
    facts["buyouts_count"] = None
    facts["buyouts_revenue"] = None
    report = build_local_report_from_facts("2026-04-01", facts)
    markdown = report["pdf_markdown"]

    assert markdown.count("10000 RUB") == 1
    assert "Сумма выкупов: н/д" in markdown


def test_buyouts_qty_uses_daily_detailed_sales_rows_when_finance_delayed():
    facts = _base_facts()
    facts["date"] = "2026-04-02"
    facts["report_date"] = "2026-04-02"
    facts["account_summary"]["buyouts"] = 0
    facts["funnel_summary"]["buys"] = 0
    facts["financial_summary"]["rows_count"] = 0
    facts["financial_summary"]["sku_financials"] = {}
    facts["daily_detailed_report_rows"] = [
        {
            "\u041a\u043e\u0434 \u043d\u043e\u043c\u0435\u043d\u043a\u043b\u0430\u0442\u0443\u0440\u044b": "1001008",
            "\u0422\u0438\u043f \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0430": "\u041f\u0440\u043e\u0434\u0430\u0436\u0430",
            "\u041e\u0431\u043e\u0441\u043d\u043e\u0432\u0430\u043d\u0438\u0435 \u0434\u043b\u044f \u043e\u043f\u043b\u0430\u0442\u044b": "\u041f\u0440\u043e\u0434\u0430\u0436\u0430",
            "\u041a\u043e\u043b-\u0432\u043e": "1",
        },
        {
            "\u041a\u043e\u0434 \u043d\u043e\u043c\u0435\u043d\u043a\u043b\u0430\u0442\u0443\u0440\u044b": "1001008",
            "\u0422\u0438\u043f \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0430": "",
            "\u041e\u0431\u043e\u0441\u043d\u043e\u0432\u0430\u043d\u0438\u0435 \u0434\u043b\u044f \u043e\u043f\u043b\u0430\u0442\u044b": "\u041b\u043e\u0433\u0438\u0441\u0442\u0438\u043a\u0430",
            "\u041a\u043e\u043b-\u0432\u043e": "0",
        },
    ]

    detailed_buyouts, detailed_source = _extract_buyouts_from_daily_detailed_facts(facts)
    assert detailed_buyouts == 1
    assert detailed_source == "facts.daily_detailed_report_rows"

    report = build_local_report_from_facts("2026-04-02", facts)
    markdown = report["pdf_markdown"]
    enforced = _enforce_kpi_totals(markdown, facts)

    buyouts_label = "\u0412\u044b\u043a\u0443\u043f\u044b"
    assert f"- {buyouts_label}: 1" in markdown
    assert f"- {buyouts_label}: 1" in enforced


def test_report_returns_debug_sources_for_orders_and_buyouts():
    facts = _base_facts()
    facts["orders_count"] = 10
    facts["orders_revenue"] = 10000
    facts["buyouts_count"] = 5
    facts["buyouts_revenue"] = 5000
    facts["debug_sources"] = {
        "orders_source": "analytics_api",
        "buyouts_source": "finance_api",
        "raw_orders": {"orders_count": 10, "orders_revenue": 10000},
        "raw_buyouts": {"buyouts_count": 5, "buyouts_revenue": 5000},
    }

    report = build_local_report_from_facts("2026-04-01", facts)
    debug = report.get("debug_sources") or {}

    assert debug.get("orders_source") == "analytics_api"
    assert debug.get("buyouts_source") == "finance_api"
