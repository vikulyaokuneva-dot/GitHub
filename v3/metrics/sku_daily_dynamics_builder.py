from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Tuple


_MISSING_TEXT = {"", "none", "null", "nan", "n/a", "-", "—"}
_INVALID_SKU_VALUES = {"0", "0.0", "00", "000", "unknown"}

_COMPARISON_METRICS: Tuple[str, ...] = (
    "orders",
    "buyouts",
    "revenue",
    "net_profit",
    "stock",
    "impressions",
    "clicks",
    "ctr",
    "ads_spend",
)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    numeric = _safe_float(value)
    if numeric is None:
        return None
    try:
        return int(round(numeric))
    except (TypeError, ValueError):
        return None


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip().lower()
    return text in _MISSING_TEXT


def _normalize_sku(value: Any) -> str:
    if _is_missing(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        try:
            text = str(int(float(text)))
        except (TypeError, ValueError):
            pass
    if text.strip().lower() in _INVALID_SKU_VALUES:
        return ""
    return text


def _pick_value(row: Mapping[str, Any], keys: Iterable[str]) -> Any:
    if not isinstance(row, Mapping):
        return None
    lowered = {str(k).strip().lower(): v for k, v in row.items()}
    for key in keys:
        if key in row and not _is_missing(row.get(key)):
            return row.get(key)
        lowered_value = lowered.get(str(key).strip().lower())
        if not _is_missing(lowered_value):
            return lowered_value
    return None


def _extract_sku(row: Mapping[str, Any]) -> str:
    return _normalize_sku(
        _pick_value(
            row,
            (
                "sku",
                "seller_sku",
                "supplier_sku",
                "vendor_code",
                "vendorCode",
                "supplierArticle",
                "nm_id",
                "nmId",
                "nmid",
                "артикул",
                "артикул_продавца",
                "артикул_поставщика",
                "код_номенклатуры",
            ),
        )
    )


def _extract_metadata_for_sku(rows: Iterable[Mapping[str, Any]], sku: str) -> Dict[str, Any]:
    meta: Dict[str, Any] = {
        "nm_id": None,
        "vendor_code": None,
        "name": None,
        "brand": None,
        "subject": None,
    }
    for row in rows:
        if _extract_sku(row) != sku:
            continue
        if meta["nm_id"] is None:
            meta["nm_id"] = _pick_value(row, ("nm_id", "nmId", "nmid", "nmID"))
        if meta["vendor_code"] is None:
            meta["vendor_code"] = _pick_value(
                row,
                (
                    "vendor_code",
                    "vendorCode",
                    "supplierArticle",
                    "seller_sku",
                    "supplier_sku",
                    "артикул_продавца",
                    "артикул_поставщика",
                ),
            )
        if meta["name"] is None:
            meta["name"] = _pick_value(
                row,
                ("name", "nm_name", "product_name", "title", "наименование", "товар"),
            )
        if meta["brand"] is None:
            meta["brand"] = _pick_value(row, ("brand", "brand_name", "бренд"))
        if meta["subject"] is None:
            meta["subject"] = _pick_value(
                row,
                ("subject", "subject_name", "category", "категория", "предмет"),
            )
    for key, value in list(meta.items()):
        if _is_missing(value):
            meta[key] = None
        elif value is not None:
            meta[key] = str(value).strip()
    return meta


def _to_metric_map(item: Mapping[str, Any]) -> Dict[str, float | None]:
    return {
        "orders": _safe_float(item.get("orders")),
        "buyouts": _safe_float(item.get("buyouts")),
        "revenue": _safe_float(item.get("revenue")),
        "net_profit": _safe_float(item.get("net_profit")),
        "stock": _safe_float(item.get("stock")),
        "impressions": _safe_float(item.get("impressions")),
        "clicks": _safe_float(item.get("clicks")),
        "ctr": _safe_float(item.get("ctr")),
        "ads_spend": _safe_float(item.get("ads_spend")),
    }


def _pct_delta(current: float, baseline: float) -> float | None:
    if abs(baseline) <= 1e-9:
        if abs(current) <= 1e-9:
            return 0.0
        return None
    return round((current - baseline) / abs(baseline) * 100.0, 2)


def _build_comparison_entry(current: float | None, baseline: float | None, baseline_key: str, days: int | None = None) -> Dict[str, Any] | None:
    if current is None or baseline is None:
        return None
    item: Dict[str, Any] = {
        "value": round(float(current), 4),
        baseline_key: round(float(baseline), 4),
        "delta": round(float(current - baseline), 4),
        "delta_pct": _pct_delta(float(current), float(baseline)),
    }
    if days is not None:
        item["days"] = int(days)
    return item


def _read_metrics_file(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _history_dates_before_run(history_root: Path, run_date: str) -> List[str]:
    daily_dir = history_root / "daily"
    if not daily_dir.is_dir():
        return []
    dates = [item.name for item in daily_dir.iterdir() if item.is_dir()]
    return sorted([d for d in dates if d < run_date])


def _load_history_sku_rows(history_root: Path, run_date: str) -> Dict[str, Dict[str, Dict[str, Any]]]:
    series: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for snapshot_date in _history_dates_before_run(history_root, run_date):
        metrics_path = history_root / "daily" / snapshot_date / "metrics.json"
        payload = _read_metrics_file(metrics_path)
        rows = payload.get("sku_metrics", [])
        if not isinstance(rows, list):
            continue
        date_bucket: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            sku = _normalize_sku(row.get("sku"))
            if not sku:
                continue
            date_bucket[sku] = dict(row)
        series[snapshot_date] = date_bucket
    return series


def _previous_day_key(run_date: str) -> str | None:
    try:
        parsed = date.fromisoformat(run_date)
    except ValueError:
        return None
    return (parsed - timedelta(days=1)).isoformat()


def _build_previous_day_comparison(
    *,
    sku: str,
    current_metrics: Dict[str, float | None],
    history_rows_by_date: Dict[str, Dict[str, Dict[str, Any]]],
    run_date: str,
) -> Dict[str, Any]:
    previous_key = _previous_day_key(run_date)
    if not previous_key:
        return {}
    previous_rows = history_rows_by_date.get(previous_key, {})
    if not isinstance(previous_rows, dict):
        return {}
    previous_row = previous_rows.get(sku, {})
    if not isinstance(previous_row, dict):
        return {}

    baseline = {
        "orders": _safe_float(previous_row.get("orders")),
        "buyouts": _safe_float(previous_row.get("buys", previous_row.get("buyouts"))),
        "revenue": _safe_float(previous_row.get("revenue")),
        "net_profit": _safe_float(previous_row.get("profit", previous_row.get("net_profit"))),
        "stock": _safe_float(previous_row.get("stock")),
        "impressions": _safe_float(previous_row.get("impressions")),
        "clicks": _safe_float(previous_row.get("clicks")),
        "ctr": _safe_float(previous_row.get("ctr")),
        "ads_spend": _safe_float(previous_row.get("ads_spend")),
    }
    out: Dict[str, Any] = {}
    for metric in _COMPARISON_METRICS:
        item = _build_comparison_entry(current_metrics.get(metric), baseline.get(metric), "previous")
        if item is not None:
            out[metric] = item
    return out


def _build_7d_comparison(
    *,
    sku: str,
    current_metrics: Dict[str, float | None],
    history_rows_by_date: Dict[str, Dict[str, Dict[str, Any]]],
) -> Dict[str, Any]:
    dates = sorted(history_rows_by_date.keys())
    if not dates:
        return {}
    recent_dates = dates[-7:]
    metric_buckets: Dict[str, List[float]] = {metric: [] for metric in _COMPARISON_METRICS}
    for snapshot_date in recent_dates:
        snapshot_rows = history_rows_by_date.get(snapshot_date, {})
        if not isinstance(snapshot_rows, dict):
            continue
        row = snapshot_rows.get(sku, {})
        if not isinstance(row, dict):
            continue
        source_values = {
            "orders": _safe_float(row.get("orders")),
            "buyouts": _safe_float(row.get("buys", row.get("buyouts"))),
            "revenue": _safe_float(row.get("revenue")),
            "net_profit": _safe_float(row.get("profit", row.get("net_profit"))),
            "stock": _safe_float(row.get("stock")),
            "impressions": _safe_float(row.get("impressions")),
            "clicks": _safe_float(row.get("clicks")),
            "ctr": _safe_float(row.get("ctr")),
            "ads_spend": _safe_float(row.get("ads_spend")),
        }
        for metric, value in source_values.items():
            if value is not None:
                metric_buckets[metric].append(float(value))

    out: Dict[str, Any] = {}
    for metric in _COMPARISON_METRICS:
        values = metric_buckets.get(metric, [])
        if not values:
            continue
        avg_value = sum(values) / float(len(values))
        entry = _build_comparison_entry(
            current_metrics.get(metric),
            avg_value,
            "avg_7d",
            days=len(values),
        )
        if entry is not None:
            out[metric] = entry
    return out


def _value_or_none(value: float | int | None, *, digits: int = 2) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    return round(float(value), digits)


def build_sku_daily_dynamics(
    *,
    run_date: str,
    metrics: Dict[str, Any],
    sales_rows: List[Dict[str, Any]] | None = None,
    ads_rows: List[Dict[str, Any]] | None = None,
    stocks_rows: List[Dict[str, Any]] | None = None,
    history_root: str | Path | None = None,
) -> Dict[str, Any]:
    safe_metrics = metrics if isinstance(metrics, dict) else {}
    safe_sales = [row for row in (sales_rows or []) if isinstance(row, dict)]
    safe_ads = [row for row in (ads_rows or []) if isinstance(row, dict) and not bool(row.get("_is_campaign_total", False))]
    safe_stocks = [row for row in (stocks_rows or []) if isinstance(row, dict)]

    sku_metrics_raw = safe_metrics.get("sku_metrics", [])
    sku_metrics_rows = [row for row in sku_metrics_raw if isinstance(row, dict)] if isinstance(sku_metrics_raw, list) else []
    sku_metrics_map: Dict[str, Dict[str, Any]] = {}
    for row in sku_metrics_rows:
        sku = _normalize_sku(row.get("sku"))
        if sku:
            sku_metrics_map[sku] = dict(row)

    sales_skus = {_extract_sku(row) for row in safe_sales if _extract_sku(row)}
    ads_skus = {_extract_sku(row) for row in safe_ads if _extract_sku(row)}
    stocks_skus = {_extract_sku(row) for row in safe_stocks if _extract_sku(row)}

    all_skus = sorted(
        {
            sku
            for sku in (
                list(sku_metrics_map.keys()) + list(sales_skus) + list(ads_skus) + list(stocks_skus)
            )
            if sku
        }
    )

    all_source_rows: List[Mapping[str, Any]] = []
    all_source_rows.extend(safe_sales)
    all_source_rows.extend(safe_ads)
    all_source_rows.extend(safe_stocks)

    history_rows_by_date: Dict[str, Dict[str, Dict[str, Any]]] = {}
    if history_root:
        history_rows_by_date = _load_history_sku_rows(Path(history_root), run_date)

    items: List[Dict[str, Any]] = []
    for sku in all_skus:
        row = sku_metrics_map.get(sku, {})
        has_sales = sku in sales_skus
        has_ads = sku in ads_skus
        has_stock = sku in stocks_skus
        has_financial_base = has_sales and isinstance(row, dict) and bool(row)

        metadata = _extract_metadata_for_sku(all_source_rows, sku)

        orders_value = _safe_int(row.get("orders")) if has_sales else None
        buyouts_value = _safe_int(row.get("buys", row.get("buyouts"))) if has_sales else None
        revenue_value = _safe_float(row.get("revenue")) if has_sales else None
        cost_price_value = _safe_float(row.get("cost_price")) if has_financial_base else None
        wb_commission_value = _safe_float(row.get("wb_commission")) if has_financial_base else None
        gross_profit_value = (
            _value_or_none((revenue_value or 0.0) - (cost_price_value or 0.0) - (wb_commission_value or 0.0), digits=2)
            if has_financial_base and revenue_value is not None and cost_price_value is not None and wb_commission_value is not None
            else None
        )
        net_profit_value = _safe_float(row.get("profit", row.get("net_profit"))) if has_financial_base else None
        ads_spend_value = _safe_float(row.get("ads_spend")) if has_ads else None
        stock_value = _safe_int(row.get("stock")) if has_stock else None
        impressions_value = _safe_int(row.get("impressions")) if has_ads else None
        clicks_value = _safe_int(row.get("clicks")) if has_ads else None
        ctr_value = _safe_float(row.get("ctr")) if has_ads else None

        avg_check_value = None
        if revenue_value is not None and buyouts_value is not None and buyouts_value > 0:
            avg_check_value = revenue_value / float(buyouts_value)

        margin_pct_value = None
        if net_profit_value is not None and revenue_value is not None and revenue_value > 0:
            margin_pct_value = net_profit_value / revenue_value * 100.0

        profitability_pct_value = None
        if net_profit_value is not None and cost_price_value is not None and cost_price_value > 0:
            profitability_pct_value = net_profit_value / cost_price_value * 100.0

        item: Dict[str, Any] = {
            "sku": sku,
            "nm_id": metadata["nm_id"],
            "vendor_code": metadata["vendor_code"],
            "name": metadata["name"],
            "brand": metadata["brand"],
            "subject": metadata["subject"],
            "impressions": impressions_value,
            "clicks": clicks_value,
            "ctr": _value_or_none(ctr_value, digits=2),
            "cart_count": None,
            "orders": orders_value,
            "buyouts": buyouts_value,
            "revenue": _value_or_none(revenue_value, digits=2),
            "gross_profit": _value_or_none(gross_profit_value, digits=2),
            "net_profit": _value_or_none(net_profit_value, digits=2),
            "ads_spend": _value_or_none(ads_spend_value, digits=2),
            "stock": stock_value,
            "avg_check": _value_or_none(avg_check_value, digits=2),
            "margin_pct": _value_or_none(margin_pct_value, digits=2),
            "profitability_pct": _value_or_none(profitability_pct_value, digits=2),
            "vs_previous_day": {},
            "vs_7d_avg": {},
            "data_confidence": "unknown",
            "source_completeness": "partial",
            "source_flags": {},
            "notes": [],
        }

        current_metric_map = _to_metric_map(item)
        item["vs_previous_day"] = _build_previous_day_comparison(
            sku=sku,
            current_metrics=current_metric_map,
            history_rows_by_date=history_rows_by_date,
            run_date=run_date,
        )
        item["vs_7d_avg"] = _build_7d_comparison(
            sku=sku,
            current_metrics=current_metric_map,
            history_rows_by_date=history_rows_by_date,
        )

        available_metric_count = sum(1 for key in _COMPARISON_METRICS if current_metric_map.get(key) is not None)
        if available_metric_count == 0:
            data_confidence = "unknown"
            source_completeness = "partial"
        elif available_metric_count >= 7:
            data_confidence = "high"
            source_completeness = "full"
        elif available_metric_count >= 4:
            data_confidence = "medium"
            source_completeness = "partial"
        else:
            data_confidence = "low"
            source_completeness = "partial"

        item["data_confidence"] = data_confidence
        item["source_completeness"] = source_completeness
        item["source_flags"] = {
            "sales": "available" if has_sales else "missing",
            "ads": "available" if has_ads else "missing",
            "stocks": "available" if has_stock else "missing",
            "history_previous_day": "available" if bool(item["vs_previous_day"]) else "missing",
            "history_7d": "available" if bool(item["vs_7d_avg"]) else "missing",
        }
        if not has_financial_base:
            item["notes"].append("financial_base_missing")
        if not has_ads:
            item["notes"].append("ads_data_missing")
        if not has_stock:
            item["notes"].append("stock_data_missing")

        items.append(item)

    return {
        "date": str(run_date or ""),
        "sku_count": len(items),
        "items": items,
    }
