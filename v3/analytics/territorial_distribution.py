from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping


_WAREHOUSE_PATTERNS: List[tuple[str, str]] = [
    ("электросталь", "Электросталь"),
    ("краснодар", "Краснодар"),
    ("тула", "Тула"),
    ("невинномысск", "Невинномысск"),
    ("котовск", "Котовск"),
    ("екатеринбург", "Екатеринбург"),
    ("рязань", "Рязань"),
    ("самара", "Самара"),
    ("волгоград", "Волгоград"),
    ("барнаул", "Барнаул"),
    ("воронеж", "Воронеж"),
    ("казань", "Казань"),
    ("коледино", "Коледино"),
    ("подольск", "Подольск"),
    ("санкт петербург", "Санкт-Петербург"),
    ("петербург", "Санкт-Петербург"),
    ("новосибирск", "Новосибирск"),
    ("хабаровск", "Хабаровск"),
    ("уссурийск", "Уссурийск"),
    ("красноярск", "Красноярск"),
    ("иркутск", "Иркутск"),
    ("тюмень", "Тюмень"),
    ("омск", "Омск"),
    ("саратов", "Саратов"),
    ("уфа", "Уфа"),
    ("нижний новгород", "Нижний Новгород"),
]

_INVALID_WAREHOUSE_TOKENS = (
    "федеральный округ",
    "округ мп",
    "россия",
    "страна",
)

