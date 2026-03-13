from __future__ import annotations

from typing import Any, Dict, List, Mapping

from .query_utils import append_warning_once, pick_first, safe_round, to_int_or_none

SKU_ALIASES = ("sku", "nm_id", "nmid", "offer_id", "product_id")
QUERY_ALIASES = (
    "query",
    "keyword",
    "search_query",
    "search_term",
    "phrase",
    "search_phrase",
    "key_phrase",
    "query_text",
)
IMPRESSIONS_ALIASES = ("impressions", "views", "shows")
CLICKS_ALIASES = ("clicks", "click")
ADD_TO_CART_ALIASES = ("add_to_cart", "carts", "cart_adds", "cart_add", "cart_count")
ORDERS_ALIASES = ("orders", "orders_count", "ordered_units")
BUYOUTS_ALIASES = ("buyouts", "sales", "buys", "buyout_units", "purchased_units")
SPEND_ALIASES = ("spend", "ads_spend", "ad_spend", "cost", "expenses")
AVG_POSITION_ALIASES = ("avg_position", "position_avg", "average_position", "position")
DATE_ALIASES = ("date", "day", "report_date")
PERIOD_ALIASES = ("period", "interval")


def _extract_rows(source: Any) -> List[Dict[str, Any]]:
    if isinstance(source, list):
        return [row for row in source if isinstance(row, dict)]
    if not isinstance(source, dict):
        return []

    for key in ("query_rows", "keyword_rows", "ads_rows", "items", "rows"):
        value = source.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def extract_keyword_rows(source: Any) -> Dict[str, Any]:
    rows = _extract_rows(source)
    warnings: List[Dict[str, Any]] = []

    query_rows: List[Dict[str, Any]] = []
    rows_without_query = 0
    rows_without_sku = 0

    for row in rows:
        if not isinstance(row, Mapping):
            continue

        sku = str(pick_first(row, SKU_ALIASES) or "").strip()
        query = str(pick_first(row, QUERY_ALIASES) or "").strip()

        if not sku:
            rows_without_sku += 1
            continue
        if not query:
            rows_without_query += 1
            continue

        item = {
            "sku": sku,
            "query": query,
            "impressions": to_int_or_none(pick_first(row, IMPRESSIONS_ALIASES)),
            "clicks": to_int_or_none(pick_first(row, CLICKS_ALIASES)),
            "add_to_cart": to_int_or_none(pick_first(row, ADD_TO_CART_ALIASES)),
            "orders": to_int_or_none(pick_first(row, ORDERS_ALIASES)),
            "buyouts": to_int_or_none(pick_first(row, BUYOUTS_ALIASES)),
            "spend": safe_round(pick_first(row, SPEND_ALIASES), 2),
            "avg_position": safe_round(pick_first(row, AVG_POSITION_ALIASES), 4),
            "date": str(pick_first(row, DATE_ALIASES) or "").strip() or None,
            "period": str(pick_first(row, PERIOD_ALIASES) or "").strip() or None,
        }
        query_rows.append(item)

    if not rows:
        append_warning_once(
            warnings,
            "keyword_source_rows_missing",
            "Keyword source rows are missing in the current daily input.",
        )
    if rows_without_query > 0:
        append_warning_once(
            warnings,
            "keyword_query_column_missing",
            f"Rows skipped without query value: {rows_without_query}.",
        )
    if rows_without_sku > 0:
        append_warning_once(
            warnings,
            "keyword_sku_missing",
            f"Rows skipped without SKU value: {rows_without_sku}.",
        )

    status = "ok"
    if not query_rows:
        status = "insufficient_data"
    elif rows_without_query > 0 or rows_without_sku > 0:
        status = "partial"

    return {
        "status": status,
        "warnings": warnings,
        "items": query_rows,
        "stats": {
            "rows_input": len(rows),
            "rows_with_query": len(query_rows),
            "rows_without_query": rows_without_query,
            "rows_without_sku": rows_without_sku,
        },
    }
