"""Facts builder for Ozon express audit MVP."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


COLUMN_HINTS: dict[str, tuple[str, ...]] = {
    "sku": ("sku", "Р°СЂС‚РёРєСѓР»", "offer id", "ozon sku", "id С‚РѕРІР°СЂР°"),
    "product_name": ("С‚РѕРІР°СЂ", "РЅР°РёРјРµРЅРѕРІР°РЅРёРµ", "name", "РЅР°Р·РІР°РЅРёРµ"),
    "orders": ("Р·Р°РєР°Р·", "Р·Р°РєР°Р·Р°РЅРѕ", "orders", "sales", "РїСЂРѕРґР°Р¶Рё", "С‚РѕРІР°СЂРѕРІ Р·Р°РєР°Р·Р°РЅРѕ", "quantity ordered"),
    "revenue": ("РІС‹СЂСѓС‡РєР°", "СЃСѓРјРјР°", "РЅР° СЃСѓРјРјСѓ", "revenue"),
    "buyouts": ("РІС‹РєСѓРї", "РґРѕСЃС‚Р°РІР»РµРЅРѕ", "purchased"),
    "cancellations": ("РѕС‚РјРµРЅ", "canceled", "РѕС‚РјРµРЅРµРЅРѕ"),
    "impressions": ("РїРѕРєР°Р·С‹", "impressions"),
    "visitors": ("РїРѕСЃРµС‚РёС‚РµР»", "visitors", "СѓРЅРёРєР°Р»СЊРЅС‹Рµ РїРѕСЃРµС‚РёС‚РµР»Рё"),
    "card_views": ("РїРѕСЃРµС‰РµРЅРёСЏ РєР°СЂС‚РѕС‡РєРё", "РїСЂРѕСЃРјРѕС‚СЂС‹ РєР°СЂС‚РѕС‡РєРё", "card views"),
    "add_to_cart": ("РІ РєРѕСЂР·РёРЅСѓ", "РґРѕР±Р°РІРёР»Рё РІ РєРѕСЂР·РёРЅСѓ", "add to cart"),
    "stock": ("РѕСЃС‚Р°С‚РѕРє", "stock", "РЅР° СЃРєР»Р°РґРµ"),
    "reviews": ("РѕС‚Р·С‹РІ", "reviews"),
    "price_index": ("РёРЅРґРµРєСЃ С†РµРЅ", "price index"),
    "drr": ("РґСЂСЂ",),
    "promotion_days": ("РґРЅРµР№ РїСЂРѕРґРІРёР¶РµРЅРёСЏ", "РґРЅРё РїСЂРѕРґРІРёР¶РµРЅРёСЏ", "РїСЂРѕРґРІРёР¶"),
    "promo_days": ("РґРЅРµР№ РІ Р°РєС†РёСЏС…", "РґРЅРё РІ Р°РєС†РёСЏС…", "Р°РєС†Рё"),
}


def _norm(text: Any) -> str:
    value = str(text or "").lower().replace("\xa0", " ").strip()
    value = value.replace("\n", " ").replace("\r", " ")
    value = re.sub(r"\s+", " ", value)
    return value


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, str):
            cleaned = value.replace(" ", "").replace(",", ".")
            return float(cleaned)
        return float(value)
    except Exception:
        return None


def _parse_int(value: Any) -> int | None:
    parsed = _parse_float(value)
    if parsed is None:
        return None
    try:
        return int(parsed)
    except Exception:
        return None


def _normalize_drr(value: Any) -> float | None:
    parsed = _parse_float(value)
    if parsed is None:
        return None
    if parsed > 1.5:
        return parsed / 100.0
    return parsed


def _find_column(columns: list[str], hints: tuple[str, ...]) -> str | None:
    scored: list[tuple[int, str]] = []
    for col in columns:
        col_norm = _norm(col)
        if not col_norm:
            continue
        score = 0
        for token in hints:
            tok = _norm(token)
            if not tok:
                continue
            if col_norm == tok:
                score += 120
            elif col_norm.startswith(tok):
                score += 25
            elif tok in col_norm:
                score += 12
        if score > 0:
            scored.append((score, col))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def _extract_columns(columns: list[str]) -> dict[str, str | None]:
    resolved = {name: _find_column(columns, hints) for name, hints in COLUMN_HINTS.items()}

    name_col = resolved.get("product_name")
    orders_col = resolved.get("orders")
    if name_col and orders_col and name_col == orders_col:
        resolved["product_name"] = None

    sku_col = resolved.get("sku")
    revenue_col = resolved.get("revenue")
    if sku_col and orders_col and sku_col == orders_col:
        sku_norm = _norm(sku_col)
        if "Р·Р°РєР°Р·" in sku_norm or "order" in sku_norm or "РїСЂРѕРґР°Р¶" in sku_norm or "sales" in sku_norm:
            resolved["sku"] = None
    if sku_col and revenue_col and sku_col == revenue_col:
        sku_norm = _norm(sku_col)
        if "РІС‹СЂСѓС‡" in sku_norm or "revenue" in sku_norm or "СЃСѓРјРј" in sku_norm:
            resolved["sku"] = None

    return resolved


def _label_from_row(row: dict[str, Any], detected: dict[str, str | None]) -> tuple[str, str]:
    sku_col = detected.get("sku")
    name_col = detected.get("product_name")
    sku = _text(row.get(sku_col)) if sku_col else ""
    name = _text(row.get(name_col)) if name_col else ""
    if sku:
        return sku, name
    if name:
        return name, name
    return "", ""


def _price_index_bucket(value: Any) -> str | None:
    text = _norm(value)
    if text:
        if "СЃСѓРїРµСЂ" in text and ("РІС‹РіРѕРґ" in text or "profit" in text):
            return "super_profitable"
        if "РІС‹РіРѕРґ" in text or "profitable" in text:
            return "profitable"
        if "neutral" in text or "РЅРµР№С‚СЂ" in text:
            return "neutral"
        if "РЅРµРІС‹РіРѕРґ" in text or "unprofit" in text:
            return "unprofitable"
    number = _parse_float(value)
    if number is None:
        return None
    if number < 0.9:
        return "super_profitable"
    if number <= 1.05:
        return "profitable"
    if number <= 1.2:
        return "neutral"
    return "unprofitable"


def _sum_or_none(values: list[float | None]) -> float | None:
    known = [x for x in values if x is not None]
    if not known:
        return None
    return float(sum(known))


def _build_assortment_summary(aggregated: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [x for x in aggregated if (x.get("revenue") or 0) > 0]
    if not rows:
        return {
            "top_5_revenue_share_pct": None,
            "top_10_revenue_share_pct": None,
            "sales_concentration_comment": "РќРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РґР°РЅРЅС‹С… РїРѕ РІС‹СЂСѓС‡РєРµ.",
        }
    rows = sorted(rows, key=lambda x: float(x.get("revenue") or 0.0), reverse=True)
    total = sum(float(x.get("revenue") or 0.0) for x in rows)
    if total <= 0:
        return {
            "top_5_revenue_share_pct": None,
            "top_10_revenue_share_pct": None,
            "sales_concentration_comment": "РќРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РґР°РЅРЅС‹С… РїРѕ РІС‹СЂСѓС‡РєРµ.",
        }
    top5 = sum(float(x.get("revenue") or 0.0) for x in rows[:5]) / total
    top10 = sum(float(x.get("revenue") or 0.0) for x in rows[:10]) / total
    if top10 >= 0.85 or top5 >= 0.7:
        comment = "РџСЂРѕРґР°Р¶Рё Р·Р°РјРµС‚РЅРѕ СЃРѕСЃСЂРµРґРѕС‚РѕС‡РµРЅС‹ РІ РѕРіСЂР°РЅРёС‡РµРЅРЅРѕРј С‡РёСЃР»Рµ SKU."
    elif top10 >= 0.65:
        comment = "РљРѕРЅС†РµРЅС‚СЂР°С†РёСЏ РїСЂРѕРґР°Р¶ СѓРјРµСЂРµРЅРЅР°СЏ."
    else:
        comment = "РџСЂРѕРґР°Р¶Рё СЂР°СЃРїСЂРµРґРµР»РµРЅС‹ РѕС‚РЅРѕСЃРёС‚РµР»СЊРЅРѕ СЂР°РІРЅРѕРјРµСЂРЅРѕ."
    return {
        "top_5_revenue_share_pct": round(top5 * 100.0, 2),
        "top_10_revenue_share_pct": round(top10 * 100.0, 2),
        "sales_concentration_comment": comment,
    }


def _build_abc_like_summary(aggregated: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [x for x in aggregated if (x.get("revenue") or 0) > 0 and x.get("label")]
    rows = sorted(rows, key=lambda x: float(x.get("revenue") or 0.0), reverse=True)
    total = sum(float(x.get("revenue") or 0.0) for x in rows)
    if total <= 0:
        return {
            "available": False,
            "counts": {"A": 0, "B": 0, "C": 0},
            "top_a": [],
        }
    counts = {"A": 0, "B": 0, "C": 0}
    top_a: list[str] = []
    cumulative = 0.0
    for row in rows:
        share = float(row.get("revenue") or 0.0) / total
        cumulative += share
        category = "A" if cumulative <= 0.80 else "B" if cumulative <= 0.95 else "C"
        counts[category] += 1
        if category == "A" and len(top_a) < 12:
            top_a.append(str(row.get("label")))
    return {
        "available": True,
        "counts": counts,
        "top_a": top_a,
    }


def build_ozon_facts(data: dict[str, Any]) -> dict[str, Any]:
    columns = [str(x) for x in (data.get("columns") or [])]
    rows = data.get("rows") or []
    if not isinstance(rows, list):
        rows = []

    diagnostics = data.get("diagnostics") if isinstance(data.get("diagnostics"), dict) else {}
    detected = _extract_columns(columns)

    parsed_rows: list[dict[str, Any]] = []
    aggregated_map: dict[str, dict[str, Any]] = {}

    for row in rows:
        if not isinstance(row, dict):
            continue
        label, product_name = _label_from_row(row, detected)
        if not label:
            continue

        item = {
            "label": label,
            "sku": _text(row.get(detected.get("sku"))) if detected.get("sku") else "",
            "name": product_name,
            "orders": _parse_int(row.get(detected.get("orders"))) if detected.get("orders") else None,
            "revenue": _parse_float(row.get(detected.get("revenue"))) if detected.get("revenue") else None,
            "buyouts": _parse_int(row.get(detected.get("buyouts"))) if detected.get("buyouts") else None,
            "cancellations": _parse_int(row.get(detected.get("cancellations"))) if detected.get("cancellations") else None,
            "stock": _parse_float(row.get(detected.get("stock"))) if detected.get("stock") else None,
            "reviews": _parse_float(row.get(detected.get("reviews"))) if detected.get("reviews") else None,
            "price_index_raw": row.get(detected.get("price_index")) if detected.get("price_index") else None,
            "price_index_bucket": _price_index_bucket(row.get(detected.get("price_index"))) if detected.get("price_index") else None,
            "drr": _normalize_drr(row.get(detected.get("drr"))) if detected.get("drr") else None,
            "impressions": _parse_float(row.get(detected.get("impressions"))) if detected.get("impressions") else None,
            "visitors": _parse_float(row.get(detected.get("visitors"))) if detected.get("visitors") else None,
            "card_views": _parse_float(row.get(detected.get("card_views"))) if detected.get("card_views") else None,
            "add_to_cart": _parse_float(row.get(detected.get("add_to_cart"))) if detected.get("add_to_cart") else None,
            "promotion_days": _parse_float(row.get(detected.get("promotion_days"))) if detected.get("promotion_days") else None,
            "promo_days": _parse_float(row.get(detected.get("promo_days"))) if detected.get("promo_days") else None,
        }
        parsed_rows.append(item)

        agg = aggregated_map.get(label)
        if agg is None:
            agg = {
                "label": label,
                "sku": item["sku"] or label,
                "name": item["name"],
                "orders": 0.0,
                "revenue": 0.0,
                "buyouts": 0.0,
                "cancellations": 0.0,
                "stock": 0.0,
                "reviews": 0.0,
                "price_index_bucket": None,
                "drr_max": None,
                "promotion_days": 0.0,
                "promo_days": 0.0,
            }
            aggregated_map[label] = agg

        if item["orders"] is not None:
            agg["orders"] += float(item["orders"])
        if item["revenue"] is not None:
            agg["revenue"] += float(item["revenue"])
        if item["buyouts"] is not None:
            agg["buyouts"] += float(item["buyouts"])
        if item["cancellations"] is not None:
            agg["cancellations"] += float(item["cancellations"])
        if item["stock"] is not None:
            agg["stock"] += float(item["stock"])
        if item["reviews"] is not None:
            agg["reviews"] += float(item["reviews"])
        if item["price_index_bucket"] == "unprofitable":
            agg["price_index_bucket"] = "unprofitable"
        elif agg["price_index_bucket"] is None and item["price_index_bucket"] is not None:
            agg["price_index_bucket"] = item["price_index_bucket"]
        if item["drr"] is not None:
            if agg["drr_max"] is None or float(item["drr"]) > float(agg["drr_max"]):
                agg["drr_max"] = float(item["drr"])
        if item["promotion_days"] is not None:
            agg["promotion_days"] += float(item["promotion_days"])
        if item["promo_days"] is not None:
            agg["promo_days"] += float(item["promo_days"])

    aggregated = list(aggregated_map.values())
    sku_count = len(aggregated)
    has_orders = bool(detected.get("orders"))

    sku_with_orders_count = None
    sku_without_orders_count = None
    total_orders = None
    if has_orders:
        sku_with_orders_count = len([x for x in aggregated if float(x.get("orders") or 0.0) > 0])
        sku_without_orders_count = len([x for x in aggregated if float(x.get("orders") or 0.0) <= 0])
        total_orders = int(sum(float(x.get("orders") or 0.0) for x in aggregated))

    total_revenue = _sum_or_none([float(x.get("revenue")) for x in aggregated]) if detected.get("revenue") else None
    total_buyouts = _sum_or_none([float(x.get("buyouts")) for x in aggregated]) if detected.get("buyouts") else None
    total_cancellations = _sum_or_none([float(x.get("cancellations")) for x in aggregated]) if detected.get("cancellations") else None
    total_stock = _sum_or_none([float(x.get("stock")) for x in aggregated]) if detected.get("stock") else None
    total_reviews = _sum_or_none([float(x.get("reviews")) for x in aggregated]) if detected.get("reviews") else None

    funnel_summary = {
        "total_impressions": _sum_or_none([x.get("impressions") for x in parsed_rows]) if detected.get("impressions") else None,
        "total_visitors": _sum_or_none([x.get("visitors") for x in parsed_rows]) if detected.get("visitors") else None,
        "total_card_views": _sum_or_none([x.get("card_views") for x in parsed_rows]) if detected.get("card_views") else None,
        "total_add_to_cart": _sum_or_none([x.get("add_to_cart") for x in parsed_rows]) if detected.get("add_to_cart") else None,
    }

    assortment_summary = _build_assortment_summary(aggregated)
    abc_like_summary = _build_abc_like_summary(aggregated)

    price_counts = defaultdict(int)
    for row in parsed_rows:
        bucket = row.get("price_index_bucket")
        if bucket:
            price_counts[str(bucket)] += 1
    price_index_summary = {
        "super_profitable": int(price_counts.get("super_profitable", 0)),
        "profitable": int(price_counts.get("profitable", 0)),
        "neutral": int(price_counts.get("neutral", 0)),
        "unprofitable": int(price_counts.get("unprofitable", 0)),
    }

    drr_rows = [x for x in aggregated if x.get("drr_max") is not None]
    drr_rows_sorted = sorted(drr_rows, key=lambda x: float(x.get("drr_max") or 0.0), reverse=True)
    promotion_summary = {
        "promoted_sku_count": len(
            [
                x
                for x in aggregated
                if float(x.get("promotion_days") or 0.0) > 0
                or float(x.get("promo_days") or 0.0) > 0
                or x.get("drr_max") is not None
            ]
        ),
        "sku_with_drr_count": len(drr_rows),
        "avg_drr": round(sum(float(x.get("drr_max") or 0.0) for x in drr_rows) / len(drr_rows), 4) if drr_rows else None,
        "max_drr": round(float(drr_rows_sorted[0].get("drr_max")), 4) if drr_rows_sorted else None,
        "top_drr_sku": [
            {
                "label": x.get("label"),
                "sku": x.get("sku"),
                "name": x.get("name"),
                "drr": round(float(x.get("drr_max") or 0.0), 4),
            }
            for x in drr_rows_sorted[:5]
        ],
    }

    top_source = "revenue" if detected.get("revenue") else "orders"
    top_rows = sorted(aggregated, key=lambda x: float(x.get(top_source) or 0.0), reverse=True)
    top_sku = [
        {
            "label": x.get("label"),
            "sku": x.get("sku"),
            "name": x.get("name"),
            "orders": int(float(x.get("orders") or 0.0)) if has_orders else None,
            "revenue": round(float(x.get("revenue") or 0.0), 2) if detected.get("revenue") else None,
            "stock": round(float(x.get("stock") or 0.0), 2) if detected.get("stock") else None,
            "drr": round(float(x.get("drr_max") or 0.0), 4) if x.get("drr_max") is not None else None,
            "price_index_bucket": x.get("price_index_bucket"),
        }
        for x in top_rows[:10]
        if x.get("label")
    ]

    problem_sku: list[dict[str, Any]] = []
    for row in aggregated:
        label = row.get("label")
        if not label:
            continue
        orders = float(row.get("orders") or 0.0)
        stock = float(row.get("stock") or 0.0)
        cancellations = float(row.get("cancellations") or 0.0)
        buyouts = float(row.get("buyouts") or 0.0)
        drr = row.get("drr_max")
        price_bucket = row.get("price_index_bucket")

        if has_orders and detected.get("stock") and orders <= 0 and stock > 0:
            problem_sku.append(
                {
                    "type": "no_orders_with_stock",
                    "label": label,
                    "sku": row.get("sku"),
                    "name": row.get("name"),
                    "orders": int(orders),
                    "stock": round(stock, 2),
                    "reason": "Р±РµР· Р·Р°РєР°Р·РѕРІ, РЅРѕ СЃ РѕСЃС‚Р°С‚РєРѕРј",
                }
            )

        denom = max(orders, buyouts)
        cancel_share = (cancellations / denom) if denom > 0 else None
        if detected.get("cancellations") and cancel_share is not None and cancellations >= 3 and cancel_share >= 0.30:
            problem_sku.append(
                {
                    "type": "high_cancellation_share",
                    "label": label,
                    "sku": row.get("sku"),
                    "name": row.get("name"),
                    "cancellations": int(cancellations),
                    "cancel_share_pct": round(cancel_share * 100.0, 2),
                    "reason": "РІС‹СЃРѕРєР°СЏ РґРѕР»СЏ РѕС‚РјРµРЅ",
                }
            )

        if drr is not None and float(drr) > 0.25:
            problem_sku.append(
                {
                    "type": "high_drr",
                    "label": label,
                    "sku": row.get("sku"),
                    "name": row.get("name"),
                    "drr_pct": round(float(drr) * 100.0, 2),
                    "reason": "РІС‹СЃРѕРєРёР№ Р”Р Р ",
                }
            )

        if has_orders and orders > 0 and price_bucket == "unprofitable":
            problem_sku.append(
                {
                    "type": "bad_price_index_on_selling",
                    "label": label,
                    "sku": row.get("sku"),
                    "name": row.get("name"),
                    "orders": int(orders),
                    "reason": "РїСЂРѕРґР°РµС‚СЃСЏ, РЅРѕ РёРЅРґРµРєСЃ С†РµРЅС‹ РЅРµРІС‹РіРѕРґРЅС‹Р№",
                }
            )

    summary = {
        "row_count": int(data.get("row_count") or 0),
        "sku_count": int(sku_count),
        "sku_with_orders_count": int(sku_with_orders_count or 0) if has_orders else None,
        "sku_without_orders_count": int(sku_without_orders_count or 0) if has_orders else None,
        "total_orders": int(total_orders or 0) if has_orders else None,
        "total_revenue": round(float(total_revenue), 2) if total_revenue is not None else None,
        "total_buyouts": int(total_buyouts or 0) if total_buyouts is not None else None,
        "total_cancellations": int(total_cancellations or 0) if total_cancellations is not None else None,
        "total_stock": round(float(total_stock), 2) if total_stock is not None else None,
        "total_reviews": round(float(total_reviews), 2) if total_reviews is not None else None,
    }

    return {
        "summary": summary,
        "funnel_summary": funnel_summary,
        "assortment_summary": assortment_summary,
        "price_index_summary": price_index_summary,
        "promotion_summary": promotion_summary,
        "abc_like_summary": abc_like_summary,
        "top_sku": top_sku,
        "problem_sku": problem_sku[:40],
        "detected_columns": detected,
        "chosen_sheet": diagnostics.get("chosen_sheet"),
        "chosen_header_row": diagnostics.get("chosen_header_row"),
        "row_count": int(data.get("row_count") or 0),
        "parse_candidates": diagnostics.get("parse_candidates") or [],
        "data_quality": {
            "has_orders": bool(detected.get("orders")),
            "has_revenue": bool(detected.get("revenue")),
            "has_stock": bool(detected.get("stock")),
            "has_drr": bool(detected.get("drr")),
            "has_price_index": bool(detected.get("price_index")),
            "has_cancellations": bool(detected.get("cancellations")),
            "has_buyouts": bool(detected.get("buyouts")),
            "has_impressions": bool(detected.get("impressions")),
            "has_visitors": bool(detected.get("visitors")),
            "has_add_to_cart": bool(detected.get("add_to_cart")),
            "row_count": int(data.get("row_count") or 0),
        },
        "period_hint": diagnostics.get("period_hint") or {"status": "unknown", "label": "РїРµСЂРёРѕРґ РЅРµ СЂР°СЃРїРѕР·РЅР°РЅ Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРё"},
    }
