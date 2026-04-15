from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple


def _to_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _pct(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None:
        return None
    if denominator <= 0:
        return None
    return round(numerator / denominator * 100.0, 2)


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        return value
    return None


def _source_is_known(value: Any) -> bool:
    return not _is_unknown_source(value)


def _read_metric_from_dict(source: Dict[str, Any], keys: Tuple[str, ...], *, as_int: bool) -> Tuple[int | float | None, bool]:
    if not isinstance(source, dict):
        return None, False
    for key in keys:
        if key not in source:
            continue
        raw_value = source.get(key)
        value = _to_int_or_none(raw_value) if as_int else _to_float_or_none(raw_value)
        if value is None:
            continue
        return value, True
    return None, False


def _field_status(value: int | float | None, source: str) -> str:
    if value is None:
        return "missing"
    if abs(float(value)) <= 1e-12:
        return "confirmed_zero" if _source_is_known(source) else "missing"
    return "confirmed" if _source_is_known(source) else "missing"


def _resolve_conversion_status(
    *,
    value: float | None,
    numerator: int | float | None,
    denominator: int | float | None,
    missing_code: str,
    non_positive_code: str,
    overridden_code: str = "",
    is_overridden: bool = False,
) -> Dict[str, str]:
    if value is not None:
        return {"status": "computed", "reason": ""}
    if is_overridden and overridden_code:
        return {"status": "insufficient_data", "reason": overridden_code}
    if numerator is None or denominator is None:
        return {"status": "insufficient_data", "reason": missing_code}
    if float(denominator) <= 0:
        return {"status": "insufficient_data", "reason": non_positive_code}
    return {"status": "insufficient_data", "reason": missing_code}


def _level_from_flags(*, has_all: bool, has_any: bool) -> str:
    if has_all:
        return "full"
    if has_any:
        return "partial"
    return "missing"


def _sanitize_count(value: Any, *, source: Any) -> int | None:
    normalized = _to_int_or_none(value)
    if normalized is None:
        return None
    if normalized == 0 and not _source_is_known(source):
        return None
    return normalized


def _extract_funnel_xlsx_payload(metrics: Dict[str, Any], explicit: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if isinstance(explicit, dict) and isinstance(explicit.get("cabinet_totals"), dict):
        return explicit

    candidates: List[Any] = []
    if isinstance(metrics, dict):
        candidates.extend(
            [
                metrics.get("funnel_xlsx"),
                metrics.get("funnel_report_xlsx"),
                metrics.get("funnel_report"),
                metrics.get("local_funnel"),
                metrics.get("wb_funnel_xlsx"),
            ]
        )
        input_debug = metrics.get("input_debug", {})
        if isinstance(input_debug, dict):
            candidates.extend(
                [
                    input_debug.get("funnel_xlsx"),
                    input_debug.get("funnel_report"),
                    input_debug.get("local_funnel"),
                ]
            )

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if isinstance(candidate.get("cabinet_totals"), dict):
            return candidate
        if any(key in candidate for key in ("views", "add_to_cart", "orders", "buyouts")):
            return {
                "cabinet_totals": {
                    "views": candidate.get("views"),
                    "add_to_cart": candidate.get("add_to_cart"),
                    "orders": candidate.get("orders"),
                    "buyouts": candidate.get("buyouts"),
                    "orders_amount": candidate.get("orders_amount"),
                    "buyouts_amount": candidate.get("buyouts_amount"),
                },
                "sku_rows": candidate.get("sku_rows") if isinstance(candidate.get("sku_rows"), list) else [],
            }
    return {}


def _pick_priority_metric(*, xlsx_value: Any, api_value: Any, api_source: str) -> Tuple[int | None, str]:
    xlsx_count = _to_int_or_none(xlsx_value)
    if xlsx_count is not None:
        return xlsx_count, "funnel_xlsx"
    api_count = _sanitize_count(api_value, source=api_source)
    if api_count is not None:
        return api_count, "api"
    return None, "unknown"


def _pick_priority_float(*, xlsx_value: Any, api_value: Any, api_source: str) -> Tuple[float | None, str]:
    xlsx_number = _to_float_or_none(xlsx_value)
    if xlsx_number is not None:
        return xlsx_number, "funnel_xlsx"
    api_number = _to_float_or_none(api_value)
    if api_number is None:
        return None, "unknown"
    if abs(api_number) <= 1e-12 and not _source_is_known(api_source):
        return None, "unknown"
    return api_number, "api"


def _is_unknown_source(value: Any) -> bool:
    token = str(value or "").strip().lower()
    return token in {"", "unknown", "not_confirmed", "missing", "unavailable"}


def _build_status(*, views: int | None, add_to_cart: int | None, orders: int | None, buyouts: int | None) -> Dict[str, str]:
    if views is not None and add_to_cart is not None:
        traffic = "confirmed"
    elif views is not None or add_to_cart is not None:
        traffic = "partial"
    else:
        traffic = "unknown"

    if views is not None and orders is not None:
        conversion = "confirmed"
    elif orders is not None:
        conversion = "partial"
    else:
        conversion = "unknown"

    if orders is not None and buyouts is not None:
        buyout_stage = "confirmed"
    elif orders is not None or buyouts is not None:
        buyout_stage = "partial"
    else:
        buyout_stage = "unknown"

    return {
        "traffic": traffic,
        "conversion": conversion,
        "buyout_stage": buyout_stage,
    }


def calculate_funnel_metrics(
    *,
    views: int | None,
    add_to_cart: int | None,
    orders: int | None,
    buyouts: int | None,
    ads_spend: float | None,
    revenue: float | None = None,
    commission: float | None = None,
    logistics: float | None = None,
    tax: float | None = None,
    cogs: float | None = None,
    profit: float | None = None,
) -> Dict[str, Any]:
    view_to_order_conversion = _pct(float(orders) if orders is not None else None, float(views) if views is not None else None)
    cart_rate = _pct(float(add_to_cart) if add_to_cart is not None else None, float(views) if views is not None else None)
    cart_to_order = _pct(float(orders) if orders is not None else None, float(add_to_cart) if add_to_cart is not None else None)
    raw_buyout_rate = _pct(float(buyouts) if buyouts is not None else None, float(orders) if orders is not None else None)
    buyout_rate_over_100 = bool(raw_buyout_rate is not None and raw_buyout_rate > 100.0)
    buyout_rate_note = (
        "order_to_buyout_conversion_gt_100: possible date shift between orders and buyouts"
        if buyout_rate_over_100
        else ""
    )
    buyout_rate = None if buyout_rate_over_100 else raw_buyout_rate

    cpo: float | None = None
    if ads_spend is not None and orders is not None and orders > 0:
        cpo = round(float(ads_spend) / float(orders), 2)

    marketing_layer = {
        "basis": "orders",
        "orders": orders,
        "ads_spend": round(float(ads_spend), 2) if ads_spend is not None else None,
        "cpo": cpo,
    }
    financial_layer = {
        "basis": "buyouts",
        "buyouts": buyouts,
        "revenue": round(float(revenue), 2) if revenue is not None else None,
        "commission": round(float(commission), 2) if commission is not None else None,
        "logistics": round(float(logistics), 2) if logistics is not None else None,
        "tax": round(float(tax), 2) if tax is not None else None,
        "cogs": round(float(cogs), 2) if cogs is not None else None,
        "profit": round(float(profit), 2) if profit is not None else None,
    }

    return {
        "views": views,
        "add_to_cart": add_to_cart,
        "orders": orders,
        "buyouts": buyouts,
        "view_to_order_conversion": view_to_order_conversion,
        "cart_rate": cart_rate,
        "cart_to_order": cart_to_order,
        "buyout_rate": buyout_rate,
        "buyout_rate_over_100": buyout_rate_over_100,
        "buyout_rate_note": buyout_rate_note,
        "ads_spend": round(float(ads_spend), 2) if ads_spend is not None else None,
        "cpo": cpo,
        "marketing_layer": marketing_layer,
        "financial_layer": financial_layer,
    }


def assemble_sales_funnel(
    *,
    run_date: str,
    metrics: Dict[str, Any],
    ads_diagnostics: Dict[str, Any],
    funnel_xlsx_payload: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    safe_metrics = metrics if isinstance(metrics, dict) else {}
    safe_totals = safe_metrics.get("totals", {})
    if not isinstance(safe_totals, dict):
        safe_totals = {}
    safe_commerce_kpi = safe_metrics.get("commerce_kpi", {})
    if not isinstance(safe_commerce_kpi, dict):
        safe_commerce_kpi = {}
    safe_daily_kpi = safe_metrics.get("daily_kpi", {})
    if not isinstance(safe_daily_kpi, dict):
        safe_daily_kpi = {}
    safe_financial_kpi = safe_metrics.get("financial_kpi", {})
    if not isinstance(safe_financial_kpi, dict):
        safe_financial_kpi = {}
    safe_data_sources = safe_metrics.get("data_sources", {})
    if not isinstance(safe_data_sources, dict):
        safe_data_sources = {}
    safe_data_quality = safe_metrics.get("data_quality", {})
    if not isinstance(safe_data_quality, dict):
        safe_data_quality = {}
    safe_ads_diag = ads_diagnostics if isinstance(ads_diagnostics, dict) else {}
    selected_totals = safe_ads_diag.get("selected_totals", {})
    if not isinstance(selected_totals, dict):
        selected_totals = {}
    safe_funnel_xlsx = _extract_funnel_xlsx_payload(safe_metrics, funnel_xlsx_payload)
    funnel_xlsx_totals = safe_funnel_xlsx.get("cabinet_totals", {})
    if not isinstance(funnel_xlsx_totals, dict):
        funnel_xlsx_totals = {}
    upper_flag_known = (
        "funnel_upper_available" in safe_data_quality
        or "funnel_upper_unavailable_from_api" in safe_data_quality
    )
    funnel_upper_available = bool(safe_data_quality.get("funnel_upper_available", False))
    funnel_upper_unavailable_from_api = bool(
        safe_data_quality.get("funnel_upper_unavailable_from_api", False)
    )
    funnel_contract_source = str(safe_data_quality.get("funnel_contract_source") or "missing")
    if not upper_flag_known and "api_funnel_contract" in (safe_metrics.get("diagnostics", {}) if isinstance(safe_metrics.get("diagnostics", {}), dict) else {}):
        diagnostics = safe_metrics.get("diagnostics", {})
        api_contract = diagnostics.get("api_funnel_contract", {}) if isinstance(diagnostics, dict) else {}
        if isinstance(api_contract, dict):
            funnel_upper_available = bool(api_contract.get("upper_funnel_available", False))
            funnel_upper_unavailable_from_api = bool(api_contract.get("upper_funnel_unavailable_from_api", False))
            funnel_contract_source = str(api_contract.get("source") or funnel_contract_source)
            upper_flag_known = True
    allow_api_upper_fallback = bool(funnel_upper_available) if upper_flag_known else True

    orders_confirmed = bool(
        safe_commerce_kpi.get(
            "orders_count_confirmed",
            safe_daily_kpi.get("orders_count_confirmed", False),
        )
    )
    buyouts_confirmed = bool(
        safe_commerce_kpi.get(
            "buyouts_count_confirmed",
            safe_daily_kpi.get("buyouts_count_confirmed", False),
        )
    )

    orders_value = _to_int_or_none(
        _first_present(
            safe_commerce_kpi.get("daily_orders_count"),
            safe_daily_kpi.get("daily_orders_count"),
        )
    )
    buyouts_value = _to_int_or_none(
        _first_present(
            safe_commerce_kpi.get("daily_buyouts_count"),
            safe_daily_kpi.get("daily_buyouts_count"),
        )
    )
    orders = orders_value if orders_confirmed else None
    buyouts = buyouts_value if buyouts_confirmed else None

    orders_source = _first_present(
        safe_data_sources.get("orders_count"),
        safe_daily_kpi.get("data_source_orders_count"),
        safe_daily_kpi.get("source_count"),
    )
    buyouts_source = _first_present(
        safe_data_sources.get("buyouts_count"),
        safe_daily_kpi.get("data_source_buyouts_count"),
        safe_daily_kpi.get("source_count"),
    )
    traffic_source = _first_present(safe_data_sources.get("views"))
    add_to_cart_source = _first_present(safe_data_sources.get("add_to_cart"))

    # Keep conversion metrics available when counts are present in known sources,
    # even if confirmation flags are not final yet.
    orders_for_calc = orders
    if orders_for_calc is None:
        orders_totals_value = _to_int_or_none(safe_totals.get("orders"))
        if orders_totals_value is not None and (orders_totals_value > 0 or not _is_unknown_source(orders_source)):
            orders_for_calc = orders_totals_value
    buyouts_for_calc = buyouts
    if buyouts_for_calc is None:
        buyouts_totals_value = _to_int_or_none(safe_totals.get("buys"))
        if buyouts_totals_value is not None and (buyouts_totals_value > 0 or not _is_unknown_source(buyouts_source)):
            buyouts_for_calc = buyouts_totals_value
    orders_for_calc, orders_source_final = _pick_priority_metric(
        xlsx_value=funnel_xlsx_totals.get("orders"),
        api_value=orders_for_calc,
        api_source=str(orders_source or "unknown"),
    )
    buyouts_for_calc, buyouts_source_final = _pick_priority_metric(
        xlsx_value=funnel_xlsx_totals.get("buyouts"),
        api_value=buyouts_for_calc,
        api_source=str(buyouts_source or "unknown"),
    )

    views_xlsx_raw, views_xlsx_present = _read_metric_from_dict(
        funnel_xlsx_totals,
        ("views",),
        as_int=True,
    )
    views_ads_raw, views_ads_present = _read_metric_from_dict(
        selected_totals,
        ("ads_impressions", "impressions", "views"),
        as_int=True,
    )
    views_api_raw, views_api_present = _read_metric_from_dict(
        safe_commerce_kpi,
        ("views",),
        as_int=True,
    )
    if not views_api_present:
        views_api_raw, views_api_present = _read_metric_from_dict(
            safe_daily_kpi,
            ("views",),
            as_int=True,
        )
    if not views_api_present:
        views_api_raw, views_api_present = _read_metric_from_dict(
            safe_totals,
            ("views", "card_views"),
            as_int=True,
        )

    if views_xlsx_present:
        views = int(views_xlsx_raw if views_xlsx_raw is not None else 0)
        views_source_final = "funnel_xlsx"
    elif views_ads_present:
        views = int(views_ads_raw if views_ads_raw is not None else 0)
        views_source_final = "analytics_api"
    elif allow_api_upper_fallback and views_api_present:
        views = int(views_api_raw if views_api_raw is not None else 0)
        views_source_final = str(traffic_source or "metrics_totals")
    else:
        views = None
        views_source_final = "unavailable_from_api" if funnel_upper_unavailable_from_api else "unknown"

    add_to_cart_xlsx_raw, add_to_cart_xlsx_present = _read_metric_from_dict(
        funnel_xlsx_totals,
        ("add_to_cart",),
        as_int=True,
    )
    add_to_cart_api_raw, add_to_cart_api_present = _read_metric_from_dict(
        safe_commerce_kpi,
        ("add_to_cart",),
        as_int=True,
    )
    if not add_to_cart_api_present:
        add_to_cart_api_raw, add_to_cart_api_present = _read_metric_from_dict(
            safe_daily_kpi,
            ("add_to_cart",),
            as_int=True,
        )
    if not add_to_cart_api_present:
        add_to_cart_api_raw, add_to_cart_api_present = _read_metric_from_dict(
            safe_totals,
            ("add_to_cart", "cart_count"),
            as_int=True,
        )

    if add_to_cart_xlsx_present:
        add_to_cart = int(add_to_cart_xlsx_raw if add_to_cart_xlsx_raw is not None else 0)
        add_to_cart_source_final = "funnel_xlsx"
    elif allow_api_upper_fallback and add_to_cart_api_present:
        add_to_cart = int(add_to_cart_api_raw if add_to_cart_api_raw is not None else 0)
        add_to_cart_source_final = str(add_to_cart_source or "metrics_totals")
    else:
        add_to_cart = None
        add_to_cart_source_final = "unavailable_from_api" if funnel_upper_unavailable_from_api else "unknown"

    impressions_xlsx_raw, impressions_xlsx_present = _read_metric_from_dict(
        funnel_xlsx_totals,
        ("impressions",),
        as_int=True,
    )
    impressions_ads_raw, impressions_ads_present = _read_metric_from_dict(
        selected_totals,
        ("ads_impressions", "impressions"),
        as_int=True,
    )
    impressions_api_raw, impressions_api_present = _read_metric_from_dict(
        safe_totals,
        ("ads_impressions", "impressions"),
        as_int=True,
    )
    if impressions_xlsx_present:
        impressions = int(impressions_xlsx_raw if impressions_xlsx_raw is not None else 0)
        impressions_source_final = "funnel_xlsx"
    elif impressions_ads_present:
        impressions = int(impressions_ads_raw if impressions_ads_raw is not None else 0)
        impressions_source_final = "analytics_api"
    elif allow_api_upper_fallback and impressions_api_present:
        impressions = int(impressions_api_raw if impressions_api_raw is not None else 0)
        impressions_source_final = "metrics_totals"
    else:
        impressions = None
        impressions_source_final = "unavailable_from_api" if funnel_upper_unavailable_from_api else "unknown"

    clicks_xlsx_raw, clicks_xlsx_present = _read_metric_from_dict(
        funnel_xlsx_totals,
        ("clicks",),
        as_int=True,
    )
    clicks_ads_raw, clicks_ads_present = _read_metric_from_dict(
        selected_totals,
        ("ads_clicks", "clicks"),
        as_int=True,
    )
    clicks_api_raw, clicks_api_present = _read_metric_from_dict(
        safe_totals,
        ("ads_clicks", "clicks"),
        as_int=True,
    )
    if clicks_xlsx_present:
        clicks = int(clicks_xlsx_raw if clicks_xlsx_raw is not None else 0)
        clicks_source_final = "funnel_xlsx"
    elif clicks_ads_present:
        clicks = int(clicks_ads_raw if clicks_ads_raw is not None else 0)
        clicks_source_final = "analytics_api"
    elif allow_api_upper_fallback and clicks_api_present:
        clicks = int(clicks_api_raw if clicks_api_raw is not None else 0)
        clicks_source_final = "metrics_totals"
    else:
        clicks = None
        clicks_source_final = "unavailable_from_api" if funnel_upper_unavailable_from_api else "unknown"

    ctr = _pct(float(clicks) if clicks is not None else None, float(impressions) if impressions is not None else None)

    ads_spend = _to_float_or_none(
        _first_present(
            safe_financial_kpi.get("ads_spend"),
            safe_totals.get("ads_spend_total"),
            safe_totals.get("ads_spend"),
            selected_totals.get("ads_spend"),
        )
    )
    if str(safe_data_sources.get("ads_spend") or "").strip().lower() == "unknown":
        ads_spend = None
    revenue = _to_float_or_none(
        _first_present(
            safe_financial_kpi.get("revenue"),
            safe_totals.get("total_revenue"),
            safe_totals.get("revenue"),
        )
    )
    commission = _to_float_or_none(_first_present(safe_financial_kpi.get("wb_commission"), safe_totals.get("wb_commission")))
    logistics = _to_float_or_none(_first_present(safe_financial_kpi.get("logistics"), safe_totals.get("logistics")))
    tax = _to_float_or_none(_first_present(safe_financial_kpi.get("tax"), safe_totals.get("tax")))
    cogs = _to_float_or_none(_first_present(safe_financial_kpi.get("cost_price"), safe_totals.get("cost_price")))
    profit = _to_float_or_none(_first_present(safe_financial_kpi.get("net_profit"), safe_totals.get("net_profit"), safe_totals.get("profit")))

    orders_amount, orders_amount_source = _pick_priority_float(
        xlsx_value=funnel_xlsx_totals.get("orders_amount"),
        api_value=None,
        api_source="unknown",
    )
    buyouts_amount, buyouts_amount_source = _pick_priority_float(
        xlsx_value=funnel_xlsx_totals.get("buyouts_amount"),
        api_value=None,
        api_source="unknown",
    )

    cabinet_metrics = calculate_funnel_metrics(
        views=views,
        add_to_cart=add_to_cart,
        orders=orders_for_calc,
        buyouts=buyouts_for_calc,
        ads_spend=ads_spend,
        revenue=revenue,
        commission=commission,
        logistics=logistics,
        tax=tax,
        cogs=cogs,
        profit=profit,
    )
    views_status = _field_status(views, views_source_final)
    impressions_status = _field_status(impressions, impressions_source_final)
    clicks_status = _field_status(clicks, clicks_source_final)
    add_to_cart_status = _field_status(add_to_cart, add_to_cart_source_final)
    orders_status = _field_status(cabinet_metrics.get("orders"), orders_source_final)
    buyouts_status = _field_status(cabinet_metrics.get("buyouts"), buyouts_source_final)

    upper_has_all = all(
        status in {"confirmed", "confirmed_zero"}
        for status in (views_status, impressions_status, clicks_status, add_to_cart_status)
    )
    upper_has_any = any(
        status in {"confirmed", "confirmed_zero"}
        for status in (views_status, impressions_status, clicks_status, add_to_cart_status)
    )
    upper_funnel_level = _level_from_flags(has_all=upper_has_all, has_any=upper_has_any)
    middle_funnel_level = "full" if orders_status in {"confirmed", "confirmed_zero"} else "missing"
    lower_funnel_level = "full" if buyouts_status in {"confirmed", "confirmed_zero"} else "missing"

    reason_codes: List[str] = []
    if upper_funnel_level == "missing" and funnel_upper_unavailable_from_api:
        reason_codes.append("upper_funnel_unavailable_from_api")
    if upper_funnel_level == "partial":
        reason_codes.append("upper_funnel_partial_fields")
    if middle_funnel_level == "missing":
        reason_codes.append("orders_missing_or_unconfirmed")
    if lower_funnel_level == "missing":
        reason_codes.append("buyouts_missing_or_unconfirmed")

    if upper_funnel_level == "full" and middle_funnel_level == "full" and lower_funnel_level == "full":
        overall_level = "full"
    elif (
        upper_funnel_level == "missing"
        and middle_funnel_level == "missing"
        and lower_funnel_level == "missing"
    ):
        overall_level = "missing"
    else:
        overall_level = "partial"

    conversion_status = {
        "view_to_order": _resolve_conversion_status(
            value=cabinet_metrics.get("view_to_order_conversion"),
            numerator=cabinet_metrics.get("orders"),
            denominator=cabinet_metrics.get("views"),
            missing_code="views_or_orders_missing",
            non_positive_code="views_non_positive",
        ),
        "cart_to_order": _resolve_conversion_status(
            value=cabinet_metrics.get("cart_to_order"),
            numerator=cabinet_metrics.get("orders"),
            denominator=cabinet_metrics.get("add_to_cart"),
            missing_code="add_to_cart_or_orders_missing",
            non_positive_code="add_to_cart_non_positive",
        ),
        "order_to_buyout": _resolve_conversion_status(
            value=cabinet_metrics.get("buyout_rate"),
            numerator=cabinet_metrics.get("buyouts"),
            denominator=cabinet_metrics.get("orders"),
            missing_code="orders_or_buyouts_missing",
            non_positive_code="orders_non_positive",
            overridden_code="order_to_buyout_over_100_possible_date_shift",
            is_overridden=bool(cabinet_metrics.get("buyout_rate_over_100", False)),
        ),
        "ctr": _resolve_conversion_status(
            value=ctr,
            numerator=clicks,
            denominator=impressions,
            missing_code="impressions_or_clicks_missing",
            non_positive_code="impressions_non_positive",
        ),
        "cpo": _resolve_conversion_status(
            value=cabinet_metrics.get("cpo"),
            numerator=ads_spend,
            denominator=cabinet_metrics.get("orders"),
            missing_code="ads_spend_or_orders_missing",
            non_positive_code="orders_non_positive",
        ),
    }

    sku_funnel: List[Dict[str, Any]] = []
    for row in safe_metrics.get("sku_metrics", []):
        if not isinstance(row, dict):
            continue
        sku_orders = _to_int_or_none(row.get("orders"))
        sku_buyouts = _to_int_or_none(_first_present(row.get("buyouts"), row.get("buys")))
        sku_views = _to_int_or_none(
            _first_present(
                row.get("views"),
                row.get("card_views"),
                row.get("impressions"),
            )
        )
        if sku_views is not None and sku_views <= 0:
            if _to_float_or_none(row.get("ads_spend")) is None and _to_int_or_none(row.get("clicks")) is None:
                sku_views = None
        sku_add_to_cart = _to_int_or_none(_first_present(row.get("add_to_cart"), row.get("cart_count")))
        sku_ads_spend = _to_float_or_none(row.get("ads_spend"))
        sku_revenue = _to_float_or_none(row.get("revenue"))
        sku_commission = _to_float_or_none(_first_present(row.get("commission"), row.get("wb_commission")))
        sku_logistics = _to_float_or_none(row.get("logistics"))
        sku_tax = _to_float_or_none(row.get("tax"))
        sku_cogs = _to_float_or_none(_first_present(row.get("cogs"), row.get("cost_price")))
        sku_profit = _to_float_or_none(row.get("profit"))
        sku_metrics = calculate_funnel_metrics(
            views=sku_views,
            add_to_cart=sku_add_to_cart,
            orders=sku_orders,
            buyouts=sku_buyouts,
            ads_spend=sku_ads_spend,
            revenue=sku_revenue,
            commission=sku_commission,
            logistics=sku_logistics,
            tax=sku_tax,
            cogs=sku_cogs,
            profit=sku_profit,
        )
        sku_metrics["sku"] = str(row.get("sku") or "")
        sku_funnel.append(sku_metrics)

    data_sources = {
        "views": views_source_final,
        "impressions": impressions_source_final,
        "clicks": clicks_source_final,
        "add_to_cart": add_to_cart_source_final,
        "orders": orders_source_final,
        "buyouts": buyouts_source_final,
        "orders_amount": orders_amount_source,
        "buyouts_amount": buyouts_amount_source,
        "ads_spend": str(safe_data_sources.get("ads_spend") or "unknown"),
        "cpo": "derived",
    }
    status = _build_status(
        views=views,
        add_to_cart=add_to_cart,
        orders=cabinet_metrics.get("orders"),
        buyouts=cabinet_metrics.get("buyouts"),
    )

    order_to_buyout_over_100 = bool(cabinet_metrics.get("buyout_rate_over_100", False))
    order_to_buyout_note = str(cabinet_metrics.get("buyout_rate_note") or "")
    if order_to_buyout_over_100 and isinstance(status, dict):
        status["buyout_stage"] = "partial"

    funnel_status = {
        "upper_funnel": upper_funnel_level,
        "middle_funnel": middle_funnel_level,
        "lower_funnel": lower_funnel_level,
        "overall": overall_level,
        "reason_codes": reason_codes,
    }

    funnel_payload = {
        "views": cabinet_metrics["views"],
        "views_status": views_status,
        "views_source": views_source_final,
        "impressions": impressions,
        "impressions_status": impressions_status,
        "impressions_source": impressions_source_final,
        "clicks": clicks,
        "clicks_status": clicks_status,
        "clicks_source": clicks_source_final,
        "add_to_cart": cabinet_metrics["add_to_cart"],
        "add_to_cart_status": add_to_cart_status,
        "add_to_cart_source": add_to_cart_source_final,
        "orders": cabinet_metrics["orders"],
        "orders_status": orders_status,
        "orders_source": orders_source_final,
        "buyouts": cabinet_metrics["buyouts"],
        "buyouts_status": buyouts_status,
        "buyouts_source": buyouts_source_final,
        "view_to_order_conversion": cabinet_metrics["view_to_order_conversion"],
        "view_to_order_status": str((conversion_status.get("view_to_order") or {}).get("status") or ""),
        "view_to_order_reason": str((conversion_status.get("view_to_order") or {}).get("reason") or ""),
        "view_to_order": cabinet_metrics["view_to_order_conversion"],
        "cart_rate": cabinet_metrics["cart_rate"],
        "cart_to_order": cabinet_metrics["cart_to_order"],
        "cart_to_order_status": str((conversion_status.get("cart_to_order") or {}).get("status") or ""),
        "cart_to_order_reason": str((conversion_status.get("cart_to_order") or {}).get("reason") or ""),
        "buyout_rate": cabinet_metrics["buyout_rate"],
        "order_to_buyout_status": str((conversion_status.get("order_to_buyout") or {}).get("status") or ""),
        "order_to_buyout_reason": str((conversion_status.get("order_to_buyout") or {}).get("reason") or ""),
        "order_to_buyout": cabinet_metrics["buyout_rate"],
        "order_to_buyout_over_100": order_to_buyout_over_100,
        "order_to_buyout_note": order_to_buyout_note,
        "orders_amount": round(orders_amount, 2) if orders_amount is not None else None,
        "buyouts_amount": round(buyouts_amount, 2) if buyouts_amount is not None else None,
        "ads_spend": cabinet_metrics["ads_spend"],
        "cpo": cabinet_metrics["cpo"],
        "cpo_status": str((conversion_status.get("cpo") or {}).get("status") or ""),
        "cpo_reason": str((conversion_status.get("cpo") or {}).get("reason") or ""),
        # Backward-compatible aliases for existing report/email blocks.
        "ctr": ctr,
        "ctr_status": str((conversion_status.get("ctr") or {}).get("status") or ""),
        "ctr_reason": str((conversion_status.get("ctr") or {}).get("reason") or ""),
        "cart_count": cabinet_metrics["add_to_cart"],
        "cart_conversion_pct": cabinet_metrics["cart_to_order"],
        "cart_rate_pct": cabinet_metrics["cart_rate"],
        "click_to_order_conversion_pct": _pct(
            float(cabinet_metrics["orders"]) if cabinet_metrics["orders"] is not None else None,
            float(clicks) if clicks is not None else None,
        ),
        "order_to_buyout_conversion_pct": cabinet_metrics["buyout_rate"],
        "conversion_rates": {
            "view_to_order": cabinet_metrics["view_to_order_conversion"],
            "cart_to_order": cabinet_metrics["cart_to_order"],
            "order_to_buyout": cabinet_metrics["buyout_rate"],
            "order_to_buyout_over_100": order_to_buyout_over_100,
            "order_to_buyout_note": order_to_buyout_note,
        },
        "conversion_status": conversion_status,
        "funnel_status": funnel_status,
        "marketing_layer": cabinet_metrics["marketing_layer"],
        "financial_layer": cabinet_metrics["financial_layer"],
    }

    print(
        "[funnel_semantics] "
        + json.dumps(
            {
                "target_date": str(run_date or ""),
                "funnel_contract_source": funnel_contract_source,
                "sources_checked_upper": [
                    "funnel_xlsx",
                    "ads_selected_totals",
                    "api_upper_fallback" if allow_api_upper_fallback else "api_upper_fallback_blocked",
                ],
                "fields": {
                    "views": {"status": views_status, "source": views_source_final, "value": views},
                    "impressions": {"status": impressions_status, "source": impressions_source_final, "value": impressions},
                    "clicks": {"status": clicks_status, "source": clicks_source_final, "value": clicks},
                    "add_to_cart": {"status": add_to_cart_status, "source": add_to_cart_source_final, "value": add_to_cart},
                },
                "orders_source": orders_source_final,
                "buyouts_source": buyouts_source_final,
                "overall": overall_level,
                "reason_codes": reason_codes,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )

    return {
        "date": str(run_date or ""),
        "funnel": funnel_payload,
        "data_sources": data_sources,
        "status": status,
        "funnel_status": funnel_status,
        "marketing_layer": cabinet_metrics["marketing_layer"],
        "financial_layer": cabinet_metrics["financial_layer"],
        "sku_funnel": sku_funnel,
    }





