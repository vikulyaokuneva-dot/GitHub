"""Normalizer for search queries rows."""

from __future__ import annotations

from typing import Any

from modules.search_queries.reader import HEADER_ALIASES


def _to_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("%", "").replace(" ", "").replace(",", ".")
    if text == "":
        return 0.0
    try:
        return float(text)
    except Exception:
        return 0.0


def _to_int(value: Any) -> int:
    try:
        return int(round(_to_float(value)))
    except Exception:
        return 0


def _pick_value(row: dict[str, Any], field: str) -> Any:
    aliases = HEADER_ALIASES.get(field, ())
    for alias in aliases:
        if alias in row:
            return row.get(alias)
    return None


def normalize_search_queries_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize raw excel rows to unified schema."""
    normalized: list[dict[str, Any]] = []
    for row in rows:
        record = {
            "seller_sku": _to_str(_pick_value(row, "seller_sku")),
            "wb_sku": _to_str(_pick_value(row, "wb_sku")),
            "query": _to_str(_pick_value(row, "query")),
            "query_count": _to_int(_pick_value(row, "query_count")),
            "visibility_pct": round(_to_float(_pick_value(row, "visibility_pct")), 4),
            "avg_position": round(_to_float(_pick_value(row, "avg_position")), 4),
            "median_position": round(_to_float(_pick_value(row, "median_position")), 4),
            "card_clicks": _to_int(_pick_value(row, "card_clicks")),
            "add_to_cart": _to_int(_pick_value(row, "add_to_cart")),
            "cart_conv_pct": round(_to_float(_pick_value(row, "cart_conv_pct")), 4),
            "orders_count": _to_int(_pick_value(row, "orders_count")),
            "order_conv_pct": round(_to_float(_pick_value(row, "order_conv_pct")), 4),
            "price_min": round(_to_float(_pick_value(row, "price_min")), 4),
            "price_max": round(_to_float(_pick_value(row, "price_max")), 4),
        }
        if not record["query"]:
            # Query is a primary key-like field; skip empty lines.
            continue
        normalized.append(record)
    return normalized

