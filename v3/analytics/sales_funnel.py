from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Tuple

from ..validation.sku_normalization import normalize_sku

DEFAULT_FUNNEL_THRESHOLDS: Dict[str, float] = {
    "min_views_for_analysis": 50.0,
    "low_cart_rate": 0.03,
    "low_conversion": 0.01,
    "low_cart_to_order": 0.25,
    "low_buyout_rate": 0.8,
    "min_ads_spend_for_efficiency": 1.0,
    "max_orders_for_ads_efficiency_problem": 0.0,
    "weak_conversion_for_ads_efficiency": 0.005,
}

FUNNEL_ISSUE_TYPES: Tuple[str, ...] = (
    "traffic_problem",
    "card_problem",
    "price_or_offer_problem",
    "buyout_problem",
    "ads_efficiency_problem",
    "healthy_funnel",
    "insufficient_data",
)

FUNNEL_ISSUE_REASONS_RU: Dict[str, str] = {
    "traffic_problem": "РќРёР·РєРёР№ С‚СЂР°С„РёРє: С‚РѕРІР°СЂ РїРѕР»СѓС‡Р°РµС‚ СЃР»РёС€РєРѕРј РјР°Р»Рѕ РїСЂРѕСЃРјРѕС‚СЂРѕРІ.",
    "card_problem": "РџСЂРѕР±Р»РµРјР° РєР°СЂС‚РѕС‡РєРё: РїСЂРѕСЃРјРѕС‚СЂС‹ РµСЃС‚СЊ, РЅРѕ С‚РѕРІР°СЂ СЃР»Р°Р±Рѕ РґРѕР±Р°РІР»СЏСЋС‚ РІ РєРѕСЂР·РёРЅСѓ РёР»Рё Р·Р°РєР°Р·С‹РІР°СЋС‚.",
    "price_or_offer_problem": "РџСЂРѕР±Р»РµРјР° РѕС„С„РµСЂР°: С‚РѕРІР°СЂ РєР»Р°РґСѓС‚ РІ РєРѕСЂР·РёРЅСѓ, РЅРѕ РїР»РѕС…Рѕ РѕС„РѕСЂРјР»СЏСЋС‚ Р·Р°РєР°Р·.",
    "buyout_problem": "РџСЂРѕР±Р»РµРјР° РІС‹РєСѓРїР°: Р·Р°РєР°Р·С‹ РµСЃС‚СЊ, РЅРѕ РЅРёР·РєРёР№ РїСЂРѕС†РµРЅС‚ РІС‹РєСѓРїР°.",
    "ads_efficiency_problem": "РџСЂРѕР±Р»РµРјР° СЂРµРєР»Р°РјС‹: СЂР°СЃС…РѕРґС‹ РµСЃС‚СЊ, РЅРѕ Р·Р°РєР°Р·С‹ РЅРµ РїРѕРґС‚РІРµСЂР¶РґР°СЋС‚ СЌС„С„РµРєС‚РёРІРЅРѕСЃС‚СЊ С‚СЂР°С„РёРєР°.",
    "healthy_funnel": "Р’РѕСЂРѕРЅРєР° РІС‹РіР»СЏРґРёС‚ СѓСЃС‚РѕР№С‡РёРІРѕ РїРѕ РєР»СЋС‡РµРІС‹Рј СЌС‚Р°РїР°Рј.",
    "insufficient_data": "РќРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РґР°РЅРЅС‹С… РґР»СЏ СѓРІРµСЂРµРЅРЅРѕР№ РґРёР°РіРЅРѕСЃС‚РёРєРё РІРѕСЂРѕРЅРєРё.",
}

_SKU_ALIASES: Tuple[str, ...] = ("sku", "nm_id", "nmid", "offer_id", "product_id")
_VIEWS_ALIASES: Tuple[str, ...] = ("views", "impressions", "card_views")
_CART_ALIASES: Tuple[str, ...] = ("add_to_cart", "carts", "cart_adds", "cart_count")
_ORDERS_ALIASES: Tuple[str, ...] = ("orders", "ordered_units", "orders_count")
_BUYOUTS_ALIASES: Tuple[str, ...] = ("buyouts", "sales", "purchased_units", "buyout_units", "buys")
_ADS_SPEND_ALIASES: Tuple[str, ...] = ("ads_spend", "ad_spend", "spend")


def _normalize_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered in {"none", "null", "nan", "-", "n/a", "na"}:
        return None
    candidate = text.replace(" ", "").replace(",", ".")
    try:
        return float(candidate)
    except (TypeError, ValueError):
        return None


def _normalize_count(value: Any) -> int | None:
    parsed = _normalize_number(value)
    if parsed is None:
        return None
    return int(round(parsed))


def safe_div(numerator: Any, denominator: Any) -> float | None:
    num = _normalize_number(numerator)
    den = _normalize_number(denominator)
    if num is None or den is None or den <= 0:
        return None
    return round(num / den, 4)


