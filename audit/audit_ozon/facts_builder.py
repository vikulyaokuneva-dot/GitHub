"""Facts builder for Ozon express audit."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


COLUMN_HINTS: dict[str, tuple[str, ...]] = {
    "sku": ("sku", "артикул", "offer id", "ozon sku", "id товара", "товар"),
    "product_name": ("наименование", "название", "name", "товар"),
    "orders": ("заказ", "заказано", "orders", "sales", "продажи", "товаров заказано", "quantity ordered"),
    "revenue": ("выручка", "сумма", "на сумму", "revenue"),
    "buyouts": ("выкуп", "доставлено", "purchased"),
    "cancellations": ("отмен", "canceled", "отменено"),
    "stock": ("остаток", "stock", "на складе"),
    "reviews": ("отзыв", "reviews"),
    "price_index": ("индекс цен", "price index"),
    "drr": ("дрр",),
    "spend": ("расход", "затраты", "спенд", "spend", "реклам", "promotion cost"),
    "impressions": ("показы", "impressions"),
    "visitors": ("посетител", "visitors", "уникальные посетители"),
    "card_views": ("посещения карточки", "просмотры карточки", "card views"),
    "add_to_cart": ("в корзину", "добавили в корзину", "add to cart"),
    "promotion_days": ("дней продвижения", "дни продвижения", "продвиж"),
    "promo_days": ("дней в акциях", "дни в акциях", "акци"),
}


def _norm(text: Any) -> str:
    value = str(text or "").lower().replace("\xa0", " ").strip()
    value = value.replace("\n", " ").replace("\r", " ")
    return " ".join(value.split())


def _text(value: Any) -> str:
    return str(value or "").strip()


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        raw = value.replace("\xa0", " ").strip()
        if raw in {"", "-", "—", "–", "nan", "None"}:
            return None
        cleaned = raw.replace("%", "").replace(" ", "").replace(",", ".")
        try:
            return float(cleaned)
        except Exception:
            return None
    try:
        return float(value)
    except Exception:
        return None


def _parse_int(value: Any) -> int | None:
    parsed = _parse_float(value)
    if parsed is None:
        return None
    try:
        return int(round(parsed))
    except Exception:
        return None


def _normalize_ratio(value: Any) -> float | None:
    parsed = _parse_float(value)
    if parsed is None:
        return None
    if parsed < 0:
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
        for hint in hints:
            token = _norm(hint)
            if not token:
                continue
            if col_norm == token:
                score += 120
            elif col_norm.startswith(token):
                score += 25
            elif token in col_norm:
                score += 12
        if score > 0:
            scored.append((score, col))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def _extract_columns(columns: list[str]) -> dict[str, str | None]:
    resolved = {name: _find_column(columns, hints) for name, hints in COLUMN_HINTS.items()}
    if resolved.get("sku") and resolved.get("sku") == resolved.get("orders"):
        resolved["sku"] = None
    if resolved.get("product_name") and resolved.get("product_name") == resolved.get("orders"):
        resolved["product_name"] = None
    return resolved


def _price_index_bucket(value: Any) -> str | None:
    text = _norm(value)
    if text:
        if "супер" in text and ("выгод" in text or "profit" in text):
            return "super_profitable"
        if "невыгод" in text or "unprofit" in text:
            return "unprofitable"
        if "выгод" in text or "profitable" in text:
            return "profitable"
        if "neutral" in text or "нейтрал" in text:
            return "neutral"

    num = _parse_float(value)
    if num is None:
        return None
    if num <= 0.95:
        return "super_profitable"
    if num <= 1.05:
        return "profitable"
    if num <= 1.2:
        return "neutral"
    return "unprofitable"


def _safe_sum(values: list[float | None]) -> float | None:
    known = [x for x in values if x is not None]
    if not known:
        return None
    return float(sum(known))


def _build_abc_analysis(rows: list[dict[str, Any]], has_orders: bool) -> dict[str, Any]:
    eligible = [x for x in rows if float(x.get("revenue") or 0.0) > 0 and x.get("label")]
    if has_orders:
        eligible = [x for x in eligible if float(x.get("orders") or 0.0) > 0]

    eligible = sorted(eligible, key=lambda x: float(x.get("revenue") or 0.0), reverse=True)
    total_revenue = sum(float(x.get("revenue") or 0.0) for x in eligible)
    groups: dict[str, list[dict[str, Any]]] = {"A": [], "B": [], "C": []}

    if total_revenue <= 0:
        return {
            "available": False,
            "A": [],
            "B": [],
            "C": [],
            "summary": {
                "a_revenue_share_pct": None,
                "b_revenue_share_pct": None,
                "c_revenue_share_pct": None,
                "counts": {"A": 0, "B": 0, "C": 0},
                "concentration_comment": "Недостаточно данных по выручке для ABC-анализа.",
            },
        }

    cumulative = 0.0
    for row in eligible:
        revenue = float(row.get("revenue") or 0.0)
        share = revenue / total_revenue
        cumulative_after = cumulative + share
        if cumulative_after <= 0.80 or not groups["A"]:
            category = "A"
        elif cumulative_after <= 0.95 or not groups["B"]:
            category = "B"
        else:
            category = "C"
        groups[category].append(
            {
                "label": row.get("label"),
                "sku": row.get("sku"),
                "orders": int(float(row.get("orders") or 0.0)),
                "revenue": round(revenue, 2),
                "share_pct": round(share * 100.0, 2),
                "cum_share_pct": round(cumulative_after * 100.0, 2),
            }
        )
        cumulative = cumulative_after

    revenue_by_group = {
        "A": sum(float(x.get("revenue") or 0.0) for x in groups["A"]),
        "B": sum(float(x.get("revenue") or 0.0) for x in groups["B"]),
        "C": sum(float(x.get("revenue") or 0.0) for x in groups["C"]),
    }
    shares = {
        k: round((v / total_revenue) * 100.0, 2) if total_revenue > 0 else None for k, v in revenue_by_group.items()
    }

    a_count = len(groups["A"])
    a_share = float(shares.get("A") or 0.0)
    if a_count <= 5 and a_share >= 50:
        concentration_comment = f"Выручка концентрирована: группа A включает {a_count} SKU и дает {a_share:.1f}% оборота."
    elif a_count <= 10 and a_share >= 45:
        concentration_comment = f"Концентрация выручки умеренно высокая: {a_count} SKU группы A дают {a_share:.1f}%."
    else:
        concentration_comment = f"Концентрация выручки умеренная: группа A дает {a_share:.1f}% при {a_count} SKU."

    return {
        "available": True,
        "A": groups["A"],
        "B": groups["B"],
        "C": groups["C"],
        "summary": {
            "a_revenue_share_pct": shares["A"],
            "b_revenue_share_pct": shares["B"],
            "c_revenue_share_pct": shares["C"],
            "counts": {"A": len(groups["A"]), "B": len(groups["B"]), "C": len(groups["C"])},
            "concentration_comment": concentration_comment,
        },
    }


def _build_key_findings(
    *,
    sku_count: int,
    sku_without_orders_count: int | None,
    assortment_summary: dict[str, Any],
    abc_summary: dict[str, Any],
    price_index_summary: dict[str, Any],
    promotion_summary: dict[str, Any],
    suspicious_count: int,
) -> list[str]:
    findings: list[str] = []

    top5_share = assortment_summary.get("top_5_revenue_share_pct")
    if top5_share is not None:
        findings.append(
            f"5 SKU формируют {float(top5_share):.1f}% выручки -> зависимость оборота от ограниченного ядра ассортимента."
        )

    if sku_without_orders_count is not None and sku_count > 0:
        share = (float(sku_without_orders_count) / float(sku_count)) * 100.0
        findings.append(
            f"SKU без заказов: {sku_without_orders_count} из {sku_count} ({share:.1f}%) -> значимая часть ассортимента не участвует в обороте."
        )

    a_share = abc_summary.get("a_revenue_share_pct")
    a_count = (abc_summary.get("counts") or {}).get("A")
    if a_share is not None and a_count is not None:
        findings.append(
            f"ABC: группа A ({int(a_count)} SKU) дает {float(a_share):.1f}% выручки -> приоритет управления должен быть на SKU ядра."
        )

    unprofitable = int(price_index_summary.get("unprofitable") or 0)
    if unprofitable > 0:
        findings.append(
            f"{unprofitable} SKU имеют невыгодный индекс цены -> риск потери маржи на продающих позициях."
        )

    critical_drr = int(promotion_summary.get("critical_drr_count") or 0)
    high_drr = int(promotion_summary.get("high_drr_count") or 0)
    if critical_drr > 0:
        findings.append(
            f"{critical_drr} SKU тратят на рекламу более 30% выручки -> высокая вероятность убыточного продвижения."
        )
    elif high_drr > 0:
        findings.append(
            f"{high_drr} SKU имеют ДРР выше 25% -> рекламная модель требует пересчета ставок и целевой маржи."
        )

    if suspicious_count > 0:
        findings.append(
            f"Обнаружены {suspicious_count} SKU с выручкой без заказов -> выгрузка требует сверки перед финальными решениями."
        )

    return findings[:7]


def build_ozon_facts(data: dict[str, Any]) -> dict[str, Any]:
    columns = [str(x) for x in (data.get("columns") or [])]
    rows = data.get("rows") if isinstance(data.get("rows"), list) else []
    diagnostics = data.get("diagnostics") if isinstance(data.get("diagnostics"), dict) else {}

    detected = _extract_columns(columns)
    has_orders = bool(detected.get("orders"))
    has_revenue = bool(detected.get("revenue"))
    has_stock = bool(detected.get("stock"))
    has_buyouts = bool(detected.get("buyouts"))
    has_cancellations = bool(detected.get("cancellations"))
    has_spend = bool(detected.get("spend"))

    parsed_rows: list[dict[str, Any]] = []
    aggregated_map: dict[str, dict[str, Any]] = {}

    for row in rows:
        if not isinstance(row, dict):
            continue

        sku_col = detected.get("sku")
        name_col = detected.get("product_name")
        sku = _text(row.get(sku_col)) if sku_col else ""
        product_name = _text(row.get(name_col)) if name_col else ""
        label = sku or product_name
        if not label:
            continue

        orders = _parse_int(row.get(detected.get("orders"))) if detected.get("orders") else None
        revenue = _parse_float(row.get(detected.get("revenue"))) if detected.get("revenue") else None
        buyouts = _parse_int(row.get(detected.get("buyouts"))) if detected.get("buyouts") else None
        cancellations = _parse_int(row.get(detected.get("cancellations"))) if detected.get("cancellations") else None
        stock = _parse_float(row.get(detected.get("stock"))) if detected.get("stock") else None
        reviews = _parse_float(row.get(detected.get("reviews"))) if detected.get("reviews") else None
        spend = _parse_float(row.get(detected.get("spend"))) if detected.get("spend") else None
        drr_raw = _normalize_ratio(row.get(detected.get("drr"))) if detected.get("drr") else None
        drr_active = drr_raw if spend is not None and spend > 0 else None

        parsed = {
            "label": label,
            "sku": sku or label,
            "name": product_name,
            "orders": orders,
            "revenue": revenue,
            "buyouts": buyouts,
            "cancellations": cancellations,
            "stock": stock,
            "reviews": reviews,
            "spend": spend,
            "drr_raw": drr_raw,
            "drr_active": drr_active,
            "price_index_bucket": _price_index_bucket(row.get(detected.get("price_index"))) if detected.get("price_index") else None,
            "impressions": _parse_float(row.get(detected.get("impressions"))) if detected.get("impressions") else None,
            "visitors": _parse_float(row.get(detected.get("visitors"))) if detected.get("visitors") else None,
            "card_views": _parse_float(row.get(detected.get("card_views"))) if detected.get("card_views") else None,
            "add_to_cart": _parse_float(row.get(detected.get("add_to_cart"))) if detected.get("add_to_cart") else None,
            "promotion_days": _parse_float(row.get(detected.get("promotion_days"))) if detected.get("promotion_days") else None,
            "promo_days": _parse_float(row.get(detected.get("promo_days"))) if detected.get("promo_days") else None,
        }
        parsed_rows.append(parsed)

        agg = aggregated_map.get(label)
        if agg is None:
            agg = {
                "label": label,
                "sku": sku or label,
                "name": product_name,
                "orders": 0.0,
                "revenue": 0.0,
                "buyouts": 0.0,
                "cancellations": 0.0,
                "stock": 0.0,
                "reviews": 0.0,
                "spend": 0.0,
                "impressions": 0.0,
                "visitors": 0.0,
                "card_views": 0.0,
                "add_to_cart": 0.0,
                "promotion_days": 0.0,
                "promo_days": 0.0,
                "price_index_bucket": None,
                "drr_active_values": [],
            }
            aggregated_map[label] = agg

        if orders is not None:
            agg["orders"] += float(max(orders, 0))
        if revenue is not None:
            agg["revenue"] += float(max(revenue, 0.0))
        if buyouts is not None:
            agg["buyouts"] += float(max(buyouts, 0))
        if cancellations is not None:
            agg["cancellations"] += float(max(cancellations, 0))
        if stock is not None:
            agg["stock"] += float(max(stock, 0.0))
        if reviews is not None:
            agg["reviews"] += float(max(reviews, 0.0))
        if spend is not None and spend > 0:
            agg["spend"] += float(spend)
        if parsed["impressions"] is not None:
            agg["impressions"] += float(max(parsed["impressions"], 0.0))
        if parsed["visitors"] is not None:
            agg["visitors"] += float(max(parsed["visitors"], 0.0))
        if parsed["card_views"] is not None:
            agg["card_views"] += float(max(parsed["card_views"], 0.0))
        if parsed["add_to_cart"] is not None:
            agg["add_to_cart"] += float(max(parsed["add_to_cart"], 0.0))
        if parsed["promotion_days"] is not None:
            agg["promotion_days"] += float(max(parsed["promotion_days"], 0.0))
        if parsed["promo_days"] is not None:
            agg["promo_days"] += float(max(parsed["promo_days"], 0.0))

        bucket = parsed["price_index_bucket"]
        if bucket == "unprofitable":
            agg["price_index_bucket"] = "unprofitable"
        elif agg["price_index_bucket"] is None and bucket is not None:
            agg["price_index_bucket"] = bucket

        if drr_active is not None:
            casted = agg.get("drr_active_values")
            if isinstance(casted, list):
                casted.append(float(drr_active))

    aggregated = list(aggregated_map.values())
    sku_count = len(aggregated)

    for item in aggregated:
        drr_values = item.get("drr_active_values") if isinstance(item.get("drr_active_values"), list) else []
        item["drr"] = (sum(drr_values) / len(drr_values)) if drr_values else None

    sku_with_orders_count = len([x for x in aggregated if float(x.get("orders") or 0.0) > 0]) if has_orders else None
    sku_without_orders_count = len([x for x in aggregated if float(x.get("orders") or 0.0) <= 0]) if has_orders else None
    total_orders = int(sum(float(x.get("orders") or 0.0) for x in aggregated)) if has_orders else None
    total_revenue = _safe_sum([float(x.get("revenue")) for x in aggregated]) if has_revenue else None
    total_buyouts = _safe_sum([float(x.get("buyouts")) for x in aggregated]) if has_buyouts else None
    total_cancellations = _safe_sum([float(x.get("cancellations")) for x in aggregated]) if has_cancellations else None
    total_stock = _safe_sum([float(x.get("stock")) for x in aggregated]) if has_stock else None
    total_reviews = _safe_sum([float(x.get("reviews")) for x in aggregated]) if detected.get("reviews") else None

    suspicious_revenue_without_orders: list[dict[str, Any]] = []
    for item in aggregated:
        if has_orders and has_revenue and float(item.get("orders") or 0.0) <= 0 and float(item.get("revenue") or 0.0) > 0:
            suspicious_revenue_without_orders.append(
                {
                    "label": item.get("label"),
                    "sku": item.get("sku"),
                    "orders": int(float(item.get("orders") or 0.0)),
                    "revenue": round(float(item.get("revenue") or 0.0), 2),
                }
            )

    if has_revenue:
        top_pool = [x for x in aggregated if float(x.get("revenue") or 0.0) > 0]
        if has_orders:
            top_pool = [x for x in top_pool if float(x.get("orders") or 0.0) > 0]
        top_rows = sorted(top_pool, key=lambda x: float(x.get("revenue") or 0.0), reverse=True)
    elif has_orders:
        top_pool = [x for x in aggregated if float(x.get("orders") or 0.0) > 0]
        top_rows = sorted(top_pool, key=lambda x: float(x.get("orders") or 0.0), reverse=True)
    else:
        top_rows = []

    top_sku = [
        {
            "label": x.get("label"),
            "sku": x.get("sku"),
            "name": x.get("name"),
            "orders": int(float(x.get("orders") or 0.0)) if has_orders else None,
            "revenue": round(float(x.get("revenue") or 0.0), 2) if has_revenue else None,
            "stock": round(float(x.get("stock") or 0.0), 2) if has_stock else None,
            "ad_spend": round(float(x.get("spend") or 0.0), 2) if has_spend else None,
            "drr": round(float(x.get("drr") or 0.0), 4) if x.get("drr") is not None else None,
            "price_index_bucket": x.get("price_index_bucket"),
        }
        for x in top_rows[:10]
        if x.get("label")
    ]

    abc_analysis = _build_abc_analysis(aggregated, has_orders=has_orders)
    abc_summary = abc_analysis.get("summary") if isinstance(abc_analysis.get("summary"), dict) else {}

    assortment_summary = {
        "top_5_revenue_share_pct": None,
        "top_10_revenue_share_pct": None,
        "sales_concentration_comment": "Недостаточно данных по выручке.",
    }
    revenue_rows = [x for x in aggregated if float(x.get("revenue") or 0.0) > 0]
    if has_revenue and revenue_rows:
        if has_orders:
            revenue_rows = [x for x in revenue_rows if float(x.get("orders") or 0.0) > 0]
        revenue_rows = sorted(revenue_rows, key=lambda x: float(x.get("revenue") or 0.0), reverse=True)
        total_rev = sum(float(x.get("revenue") or 0.0) for x in revenue_rows)
        if total_rev > 0:
            top5_share = sum(float(x.get("revenue") or 0.0) for x in revenue_rows[:5]) / total_rev
            top10_share = sum(float(x.get("revenue") or 0.0) for x in revenue_rows[:10]) / total_rev
            if top10_share >= 0.85 or top5_share >= 0.70:
                comment = f"Выручка концентрирована: top-10 SKU дают {top10_share * 100:.1f}% оборота."
            elif top10_share >= 0.65:
                comment = f"Концентрация выручки умеренная: top-10 SKU дают {top10_share * 100:.1f}%."
            else:
                comment = f"Выручка распределена относительно равномерно: top-10 SKU дают {top10_share * 100:.1f}%."
            assortment_summary = {
                "top_5_revenue_share_pct": round(top5_share * 100.0, 2),
                "top_10_revenue_share_pct": round(top10_share * 100.0, 2),
                "sales_concentration_comment": comment,
            }

    price_counts = defaultdict(int)
    for row in aggregated:
        bucket = row.get("price_index_bucket")
        if bucket:
            price_counts[str(bucket)] += 1
    price_index_summary = {
        "super_profitable": int(price_counts.get("super_profitable", 0)),
        "profitable": int(price_counts.get("profitable", 0)),
        "neutral": int(price_counts.get("neutral", 0)),
        "unprofitable": int(price_counts.get("unprofitable", 0)),
    }

    ad_active_rows = [x for x in aggregated if float(x.get("spend") or 0.0) > 0]
    drr_active_rows = [x for x in ad_active_rows if x.get("drr") is not None]
    drr_sorted = sorted(drr_active_rows, key=lambda x: float(x.get("drr") or 0.0), reverse=True)
    revenue_with_ads = sum(float(x.get("revenue") or 0.0) for x in ad_active_rows)

    promotion_summary = {
        "sku_with_ads_count": len(ad_active_rows),
        "sku_without_ads_count": max(sku_count - len(ad_active_rows), 0),
        "ads_sku_share_pct": round((len(ad_active_rows) / sku_count) * 100.0, 2) if sku_count > 0 else None,
        "revenue_with_ads_share_pct": round((revenue_with_ads / total_revenue) * 100.0, 2) if total_revenue and total_revenue > 0 else None,
        "sku_with_drr_count": len(drr_active_rows),
        "avg_drr_active": round(sum(float(x.get("drr") or 0.0) for x in drr_active_rows) / len(drr_active_rows), 4) if drr_active_rows else None,
        "max_drr_active": round(float(drr_sorted[0].get("drr")), 4) if drr_sorted else None,
        "high_drr_count": len([x for x in drr_active_rows if float(x.get("drr") or 0.0) > 0.25]),
        "critical_drr_count": len([x for x in drr_active_rows if float(x.get("drr") or 0.0) > 0.30]),
        "top_drr_sku": [
            {
                "label": x.get("label"),
                "sku": x.get("sku"),
                "drr_pct": round(float(x.get("drr") or 0.0) * 100.0, 2),
                "ad_spend": round(float(x.get("spend") or 0.0), 2),
                "revenue": round(float(x.get("revenue") or 0.0), 2),
            }
            for x in drr_sorted[:10]
        ],
    }

    funnel_summary = {
        "total_impressions": _safe_sum([x.get("impressions") for x in parsed_rows]) if detected.get("impressions") else None,
        "total_visitors": _safe_sum([x.get("visitors") for x in parsed_rows]) if detected.get("visitors") else None,
        "total_card_views": _safe_sum([x.get("card_views") for x in parsed_rows]) if detected.get("card_views") else None,
        "total_add_to_cart": _safe_sum([x.get("add_to_cart") for x in parsed_rows]) if detected.get("add_to_cart") else None,
    }

    problem_sku: list[dict[str, Any]] = []
    for row in aggregated:
        label = row.get("label")
        if not label:
            continue
        orders = float(row.get("orders") or 0.0)
        stock = float(row.get("stock") or 0.0)
        revenue = float(row.get("revenue") or 0.0)
        cancellations = float(row.get("cancellations") or 0.0)
        buyouts = float(row.get("buyouts") or 0.0)
        drr = row.get("drr")
        spend = float(row.get("spend") or 0.0)
        price_bucket = row.get("price_index_bucket")

        if has_orders and has_stock and orders <= 0 and stock > 0:
            problem_sku.append(
                {
                    "type": "no_orders_with_stock",
                    "label": label,
                    "sku": row.get("sku"),
                    "orders": int(orders),
                    "stock": round(stock, 2),
                    "reason": "Есть остаток при нулевых заказах -> деньги заморожены в неликвиде.",
                }
            )

        if has_orders and has_revenue and orders <= 0 and revenue > 0:
            problem_sku.append(
                {
                    "type": "suspicious_revenue_without_orders",
                    "label": label,
                    "sku": row.get("sku"),
                    "orders": int(orders),
                    "revenue": round(revenue, 2),
                    "reason": "Выручка есть, а заказов нет -> требуется проверка выгрузки.",
                }
            )

        denom = max(orders, buyouts)
        cancel_share = (cancellations / denom) if denom > 0 else None
        if has_cancellations and cancel_share is not None and cancellations >= 3 and cancel_share >= 0.30:
            problem_sku.append(
                {
                    "type": "high_cancellation_share",
                    "label": label,
                    "sku": row.get("sku"),
                    "cancel_share_pct": round(cancel_share * 100.0, 2),
                    "cancellations": int(cancellations),
                    "reason": "Высокая доля отмен -> потеря оборота и ухудшение выкупа.",
                }
            )

        if spend > 0 and drr is not None and float(drr) > 0.25:
            severity = "critical" if float(drr) > 0.30 else "high"
            problem_sku.append(
                {
                    "type": "high_drr",
                    "severity": severity,
                    "label": label,
                    "sku": row.get("sku"),
                    "drr_pct": round(float(drr) * 100.0, 2),
                    "ad_spend": round(spend, 2),
                    "revenue": round(revenue, 2),
                    "reason": "Высокий ДРР при реальном рекламном расходе -> риск убыточного продвижения.",
                }
            )

        if has_orders and has_buyouts and orders >= 5:
            buyout_rate = (buyouts / orders) if orders > 0 else None
            if buyout_rate is not None and buyout_rate < 0.60:
                problem_sku.append(
                    {
                        "type": "low_buyout_rate",
                        "label": label,
                        "sku": row.get("sku"),
                        "orders": int(orders),
                        "buyouts": int(buyouts),
                        "buyout_rate_pct": round(buyout_rate * 100.0, 2),
                        "reason": "Низкий выкуп -> нужно проверить карточку, цену и ожидания клиента.",
                    }
                )

        if has_orders and orders > 0 and price_bucket == "unprofitable":
            problem_sku.append(
                {
                    "type": "bad_price_index_on_selling",
                    "label": label,
                    "sku": row.get("sku"),
                    "orders": int(orders),
                    "reason": "SKU продается при невыгодном индексе цены -> давление на маржу.",
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

    key_findings = _build_key_findings(
        sku_count=sku_count,
        sku_without_orders_count=sku_without_orders_count,
        assortment_summary=assortment_summary,
        abc_summary=abc_summary,
        price_index_summary=price_index_summary,
        promotion_summary=promotion_summary,
        suspicious_count=len(suspicious_revenue_without_orders),
    )

    data_quality = {
        "has_orders": has_orders,
        "has_revenue": has_revenue,
        "has_stock": has_stock,
        "has_drr": bool(detected.get("drr")),
        "has_spend": has_spend,
        "has_price_index": bool(detected.get("price_index")),
        "has_cancellations": has_cancellations,
        "has_buyouts": has_buyouts,
        "has_impressions": bool(detected.get("impressions")),
        "has_visitors": bool(detected.get("visitors")),
        "has_add_to_cart": bool(detected.get("add_to_cart")),
        "consistency_ok": len(suspicious_revenue_without_orders) == 0,
        "suspicious_revenue_without_orders_count": len(suspicious_revenue_without_orders),
        "top_sku_consistency_ok": all(float(x.get("orders") or 0.0) > 0 for x in top_sku) if has_orders else True,
        "row_count": int(data.get("row_count") or 0),
    }

    period_hint = diagnostics.get("period_hint") if isinstance(diagnostics.get("period_hint"), dict) else {}

    return {
        "summary": summary,
        "funnel_summary": funnel_summary,
        "assortment_summary": assortment_summary,
        "price_index_summary": price_index_summary,
        "promotion_summary": promotion_summary,
        "abc_analysis": abc_analysis,
        "top_sku": top_sku,
        "problem_sku": problem_sku[:100],
        "consistency_checks": {
            "suspicious_revenue_without_orders": suspicious_revenue_without_orders[:50],
        },
        "key_findings": key_findings,
        "detected_columns": detected,
        "chosen_sheet": diagnostics.get("chosen_sheet"),
        "chosen_header_row": diagnostics.get("chosen_header_row"),
        "row_count": int(data.get("row_count") or 0),
        "parse_candidates": diagnostics.get("parse_candidates") or [],
        "data_quality": data_quality,
        "period": {
            "status": str(period_hint.get("status") or "unknown"),
            "date_from": period_hint.get("date_from"),
            "date_to": period_hint.get("date_to"),
            "label_ru": period_hint.get("label_ru"),
            "fallback_used": bool(period_hint.get("fallback_used")),
            "message": period_hint.get("message"),
        },
    }
