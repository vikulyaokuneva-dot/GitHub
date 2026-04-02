"""Normalizer for search queries rows."""

from __future__ import annotations

from typing import Any

from modules.search_queries.reader import match_field_by_header


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


def _pick_value(row: dict[str, Any], field: str, recognized_columns: dict[str, str] | None) -> Any:
    if recognized_columns:
        header = recognized_columns.get(field)
        if header and header in row:
            return row.get(header)

    for key, value in row.items():
        detected = match_field_by_header(key)
        if detected == field:
            return value
    return None


def normalize_search_queries_rows(
    rows: list[dict[str, Any]],
    recognized_columns: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Normalize raw excel rows to unified schema."""
    normalized: list[dict[str, Any]] = []
    for row in rows:
        record = {
            "seller_sku": _to_str(_pick_value(row, "seller_sku", recognized_columns)),
            "wb_sku": _to_str(_pick_value(row, "wb_sku", recognized_columns)),
            "query": _to_str(_pick_value(row, "query", recognized_columns)),
            "query_count": _to_int(_pick_value(row, "query_count", recognized_columns)),
            "visibility_pct": round(_to_float(_pick_value(row, "visibility_pct", recognized_columns)), 4),
            "avg_position": round(_to_float(_pick_value(row, "avg_position", recognized_columns)), 4),
            "median_position": round(_to_float(_pick_value(row, "median_position", recognized_columns)), 4),
            "card_clicks": _to_int(_pick_value(row, "card_clicks", recognized_columns)),
            "add_to_cart": _to_int(_pick_value(row, "add_to_cart", recognized_columns)),
            "cart_conv_pct": round(_to_float(_pick_value(row, "cart_conv_pct", recognized_columns)), 4),
            "orders_count": _to_int(_pick_value(row, "orders_count", recognized_columns)),
            "order_conv_pct": round(_to_float(_pick_value(row, "order_conv_pct", recognized_columns)), 4),
            "price_min": round(_to_float(_pick_value(row, "price_min", recognized_columns)), 4),
            "price_max": round(_to_float(_pick_value(row, "price_max", recognized_columns)), 4),
        }
        if not record["query"]:
            # Query is a primary key-like field; skip empty lines.
            continue
        normalized.append(record)
    return normalized
