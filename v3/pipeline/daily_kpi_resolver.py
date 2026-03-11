from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence, Tuple

SOURCE_SUPPLIER_GOODS = "supplier_goods_report"
SOURCE_ORDERS_API = "orders_api"
SOURCE_SALES_API = "sales_api"
SOURCE_REALIZATION_API = "realization_api"
SOURCE_FALLBACK = "metrics_totals_fallback"

_SOURCE_PATH_ALIASES: Dict[str, Tuple[Tuple[str, ...], ...]] = {
    SOURCE_SUPPLIER_GOODS: (
        ("supplier_goods_report",),
        ("supplier_goods_daily",),
        ("supplier_goods",),
        ("daily_kpi", "supplier_goods_report"),
        ("reports", "supplier_goods_report"),
        ("raw", "supplier_goods_report"),
    ),
    SOURCE_ORDERS_API: (
        ("orders_api",),
        ("api_orders",),
        ("api_orders_rows",),
        ("orders_rows",),
        ("api", "orders"),
        ("wb_api", "orders"),
    ),
    SOURCE_SALES_API: (
        ("sales_api",),
        ("api_sales",),
        ("api_sales_rows",),
        ("sales_rows",),
        ("api", "sales"),
        ("wb_api", "sales"),
    ),
    SOURCE_REALIZATION_API: (
        ("realization_api",),
        ("api_realization",),
        ("api_realization_rows",),
        ("realization_rows",),
        ("api", "realization"),
        ("wb_api", "realization"),
    ),
    SOURCE_FALLBACK: (
        ("metrics_totals_fallback",),
        ("metrics_totals",),
        ("totals",),
        ("metrics", "totals"),
        ("summary", "totals"),
        ("metrics",),
    ),
}

_PRIORITY_BY_METRIC: Dict[str, Tuple[str, ...]] = {
    "orders_count": (
        SOURCE_SUPPLIER_GOODS,
        SOURCE_ORDERS_API,
        SOURCE_SALES_API,
        SOURCE_FALLBACK,
    ),
    "orders_amount": (
        SOURCE_SUPPLIER_GOODS,
        SOURCE_SALES_API,
        SOURCE_FALLBACK,
    ),
    "buyouts_count": (
        SOURCE_SUPPLIER_GOODS,
        SOURCE_SALES_API,
        SOURCE_REALIZATION_API,
        SOURCE_FALLBACK,
    ),
    "buyouts_amount": (
        SOURCE_SUPPLIER_GOODS,
        SOURCE_SALES_API,
        SOURCE_REALIZATION_API,
        SOURCE_FALLBACK,
    ),
}

_METRIC_KIND: Dict[str, str] = {
    "orders_count": "count",
    "orders_amount": "amount",
    "buyouts_count": "count",
    "buyouts_amount": "amount",
}

_METRIC_FIELD_ALIASES: Dict[str, Tuple[str, ...]] = {
    "orders_count": (
        "orders_count",
        "daily_orders_count",
        "orders",
        "order_count",
        "orderscount",
        "ordered_qty",
        "ordered_quantity",
        "ordered_units",
        "quantity",
        "qty",
        "заказы",
        "заказы_шт",
        "количество_заказов",
        "кол_во_заказов",
        "заказанные_товары_шт",
        "заказано_шт",
    ),
    "orders_amount": (
        "orders_amount",
        "daily_orders_amount",
        "orders_sum",
        "orders_total",
        "orders_total_amount",
        "sum_orders",
        "amount",
        "total_amount",
        "total_price",
        "totalprice",
        "price",
        "price_with_disc",
        "pricewithdisc",
        "finished_price",
        "finishedprice",
        "sum_to_pay",
        "сумма_заказов_минус_комиссия_wb_руб",
        "сумма_заказов_руб",
        "заказов_на_сумму",
    ),
    "buyouts_count": (
        "buyouts_count",
        "daily_buyouts_count",
        "buyouts",
        "buys",
        "sales_count",
        "sale_count",
        "realization_count",
        "realized_count",
        "quantity",
        "qty",
        "выкупы",
        "выкупили_шт",
        "количество_выкупов",
        "кол_во_выкупов",
        "продажи_шт",
        "реализовано",
    ),
    "buyouts_amount": (
        "buyouts_amount",
        "daily_buyouts_amount",
        "buyouts_sum",
        "buyouts_total",
        "buys_amount",
        "realization_amount",
        "amount",
        "total_amount",
        "revenue",
        "total_revenue",
        "sum_to_pay",
        "к_перечислению",
        "к_перечислению_за_товар_руб",
        "к_перечислению_продавцу_за_товар_руб",
        "сумма_продаж",
        "сумма_реализации",
    ),
}

