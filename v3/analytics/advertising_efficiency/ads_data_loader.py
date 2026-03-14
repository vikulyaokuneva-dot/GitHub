from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping

from ...validation.sku_normalization import normalize_sku


_SKU_ALIASES = (
    "sku",
    "nm_id",
    "nmid",
    "nmId",
    "article",
    "article_wb",
    "offer_id",
)
_QUERY_ALIASES = (
    "query",
    "keyword",
    "search_query",
    "search_term",
    "phrase",
    "query_text",
)
_IMPRESSIONS_ALIASES = ("impressions", "views", "shows")
_CLICKS_ALIASES = ("clicks", "click")
_ORDERS_ALIASES = ("orders", "orders_count", "ordered_units", "ads_orders")
_BUYOUTS_ALIASES = ("buyouts", "sales_count", "buys", "buyout_units")
_REVENUE_ALIASES = ("revenue", "sales_amount", "buyouts_amount", "orders_amount")
_SPEND_ALIASES = ("ads_spend", "ad_spend", "spend", "cost", "expenses")
_COST_PRICE_ALIASES = ("cost_price", "cogs", "cost_of_goods", "cost_of_goods_sold")


def _as_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    token = str(value).strip().replace(" ", "").replace(",", ".")
    if not token:
        return None
    try:
        return float(token)
    except ValueError:
        return None


def _pick_first(row: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in row:
            return row.get(key)
    lowered = {str(k).strip().lower(): k for k in row.keys()}
    for key in keys:
        real = lowered.get(str(key).lower())
        if real is not None:
            return row.get(real)
    return None


def _extract_rows(source: Any) -> List[Dict[str, Any]]:
    if isinstance(source, list):
        return [row for row in source if isinstance(row, dict)]
    if not isinstance(source, dict):
        return []
    for key in ("ads_rows", "query_rows", "items", "rows"):
        value = source.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def _normalize_ads_row(row: Mapping[str, Any]) -> Dict[str, Any]:
    raw_sku = _pick_first(row, _SKU_ALIASES)
    sku = normalize_sku(raw_sku)
    query = str(_pick_first(row, _QUERY_ALIASES) or "").strip()

    impressions = _as_float_or_none(_pick_first(row, _IMPRESSIONS_ALIASES))
    clicks = _as_float_or_none(_pick_first(row, _CLICKS_ALIASES))
    orders = _as_float_or_none(_pick_first(row, _ORDERS_ALIASES))
    buyouts = _as_float_or_none(_pick_first(row, _BUYOUTS_ALIASES))
    revenue = _as_float_or_none(_pick_first(row, _REVENUE_ALIASES))
    ad_spend = _as_float_or_none(_pick_first(row, _SPEND_ALIASES))
    cost_price = _as_float_or_none(_pick_first(row, _COST_PRICE_ALIASES))

    return {
        "sku": sku,
        "query": query,
        "impressions": max(0.0, impressions or 0.0),
        "clicks": max(0.0, clicks or 0.0),
        "orders": max(0.0, orders or 0.0),
        "buyouts": None if buyouts is None else max(0.0, buyouts),
        "revenue": None if revenue is None else max(0.0, revenue),
        "ad_spend": max(0.0, ad_spend or 0.0),
        "cost_price": None if cost_price is None else max(0.0, cost_price),
        "is_campaign_total": bool(row.get("_is_campaign_total", False)),
        "source": "ads_rows",
    }


def _normalize_keyword_query_row(row: Mapping[str, Any]) -> Dict[str, Any]:
    raw_sku = _pick_first(row, _SKU_ALIASES)
    sku = normalize_sku(raw_sku)
    query = str(_pick_first(row, _QUERY_ALIASES) or "").strip()
    impressions = _as_float_or_none(_pick_first(row, _IMPRESSIONS_ALIASES))
    clicks = _as_float_or_none(_pick_first(row, _CLICKS_ALIASES))
    orders = _as_float_or_none(_pick_first(row, _ORDERS_ALIASES))
    buyouts = _as_float_or_none(_pick_first(row, _BUYOUTS_ALIASES))
    ad_spend = _as_float_or_none(_pick_first(row, _SPEND_ALIASES))

    return {
        "sku": sku,
        "query": query,
        "impressions": max(0.0, impressions or 0.0),
        "clicks": max(0.0, clicks or 0.0),
        "orders": max(0.0, orders or 0.0),
        "buyouts": None if buyouts is None else max(0.0, buyouts),
        "revenue": None,
        "ad_spend": max(0.0, ad_spend or 0.0),
        "cost_price": None,
        "is_campaign_total": False,
        "source": "keyword_monitoring",
    }


def _build_sku_metrics_index(metrics: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    rows = metrics.get("sku_metrics", []) if isinstance(metrics, dict) else []
    if not isinstance(rows, list):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        sku = normalize_sku(row.get("sku") or row.get("nm_id") or row.get("offer_id"))
        if sku:
            out[sku] = row
    return out


def load_ads_efficiency_sources(
    *,
    metrics: Dict[str, Any],
    ads_rows: List[Dict[str, Any]] | None,
    keyword_monitoring: Dict[str, Any] | None,
) -> Dict[str, Any]:
    safe_ads_rows = ads_rows if isinstance(ads_rows, list) else []
    safe_keyword = keyword_monitoring if isinstance(keyword_monitoring, dict) else {}

    normalized_ads = [_normalize_ads_row(row) for row in safe_ads_rows if isinstance(row, dict)]
    sku_ads_rows = [row for row in normalized_ads if row.get("sku") and not bool(row.get("is_campaign_total", False))]
    query_ads_rows = [row for row in sku_ads_rows if str(row.get("query") or "").strip()]

    keyword_query_rows = safe_keyword.get("query_items", safe_keyword.get("items", []))
    if not isinstance(keyword_query_rows, list):
        keyword_query_rows = []

    normalized_keyword_queries = [_normalize_keyword_query_row(row) for row in keyword_query_rows if isinstance(row, dict)]
    normalized_keyword_queries = [
        row for row in normalized_keyword_queries if str(row.get("query") or "").strip() and row.get("sku")
    ]

    if not query_ads_rows and normalized_keyword_queries:
        query_rows = normalized_keyword_queries
        query_source = "keyword_monitoring"
    else:
        query_rows = query_ads_rows
        query_source = "ads_rows"

    campaign_totals_rows = [row for row in normalized_ads if bool(row.get("is_campaign_total", False))]

    campaign_total_spend = sum(float(row.get("ad_spend") or 0.0) for row in campaign_totals_rows)
    row_spend = sum(float(row.get("ad_spend") or 0.0) for row in sku_ads_rows)

    return {
        "sku_metrics_index": _build_sku_metrics_index(metrics if isinstance(metrics, dict) else {}),
        "sku_ads_rows": sku_ads_rows,
        "query_rows": query_rows,
        "query_source": query_source,
        "campaign_total_spend": round(campaign_total_spend, 2),
        "rows_spend": round(row_spend, 2),
        "ads_rows_count": len(sku_ads_rows),
        "query_rows_count": len(query_rows),
    }
