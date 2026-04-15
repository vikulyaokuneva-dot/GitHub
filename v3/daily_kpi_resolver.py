from __future__ import annotations

from datetime import datetime
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


def _row_day_token(row: Dict[str, Any]) -> str:
    if not isinstance(row, dict):
        return ""
    for key in (
        "date",
        "orderDate",
        "saleDate",
        "order_dt",
        "sale_dt",
        "lastChangeDate",
        "create_dt",
        "createdAt",
    ):
        token = _normalize_day_token(row.get(key))
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
    amount_keys = (
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
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in amount_keys:
            if key not in row:
                continue
            value = row.get(key)
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            return True
    return False


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


def _build_metric_trace(
    *,
    metric: str,
    value: float | int,
    source: str,
    confirmed: bool,
    unknown_reason: str,
    fallback_used: bool,
    rejected_candidates: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "metric": metric,
        "value": value,
        "source": source,
        "confirmed": bool(confirmed),
        "unknown_reason": str(unknown_reason or ""),
        "fallback_used": bool(fallback_used),
        "rejected_candidates": rejected_candidates,
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
    selected: Dict[str, Any] | None = None

    for _, candidate in indexed_candidates:
        source = str(candidate.get("source") or DAILY_SOURCE_UNKNOWN)
        entity = str(candidate.get("entity") or "")
        confirmed = bool(candidate.get("confirmed", False))
        reject_reason = ""

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
                }
            )
            continue

        selected = candidate
        break

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

    trace = _build_metric_trace(
        metric=metric,
        value=value,
        source=source,
        confirmed=confirmed,
        unknown_reason=unknown_reason,
        fallback_used=fallback_used,
        rejected_candidates=rejected,
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

    safe_orders_rows = _filter_rows_by_day(safe_orders_rows, target_date)
    safe_sales_rows = _filter_rows_by_day(safe_sales_rows, target_date)
    safe_realization_rows = _filter_rows_by_day(safe_realization_rows, target_date)

    extracted = _extract_raw_daily_candidates(
        totals=safe_totals,
        supplier_goods_daily=safe_supplier,
        api_orders_rows=safe_orders_rows,
        api_sales_rows=safe_sales_rows,
        api_realization_rows=safe_realization_rows,
        source_mode=str(source_mode or ""),
        input_debug=safe_input_debug,
        api_debug=safe_api_debug,
    )
    normalized_candidates = _normalize_daily_candidates(extracted.get("candidates", {}))
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