_ROW_CONTAINER_KEYS: Tuple[str, ...] = (
    "rows",
    "items",
    "records",
    "results",
    "list",
    "data",
    "orders",
    "sales",
    "realization",
)

_MAX_TREE_DEPTH = 5
_MAX_LIST_ITEMS_TO_SCAN = 2000


@dataclass(frozen=True)
class _MetricCandidate:
    value: Optional[float]
    method: str
    matched_field: str
    details: Dict[str, Any]


def resolve_daily_kpi(raw_bundle: dict) -> dict:
    """Resolve daily commerce KPI from raw payloads without making API calls.

    Selection is done independently for each metric with configured source priorities:
    - `orders_count`: supplier_goods_report -> orders_api -> sales_api -> metrics_totals_fallback
    - `orders_amount`: supplier_goods_report -> sales_api -> metrics_totals_fallback
    - `buyouts_*`: supplier_goods_report -> sales_api -> realization_api -> metrics_totals_fallback

    Returns:
        Dict with KPI values, selected source per metric, diagnostic trace and warnings.
    """
    warnings: List[Dict[str, Any]] = []
    bundle: Dict[str, Any]
    if isinstance(raw_bundle, dict):
        bundle = raw_bundle
    else:
        bundle = {}
        warnings.append(
            {
                "code": "daily_kpi_raw_bundle_not_dict",
                "message": "raw_bundle is not a dict, fallback to empty payload.",
            }
        )

    source_payloads, source_meta = _resolve_source_payloads(bundle)

    resolved_values: Dict[str, Any] = {
        "orders_count": 0,
        "orders_amount": 0.0,
        "buyouts_count": 0,
        "buyouts_amount": 0.0,
    }
    selected_sources: Dict[str, str] = {}
    resolution_trace: Dict[str, List[Dict[str, Any]]] = {}

    for metric, priority in _PRIORITY_BY_METRIC.items():
        kind = _METRIC_KIND[metric]
        chosen_source = priority[-1]
        chosen_value: Optional[float] = None
        metric_trace: List[Dict[str, Any]] = []

        for source in priority:
            payload = source_payloads.get(source)
            candidate = _extract_metric_candidate(payload=payload, metric=metric, kind=kind)
            metric_trace.append(
                {
                    "source": source,
                    "payload_present": bool(source_meta.get(source, {}).get("present")),
                    "value_found": candidate.value is not None,
                    "value": round(float(candidate.value), 4) if candidate.value is not None else None,
                    "method": candidate.method,
                    "matched_field": candidate.matched_field,
                    "details": candidate.details,
                }
            )
            if candidate.value is not None:
                chosen_source = source
                chosen_value = candidate.value
                break

        if chosen_value is None:
            _append_warning(
                warnings,
                code="daily_kpi_metric_default_zero",
                message=f"Could not resolve {metric}; defaulted to zero.",
                metric=metric,
                details={"priority": list(priority)},
            )
            chosen_value = 0.0

        resolved_values[metric] = _coerce_metric_value(chosen_value, kind)
        selected_sources[metric] = chosen_source
        resolution_trace[metric] = metric_trace

        if chosen_source == SOURCE_FALLBACK:
            _append_warning(
                warnings,
                code="daily_kpi_fallback_used",
                message=f"{metric} resolved from metrics_totals_fallback.",
                metric=metric,
            )

    return {
        "orders_count": resolved_values["orders_count"],
        "orders_amount": resolved_values["orders_amount"],
        "buyouts_count": resolved_values["buyouts_count"],
        "buyouts_amount": resolved_values["buyouts_amount"],
        "sources": selected_sources,
        "diagnostics": {
            "source_payloads": source_meta,
            "resolution_trace": resolution_trace,
        },
        "warnings": warnings,
    }


