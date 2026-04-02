from __future__ import annotations

from typing import Any

FINANCE_DELAYED_MESSAGE = (
    "Заказы уже есть, но WB ещё не отдал финансовые строки/выкупы за эту дату. "
    "Данные по выкупам, логистике и прибыли могут обновиться позже."
)

FINANCE_MISSING_MESSAGE = (
    "WB пока не отдал финансовые строки за дату отчёта. "
    "Финансовые показатели могут появиться позже."
)

FINANCE_OK_MESSAGE = "Финансовые строки за дату отчёта доступны."


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        s = s.replace(" ", "").replace(",", ".")
        try:
            return float(s)
        except Exception:
            return None
    try:
        return float(value)
    except Exception:
        return None


def safe_int(value: Any) -> int | None:
    v = safe_float(value)
    if v is None:
        return None
    return int(v)


def safe_pct(numerator: Any, denominator: Any) -> float | None:
    n = safe_float(numerator)
    d = safe_float(denominator)
    if n is None or d is None or d == 0:
        return None
    return round((n / d) * 100.0, 2)


def _pick_int(candidates: list[tuple[str, Any]]) -> tuple[int | None, str | None]:
    for source, raw in candidates:
        parsed = safe_int(raw)
        if parsed is not None:
            return parsed, source
    return None, None


def _pick_float(candidates: list[tuple[str, Any]]) -> tuple[float | None, str | None]:
    for source, raw in candidates:
        parsed = safe_float(raw)
        if parsed is not None:
            return parsed, source
    return None, None


def derive_finance_status(orders: Any, financial_rows_count: Any) -> tuple[str, str, int, int]:
    orders_i = safe_int(orders) or 0
    rows_i = safe_int(financial_rows_count) or 0
    if rows_i > 0:
        return "ok", FINANCE_OK_MESSAGE, orders_i, rows_i
    if orders_i > 0:
        return "delayed", FINANCE_DELAYED_MESSAGE, orders_i, rows_i
    return "missing", FINANCE_MISSING_MESSAGE, orders_i, rows_i


def compute_report_metrics(facts: dict) -> dict:
    account_summary = facts.get("account_summary") or {}
    funnel_summary = facts.get("funnel_summary") or {}
    financial_summary = facts.get("financial_summary") or {}
    stock_summary = facts.get("stock_summary") or {}
    sku_summary = facts.get("sku_summary") or {}
    ads_block_key = "ad_summary" if isinstance(facts.get("ad_summary"), dict) else "ads_summary"
    ad_summary = facts.get(ads_block_key) or {}

    orders, orders_source = _pick_int(
        [
            ("account_summary.orders", account_summary.get("orders")),
            ("funnel_summary.orders", funnel_summary.get("orders")),
        ]
    )
    views, views_source = _pick_int([("funnel_summary.views", funnel_summary.get("views"))])
    add_to_cart, add_to_cart_source = _pick_int([("funnel_summary.add_to_cart", funnel_summary.get("add_to_cart"))])
    revenue_orders, revenue_orders_source = _pick_float(
        [("funnel_summary.revenue_orders", funnel_summary.get("revenue_orders"))]
    )

    stock_units, stock_units_source = _pick_int([("stock_summary.stock_units", stock_summary.get("stock_units"))])
    sku_count, sku_count_source = _pick_int([("stock_summary.sku_count", stock_summary.get("sku_count"))])

    ad_spend, ad_spend_source = _pick_float(
        [
            (f"{ads_block_key}.total_spend", ad_summary.get("total_spend")),
            (f"{ads_block_key}.spend", ad_summary.get("spend")),
        ]
    )
    ad_attributed_revenue, ad_attributed_revenue_source = _pick_float(
        [
            (f"{ads_block_key}.ad_attributed_revenue", ad_summary.get("ad_attributed_revenue")),
            (f"{ads_block_key}.revenue_attr", ad_summary.get("revenue_attr")),
            (f"{ads_block_key}.revenue", ad_summary.get("revenue")),
        ]
    )

    rows_count, rows_count_source = _pick_int(
        [("financial_summary.rows_count", financial_summary.get("rows_count"))]
    )

    cr_cart = safe_pct(add_to_cart, views)
    cr_order = safe_pct(orders, add_to_cart)

    roas = None
    roas_source = None
    if ad_spend is not None and ad_attributed_revenue is not None and ad_spend != 0:
        roas = round(ad_attributed_revenue / ad_spend, 2)
        roas_source = "ad_attributed_revenue/ad_spend"

    finance_status, finance_message, _, rows_count_i = derive_finance_status(orders, rows_count)
    finance_available = finance_status == "ok"
    ads_attribution_available = ad_attributed_revenue is not None
    ads_efficiency_limited = ad_spend is not None and ad_attributed_revenue is None

    no_sales_with_stock = sku_summary.get("no_sales_with_stock")
    if not isinstance(no_sales_with_stock, list):
        no_sales_with_stock = []
    no_sales_top5 = no_sales_with_stock[:5]

    return {
        "orders": orders,
        "views": views,
        "add_to_cart": add_to_cart,
        "cr_cart": cr_cart,
        "cr_order": cr_order,
        "revenue_orders": revenue_orders,
        "ad_spend": ad_spend,
        "ad_attributed_revenue": ad_attributed_revenue,
        "roas": roas,
        "stock_units": stock_units,
        "sku_count": sku_count,
        "financial_rows_count": rows_count_i,
        "finance_available": finance_available,
        "finance_status": finance_status,
        "finance_message": finance_message,
        "ads_attribution_available": ads_attribution_available,
        "ads_efficiency_limited": ads_efficiency_limited,
        "no_sales_with_stock_top5": no_sales_top5,
        "sources": {
            "orders": orders_source,
            "views": views_source,
            "add_to_cart": add_to_cart_source,
            "cr_cart": "add_to_cart/views*100",
            "cr_order": "orders/add_to_cart*100",
            "revenue_orders": revenue_orders_source,
            "ad_spend": ad_spend_source,
            "ad_attributed_revenue": ad_attributed_revenue_source,
            "roas": roas_source,
            "stock_units": stock_units_source,
            "sku_count": sku_count_source,
            "financial_rows_count": rows_count_source,
        },
        "raw_values": {
            "account_summary.orders": account_summary.get("orders"),
            "funnel_summary.orders": funnel_summary.get("orders"),
            "funnel_summary.views": funnel_summary.get("views"),
            "funnel_summary.add_to_cart": funnel_summary.get("add_to_cart"),
            "funnel_summary.cr_cart": funnel_summary.get("cr_cart"),
            "funnel_summary.cr_order": funnel_summary.get("cr_order"),
            "funnel_summary.revenue_orders": funnel_summary.get("revenue_orders"),
            "stock_summary.stock_units": stock_summary.get("stock_units"),
            "stock_summary.sku_count": stock_summary.get("sku_count"),
            f"{ads_block_key}.total_spend": ad_summary.get("total_spend"),
            f"{ads_block_key}.spend": ad_summary.get("spend"),
            f"{ads_block_key}.ad_attributed_revenue": ad_summary.get("ad_attributed_revenue"),
            f"{ads_block_key}.revenue_attr": ad_summary.get("revenue_attr"),
            f"{ads_block_key}.revenue": ad_summary.get("revenue"),
            "financial_summary.rows_count": financial_summary.get("rows_count"),
        },
    }