_VALID_STATUSES = {"balanced", "moderate_mismatch", "misallocated"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(" ", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _warehouse_token(value: str) -> str:
    text = value.lower().replace("ё", "е")
    text = re.sub(r"[^a-zа-я0-9]+", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def normalize_warehouse_name(value: Any) -> str | None:
    raw = _clean_text(value)
    if not raw:
        return None

    token = _warehouse_token(raw)
    if not token:
        return None
    if any(noise in token for noise in _INVALID_WAREHOUSE_TOKENS):
        return None

    for pattern, canonical in _WAREHOUSE_PATTERNS:
        if pattern in token:
            return canonical
    return None


def _extract_rows(container: Any, keys: Iterable[str]) -> List[Dict[str, Any]]:
    if isinstance(container, list):
        return [row for row in container if isinstance(row, dict)]
    if not isinstance(container, dict):
        return []
    for key in keys:
        value = container.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def _extract_sku_metrics(metrics: Any) -> List[Dict[str, Any]]:
    return _extract_rows(metrics, ("sku_metrics", "items", "skus"))


def _resolve_qty(row: Mapping[str, Any], candidates: Iterable[str]) -> float:
    for key in candidates:
        value = _as_float(row.get(key))
        if value is not None:
            return max(value, 0.0)
    return 0.0


def _resolve_sku_token(value: Any) -> str:
    token = _clean_text(value)
    if not token:
        return ""
    if re.fullmatch(r"\d+(\.0+)?", token):
        return token.split(".", 1)[0]
    normalized = token.lower().replace("ё", "е")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _resolve_warehouse_from_row(row: Mapping[str, Any]) -> str | None:
    for key in ("warehouse", "warehouse_name", "stock_warehouse", "office", "office_name"):
        normalized = normalize_warehouse_name(row.get(key))
        if normalized:
            return normalized
    return None


def _build_sku_alias_map(sales_rows: List[Dict[str, Any]], metric_skus: set[str]) -> Dict[str, str]:
    weighted_links: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in sales_rows:
        sku = _resolve_sku_token(row.get("sku"))
        seller_sku = _resolve_sku_token(row.get("seller_sku"))
        if not sku:
            continue
        qty = _resolve_qty(row, ("buys", "sales_count", "orders", "quantity"))
        if seller_sku:
            weighted_links[seller_sku][sku] += qty if qty > 0 else 1.0
        weighted_links[sku][sku] += qty if qty > 0 else 1.0

    alias_map: Dict[str, str] = {}
    for alias, links in weighted_links.items():
        if not links:
            continue
        target = max(links.items(), key=lambda item: item[1])[0]
        alias_map[alias] = target
    for sku in metric_skus:
        alias_map.setdefault(sku, sku)
    return alias_map


def extract_demand_by_warehouse(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    demand: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in rows:
        sku = _resolve_sku_token(row.get("sku"))
        if not sku:
            continue

        buys = _resolve_qty(row, ("buys", "sales_count", "orders", "quantity"))
        if buys <= 0:
            continue

        warehouse = _resolve_warehouse_from_row(row)
        if not warehouse:
            continue
        demand[sku][warehouse] += buys
    return {sku: dict(warehouses) for sku, warehouses in demand.items()}


def _extract_stock_map_from_row(row: Mapping[str, Any]) -> Dict[str, float]:
    by_warehouse: Dict[str, float] = {}

    raw_map = row.get("stock_by_warehouse")
    if isinstance(raw_map, dict):
        for key, value in raw_map.items():
            warehouse = normalize_warehouse_name(key)
            stock_value = _as_float(value)
            if warehouse and stock_value is not None and stock_value > 0:
                by_warehouse[warehouse] = by_warehouse.get(warehouse, 0.0) + stock_value
        if by_warehouse:
            return by_warehouse

    warehouse = _resolve_warehouse_from_row(row)
    stock = _resolve_qty(row, ("stock", "qty", "quantity", "stock_qty"))
    if warehouse and stock > 0:
        by_warehouse[warehouse] = stock
    return by_warehouse


def extract_stock_by_warehouse(
    stocks_raw: Dict[str, Any] | List[Dict[str, Any]] | None,
    sku_alias_map: Dict[str, str] | None = None,
) -> Dict[str, Dict[str, float]]:
    rows = _extract_rows(stocks_raw, ("stocks_rows", "items", "rows"))
    stock_by_sku: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    aliases = sku_alias_map or {}

    for row in rows:
        raw_sku_candidates = (
            row.get("sku"),
            row.get("seller_sku"),
            row.get("nm_id"),
            row.get("nmid"),
            row.get("vendor_code"),
            row.get("offer_id"),
        )
        sku = ""
        for candidate in raw_sku_candidates:
            token = _resolve_sku_token(candidate)
            if not token:
                continue
            sku = aliases.get(token, token)
            if sku:
                break
        if not sku:
            continue

        warehouse_map = _extract_stock_map_from_row(row)
        if not warehouse_map:
            continue

        for warehouse, value in warehouse_map.items():
            stock_by_sku[sku][warehouse] += value

    return {sku: dict(warehouses) for sku, warehouses in stock_by_sku.items()}


def _shares(values: Dict[str, float]) -> Dict[str, float]:
    total = sum(max(v, 0.0) for v in values.values())
    if total <= 0:
        return {}
    return {key: round(max(value, 0.0) / total, 3) for key, value in values.items() if value > 0}


def _dominant_warehouses(share_by_warehouse: Dict[str, float], threshold: float = 0.2) -> List[str]:
    dominant = [
        (warehouse, float(share))
        for warehouse, share in share_by_warehouse.items()
        if _as_float(share) is not None and float(share) > threshold
    ]
    dominant.sort(key=lambda item: (-item[1], item[0]))
    return [warehouse for warehouse, _ in dominant]


def compute_distribution_gap(demand_share: Dict[str, float], stock_share: Dict[str, float]) -> float:
    warehouses = set(demand_share) | set(stock_share)
    if not warehouses:
        return 0.0
    return 0.5 * sum(abs(float(demand_share.get(wh, 0.0)) - float(stock_share.get(wh, 0.0))) for wh in warehouses)


def compute_ktr(demand_share: Dict[str, float], stock_share: Dict[str, float]) -> float:
    return 1.0 + compute_distribution_gap(demand_share, stock_share)


def _resolve_confidence(total_buys: float) -> str:
    if total_buys < 3:
        return "low"
    if total_buys <= 5:
        return "medium"
    return "high"


def compute_sku_distribution(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for row in rows:
        sku = _resolve_sku_token(row.get("sku"))
        if not sku:
            continue

        demand_by_warehouse = {
            wh: round(float(value), 3)
            for wh, value in (row.get("demand_by_warehouse") or {}).items()
            if _as_float(value) is not None and float(value) > 0
        }
        stock_by_warehouse = {
            wh: round(float(value), 3)
            for wh, value in (row.get("stock_by_warehouse") or {}).items()
            if _as_float(value) is not None and float(value) > 0
        }
        total_buys = round(sum(demand_by_warehouse.values()), 3)
        total_stock = round(sum(stock_by_warehouse.values()), 3)
        confidence = _resolve_confidence(total_buys)

        demand_share = _shares(demand_by_warehouse)
        stock_share = _shares(stock_by_warehouse)
        dominant_demand_warehouses = _dominant_warehouses(demand_share)
        dominant_stock_warehouses = _dominant_warehouses(stock_share)

        status: str
        gap: float | None = None
        ktr: float | None = None

        if total_buys <= 0 and total_stock <= 0:
            status = "insufficient_distribution_data"
        elif total_buys <= 0:
            status = "no_demand_data"
        elif total_stock <= 0:
            status = "no_stock_data"
        elif not demand_share or not stock_share:
            status = "insufficient_distribution_data"
        else:
            gap = round(compute_distribution_gap(demand_share, stock_share), 3)
            ktr = round(1.0 + gap, 3)
            if ktr <= 1.05:
                status = "balanced"
            elif ktr <= 1.25:
                status = "moderate_mismatch"
            else:
                status = "misallocated"

        items.append(
            {
                "sku": sku,
                "total_buys": int(round(total_buys)),
                "total_stock": int(round(total_stock)),
                "demand_by_warehouse": demand_by_warehouse,
                "stock_by_warehouse": stock_by_warehouse,
                "demand_share_by_warehouse": demand_share,
                "stock_share_by_warehouse": stock_share,
                "distribution_gap": gap,
                "ktr": ktr,
                "status": status,
                "confidence": confidence,
                "low_sample_warning": confidence == "low",
                "dominant_demand_warehouses": dominant_demand_warehouses,
                "dominant_stock_warehouses": dominant_stock_warehouses,
                "relocation_hint": None,
            }
        )

    items.sort(key=lambda item: (_as_float(item.get("ktr")) or 0.0, str(item.get("sku") or "")), reverse=True)
    return items


def build_territorial_distribution(
    metrics: Dict[str, Any],
    stocks_raw: Dict[str, Any] | List[Dict[str, Any]] | None = None,
    seller_id: str | None = None,
    run_date: str | None = None,
) -> Dict[str, Any]:
    metric_rows = _extract_sku_metrics(metrics)
    metric_skus = {
        _resolve_sku_token(row.get("sku"))
        for row in metric_rows
        if isinstance(row, dict) and _resolve_sku_token(row.get("sku"))
    }

    sales_rows = _extract_rows(
        metrics,
        ("sales_rows", "sales_raw", "raw_sales_rows", "sales_report_rows"),
    )
    stock_rows_source: Dict[str, Any] | List[Dict[str, Any]] | None = stocks_raw
    if stock_rows_source is None:
        stock_rows_source = metrics.get("stocks_rows") if isinstance(metrics, dict) else None

    demand_by_sku = extract_demand_by_warehouse(sales_rows)
    alias_map = _build_sku_alias_map(sales_rows, metric_skus)
    stock_by_sku = extract_stock_by_warehouse(stock_rows_source, sku_alias_map=alias_map)

    known_skus = set(metric_skus) | set(demand_by_sku.keys())
    if known_skus:
        sku_pool = sorted(known_skus)
    else:
        sku_pool = sorted(set(stock_by_sku.keys()))
    raw_rows: List[Dict[str, Any]] = []
    for sku in sku_pool:
        raw_rows.append(
            {
                "sku": sku,
                "demand_by_warehouse": demand_by_sku.get(sku, {}),
                "stock_by_warehouse": stock_by_sku.get(sku, {}),
            }
        )

    items = compute_sku_distribution(raw_rows)

    resolved_seller_id = str(seller_id or (metrics.get("seller_id") if isinstance(metrics, dict) else "") or "").strip()
    resolved_run_date = str(run_date or (metrics.get("run_date") if isinstance(metrics, dict) else "") or "").strip()
    sku_total = len(items)
    sku_with_ktr = sum(1 for item in items if _as_float(item.get("ktr")) is not None)
    balanced_count = sum(1 for item in items if item.get("status") == "balanced")
    moderate_count = sum(1 for item in items if item.get("status") == "moderate_mismatch")
    misallocated_count = sum(1 for item in items if item.get("status") == "misallocated")
    insufficient_distribution_data_count = sum(
        1 for item in items if item.get("status") == "insufficient_distribution_data"
    )
    no_stock_data_count = sum(1 for item in items if item.get("status") == "no_stock_data")
    insufficient_total_count = sum(1 for item in items if item.get("status") not in _VALID_STATUSES)
    valid_ktr_values = [float(item.get("ktr")) for item in items if _as_float(item.get("ktr")) is not None]
    avg_ktr = round(sum(valid_ktr_values) / len(valid_ktr_values), 3) if valid_ktr_values else 0.0

    top_misaligned = [
        str(item.get("sku") or "")
        for item in sorted(
            [row for row in items if row.get("status") == "misallocated"],
            key=lambda row: float(row.get("ktr") or 0.0),
            reverse=True,
        )[:5]
        if str(item.get("sku") or "").strip()
    ]

    return {
        "metadata": {
            "engine": "territorial_distribution_engine",
            "version": "1.0",
            "seller_id": resolved_seller_id,
            "run_date": resolved_run_date,
            "generated_at": _utc_now_iso(),
            "source_artifacts": ["metrics.json"],
        },
        "summary": {
            "sku_total": sku_total,
            "sku_with_ktr": sku_with_ktr,
            "balanced_count": balanced_count,
            "moderate_mismatch_count": moderate_count,
            "misallocated_count": misallocated_count,
            "insufficient_distribution_data_count": insufficient_distribution_data_count,
            "no_stock_data_count": no_stock_data_count,
            "insufficient_total_count": insufficient_total_count,
            "avg_ktr": avg_ktr,
            "top_misaligned_skus": top_misaligned,
        },
        "skus": items,
    }


def save_territorial_distribution(output_path: Path, data: Dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