def _resolve_source_payloads(raw_bundle: Mapping[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]]]:
    payloads: Dict[str, Any] = {}
    meta: Dict[str, Dict[str, Any]] = {}
    for source, alias_paths in _SOURCE_PATH_ALIASES.items():
        payload = None
        matched_path: Tuple[str, ...] = ()
        for path in alias_paths:
            value = _deep_get(raw_bundle, path)
            if value is None:
                continue
            payload = value
            matched_path = path
            break
        payloads[source] = payload
        meta[source] = {
            "present": payload is not None,
            "matched_path": ".".join(matched_path),
            "payload_type": type(payload).__name__ if payload is not None else "missing",
        }
    return payloads, meta


def _extract_metric_candidate(payload: Any, metric: str, kind: str) -> _MetricCandidate:
    if payload is None:
        return _MetricCandidate(value=None, method="missing_payload", matched_field="", details={})

    aliases = tuple(_normalize_key(x) for x in _METRIC_FIELD_ALIASES[metric])

    direct = _find_direct_metric_value(payload, aliases)
    if direct is not None:
        value, matched_field, path = direct
        return _MetricCandidate(
            value=value,
            method="direct_field",
            matched_field=matched_field,
            details={"path": path},
        )

    rows, rows_path = _find_rows(payload)
    if rows:
        from_rows = _metric_from_rows(rows=rows, aliases=aliases, kind=kind)
        if from_rows.value is not None:
            details = dict(from_rows.details)
            details["rows_path"] = rows_path
            return _MetricCandidate(
                value=from_rows.value,
                method=from_rows.method,
                matched_field=from_rows.matched_field,
                details=details,
            )

    return _MetricCandidate(value=None, method="not_found", matched_field="", details={})


def _find_direct_metric_value(payload: Any, aliases: Sequence[str]) -> Optional[Tuple[float, str, str]]:
    if not isinstance(payload, Mapping):
        return None

    alias_set = set(aliases)
    queue: List[Tuple[Mapping[str, Any], str, int]] = [(payload, "$", 0)]
    visited_ids: set[int] = set()

    while queue:
        node, node_path, depth = queue.pop(0)
        node_id = id(node)
        if node_id in visited_ids:
            continue
        visited_ids.add(node_id)

        for raw_key, raw_value in node.items():
            norm_key = _normalize_key(raw_key)
            if norm_key in alias_set:
                numeric = _safe_float(raw_value)
                if numeric is not None:
                    return numeric, str(raw_key), f"{node_path}.{raw_key}"

        if depth >= _MAX_TREE_DEPTH:
            continue

        for raw_key, raw_value in node.items():
            if isinstance(raw_value, Mapping):
                queue.append((raw_value, f"{node_path}.{raw_key}", depth + 1))

    return None


def _find_rows(payload: Any) -> Tuple[List[Dict[str, Any]], str]:
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        rows = [item for item in payload if isinstance(item, Mapping)]
        if rows:
            return list(rows)[:_MAX_LIST_ITEMS_TO_SCAN], "$"

    if not isinstance(payload, Mapping):
        return [], ""

    prioritized_lists: List[Tuple[List[Dict[str, Any]], str]] = []
    queue: List[Tuple[Any, str, int]] = [(payload, "$", 0)]
    visited_ids: set[int] = set()

    while queue:
        node, node_path, depth = queue.pop(0)
        node_id = id(node)
        if node_id in visited_ids:
            continue
        visited_ids.add(node_id)

        if isinstance(node, Mapping):
            # Prefer well-known row container names first.
            for raw_key, raw_value in node.items():
                if _normalize_key(raw_key) not in _ROW_CONTAINER_KEYS:
                    continue
                rows = _as_row_list(raw_value)
                if rows:
                    prioritized_lists.append((rows, f"{node_path}.{raw_key}"))

            if depth < _MAX_TREE_DEPTH:
                for raw_key, raw_value in node.items():
                    if isinstance(raw_value, (Mapping, list, tuple)):
                        queue.append((raw_value, f"{node_path}.{raw_key}", depth + 1))

        elif isinstance(node, (list, tuple)) and depth < _MAX_TREE_DEPTH:
            for idx, item in enumerate(list(node)[:_MAX_LIST_ITEMS_TO_SCAN]):
                if isinstance(item, (Mapping, list, tuple)):
                    queue.append((item, f"{node_path}[{idx}]", depth + 1))

    if prioritized_lists:
        rows, path = max(prioritized_lists, key=lambda item: len(item[0]))
        return rows[:_MAX_LIST_ITEMS_TO_SCAN], path

    return [], ""


