from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Dict, List, Tuple

DAILY_SOURCE_SUPPLIER_GOODS = "supplier_goods"
DAILY_SOURCE_ORDERS_API = "orders_api"
DAILY_SOURCE_SALES_API = "sales_api"
DAILY_SOURCE_REALIZATION_API = "realization_api"
DAILY_SOURCE_FALLBACK = "metrics_totals_fallback"
DAILY_SOURCE_UNKNOWN = "unknown"

_METRIC_ORDERS_COUNT = "daily_orders_count"
_METRIC_ORDERS_AMOUNT = "daily_orders_amount"
_METRIC_BUYOUTS_COUNT = "daily_buyouts_count"
_METRIC_BUYOUTS_AMOUNT = "daily_buyouts_amount"

_ALL_METRICS = (
    _METRIC_ORDERS_COUNT,
    _METRIC_ORDERS_AMOUNT,
    _METRIC_BUYOUTS_COUNT,
    _METRIC_BUYOUTS_AMOUNT,
)

_METRIC_ENTITY = {
    _METRIC_ORDERS_COUNT: "orders",
    _METRIC_ORDERS_AMOUNT: "orders",
    _METRIC_BUYOUTS_COUNT: "buyouts",
    _METRIC_BUYOUTS_AMOUNT: "buyouts",
}

_METRIC_KIND = {
    _METRIC_ORDERS_COUNT: "count",
    _METRIC_ORDERS_AMOUNT: "amount",
    _METRIC_BUYOUTS_COUNT: "count",
    _METRIC_BUYOUTS_AMOUNT: "amount",
}

_DATE_KEYS = (
    "date",
    "orderDate",
    "saleDate",
    "order_dt",
    "sale_dt",
    "lastChangeDate",
    "create_dt",
    "createdAt",
)
_AMOUNT_KEYS = (
    "price",
    "revenue",
    "totalPrice",
    "priceWithDisc",
    "finishedPrice",
    "forPay",
    "ppvz_for_pay",
    "order_amount",
    "buyout_amount",
)
_COUNT_KEYS = (
    "order_id",
    "orderId",
    "sale_id",
    "saleID",
    "srid",
    "nmId",
    "nm_id",
)
_DEFAULT_FALLBACK_WINDOW_DAYS = 1
_MAX_FALLBACK_WINDOW_DAYS = 7


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        if value is None:
            return 0
        return int(round(float(value)))
    except (TypeError, ValueError):
        return 0


