from src.report_metrics import compute_report_metrics, safe_pct


def test_cr_formulas_are_recomputed_from_base_fields():
    facts = {
        "account_summary": {"orders": 1},
        "funnel_summary": {
            "views": 235,
            "add_to_cart": 6,
            "orders": 99,
            "cr_cart": 99.0,
            "cr_order": 99.0,
            "revenue_orders": 1000,
        },
        "stock_summary": {"stock_units": 10, "sku_count": 2},
        "financial_summary": {"rows_count": 5},
        "ads_summary": {"spend": 100, "revenue_attr": 250},
        "sku_summary": {"no_sales_with_stock": []},
    }

    m = compute_report_metrics(facts)

    assert m["cr_cart"] == 2.55
    assert m["cr_order"] == 16.67
    assert m["sources"]["cr_cart"] == "add_to_cart/views*100"
    assert m["sources"]["cr_order"] == "orders/add_to_cart*100"


def test_safe_pct_returns_none_on_zero_or_missing_denominator():
    assert safe_pct(1, 0) is None
    assert safe_pct(1, None) is None
    assert safe_pct(None, 10) is None


def test_finance_unavailable_when_rows_count_is_zero():
    facts = {
        "account_summary": {},
        "funnel_summary": {"views": 10, "add_to_cart": 1, "orders": 1},
        "financial_summary": {"rows_count": 0},
        "stock_summary": {},
        "ads_summary": {},
        "sku_summary": {},
    }

    m = compute_report_metrics(facts)

    assert m["financial_rows_count"] == 0
    assert m["finance_available"] is False


def test_ads_without_attribution_has_no_roas():
    facts = {
        "account_summary": {},
        "funnel_summary": {"views": 100, "add_to_cart": 5, "orders": 1},
        "financial_summary": {"rows_count": 1},
        "stock_summary": {},
        "ads_summary": {"spend": 123.45},
        "sku_summary": {},
    }

    m = compute_report_metrics(facts)

    assert m["ad_spend"] == 123.45
    assert m["ad_attributed_revenue"] is None
    assert m["roas"] is None
    assert m["ads_efficiency_limited"] is True