def _as_row_list(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    out: List[Dict[str, Any]] = []
    for item in value[:_MAX_LIST_ITEMS_TO_SCAN]:
        if isinstance(item, Mapping):
            out.append(dict(item))
    return out


def _metric_from_rows(rows: Sequence[Mapping[str, Any]], aliases: Sequence[str], kind: str) -> _MetricCandidate:
    alias_order = list(dict.fromkeys(aliases))
    total = 0.0
    hits = 0
    field_hits: Dict[str, int] = {}

    for row in rows:
        value, field = _extract_row_value(row, alias_order)
        if value is None:
            continue
        hits += 1
        total += value
        if field:
            field_hits[field] = field_hits.get(field, 0) + 1

    matched_field = ""
    if field_hits:
        matched_field = max(field_hits, key=lambda k: field_hits[k])

    if kind == "count":
        if hits > 0:
            return _MetricCandidate(
                value=total,
                method="rows_sum",
                matched_field=matched_field,
                details={"rows_analyzed": len(rows), "rows_with_value": hits},
            )
        return _MetricCandidate(
            value=float(len(rows)),
            method="rows_len_fallback",
            matched_field="",
            details={"rows_analyzed": len(rows), "rows_with_value": 0},
        )

    # amount
    if hits > 0:
        return _MetricCandidate(
            value=total,
            method="rows_sum",
            matched_field=matched_field,
            details={"rows_analyzed": len(rows), "rows_with_value": hits},
        )
    return _MetricCandidate(
        value=None,
        method="rows_no_numeric_fields",
        matched_field="",
        details={"rows_analyzed": len(rows), "rows_with_value": 0},
    )


def _extract_row_value(row: Mapping[str, Any], aliases: Sequence[str]) -> Tuple[Optional[float], str]:
    normalized_row: Dict[str, Tuple[str, Any]] = {}
    for raw_key, raw_value in row.items():
        normalized_row[_normalize_key(raw_key)] = (str(raw_key), raw_value)

    for alias in aliases:
        if alias not in normalized_row:
            continue
        raw_key, raw_value = normalized_row[alias]
        numeric = _safe_float(raw_value)
        if numeric is not None:
            return numeric, raw_key
    return None, ""


def _coerce_metric_value(value: float, kind: str) -> Any:
    safe = value if math.isfinite(value) else 0.0
    safe = max(0.0, safe)
    if kind == "count":
        return int(round(safe))
    return round(float(safe), 2)


def _deep_get(data: Mapping[str, Any], path: Sequence[str]) -> Any:
    current: Any = data
    for token in path:
        if not isinstance(current, Mapping):
            return None
        current = _mapping_get_normalized(current, token)
        if current is None:
            return None
    return current


def _mapping_get_normalized(mapping: Mapping[str, Any], token: str) -> Any:
    needle = _normalize_key(token)
    for key, value in mapping.items():
        if _normalize_key(key) == needle:
            return value
    return None


def _normalize_key(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    text = text.lower()
    text = re.sub(r"[^0-9a-zа-яё]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        numeric = float(value)
        if not math.isfinite(numeric):
            return None
        return numeric
    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None

    text = (
        text.replace("\u00a0", "")
        .replace("\u202f", "")
        .replace(" ", "")
        .replace("₽", "")
        .replace("руб.", "")
        .replace("руб", "")
        .replace("%", "")
    )
    text = re.sub(r"[^0-9,.\-+]", "", text)
    if text in {"", "+", "-", ".", ",", "+.", "-.", "+,", "-,"}:
        return None

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "")
            text = text.replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")

    try:
        numeric = float(text)
    except ValueError:
        return None

    if not math.isfinite(numeric):
        return None
    return numeric


def _append_warning(
    warnings: List[Dict[str, Any]],
    code: str,
    message: str,
    metric: str = "",
    details: Optional[MutableMapping[str, Any]] = None,
) -> None:
    for item in warnings:
        if str(item.get("code")) == code and str(item.get("metric", "")) == metric:
            return

    payload: Dict[str, Any] = {"code": code, "message": message}
    if metric:
        payload["metric"] = metric
    if details:
        payload["details"] = dict(details)
    warnings.append(payload)


__all__ = ["resolve_daily_kpi"]