def _normalize_day_token(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").date().isoformat()
        except Exception:
            return ""
    return ""


def _row_day_token_with_key(row: Dict[str, Any]) -> Tuple[str, str]:
    if not isinstance(row, dict):
        return "", ""
    for key in _DATE_KEYS:
        token = _normalize_day_token(row.get(key))
        if token:
            return token, key
    return "", ""


def _row_day_token(row: Dict[str, Any]) -> str:
    token, _ = _row_day_token_with_key(row)
    if token:
        return token
    return ""


def _filter_rows_by_day(rows: List[Dict[str, Any]], target_date: str) -> List[Dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    target_day = _normalize_day_token(target_date)
    if not target_day:
        return [row for row in rows if isinstance(row, dict)]
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if _row_day_token(row) == target_day:
            out.append(row)
    return out


def _parse_day(value: str) -> date | None:
    token = _normalize_day_token(value)
    if not token:
        return None
    try:
        return datetime.strptime(token, "%Y-%m-%d").date()
    except Exception:
        return None


def _date_keys_from_rows(rows: List[Dict[str, Any]]) -> List[str]:
    keys: List[str] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        _, key = _row_day_token_with_key(row)
        if key and key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def _metric_keys_from_rows(rows: List[Dict[str, Any]], *, kind: str) -> List[str]:
    keyset = set(_AMOUNT_KEYS if kind == "amount" else _COUNT_KEYS)
    found: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in row.keys():
            if key in keyset:
                found.add(str(key))
    return sorted(found)


def _rows_day_range(rows: List[Dict[str, Any]]) -> str:
    days: List[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        day = _row_day_token(row)
        if day:
            days.append(day)
    if not days:
        return ""
    lo = min(days)
    hi = max(days)
    if lo == hi:
        return lo
    return f"{lo}..{hi}"


def _build_source_slice(
    rows: List[Dict[str, Any]],
    *,
    target_date: str,
    fallback_window_days: int,
) -> Dict[str, Any]:
    safe_rows = [row for row in rows if isinstance(row, dict)]
    target_day = _normalize_day_token(target_date)
    date_range = _rows_day_range(safe_rows)
    date_keys = _date_keys_from_rows(safe_rows)
    if not target_day:
        return {
            "target_date": "",
            "primary_rows": safe_rows,
            "fallback_rows": [],
            "fallback_date": "",
            "fallback_lag_days": 0,
            "available_date_range": date_range,
            "comparison_keys": date_keys,
        }

    primary_rows = _filter_rows_by_day(safe_rows, target_day)
    if primary_rows:
        return {
            "target_date": target_day,
            "primary_rows": primary_rows,
            "fallback_rows": [],
            "fallback_date": "",
            "fallback_lag_days": 0,
            "available_date_range": date_range,
            "comparison_keys": date_keys,
        }

    window = max(0, min(int(fallback_window_days or 0), _MAX_FALLBACK_WINDOW_DAYS))
    if window <= 0:
        return {
            "target_date": target_day,
            "primary_rows": [],
            "fallback_rows": [],
            "fallback_date": "",
            "fallback_lag_days": 0,
            "available_date_range": date_range,
            "comparison_keys": date_keys,
        }

    target_dt = _parse_day(target_day)
    if target_dt is None:
        return {
            "target_date": target_day,
            "primary_rows": [],
            "fallback_rows": [],
            "fallback_date": "",
            "fallback_lag_days": 0,
            "available_date_range": date_range,
            "comparison_keys": date_keys,
        }

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in safe_rows:
        row_day = _row_day_token(row)
        if not row_day:
            continue
        grouped.setdefault(row_day, []).append(row)

    best_day = ""
    best_score: Tuple[int, int, int] | None = None
    for row_day in grouped.keys():
        if row_day == target_day:
            continue
        row_dt = _parse_day(row_day)
        if row_dt is None:
            continue
        diff_days = (target_dt - row_dt).days
        abs_diff = abs(diff_days)
        if abs_diff > window:
            continue
        # Prefer nearest day, then lagging/past slice over future, then freshest within that class.
        score = (abs_diff, 0 if diff_days >= 0 else 1, -int(row_dt.toordinal()))
        if best_score is None or score < best_score:
            best_score = score
            best_day = row_day

    if not best_day:
        return {
            "target_date": target_day,
            "primary_rows": [],
            "fallback_rows": [],
            "fallback_date": "",
            "fallback_lag_days": 0,
            "available_date_range": date_range,
            "comparison_keys": date_keys,
        }

    lag_days = abs((_parse_day(target_day) - _parse_day(best_day)).days) if _parse_day(best_day) else 0
    return {
        "target_date": target_day,
        "primary_rows": [],
        "fallback_rows": list(grouped.get(best_day, [])),
        "fallback_date": best_day,
        "fallback_lag_days": int(lag_days),
        "available_date_range": date_range,
        "comparison_keys": date_keys,
    }


def _row_price_fallback(row: Dict[str, Any]) -> float:
    if not isinstance(row, dict):
        return 0.0
    return _safe_float(
        row.get("price", row.get("revenue", row.get("totalPrice", row.get("priceWithDisc", row.get("finishedPrice", 0.0)))))
    )


def _rows_count(rows: List[Dict[str, Any]]) -> int:
    return len([row for row in rows if isinstance(row, dict)])


def _rows_price_sum(rows: List[Dict[str, Any]]) -> float:
    return round(sum(_row_price_fallback(row) for row in rows if isinstance(row, dict)), 2)


def _rows_have_amount_signal(rows: List[Dict[str, Any]]) -> bool:
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in _AMOUNT_KEYS:
            if key not in row:
                continue
            value = row.get(key)
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            return True
    return False


def _resolve_fallback_window_days(api_debug: Dict[str, Any]) -> int:
    safe_api_debug = api_debug if isinstance(api_debug, dict) else {}
    candidates: List[int] = []
    lag_days = int(_safe_int(safe_api_debug.get("realization_fallback_lag_days")))
    if lag_days > 0:
        candidates.append(lag_days)
    endpoints = safe_api_debug.get("endpoints", [])
    if isinstance(endpoints, list):
        for row in endpoints:
            if not isinstance(row, dict):
                continue
            endpoint_lag = int(_safe_int(row.get("realization_lag_days")))
            if endpoint_lag > 0:
                candidates.append(endpoint_lag)
    resolved = max(candidates) if candidates else _DEFAULT_FALLBACK_WINDOW_DAYS
    resolved = max(_DEFAULT_FALLBACK_WINDOW_DAYS, int(resolved))
    return min(resolved, _MAX_FALLBACK_WINDOW_DAYS)


def _first_numeric_hint(source: Dict[str, Any], keys: Tuple[str, ...]) -> float | None:
    for key in keys:
        if key not in source:
            continue
        value = source.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return float(_safe_float(value))
    return None


def _candidate(
    *,
    metric: str,
    entity: str,
    value: float | int,
    source: str,
    confirmed: bool,
    fallback_used: bool,
    raw_field: str,
    unknown_reason: str = "",
    diagnostic_note: str = "",
    available_date: str = "",
    available_date_range: str = "",
    metric_keys_present: List[str] | None = None,
    comparison_key: str = "",
) -> Dict[str, Any]:
    return {
        "metric": metric,
        "entity": entity,
        "value": value,
        "source": str(source or DAILY_SOURCE_UNKNOWN),
        "confirmed": bool(confirmed),
        "fallback_used": bool(fallback_used),
        "raw_field": str(raw_field or ""),
        "unknown_reason": str(unknown_reason or ""),
        "diagnostic_note": str(diagnostic_note or ""),
        "available_date": str(available_date or ""),
        "available_date_range": str(available_date_range or ""),
        "metric_keys_present": list(metric_keys_present or []),
        "comparison_key": str(comparison_key or ""),
    }


def _extract_raw_daily_candidates(
    *,
    totals: Dict[str, Any],
    supplier_goods_daily: Dict[str, Any],
    api_orders_rows: List[Dict[str, Any]],
    api_sales_rows: List[Dict[str, Any]],
    api_realization_rows: List[Dict[str, Any]],
    source_mode: str,
    input_debug: Dict[str, Any],
    api_debug: Dict[str, Any],
) -> Dict[str, Any]:
    _ = input_debug
    _ = api_debug
    candidates: Dict[str, List[Dict[str, Any]]] = {metric: [] for metric in _ALL_METRICS}

    orders_rows_count = _rows_count(api_orders_rows)
    sales_rows_count = _rows_count(api_sales_rows)
    realization_rows_count = _rows_count(api_realization_rows)
    orders_amount_sum = _rows_price_sum(api_orders_rows)
    sales_amount_sum = _rows_price_sum(api_sales_rows)
    realization_amount_sum = _rows_price_sum(api_realization_rows)
    orders_amount_signal = _rows_have_amount_signal(api_orders_rows)
    sales_amount_signal = _rows_have_amount_signal(api_sales_rows)
    realization_amount_signal = _rows_have_amount_signal(api_realization_rows)

    supplier_found = isinstance(supplier_goods_daily, dict) and bool(supplier_goods_daily.get("found"))
    supplier_source_file = str(supplier_goods_daily.get("source_file") or "") if supplier_found else ""
    supplier_orders_count_raw = _safe_int(supplier_goods_daily.get("orders_count")) if supplier_found else 0
    supplier_buyouts_count_raw = _safe_int(supplier_goods_daily.get("buyouts_count")) if supplier_found else 0
    supplier_orders_amount_raw = round(_safe_float(supplier_goods_daily.get("orders_amount")), 2) if supplier_found else 0.0
    supplier_buyouts_amount_raw = round(_safe_float(supplier_goods_daily.get("buyouts_amount")), 2) if supplier_found else 0.0
    supplier_orders_count_confirmed = bool(supplier_goods_daily.get("orders_count_confirmed", False)) if supplier_found else False
    supplier_buyouts_count_confirmed = bool(supplier_goods_daily.get("buyouts_count_confirmed", False)) if supplier_found else False
    supplier_amounts_confirmed = bool(
        supplier_goods_daily.get("amounts_confirmed", supplier_goods_daily.get("kpi_confirmed", supplier_found))
    ) if supplier_found else False

    totals_orders_hint = int(
        round(
            _safe_float(
                totals.get("sales_activity_qty", totals.get("item_qty", totals.get("orders", 0)))
            )
        )
    )
    totals_buyouts_hint = int(
        round(
            _safe_float(
                totals.get("sales_activity_qty", totals.get("item_qty", totals.get("buys", 0)))
            )
        )
    )
    totals_orders_amount_hint = _first_numeric_hint(
        totals,
        ("orders_amount", "orders_sum", "orders_revenue", "gross_orders_amount"),
    )
    totals_buyouts_amount_hint = _first_numeric_hint(
        totals,
        ("buyouts_amount", "buys_amount", "buyouts_revenue", "gross_buyouts_amount"),
    )

    if orders_rows_count > 0:
        candidates[_METRIC_ORDERS_COUNT].append(
            _candidate(
                metric=_METRIC_ORDERS_COUNT,
                entity="orders",
                value=orders_rows_count,
                source=DAILY_SOURCE_ORDERS_API,
                confirmed=True,
                fallback_used=False,
                raw_field="len(api_orders_rows)",
            )
        )
        candidates[_METRIC_BUYOUTS_COUNT].append(
            _candidate(
                metric=_METRIC_BUYOUTS_COUNT,
                entity="orders",
                value=orders_rows_count,
                source=DAILY_SOURCE_ORDERS_API,
                confirmed=True,
                fallback_used=False,
                raw_field="len(api_orders_rows)",
                diagnostic_note="orders rows are not a buyouts entity",
            )
        )
    if orders_rows_count > 0:
        candidates[_METRIC_ORDERS_AMOUNT].append(
            _candidate(
                metric=_METRIC_ORDERS_AMOUNT,
                entity="orders",
                value=orders_amount_sum,
                source=DAILY_SOURCE_ORDERS_API,
                confirmed=orders_amount_signal,
                fallback_used=False,
                raw_field="orders_api.price/revenue",
                unknown_reason="" if orders_amount_signal else "orders_api_monetary_fields_missing",
            )
        )
        candidates[_METRIC_BUYOUTS_AMOUNT].append(
            _candidate(
                metric=_METRIC_BUYOUTS_AMOUNT,
                entity="orders",
                value=orders_amount_sum,
                source=DAILY_SOURCE_ORDERS_API,
                confirmed=orders_amount_signal,
                fallback_used=False,
                raw_field="orders_api.price/revenue",
                unknown_reason="" if orders_amount_signal else "orders_api_monetary_fields_missing",
                diagnostic_note="orders monetary rows are not a buyouts entity",
            )
        )

    if sales_rows_count > 0:
        candidates[_METRIC_BUYOUTS_COUNT].append(
            _candidate(
                metric=_METRIC_BUYOUTS_COUNT,
                entity="buyouts",
                value=sales_rows_count,
                source=DAILY_SOURCE_SALES_API,
                confirmed=True,
                fallback_used=False,
                raw_field="len(api_sales_rows)",
            )
        )
        candidates[_METRIC_ORDERS_COUNT].append(
            _candidate(
                metric=_METRIC_ORDERS_COUNT,
                entity="buyouts",
                value=sales_rows_count,
                source=DAILY_SOURCE_SALES_API,
                confirmed=True,
                fallback_used=False,
                raw_field="len(api_sales_rows)",
                diagnostic_note="sales rows are not an orders entity",
            )
        )
        candidates[_METRIC_BUYOUTS_AMOUNT].append(
            _candidate(
                metric=_METRIC_BUYOUTS_AMOUNT,
                entity="buyouts",
                value=sales_amount_sum,
                source=DAILY_SOURCE_SALES_API,
                confirmed=sales_amount_signal,
                fallback_used=False,
                raw_field="sales_api.price/revenue",
                unknown_reason="" if sales_amount_signal else "sales_api_monetary_fields_missing",
            )
        )
        candidates[_METRIC_ORDERS_AMOUNT].append(
            _candidate(
                metric=_METRIC_ORDERS_AMOUNT,
                entity="buyouts",
                value=sales_amount_sum,
                source=DAILY_SOURCE_SALES_API,
                confirmed=sales_amount_signal,
                fallback_used=False,
                raw_field="sales_api.price/revenue",
                unknown_reason="" if sales_amount_signal else "sales_api_monetary_fields_missing",
                diagnostic_note="sales monetary rows are not an orders entity",
            )
        )

    if realization_rows_count > 0:
        candidates[_METRIC_BUYOUTS_COUNT].append(
            _candidate(
                metric=_METRIC_BUYOUTS_COUNT,
                entity="buyouts",
                value=realization_rows_count,
                source=DAILY_SOURCE_REALIZATION_API,
                confirmed=True,
                fallback_used=False,
                raw_field="len(api_realization_rows)",
            )
        )
        candidates[_METRIC_ORDERS_COUNT].append(
            _candidate(
                metric=_METRIC_ORDERS_COUNT,
                entity="buyouts",
                value=realization_rows_count,
                source=DAILY_SOURCE_REALIZATION_API,
                confirmed=True,
                fallback_used=False,
                raw_field="len(api_realization_rows)",
                diagnostic_note="realization rows are not an orders entity",
            )
        )
        candidates[_METRIC_BUYOUTS_AMOUNT].append(
            _candidate(
                metric=_METRIC_BUYOUTS_AMOUNT,
                entity="buyouts",
                value=realization_amount_sum,
                source=DAILY_SOURCE_REALIZATION_API,
                confirmed=realization_amount_signal,
                fallback_used=False,
                raw_field="realization_api.price/revenue",
                unknown_reason="" if realization_amount_signal else "realization_api_monetary_fields_missing",
            )
        )
        candidates[_METRIC_ORDERS_AMOUNT].append(
            _candidate(
                metric=_METRIC_ORDERS_AMOUNT,
                entity="buyouts",
                value=realization_amount_sum,
                source=DAILY_SOURCE_REALIZATION_API,
                confirmed=realization_amount_signal,
                fallback_used=False,
                raw_field="realization_api.price/revenue",
                unknown_reason="" if realization_amount_signal else "realization_api_monetary_fields_missing",
                diagnostic_note="realization monetary rows are not an orders entity",
            )
        )

    if supplier_found:
        candidates[_METRIC_ORDERS_COUNT].append(
            _candidate(
                metric=_METRIC_ORDERS_COUNT,
                entity="orders",
                value=supplier_orders_count_raw,
                source=DAILY_SOURCE_SUPPLIER_GOODS,
                confirmed=supplier_orders_count_confirmed,
                fallback_used=True,
                raw_field="supplier_goods.orders_count",
                unknown_reason="" if supplier_orders_count_confirmed else "supplier_orders_count_not_confirmed",
            )
        )
        candidates[_METRIC_ORDERS_AMOUNT].append(
            _candidate(
                metric=_METRIC_ORDERS_AMOUNT,
                entity="orders",
                value=supplier_orders_amount_raw,
                source=DAILY_SOURCE_SUPPLIER_GOODS,
                confirmed=supplier_amounts_confirmed,
                fallback_used=True,
                raw_field="supplier_goods.orders_amount",
                unknown_reason="" if supplier_amounts_confirmed else "supplier_amounts_not_confirmed",
            )
        )
        candidates[_METRIC_BUYOUTS_COUNT].append(
            _candidate(
                metric=_METRIC_BUYOUTS_COUNT,
                entity="buyouts",
                value=supplier_buyouts_count_raw,
                source=DAILY_SOURCE_SUPPLIER_GOODS,
                confirmed=supplier_buyouts_count_confirmed,
                fallback_used=True,
                raw_field="supplier_goods.buyouts_count",
                unknown_reason="" if supplier_buyouts_count_confirmed else "supplier_buyouts_count_not_confirmed",
            )
        )
        candidates[_METRIC_BUYOUTS_AMOUNT].append(
            _candidate(
                metric=_METRIC_BUYOUTS_AMOUNT,
                entity="buyouts",
                value=supplier_buyouts_amount_raw,
                source=DAILY_SOURCE_SUPPLIER_GOODS,
                confirmed=supplier_amounts_confirmed,
                fallback_used=True,
                raw_field="supplier_goods.buyouts_amount",
                unknown_reason="" if supplier_amounts_confirmed else "supplier_amounts_not_confirmed",
            )
        )

    if totals_orders_hint > 0:
        candidates[_METRIC_ORDERS_COUNT].append(
            _candidate(
                metric=_METRIC_ORDERS_COUNT,
                entity="orders",
                value=totals_orders_hint,
                source=DAILY_SOURCE_FALLBACK,
                confirmed=False,
                fallback_used=True,
                raw_field="totals.sales_activity_qty/item_qty/orders",
                diagnostic_note="totals hints are debug-only for strict wb_api",
            )
        )
    if totals_buyouts_hint > 0:
        candidates[_METRIC_BUYOUTS_COUNT].append(
            _candidate(
                metric=_METRIC_BUYOUTS_COUNT,
                entity="buyouts",
                value=totals_buyouts_hint,
                source=DAILY_SOURCE_FALLBACK,
                confirmed=False,
                fallback_used=True,
                raw_field="totals.sales_activity_qty/item_qty/buys",
                diagnostic_note="totals hints are debug-only for strict wb_api",
            )
        )
    if totals_orders_amount_hint is not None and abs(float(totals_orders_amount_hint)) > 1e-9:
        candidates[_METRIC_ORDERS_AMOUNT].append(
            _candidate(
                metric=_METRIC_ORDERS_AMOUNT,
                entity="orders",
                value=totals_orders_amount_hint,
                source=DAILY_SOURCE_FALLBACK,
                confirmed=False,
                fallback_used=True,
                raw_field="totals.orders_amount*",
                diagnostic_note="totals hints are debug-only for strict wb_api",
            )
        )
    if totals_buyouts_amount_hint is not None and abs(float(totals_buyouts_amount_hint)) > 1e-9:
        candidates[_METRIC_BUYOUTS_AMOUNT].append(
            _candidate(
                metric=_METRIC_BUYOUTS_AMOUNT,
                entity="buyouts",
                value=totals_buyouts_amount_hint,
                source=DAILY_SOURCE_FALLBACK,
                confirmed=False,
                fallback_used=True,
                raw_field="totals.buyouts_amount*",
                diagnostic_note="totals hints are debug-only for strict wb_api",
            )
        )

    return {
        "source_mode": str(source_mode or ""),
        "candidates": candidates,
        "debug": {
            "orders_rows_count": orders_rows_count,
            "sales_rows_count": sales_rows_count,
            "realization_rows_count": realization_rows_count,
            "supplier_found": supplier_found,
            "supplier_source_file": supplier_source_file,
            "supplier_orders_count_raw": supplier_orders_count_raw,
            "supplier_buyouts_count_raw": supplier_buyouts_count_raw,
            "totals_orders_hint": totals_orders_hint,
            "totals_buyouts_hint": totals_buyouts_hint,
        },
    }


def _build_lagged_api_candidates(
    *,
    source_slices: Dict[str, Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {metric: [] for metric in _ALL_METRICS}
    source_specs = (
        (DAILY_SOURCE_ORDERS_API, "orders", _METRIC_ORDERS_COUNT, _METRIC_ORDERS_AMOUNT),
        (DAILY_SOURCE_SALES_API, "buyouts", _METRIC_BUYOUTS_COUNT, _METRIC_BUYOUTS_AMOUNT),
        (DAILY_SOURCE_REALIZATION_API, "buyouts", _METRIC_BUYOUTS_COUNT, _METRIC_BUYOUTS_AMOUNT),
    )

    for source, entity, count_metric, amount_metric in source_specs:
        slice_info = source_slices.get(source, {})
        if not isinstance(slice_info, dict):
            continue
        primary_rows = list(slice_info.get("primary_rows", [])) if isinstance(slice_info.get("primary_rows", []), list) else []
        fallback_rows = list(slice_info.get("fallback_rows", [])) if isinstance(slice_info.get("fallback_rows", []), list) else []
        if not fallback_rows:
            continue

        primary_rows_count = _rows_count(primary_rows)
        primary_amount_signal = _rows_have_amount_signal(primary_rows)
        fallback_rows_count = _rows_count(fallback_rows)
        fallback_amount_signal = _rows_have_amount_signal(fallback_rows)
        fallback_date = str(slice_info.get("fallback_date") or "")
        fallback_lag_days = int(slice_info.get("fallback_lag_days", 0) or 0)
        comparison_key = ",".join([str(key) for key in list(slice_info.get("comparison_keys", [])) if str(key)])
        fallback_date_range = _rows_day_range(fallback_rows)
        count_keys = _metric_keys_from_rows(fallback_rows, kind="count")
        amount_keys = _metric_keys_from_rows(fallback_rows, kind="amount")
        lag_note = (
            f"lagged fallback accepted from {fallback_date or 'unknown'} "
            f"(lag_days={fallback_lag_days}, target={slice_info.get('target_date') or 'unknown'})"
        )

        if primary_rows_count <= 0 and fallback_rows_count > 0:
            out[count_metric].append(
                {
                    "metric": count_metric,
                    "entity": entity,
                    "value": int(fallback_rows_count),
                    "source": source,
                    "confirmed": True,
                    "fallback_used": True,
                    "raw_field": f"len({source}.lagged_rows)",
                    "unknown_reason": "",
                    "diagnostic_note": lag_note,
                    "available_date": fallback_date,
                    "available_date_range": fallback_date_range,
                    "metric_keys_present": count_keys,
                    "comparison_key": comparison_key,
                }
            )

        if (primary_rows_count <= 0 or not primary_amount_signal) and fallback_rows_count > 0:
            out[amount_metric].append(
                {
                    "metric": amount_metric,
                    "entity": entity,
                    "value": round(_rows_price_sum(fallback_rows), 2),
                    "source": source,
                    "confirmed": bool(fallback_amount_signal),
                    "fallback_used": True,
                    "raw_field": f"{source}.lagged.price/revenue",
                    "unknown_reason": "" if fallback_amount_signal else f"{source}_lagged_monetary_fields_missing",
                    "diagnostic_note": lag_note,
                    "available_date": fallback_date,
                    "available_date_range": fallback_date_range,
                    "metric_keys_present": amount_keys,
                    "comparison_key": comparison_key,
                }
            )

    return out


def _merge_lagged_candidates(
    *,
    normalized_candidates: Dict[str, List[Dict[str, Any]]],
    lagged_candidates: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {metric: list(rows) for metric, rows in normalized_candidates.items()}
    for metric, rows in lagged_candidates.items():
        if metric not in out or not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict):
                out[metric].append(dict(row))
    return out


def _enrich_candidates_from_source_slices(
    *,
    normalized_candidates: Dict[str, List[Dict[str, Any]]],
    source_slices: Dict[str, Dict[str, Any]],
    target_date: str,
) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {metric: [] for metric in _ALL_METRICS}
    for metric, rows in normalized_candidates.items():
        kind = _METRIC_KIND.get(metric, "amount")
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            enriched = dict(row)
            source = str(enriched.get("source") or DAILY_SOURCE_UNKNOWN)
            slice_info = source_slices.get(source, {})
            if isinstance(slice_info, dict) and slice_info:
                is_fallback = bool(enriched.get("fallback_used", False))
                source_rows = list(slice_info.get("fallback_rows", [])) if is_fallback else list(slice_info.get("primary_rows", []))
                if not str(enriched.get("available_date") or ""):
                    if is_fallback:
                        enriched["available_date"] = str(slice_info.get("fallback_date") or "")
                    else:
                        enriched["available_date"] = str(target_date or "")
                if not str(enriched.get("available_date_range") or ""):
                    enriched["available_date_range"] = _rows_day_range(source_rows) or str(slice_info.get("available_date_range") or "")
                if not list(enriched.get("metric_keys_present", [])):
                    enriched["metric_keys_present"] = _metric_keys_from_rows(source_rows, kind=kind)
                if not str(enriched.get("comparison_key") or ""):
                    enriched["comparison_key"] = ",".join(
                        [str(key) for key in list(slice_info.get("comparison_keys", [])) if str(key)]
                    )
            out[metric].append(enriched)
    return out


def _normalize_daily_candidates(raw_candidates: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
    normalized: Dict[str, List[Dict[str, Any]]] = {metric: [] for metric in _ALL_METRICS}
    for metric, rows in raw_candidates.items():
        if metric not in normalized or not isinstance(rows, list):
            continue
        kind = _METRIC_KIND.get(metric, "amount")
        for row in rows:
            if not isinstance(row, dict):
                continue
            value = row.get("value")
            if kind == "count":
                normalized_value: float | int = int(max(0, _safe_int(value)))
            else:
                normalized_value = round(float(_safe_float(value)), 2)
            normalized[metric].append(
                {
                    "metric": metric,
                    "entity": str(row.get("entity") or ""),
                    "value": normalized_value,
                    "source": str(row.get("source") or DAILY_SOURCE_UNKNOWN),
                    "confirmed": bool(row.get("confirmed", False)),
                    "fallback_used": bool(row.get("fallback_used", False)),
                    "raw_field": str(row.get("raw_field") or ""),
                    "unknown_reason": str(row.get("unknown_reason") or ""),
                    "diagnostic_note": str(row.get("diagnostic_note") or ""),
                    "available_date": str(row.get("available_date") or ""),
                    "available_date_range": str(row.get("available_date_range") or ""),
                    "metric_keys_present": [str(key) for key in list(row.get("metric_keys_present", [])) if str(key)],
                    "comparison_key": str(row.get("comparison_key") or ""),
                }
            )
    return normalized


def _build_metric_policy(*, source_mode: str) -> Dict[str, Any]:
    strict_wb_api = str(source_mode or "").strip().lower() == "wb_api"
    if strict_wb_api:
        allowed_sources = {
            _METRIC_ORDERS_COUNT: [DAILY_SOURCE_ORDERS_API],
            _METRIC_ORDERS_AMOUNT: [DAILY_SOURCE_ORDERS_API],
            _METRIC_BUYOUTS_COUNT: [DAILY_SOURCE_SALES_API, DAILY_SOURCE_REALIZATION_API],
            _METRIC_BUYOUTS_AMOUNT: [DAILY_SOURCE_SALES_API, DAILY_SOURCE_REALIZATION_API],
        }
    else:
        allowed_sources = {
            _METRIC_ORDERS_COUNT: [
                DAILY_SOURCE_SUPPLIER_GOODS,
                DAILY_SOURCE_ORDERS_API,
                DAILY_SOURCE_SALES_API,
                DAILY_SOURCE_FALLBACK,
            ],
            _METRIC_ORDERS_AMOUNT: [
                DAILY_SOURCE_SALES_API,
                DAILY_SOURCE_SUPPLIER_GOODS,
                DAILY_SOURCE_ORDERS_API,
                DAILY_SOURCE_REALIZATION_API,
                DAILY_SOURCE_FALLBACK,
            ],
            _METRIC_BUYOUTS_COUNT: [
                DAILY_SOURCE_SUPPLIER_GOODS,
                DAILY_SOURCE_SALES_API,
                DAILY_SOURCE_REALIZATION_API,
                DAILY_SOURCE_FALLBACK,
            ],
            _METRIC_BUYOUTS_AMOUNT: [
                DAILY_SOURCE_SALES_API,
                DAILY_SOURCE_REALIZATION_API,
                DAILY_SOURCE_SUPPLIER_GOODS,
                DAILY_SOURCE_FALLBACK,
            ],
        }
    priority = {metric: list(values) for metric, values in allowed_sources.items()}
    return {
        "strict_wb_api": strict_wb_api,
        "allowed_sources": allowed_sources,
        "priority": priority,
    }


def _resolve_primary_status(
    *,
    metric: str,
    primary_source: str,
    candidates: List[Dict[str, Any]],
    selected_source: str,
    selected_fallback: bool,
) -> str:
    expected_entity = _METRIC_ENTITY.get(metric, "")
    primary_rows = [
        row
        for row in (candidates if isinstance(candidates, list) else [])
        if isinstance(row, dict)
        and str(row.get("source") or "") == primary_source
        and str(row.get("entity") or "") == expected_entity
        and not bool(row.get("fallback_used", False))
    ]
    if not primary_rows:
        status = "empty"
    elif any(bool(row.get("confirmed", False)) for row in primary_rows):
        status = "ok"
    else:
        status = "incomplete"
    if selected_source == primary_source and bool(selected_fallback):
        return "lagged"
    return status


def _emit_metric_selection_log(
    *,
    metric: str,
    trace: Dict[str, Any],
    target_date: str,
    report_date: str,
) -> None:
    safe_trace = trace if isinstance(trace, dict) else {}
    summary = {
        "metric": metric,
        "target_date": str(target_date or ""),
        "report_date": str(report_date or ""),
        "primary_source": str(safe_trace.get("primary_source") or ""),
        "primary_status": str(safe_trace.get("primary_status") or ""),
        "candidate_fallback_sources_count": int(safe_trace.get("fallback_candidates_count", 0) or 0),
        "selected_source": str(safe_trace.get("source") or DAILY_SOURCE_UNKNOWN),
        "selected_fallback": bool(safe_trace.get("fallback_used", False)),
        "selected_available_date": str((safe_trace.get("selected_candidate") or {}).get("available_date") or ""),
        "selected_comparison_key": str((safe_trace.get("selected_candidate") or {}).get("comparison_key") or ""),
        "unknown_reason": str(safe_trace.get("unknown_reason") or ""),
    }
    print("[daily_kpi_source] " + json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    for idx, candidate in enumerate(list(safe_trace.get("candidate_diagnostics", []))):
        if not isinstance(candidate, dict):
            continue
        row = {
            "metric": metric,
            "idx": int(idx),
            "source": str(candidate.get("source") or DAILY_SOURCE_UNKNOWN),
            "available_date": str(candidate.get("available_date") or ""),
            "available_date_range": str(candidate.get("available_date_range") or ""),
            "metric_keys_present": [str(key) for key in list(candidate.get("metric_keys_present", [])) if str(key)],
            "comparison_key": str(candidate.get("comparison_key") or ""),
            "reason": str(candidate.get("reason") or ""),
        }
        print("[daily_kpi_source_candidate] " + json.dumps(row, ensure_ascii=False, separators=(",", ":")))


def _build_metric_trace(
    *,
    metric: str,
    value: float | int,
    source: str,
    confirmed: bool,
    unknown_reason: str,
    fallback_used: bool,
    rejected_candidates: List[Dict[str, Any]],
    candidate_diagnostics: List[Dict[str, Any]],
    primary_source: str,
    primary_status: str,
    fallback_candidates_count: int,
    selected_candidate: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "metric": metric,
        "value": value,
        "source": source,
        "confirmed": bool(confirmed),
        "unknown_reason": str(unknown_reason or ""),
        "fallback_used": bool(fallback_used),
        "rejected_candidates": rejected_candidates,
        "candidate_diagnostics": candidate_diagnostics,
        "primary_source": str(primary_source or ""),
        "primary_status": str(primary_status or ""),
        "fallback_candidates_count": int(fallback_candidates_count),
        "selected_candidate": selected_candidate if isinstance(selected_candidate, dict) else {},
    }


def _assemble_daily_metric(
    *,
    metric: str,
    candidates: List[Dict[str, Any]],
    policy: Dict[str, Any],
) -> Dict[str, Any]:
    kind = _METRIC_KIND.get(metric, "amount")
    expected_entity = _METRIC_ENTITY.get(metric, "")
    strict_wb_api = bool(policy.get("strict_wb_api", False))
    allowed_sources = list((policy.get("allowed_sources", {}) or {}).get(metric, []))
    priority_map = {source: idx for idx, source in enumerate((policy.get("priority", {}) or {}).get(metric, []))}

    indexed_candidates: List[Tuple[int, Dict[str, Any]]] = list(enumerate(candidates if isinstance(candidates, list) else []))
    indexed_candidates.sort(
        key=lambda item: (
            int(priority_map.get(str(item[1].get("source") or DAILY_SOURCE_UNKNOWN), 999)),
            int(item[0]),
        )
    )

    rejected: List[Dict[str, Any]] = []
    candidate_diagnostics: List[Dict[str, Any]] = []
    selected: Dict[str, Any] | None = None
    selected_candidate_payload: Dict[str, Any] = {}

    for _, candidate in indexed_candidates:
        source = str(candidate.get("source") or DAILY_SOURCE_UNKNOWN)
        entity = str(candidate.get("entity") or "")
        confirmed = bool(candidate.get("confirmed", False))
        available_date = str(candidate.get("available_date") or "")
        available_date_range = str(candidate.get("available_date_range") or "")
        metric_keys_present = [str(key) for key in list(candidate.get("metric_keys_present", [])) if str(key)]
        comparison_key = str(candidate.get("comparison_key") or "")
        reject_reason = ""

        if selected is not None:
            candidate_diagnostics.append(
                {
                    "source": source,
                    "reason": "skipped_after_selection",
                    "entity": entity,
                    "value": candidate.get("value"),
                    "raw_field": str(candidate.get("raw_field") or ""),
                    "note": str(candidate.get("diagnostic_note") or ""),
                    "available_date": available_date,
                    "available_date_range": available_date_range,
                    "metric_keys_present": metric_keys_present,
                    "comparison_key": comparison_key,
                }
            )
            continue

        if entity != expected_entity:
            reject_reason = "entity_mismatch"
        elif source == DAILY_SOURCE_FALLBACK and strict_wb_api:
            reject_reason = "totals_hint_debug_only"
        elif source not in allowed_sources:
            reject_reason = "blocked_by_source_policy"
        elif not confirmed:
            reject_reason = "candidate_not_confirmed"

        if reject_reason:
            rejected.append(
                {
                    "source": source,
                    "reason": reject_reason,
                    "value": candidate.get("value"),
                    "entity": entity,
                    "raw_field": str(candidate.get("raw_field") or ""),
                    "note": str(candidate.get("diagnostic_note") or ""),
                    "available_date": available_date,
                    "available_date_range": available_date_range,
                    "metric_keys_present": metric_keys_present,
                    "comparison_key": comparison_key,
                }
            )
            candidate_diagnostics.append(
                {
                    "source": source,
                    "reason": reject_reason,
                    "entity": entity,
                    "value": candidate.get("value"),
                    "raw_field": str(candidate.get("raw_field") or ""),
                    "note": str(candidate.get("diagnostic_note") or ""),
                    "available_date": available_date,
                    "available_date_range": available_date_range,
                    "metric_keys_present": metric_keys_present,
                    "comparison_key": comparison_key,
                }
            )
            continue

        selected = candidate
        selected_candidate_payload = {
            "source": source,
            "entity": entity,
            "value": candidate.get("value"),
            "raw_field": str(candidate.get("raw_field") or ""),
            "note": str(candidate.get("diagnostic_note") or ""),
            "available_date": available_date,
            "available_date_range": available_date_range,
            "metric_keys_present": metric_keys_present,
            "comparison_key": comparison_key,
        }
        candidate_diagnostics.append(
            {
                "source": source,
                "reason": "accepted",
                "entity": entity,
                "value": candidate.get("value"),
                "raw_field": str(candidate.get("raw_field") or ""),
                "note": str(candidate.get("diagnostic_note") or ""),
                "available_date": available_date,
                "available_date_range": available_date_range,
                "metric_keys_present": metric_keys_present,
                "comparison_key": comparison_key,
            }
        )

    default_value: float | int = 0 if kind == "count" else 0.0
    if selected is None:
        if any(row.get("reason") == "totals_hint_debug_only" for row in rejected):
            unknown_reason = "totals_hint_debug_only"
        elif any(row.get("reason") == "blocked_by_source_policy" for row in rejected):
            unknown_reason = "blocked_by_source_policy"
        elif any(row.get("reason") == "candidate_not_confirmed" for row in rejected):
            unknown_reason = "no_confirmed_value_from_allowed_sources"
        elif rejected:
            unknown_reason = "no_valid_candidate_after_policy"
        else:
            unknown_reason = "no_candidates_found"
        source = DAILY_SOURCE_UNKNOWN
        value = default_value
        confirmed = False
        fallback_used = False
    else:
        source = str(selected.get("source") or DAILY_SOURCE_UNKNOWN)
        value = selected.get("value")
        if kind == "count":
            value = int(max(0, _safe_int(value)))
        else:
            value = round(_safe_float(value), 2)
        confirmed = True
        unknown_reason = ""
        fallback_used = bool(selected.get("fallback_used", False))

    primary_source = str(((policy.get("priority", {}) or {}).get(metric, [DAILY_SOURCE_UNKNOWN]) or [DAILY_SOURCE_UNKNOWN])[0] or DAILY_SOURCE_UNKNOWN)
    primary_status = _resolve_primary_status(
        metric=metric,
        primary_source=primary_source,
        candidates=candidates,
        selected_source=source,
        selected_fallback=fallback_used,
    )
    fallback_candidates_count = len(
        [
            row
            for row in (candidates if isinstance(candidates, list) else [])
            if isinstance(row, dict) and bool(row.get("fallback_used", False))
        ]
    )

    trace = _build_metric_trace(
        metric=metric,
        value=value,
        source=source,
        confirmed=confirmed,
        unknown_reason=unknown_reason,
        fallback_used=fallback_used,
        rejected_candidates=rejected,
        candidate_diagnostics=candidate_diagnostics,
        primary_source=primary_source,
        primary_status=primary_status,
        fallback_candidates_count=fallback_candidates_count,
        selected_candidate=selected_candidate_payload,
    )
    return {
        "metric": metric,
        "value": value,
        "source": source,
        "confirmed": confirmed,
        "unknown_reason": unknown_reason,
        "fallback_used": fallback_used,
        "trace": trace,
    }


def resolve_daily_kpi(
    totals: Dict[str, Any],
    supplier_goods_daily: Dict[str, Any],
    api_orders_rows: List[Dict[str, Any]],
    api_sales_rows: List[Dict[str, Any]],
    api_realization_rows: List[Dict[str, Any]],
    *,
    source_mode: str = "",
    input_debug: Dict[str, Any] | None = None,
    api_debug: Dict[str, Any] | None = None,
    event_date_model: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    safe_totals = totals if isinstance(totals, dict) else {}
    safe_supplier = supplier_goods_daily if isinstance(supplier_goods_daily, dict) else {}
    safe_orders_rows = api_orders_rows if isinstance(api_orders_rows, list) else []
    safe_sales_rows = api_sales_rows if isinstance(api_sales_rows, list) else []
    safe_realization_rows = api_realization_rows if isinstance(api_realization_rows, list) else []
    safe_input_debug = input_debug if isinstance(input_debug, dict) else {}
    safe_api_debug = api_debug if isinstance(api_debug, dict) else {}
    safe_event_date_model = event_date_model if isinstance(event_date_model, dict) else {}

    target_date = _normalize_day_token(safe_event_date_model.get("operational_date"))
    if not target_date:
        target_date = _normalize_day_token(safe_api_debug.get("date_from"))
    if not target_date:
        target_date = _normalize_day_token(safe_api_debug.get("run_date_requested"))
    report_date = _normalize_day_token(safe_event_date_model.get("report_date")) or _normalize_day_token(
        safe_api_debug.get("run_date_requested")
    )
    fallback_window_days = _resolve_fallback_window_days(safe_api_debug)

    source_slices = {
        DAILY_SOURCE_ORDERS_API: _build_source_slice(
            safe_orders_rows,
            target_date=target_date,
            fallback_window_days=fallback_window_days,
        ),
        DAILY_SOURCE_SALES_API: _build_source_slice(
            safe_sales_rows,
            target_date=target_date,
            fallback_window_days=fallback_window_days,
        ),
        DAILY_SOURCE_REALIZATION_API: _build_source_slice(
            safe_realization_rows,
            target_date=target_date,
            fallback_window_days=fallback_window_days,
        ),
    }

    extracted = _extract_raw_daily_candidates(
        totals=safe_totals,
        supplier_goods_daily=safe_supplier,
        api_orders_rows=list(source_slices.get(DAILY_SOURCE_ORDERS_API, {}).get("primary_rows", [])),
        api_sales_rows=list(source_slices.get(DAILY_SOURCE_SALES_API, {}).get("primary_rows", [])),
        api_realization_rows=list(source_slices.get(DAILY_SOURCE_REALIZATION_API, {}).get("primary_rows", [])),
        source_mode=str(source_mode or ""),
        input_debug=safe_input_debug,
        api_debug=safe_api_debug,
    )
    normalized_candidates = _normalize_daily_candidates(extracted.get("candidates", {}))
    lagged_candidates = _build_lagged_api_candidates(source_slices=source_slices)
    normalized_candidates = _merge_lagged_candidates(
        normalized_candidates=normalized_candidates,
        lagged_candidates=lagged_candidates,
    )
    normalized_candidates = _enrich_candidates_from_source_slices(
        normalized_candidates=normalized_candidates,
        source_slices=source_slices,
        target_date=target_date,
    )
    policy = _build_metric_policy(source_mode=str(source_mode or ""))

    metric_result_orders_count = _assemble_daily_metric(
        metric=_METRIC_ORDERS_COUNT,
        candidates=normalized_candidates.get(_METRIC_ORDERS_COUNT, []),
        policy=policy,
    )
    metric_result_orders_amount = _assemble_daily_metric(
        metric=_METRIC_ORDERS_AMOUNT,
        candidates=normalized_candidates.get(_METRIC_ORDERS_AMOUNT, []),
        policy=policy,
    )
    metric_result_buyouts_count = _assemble_daily_metric(
        metric=_METRIC_BUYOUTS_COUNT,
        candidates=normalized_candidates.get(_METRIC_BUYOUTS_COUNT, []),
        policy=policy,
    )
    metric_result_buyouts_amount = _assemble_daily_metric(
        metric=_METRIC_BUYOUTS_AMOUNT,
        candidates=normalized_candidates.get(_METRIC_BUYOUTS_AMOUNT, []),
        policy=policy,
    )
    _emit_metric_selection_log(
        metric=_METRIC_ORDERS_COUNT,
        trace=metric_result_orders_count.get("trace", {}),
        target_date=target_date,
        report_date=report_date,
    )
    _emit_metric_selection_log(
        metric=_METRIC_ORDERS_AMOUNT,
        trace=metric_result_orders_amount.get("trace", {}),
        target_date=target_date,
        report_date=report_date,
    )
    _emit_metric_selection_log(
        metric=_METRIC_BUYOUTS_COUNT,
        trace=metric_result_buyouts_count.get("trace", {}),
        target_date=target_date,
        report_date=report_date,
    )
    _emit_metric_selection_log(
        metric=_METRIC_BUYOUTS_AMOUNT,
        trace=metric_result_buyouts_amount.get("trace", {}),
        target_date=target_date,
        report_date=report_date,
    )
    print(
        "[daily_kpi_source_group] "
        + json.dumps(
            {
                "target_date": target_date,
                "report_date": report_date,
                "orders_group_selected": {
                    "count": str(metric_result_orders_count.get("source") or DAILY_SOURCE_UNKNOWN),
                    "amount": str(metric_result_orders_amount.get("source") or DAILY_SOURCE_UNKNOWN),
                },
                "buyouts_group_selected": {
                    "count": str(metric_result_buyouts_count.get("source") or DAILY_SOURCE_UNKNOWN),
                    "amount": str(metric_result_buyouts_amount.get("source") or DAILY_SOURCE_UNKNOWN),
                },
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )

    debug_block = extracted.get("debug", {}) if isinstance(extracted.get("debug"), dict) else {}
    supplier_source_file = str(debug_block.get("supplier_source_file") or "")
    strict_wb_api = bool(policy.get("strict_wb_api", False))

    count_rejected = (
        list((metric_result_orders_count.get("trace", {}) or {}).get("rejected_candidates", []))
        + list((metric_result_buyouts_count.get("trace", {}) or {}).get("rejected_candidates", []))
    )
    quantity_fallback_blocked = any(
        isinstance(row, dict) and str(row.get("reason") or "") == "totals_hint_debug_only"
        for row in count_rejected
    )

    supplier_found = bool(debug_block.get("supplier_found", False))
    supplier_goods_ignored = bool(strict_wb_api and supplier_found)

    payload = {
        "daily_orders_count": int(metric_result_orders_count.get("value", 0) or 0),
        "daily_orders_amount": round(_safe_float(metric_result_orders_amount.get("value", 0.0)), 2),
        "daily_buyouts_count": int(metric_result_buyouts_count.get("value", 0) or 0),
        "daily_buyouts_amount": round(_safe_float(metric_result_buyouts_amount.get("value", 0.0)), 2),
        "data_source_orders": str(metric_result_orders_count.get("source") or DAILY_SOURCE_UNKNOWN),
        "data_source_buyouts": str(metric_result_buyouts_count.get("source") or DAILY_SOURCE_UNKNOWN),
        "data_source_orders_count": str(metric_result_orders_count.get("source") or DAILY_SOURCE_UNKNOWN),
        "data_source_orders_amount": str(metric_result_orders_amount.get("source") or DAILY_SOURCE_UNKNOWN),
        "data_source_buyouts_count": str(metric_result_buyouts_count.get("source") or DAILY_SOURCE_UNKNOWN),
        "data_source_buyouts_amount": str(metric_result_buyouts_amount.get("source") or DAILY_SOURCE_UNKNOWN),
        "orders_amount_confirmed": bool(metric_result_orders_amount.get("confirmed", False)),
        "buyouts_amount_confirmed": bool(metric_result_buyouts_amount.get("confirmed", False)),
        "orders_count_confirmed": bool(metric_result_orders_count.get("confirmed", False)),
        "buyouts_count_confirmed": bool(metric_result_buyouts_count.get("confirmed", False)),
        "supplier_goods_source_file": supplier_source_file,
        "quantity_fallback_blocked": bool(quantity_fallback_blocked),
        "orders_count_unknown_reason": str(metric_result_orders_count.get("unknown_reason") or ""),
        "buyouts_count_unknown_reason": str(metric_result_buyouts_count.get("unknown_reason") or ""),
        "sku_activity_orders_hint": int(debug_block.get("totals_orders_hint", 0) or 0),
        "sku_activity_buyouts_hint": int(debug_block.get("totals_buyouts_hint", 0) or 0),
        "api_orders_rows_count": int(debug_block.get("orders_rows_count", 0) or 0),
        "api_sales_rows_count": int(debug_block.get("sales_rows_count", 0) or 0),
        "api_realization_rows_count": int(debug_block.get("realization_rows_count", 0) or 0),
        "supplier_orders_count_raw": int(debug_block.get("supplier_orders_count_raw", 0) or 0),
        "supplier_buyouts_count_raw": int(debug_block.get("supplier_buyouts_count_raw", 0) or 0),
        "daily_kpi_target_date": str(target_date or ""),
        "daily_kpi_report_date": str(report_date or ""),
        "daily_kpi_fallback_window_days": int(fallback_window_days),
        "trace_daily_orders_count": metric_result_orders_count.get("trace", {}),
        "trace_daily_orders_amount": metric_result_orders_amount.get("trace", {}),
        "trace_daily_buyouts_count": metric_result_buyouts_count.get("trace", {}),
        "trace_daily_buyouts_amount": metric_result_buyouts_amount.get("trace", {}),
        "daily_kpi_policy_mode": "wb_api_strict" if strict_wb_api else "legacy",
        "supplier_goods_ignored_in_wb_api": bool(supplier_goods_ignored),
    }

    if payload["data_source_orders_count"] == DAILY_SOURCE_UNKNOWN and not payload["orders_count_unknown_reason"]:
        payload["orders_count_unknown_reason"] = "orders_count source unresolved"
    if payload["data_source_buyouts_count"] == DAILY_SOURCE_UNKNOWN and not payload["buyouts_count_unknown_reason"]:
        payload["buyouts_count_unknown_reason"] = "buyouts_count source unresolved"
    return payload