def _normalize_thresholds(thresholds: Mapping[str, Any] | None) -> Dict[str, float]:
    out = dict(DEFAULT_FUNNEL_THRESHOLDS)
    if not isinstance(thresholds, Mapping):
        return out
    for key, default_value in DEFAULT_FUNNEL_THRESHOLDS.items():
        parsed = _normalize_number(thresholds.get(key))
        if parsed is None:
            continue
        if key in {"min_views_for_analysis", "min_ads_spend_for_efficiency"}:
            out[key] = max(0.0, parsed)
        elif key == "max_orders_for_ads_efficiency_problem":
            out[key] = max(0.0, parsed)
        else:
            out[key] = min(max(0.0, parsed), 1.0)
    return out


def _extract_sku_rows(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    for key in ("sku_metrics", "items", "skus"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [item for item in rows if isinstance(item, dict)]

    by_sku = payload.get("metrics_by_sku")
    if isinstance(by_sku, dict):
        rows: List[Dict[str, Any]] = []
        for sku, row in by_sku.items():
            if not isinstance(row, dict):
                continue
            row_payload = dict(row)
            row_payload.setdefault("sku", str(sku))
            rows.append(row_payload)
        return rows

    sales_funnel = payload.get("sales_funnel")
    if isinstance(sales_funnel, dict):
        sku_funnel = sales_funnel.get("sku_funnel")
        if isinstance(sku_funnel, list):
            return [item for item in sku_funnel if isinstance(item, dict)]
    return []


def _row_lookup(row: Dict[str, Any]) -> Dict[str, Any]:
    lookup: Dict[str, Any] = {}
    for key, value in row.items():
        lookup[str(key).strip().lower()] = value
    return lookup


def _pick_first(row: Dict[str, Any], lookup: Dict[str, Any], aliases: Iterable[str]) -> Any:
    for alias in aliases:
        if alias in row:
            return row.get(alias)
        if alias in lookup:
            return lookup.get(alias)
    return None


def _build_issue_type(
    *,
    views: int | None,
    add_to_cart: int | None,
    orders: int | None,
    buyouts: int | None,
    ads_spend: float | None,
    conversion: float | None,
    cart_rate: float | None,
    cart_to_order: float | None,
    buyout_rate: float | None,
    thresholds: Dict[str, float],
) -> str:
    has_core_signal = any(value is not None for value in (views, add_to_cart, orders, buyouts))
    if not has_core_signal and ads_spend is None:
        return "insufficient_data"

    ads_spend_present = ads_spend is not None and ads_spend >= thresholds["min_ads_spend_for_efficiency"]
    weak_orders = orders is None or float(orders) <= thresholds["max_orders_for_ads_efficiency_problem"]
    weak_conversion = conversion is not None and conversion <= thresholds["weak_conversion_for_ads_efficiency"]
    if ads_spend_present and (weak_orders or weak_conversion):
        return "ads_efficiency_problem"

    if views is None:
        return "insufficient_data"
    if views < thresholds["min_views_for_analysis"]:
        return "traffic_problem"

    if orders is not None and orders > 0 and buyouts is None:
        return "insufficient_data"
    if orders is not None and orders > 0 and buyout_rate is not None and buyout_rate < thresholds["low_buyout_rate"]:
        return "buyout_problem"

    if add_to_cart is not None and add_to_cart > 0:
        if orders is None:
            return "insufficient_data"
        if cart_to_order is not None and cart_to_order < thresholds["low_cart_to_order"]:
            return "price_or_offer_problem"

    low_cart_rate = cart_rate is not None and cart_rate < thresholds["low_cart_rate"]
    low_conversion = conversion is not None and conversion < thresholds["low_conversion"]
    if low_cart_rate or low_conversion:
        return "card_problem"

    if add_to_cart is None and orders is None and buyouts is None:
        return "insufficient_data"
    return "healthy_funnel"


def classify_sales_funnel_issue(
    *,
    views: int | None,
    add_to_cart: int | None,
    orders: int | None,
    buyouts: int | None,
    ads_spend: float | None,
    conversion: float | None,
    cart_rate: float | None,
    cart_to_order: float | None,
    buyout_rate: float | None,
    thresholds: Mapping[str, Any] | None = None,
) -> str:
    resolved_thresholds = _normalize_thresholds(thresholds)
    return _build_issue_type(
        views=views,
        add_to_cart=add_to_cart,
        orders=orders,
        buyouts=buyouts,
        ads_spend=ads_spend,
        conversion=conversion,
        cart_rate=cart_rate,
        cart_to_order=cart_to_order,
        buyout_rate=buyout_rate,
        thresholds=resolved_thresholds,
    )


def _build_summary(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    issue_counts = {issue_type: 0 for issue_type in FUNNEL_ISSUE_TYPES}
    for item in items:
        issue_type = str(item.get("issue_type") or "insufficient_data")
        if issue_type not in issue_counts:
            issue_type = "insufficient_data"
        issue_counts[issue_type] += 1

    top_problem_groups = [
        {"issue_type": issue_type, "count": int(count)}
        for issue_type, count in issue_counts.items()
        if issue_type not in {"healthy_funnel", "insufficient_data"} and int(count) > 0
    ]
    top_problem_groups.sort(key=lambda row: (-int(row["count"]), str(row["issue_type"])))

    top_problem_skus: List[Dict[str, Any]] = []
    for item in items:
        issue_type = str(item.get("issue_type") or "insufficient_data")
        if issue_type in {"healthy_funnel", "insufficient_data"}:
            continue
        top_problem_skus.append(
            {
                "sku": str(item.get("sku") or ""),
                "issue_type": issue_type,
                "reason": str(item.get("issue_reason_ru") or FUNNEL_ISSUE_REASONS_RU.get(issue_type, "")),
            }
        )
    top_problem_skus = top_problem_skus[:10]

    analyzed_sku_count = int(len([item for item in items if str(item.get("issue_type")) != "insufficient_data"]))
    return {
        "sku_count": len(items),
        "analyzed_sku_count": analyzed_sku_count,
        "issue_counts": issue_counts,
        "top_problem_groups": top_problem_groups[:5],
        "top_problem_skus": top_problem_skus,
    }


def build_sales_funnel_metrics(
    metrics: Any,
    *,
    thresholds: Mapping[str, Any] | None = None,
    run_date: str = "",
) -> Dict[str, Any]:
    rows = _extract_sku_rows(metrics)
    resolved_thresholds = _normalize_thresholds(thresholds)

    items: List[Dict[str, Any]] = []
    warnings: List[Dict[str, str]] = []

    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        lookup = _row_lookup(row)
        raw_sku = _pick_first(row, lookup, _SKU_ALIASES)
        sku = str(normalize_sku(raw_sku) or "").strip()
        if not sku:
            sku = f"unknown_sku_{index + 1}"

        views = _normalize_count(_pick_first(row, lookup, _VIEWS_ALIASES))
        add_to_cart = _normalize_count(_pick_first(row, lookup, _CART_ALIASES))
        orders = _normalize_count(_pick_first(row, lookup, _ORDERS_ALIASES))
        buyouts = _normalize_count(_pick_first(row, lookup, _BUYOUTS_ALIASES))
        ads_spend = _normalize_number(_pick_first(row, lookup, _ADS_SPEND_ALIASES))

        conversion = safe_div(orders, views)
        cart_rate = safe_div(add_to_cart, views)
        cart_to_order = safe_div(orders, add_to_cart)
        buyout_rate = safe_div(buyouts, orders)

        issue_type = _build_issue_type(
            views=views,
            add_to_cart=add_to_cart,
            orders=orders,
            buyouts=buyouts,
            ads_spend=ads_spend,
            conversion=conversion,
            cart_rate=cart_rate,
            cart_to_order=cart_to_order,
            buyout_rate=buyout_rate,
            thresholds=resolved_thresholds,
        )

        items.append(
            {
                "sku": sku,
                "views": views,
                "add_to_cart": add_to_cart,
                "orders": orders,
                "buyouts": buyouts,
                "ads_spend": round(float(ads_spend), 2) if ads_spend is not None else None,
                "conversion": conversion,
                "cart_rate": cart_rate,
                "cart_to_order": cart_to_order,
                "buyout_rate": buyout_rate,
                "has_views": bool(views is not None and views > 0),
                "has_cart": bool(add_to_cart is not None and add_to_cart > 0),
                "has_orders": bool(orders is not None and orders > 0),
                "has_buyouts": bool(buyouts is not None and buyouts > 0),
                "issue_type": issue_type,
                "issue_reason_ru": FUNNEL_ISSUE_REASONS_RU.get(issue_type, FUNNEL_ISSUE_REASONS_RU["insufficient_data"]),
            }
        )

    if not items:
        warnings.append({"code": "sales_funnel_sku_metrics_missing", "message": "SKU-level metrics for sales funnel are missing."})

    summary = _build_summary(items)
    insufficient_count = int(summary.get("issue_counts", {}).get("insufficient_data", 0) or 0)
    if insufficient_count > 0:
        warnings.append(
            {
                "code": "sales_funnel_insufficient_data",
                "message": f"Insufficient funnel data for {insufficient_count} SKU.",
            }
        )

    if not items:
        status = "partial_success"
    elif int(summary.get("analyzed_sku_count", 0) or 0) <= 0:
        status = "partial_success"
    elif insufficient_count > 0:
        status = "partial_success"
    else:
        status = "success"

    return {
        "date": str(run_date or ""),
        "status": status,
        "thresholds": resolved_thresholds,
        "items": items,
        "summary": summary,
        "warnings": warnings,
    }


__all__ = [
    "DEFAULT_FUNNEL_THRESHOLDS",
    "FUNNEL_ISSUE_REASONS_RU",
    "FUNNEL_ISSUE_TYPES",
    "build_sales_funnel_metrics",
    "classify_sales_funnel_issue",
    "safe_div",
]




