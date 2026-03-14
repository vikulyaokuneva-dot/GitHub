from __future__ import annotations

from typing import Any, Dict, List


def _as_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_div(numerator: Any, denominator: Any) -> float | None:
    den = _as_float(denominator)
    if den <= 0:
        return None
    return _as_float(numerator) / den


def _query_brief(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "query": str(row.get("query") or ""),
        "sku": row.get("sku"),
        "ad_spend": row.get("ad_spend"),
        "orders": row.get("orders"),
        "buyouts": row.get("buyouts"),
        "revenue": row.get("revenue"),
        "profit": row.get("profit"),
        "ROMI": row.get("ROMI"),
        "classification": row.get("classification"),
        "confidence": row.get("confidence"),
    }


def build_portfolio_ads_summary(
    *,
    sku_rows: List[Dict[str, Any]],
    query_rows: List[Dict[str, Any]],
    analysis_mode: str,
    campaign_total_spend: float,
) -> Dict[str, Any]:
    portfolio_ad_spend_rows = sum(_as_float(row.get("ad_spend")) for row in sku_rows if isinstance(row, dict))
    portfolio_ad_spend = max(portfolio_ad_spend_rows, _as_float(campaign_total_spend))
    portfolio_orders = sum(_as_float(row.get("orders_from_ads")) for row in sku_rows if isinstance(row, dict))
    portfolio_buyouts = sum(_as_float(row.get("buyouts_from_ads")) for row in sku_rows if isinstance(row, dict))
    portfolio_revenue = sum(_as_float(row.get("revenue_from_ads")) for row in sku_rows if isinstance(row, dict))
    portfolio_profit = sum(_as_float(row.get("profit_from_ads")) for row in sku_rows if isinstance(row, dict))

    portfolio_romi = _safe_div(portfolio_profit * 100.0, portfolio_ad_spend)
    portfolio_drr = _safe_div(portfolio_ad_spend * 100.0, portfolio_revenue)
    portfolio_cpo = _safe_div(portfolio_ad_spend, portfolio_orders)

    profitable_queries = [
        row
        for row in query_rows
        if isinstance(row, dict) and str(row.get("classification") or "") == "profitable"
    ]
    unprofitable_queries = [
        row
        for row in query_rows
        if isinstance(row, dict) and str(row.get("classification") or "") == "unprofitable"
    ]
    potential_queries = [
        row
        for row in profitable_queries
        if _as_float(row.get("orders")) <= 5 and _as_float(row.get("ROMI")) >= 20.0
    ]

    profitable_queries.sort(key=lambda row: (_as_float(row.get("profit")), _as_float(row.get("ROMI"))), reverse=True)
    unprofitable_queries.sort(key=lambda row: (_as_float(row.get("profit")), -_as_float(row.get("ROMI"))))
    potential_queries.sort(key=lambda row: (_as_float(row.get("ROMI")), _as_float(row.get("orders"))), reverse=True)

    summary = {
        "analysis_mode": analysis_mode,
        "portfolio_ad_spend": round(portfolio_ad_spend, 2),
        "portfolio_orders_from_ads": round(portfolio_orders, 4),
        "portfolio_buyouts_from_ads": round(portfolio_buyouts, 4),
        "portfolio_revenue_from_ads": round(portfolio_revenue, 2),
        "portfolio_profit_from_ads": round(portfolio_profit, 2),
        "portfolio_ROMI": (round(float(portfolio_romi), 4) if portfolio_romi is not None else None),
        "portfolio_DRR": (round(float(portfolio_drr), 4) if portfolio_drr is not None else None),
        "portfolio_CPO": (round(float(portfolio_cpo), 4) if portfolio_cpo is not None else None),
        "top_profitable_queries": [_query_brief(row) for row in profitable_queries[:10]],
        "top_unprofitable_queries": [_query_brief(row) for row in unprofitable_queries[:10]],
        "high_potential_queries": [_query_brief(row) for row in potential_queries[:10]],
    }

    # Compatibility aliases with requested naming.
    summary["total_ad_spend"] = summary["portfolio_ad_spend"]
    summary["orders_from_ads"] = summary["portfolio_orders_from_ads"]
    summary["buyouts_from_ads"] = summary["portfolio_buyouts_from_ads"]
    summary["revenue_from_ads"] = summary["portfolio_revenue_from_ads"]
    summary["profit_from_ads"] = summary["portfolio_profit_from_ads"]
    summary["ROMI"] = summary["portfolio_ROMI"]
    summary["DRR"] = summary["portfolio_DRR"]
    summary["CPO"] = summary["portfolio_CPO"]
    return summary
