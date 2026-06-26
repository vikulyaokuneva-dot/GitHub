from __future__ import annotations

import json
import os
from typing import Any, Dict, List


class CoreSnapshotBridgeFatalError(RuntimeError):
    """Raised when the core snapshot contract cannot be loaded safely."""


def resolve_core_snapshot_paths(*, repo_root: str, seller_id: str, run_date: str) -> Dict[str, str]:
    artifacts_dir = os.path.join(repo_root, "cabinets", seller_id, "artifacts", "wb_api_core", run_date)
    return {
        "artifacts_dir": artifacts_dir,
        "snapshot_path": os.path.join(artifacts_dir, "snapshot.json"),
        "debug_path": os.path.join(artifacts_dir, "debug.json"),
    }


def _load_json_dict_required(path: str, *, label: str) -> Dict[str, Any]:
    if not os.path.isfile(path):
        raise CoreSnapshotBridgeFatalError(f"core_snapshot_{label}_missing: {path}")
    try:
        with open(path, "r", encoding="utf-8-sig") as file:
            payload = json.load(file)
    except Exception as exc:
        raise CoreSnapshotBridgeFatalError(f"core_snapshot_{label}_invalid_json: {path}") from exc
    if not isinstance(payload, dict):
        raise CoreSnapshotBridgeFatalError(f"core_snapshot_{label}_not_object: {path}")
    return payload


def _load_json_dict_optional(path: str) -> Dict[str, Any] | None:
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8-sig") as file:
            payload = json.load(file)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def load_core_snapshot_artifacts(*, paths: Dict[str, str]) -> Dict[str, Any]:
    snapshot_path = str(paths.get("snapshot_path") or "").strip()
    debug_path = str(paths.get("debug_path") or "").strip()
    return {
        "snapshot": _load_json_dict_required(snapshot_path, label="snapshot"),
        "debug": _load_json_dict_optional(debug_path),
    }


def _warning(
    code: str,
    message: str,
    *,
    level: str = "warning",
    block: str = "",
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "code": str(code or "").strip(),
        "message": str(message or "").strip(),
        "level": str(level or "warning").strip() or "warning",
    }
    clean_block = str(block or "").strip()
    if clean_block:
        payload["block"] = clean_block
    return payload


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_float_value(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_warning_items(items: Any, *, default_block: str = "") -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not isinstance(items, list):
        return normalized
    for item in items:
        if isinstance(item, dict):
            code = str(item.get("code") or "").strip() or "core_snapshot_warning"
            message = str(item.get("message") or "").strip()
            if not message:
                continue
            normalized.append(
                {
                    "code": code,
                    "message": message,
                    "level": str(item.get("level") or "warning").strip() or "warning",
                    "block": str(item.get("block") or default_block).strip(),
                }
            )
            continue
        message = str(item or "").strip()
        if not message:
            continue
        normalized.append(_warning("core_snapshot_warning", message, block=default_block))
    return normalized


def validate_core_snapshot(
    *,
    snapshot: Dict[str, Any],
    debug: Dict[str, Any] | None,
    seller_id: str,
    run_date: str,
) -> List[Dict[str, Any]]:
    required_keys = (
        "seller_id",
        "run_date",
        "operational_date",
        "source_mode",
        "cabinet_commerce_daily",
        "finance_final_daily",
        "live_operational",
    )
    missing = [key for key in required_keys if key not in snapshot]
    if missing:
        raise CoreSnapshotBridgeFatalError(
            "core_snapshot_missing_required_keys: " + ", ".join(sorted(missing))
        )
    snapshot_seller_id = str(snapshot.get("seller_id") or "").strip()
    snapshot_run_date = str(snapshot.get("run_date") or "").strip()
    if snapshot_seller_id != str(seller_id or "").strip():
        raise CoreSnapshotBridgeFatalError(
            f"core_snapshot_seller_mismatch: expected={seller_id} actual={snapshot_seller_id}"
        )
    if snapshot_run_date != str(run_date or "").strip():
        raise CoreSnapshotBridgeFatalError(
            f"core_snapshot_run_date_mismatch: expected={run_date} actual={snapshot_run_date}"
        )

    warnings: List[Dict[str, Any]] = []
    if debug is None:
        warnings.append(
            _warning(
                "core_debug_missing",
                "debug.json is missing or unreadable; proceeding with snapshot-only contract.",
                block="meta",
            )
        )
    source_mode = str(snapshot.get("source_mode") or "").strip().lower()
    if source_mode not in {"wb_api_core_v2", "wb_api_core"}:
        warnings.append(
            _warning(
                "core_snapshot_unexpected_source_mode",
                f"snapshot source_mode={source_mode or 'unknown'} differs from expected wb_api_core_v2.",
                block="meta",
            )
        )
    return warnings


def _cabinet_status(cabinet: Dict[str, Any], cabinet_debug: Dict[str, Any]) -> str:
    if not bool(cabinet.get("available", False)):
        return "unavailable"
    if bool(cabinet_debug.get("cache_hit", False)) or bool(cabinet_debug.get("cache_fallback_used", False)):
        return "cached"
    return "ok"


def _finance_status(finance: Dict[str, Any]) -> str:
    if not bool(finance.get("available", False)):
        return "unavailable"
    if finance.get("date_aligned") is False:
        return "lagged"
    return "ok"


def _live_status(*, orders: Dict[str, Any], sales: Dict[str, Any], stocks: Dict[str, Any]) -> str:
    flags = [
        bool(orders.get("available", False)),
        bool(sales.get("available", False)),
        bool(stocks.get("available", False)),
    ]
    if all(flags):
        return "ok"
    if any(flags):
        return "partial"
    return "unavailable"


def build_core_report_payload(
    *,
    snapshot: Dict[str, Any],
    debug: Dict[str, Any] | None,
    seller_id: str,
    run_date: str,
    paths: Dict[str, str],
    validation_warnings: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    warnings: List[Dict[str, Any]] = list(validation_warnings or [])
    debug_payload = _safe_dict(debug)
    endpoints = _safe_dict(debug_payload.get("endpoints"))

    cabinet = _safe_dict(snapshot.get("cabinet_commerce_daily"))
    finance = _safe_dict(snapshot.get("finance_final_daily"))
    live_operational = _safe_dict(snapshot.get("live_operational"))
    live_orders = _safe_dict(live_operational.get("orders"))
    live_sales = _safe_dict(live_operational.get("sales"))
    live_stocks = _safe_dict(live_operational.get("stocks"))

    cabinet_debug = _safe_dict(endpoints.get("cabinet_commerce"))
    finance_debug = _safe_dict(endpoints.get("finance_final"))
    orders_debug = _safe_dict(endpoints.get("orders"))
    sales_debug = _safe_dict(endpoints.get("sales"))
    stocks_debug = _safe_dict(endpoints.get("stocks"))

    cabinet_status = _cabinet_status(cabinet, cabinet_debug)
    finance_status = _finance_status(finance)
    live_status = _live_status(orders=live_orders, sales=live_sales, stocks=live_stocks)

    warnings.extend(_normalize_warning_items(debug_payload.get("warnings"), default_block="meta"))

    if cabinet_status == "unavailable":
        warnings.append(
            _warning(
                "cabinet_commerce_unavailable",
                "cabinet_commerce_daily is unavailable in core snapshot.",
                block="cabinet_commerce",
            )
        )
    if finance_status == "unavailable":
        warnings.append(
            _warning(
                "finance_final_unavailable",
                "finance_final_daily is unavailable in core snapshot.",
                block="finance_final",
            )
        )
    elif finance_status == "lagged":
        warnings.append(
            _warning(
                "finance_final_lagged",
                "finance_final_daily actual_date differs from operational_date.",
                block="finance_final",
            )
        )
    if live_status == "partial":
        warnings.append(
            _warning(
                "live_operational_partial",
                "live_operational contains only a subset of orders/sales/stocks blocks.",
                block="live_operational",
            )
        )
    elif live_status == "unavailable":
        warnings.append(
            _warning(
                "live_operational_unavailable",
                "live_operational is unavailable in core snapshot.",
                block="live_operational",
            )
        )

    deduped_warnings: List[Dict[str, Any]] = []
    seen_warning_keys: set[tuple[str, str]] = set()
    for item in warnings:
        code = str(item.get("code") or "").strip()
        message = str(item.get("message") or "").strip()
        key = (code, message)
        if not code and not message:
            continue
        if key in seen_warning_keys:
            continue
        seen_warning_keys.add(key)
        deduped_warnings.append(item)

    return {
        "meta": {
            "seller_id": seller_id,
            "report_date": run_date,
            "operational_date": str(snapshot.get("operational_date") or "").strip(),
            "timezone": str(snapshot.get("timezone") or "").strip(),
            "source_mode": "core_snapshot",
            "generated_at": None,
            "artifacts_dir": str(paths.get("artifacts_dir") or "").strip(),
            "snapshot_path": str(paths.get("snapshot_path") or "").strip(),
            "debug_path": str(paths.get("debug_path") or "").strip(),
        },
        "cabinet_commerce": {
            "source": str(cabinet.get("source") or "").strip(),
            "status": cabinet_status,
            "available": bool(cabinet.get("available", False)),
            "target_date": cabinet.get("target_date"),
            "orders_count": cabinet.get("orders_count"),
            "orders_amount": cabinet.get("orders_amount"),
            "buyouts_count": cabinet.get("buyouts_count"),
            "buyouts_amount": cabinet.get("buyouts_amount"),
        },
        "finance_final": {
            "source": str(finance.get("source") or "").strip(),
            "status": finance_status,
            "available": bool(finance.get("available", False)),
            "target_date": finance.get("target_date"),
            "actual_date": finance.get("actual_date"),
            "date_aligned": finance.get("date_aligned"),
            "buyouts_count": None,
            "buyouts_amount": None,
            "gross_revenue": finance.get("gross_revenue"),
            "realized_sales_qty": finance.get("realized_sales_qty"),
            "realized_sales_revenue": finance.get("realized_sales_revenue"),
            "seller_payout": finance.get("seller_payout"),
            "wb_commission": finance.get("wb_commission"),
            "deliveries_qty": finance.get("deliveries_qty"),
            "returns_qty": finance.get("returns_qty"),
            "logistics": finance.get("logistics"),
            "logistics_amount": finance.get("logistics_amount"),
            "storage": finance.get("storage"),
            "penalties": finance.get("penalties"),
            "deductions": finance.get("deductions"),
            "acquiring": finance.get("acquiring"),
            "tax": finance.get("tax"),
        },
        "live_operational": {
            "status": live_status,
            "orders": {
                "source": str(live_orders.get("source") or "").strip(),
                "available": bool(live_orders.get("available", False)),
                "target_date": live_orders.get("target_date"),
                "count": live_orders.get("count"),
                "amount": live_orders.get("amount"),
            },
            "sales": {
                "source": str(live_sales.get("source") or "").strip(),
                "available": bool(live_sales.get("available", False)),
                "target_date": live_sales.get("target_date"),
                "count": live_sales.get("count"),
                "amount": live_sales.get("amount"),
            },
            "stocks": {
                "source": str(live_stocks.get("source") or "").strip(),
                "available": bool(live_stocks.get("available", False)),
                "snapshot_kind": str(live_stocks.get("snapshot_kind") or "").strip(),
                "operational_date_reference": live_stocks.get("operational_date_reference"),
                "snapshot_date": live_stocks.get("snapshot_date"),
                "total_units": live_stocks.get("total_units"),
            },
        },
        "warnings": deduped_warnings,
        "source_flags": {
            "debug_present": bool(debug_payload),
            "cabinet_commerce_cache_hit": bool(cabinet_debug.get("cache_hit", False)),
            "cabinet_commerce_cache_fallback_used": bool(cabinet_debug.get("cache_fallback_used", False)),
            "cabinet_commerce_retry_count": int(cabinet_debug.get("retry_count", 0) or 0),
            "cabinet_commerce_retry_delays": list(cabinet_debug.get("retry_delays", []) or []),
            "cabinet_commerce_final_failure_reason": str(cabinet_debug.get("final_failure_reason") or "").strip(),
            "finance_date_aligned": finance.get("date_aligned"),
            "finance_actual_date": finance.get("actual_date"),
            "finance_rows_loaded": int(finance_debug.get("rows_loaded", 0) or 0),
            "live_orders_available": bool(live_orders.get("available", False)),
            "live_orders_rows_loaded": int(orders_debug.get("rows_loaded", 0) or 0),
            "live_sales_available": bool(live_sales.get("available", False)),
            "live_sales_rows_loaded": int(sales_debug.get("rows_loaded", 0) or 0),
            "live_stocks_available": bool(live_stocks.get("available", False)),
            "live_stocks_rows_loaded": int(stocks_debug.get("rows_loaded", 0) or 0),
            "live_stocks_snapshot_date": str(live_stocks.get("snapshot_date") or "").strip(),
        },
    }


def build_core_snapshot_stage_view(core_report_payload: Dict[str, Any]) -> Dict[str, Any]:
    meta = _safe_dict(core_report_payload.get("meta"))
    cabinet = _safe_dict(core_report_payload.get("cabinet_commerce"))
    finance = _safe_dict(core_report_payload.get("finance_final"))
    live_operational = _safe_dict(core_report_payload.get("live_operational"))
    source_flags = _safe_dict(core_report_payload.get("source_flags"))

    live_orders = _safe_dict(live_operational.get("orders"))
    live_sales = _safe_dict(live_operational.get("sales"))
    live_stocks = _safe_dict(live_operational.get("stocks"))

    cabinet_source = str(cabinet.get("source") or "unknown")
    finance_source = str(finance.get("source") or "unknown")
    cabinet_available = bool(cabinet.get("available", False))
    finance_available = bool(finance.get("available", False))
    finance_status = str(finance.get("status") or "unavailable").strip().lower()
    finance_rows_loaded = int(source_flags.get("finance_rows_loaded", 0) or 0)

    buyouts_count = cabinet.get("buyouts_count")
    buyouts_amount = cabinet.get("buyouts_amount")
    buyouts_source = cabinet_source

    live_sales_count = live_sales.get("count") if isinstance(live_sales, dict) else None
    live_sales_amount = live_sales.get("amount") if isinstance(live_sales, dict) else None
    if (not buyouts_count or buyouts_count == 0) and live_sales_count and live_sales_count > 0:
        buyouts_count = live_sales_count
        buyouts_amount = live_sales_amount
        buyouts_source = "sales_api"

    buyouts_count_number = _safe_float_value(buyouts_count)
    buyouts_amount_number = _safe_float_value(buyouts_amount)
    avg_check = None
    if buyouts_count_number not in (None, 0.0) and buyouts_amount_number is not None:
        avg_check = round(buyouts_amount_number / buyouts_count_number, 2)

    buyouts_count_confirmed = buyouts_count is not None
    buyouts_amount_confirmed = buyouts_amount is not None
    buyouts_confirmed = bool(buyouts_count_confirmed or buyouts_amount_confirmed)
    financial_finality_status = "missing"
    if finance_available:
        financial_finality_status = "final" if finance_status == "ok" else "partial"
    financial_alignment_status = (
        "aligned"
        if finance.get("date_aligned") is True
        else ("lagged_fallback" if finance_available else "missing")
    )
    financial_matrix_status = "missing"
    if finance_available:
        if finance_status == "lagged":
            financial_matrix_status = "lagged"
        elif finance_status == "ok":
            financial_matrix_status = "confirmed"
        else:
            financial_matrix_status = "partial"

    daily_kpi = {
        "daily_orders_count": cabinet.get("orders_count"),
        "daily_orders_amount": cabinet.get("orders_amount"),
        "daily_buyouts_count": buyouts_count,
        "daily_buyouts_amount": buyouts_amount,
        "orders_count_confirmed": cabinet_available,
        "buyouts_count_confirmed": buyouts_confirmed,
        "buyouts_amount_confirmed": buyouts_amount_confirmed,
        "data_source_orders": cabinet_source,
        "data_source_orders_count": cabinet_source,
        "data_source_orders_amount": cabinet_source,
        "data_source_buyouts": buyouts_source,
        "data_source_buyouts_count": buyouts_source,
        "data_source_buyouts_amount": buyouts_source,
    }
    order_kpi = {
        "date": cabinet.get("target_date") or meta.get("operational_date"),
        "orders_count": cabinet.get("orders_count"),
        "orders_amount": cabinet.get("orders_amount"),
        "orders_count_confirmed": cabinet_available,
        "orders_amount_confirmed": bool(cabinet_available and cabinet.get("orders_amount") is not None),
        "source_count": cabinet_source,
        "source_amount": cabinet_source,
    }
    buyout_kpi = {
        "date": cabinet.get("target_date") or meta.get("operational_date"),
        "buyouts_count": buyouts_count,
        "buyouts_amount": buyouts_amount,
        "buyouts_count_confirmed": buyouts_count_confirmed,
        "buyouts_amount_confirmed": buyouts_amount_confirmed,
        "source_count": buyouts_source,
        "source_amount": buyouts_source,
    }
    financial_components = {
        "revenue": {"available": finance.get("seller_payout") is not None},
        "seller_payout": {"available": finance.get("seller_payout") is not None},
        "commission": {"available": finance.get("wb_commission") is not None},
        "acquiring": {"available": finance.get("acquiring") is not None},
        "pvz_service": {"available": False},
        "logistics": {"available": finance.get("logistics") is not None},
        "storage": {"available": finance.get("storage") is not None},
        "deductions": {"available": finance.get("deductions") is not None},
        "penalties": {"available": finance.get("penalties") is not None},
        "cost_price": {"available": False},
        "tax": {"available": finance.get("tax") is not None},
        "ads_spend": {"available": False},
        "net_profit": {"available": False},
    }
    financial_kpi = {
        "revenue": finance.get("seller_payout"),
        "gross_revenue": finance.get("gross_revenue"),
        "wb_realized_revenue": None,
        "seller_payout": finance.get("seller_payout"),
        "wb_commission": finance.get("wb_commission"),
        "logistics": finance.get("logistics"),
        "storage": finance.get("storage"),
        "penalties": finance.get("penalties"),
        "deductions": finance.get("deductions"),
        "acquiring": finance.get("acquiring"),
        "pvz_service": None,
        "tax": finance.get("tax"),
        "cost_price": None,
        "gross_profit": None,
        "net_profit": None,
        "margin_pct": None,
        "profitability_pct": None,
        "financial_source": finance_source,
        "financial_finality_status": financial_finality_status,
        "financial_status": finance_status,
        "is_partial": bool(finance_status != "ok"),
        "financial_partial": bool(finance_status != "ok"),
        "net_profit_partial": True,
        "financial_margin_not_final": True,
        "completeness_pct": 100.0 if finance_available and finance_rows_loaded > 0 else 0.0,
        "kernel_rows_total": finance_rows_loaded,
        "financial_alignment_status": financial_alignment_status,
        "financial_date_aligned": bool(finance.get("date_aligned") is True),
        "financial_date_misaligned": bool(finance_available and finance.get("date_aligned") is False),
        "financial_actual_date": finance.get("actual_date"),
        "financial_target_date": finance.get("target_date") or meta.get("operational_date"),
        "components": financial_components,
    }
    render_kpi = {
        "orders_count": cabinet.get("orders_count"),
        "orders_amount": cabinet.get("orders_amount"),
        "buyouts_count": buyouts_count,
        "buyouts_amount": buyouts_amount,
        "avg_check": avg_check,
        "revenue": finance.get("seller_payout"),
        "gross_profit": None,
        "net_profit": None,
        "margin_pct": None,
        "profitability_pct": None,
        "financial_lagged": bool(finance_status == "lagged"),
        "financial_actual_date": finance.get("actual_date"),
        "financial_target_date": finance.get("target_date") or meta.get("operational_date"),
        "financial_alignment_status": financial_alignment_status,
    }
    event_date_model = {
        "report_date": meta.get("report_date"),
        "operational_date": meta.get("operational_date"),
        "financial_date": finance.get("actual_date"),
    }
    daily_status_matrix = {
        "orders": "confirmed" if cabinet_available else "missing",
        "buyouts": "confirmed" if buyouts_confirmed else "missing",
        "financials": financial_matrix_status,
    }
    data_quality = {
        "financial_finality_status": financial_finality_status,
        "financial_alignment_status": financial_alignment_status,
        "financial_date_misaligned": bool(finance_available and finance.get("date_aligned") is False),
        "financial_actual_date": finance.get("actual_date"),
        "financial_target_date": finance.get("target_date") or meta.get("operational_date"),
        "financial_snapshot_status": "confirmed" if finance_available else "missing",
        "financial_rows_effective": finance_rows_loaded,
        "financial_completeness_pct": 100.0 if finance_available and finance_rows_loaded > 0 else 0.0,
    }
    data_sources = {
        "orders": cabinet_source,
        "orders_count": cabinet_source,
        "orders_amount": cabinet_source,
        "buyouts": buyouts_source,
        "buyouts_count": buyouts_source,
        "buyouts_amount": buyouts_source,
        "revenue": finance_source,
    }
    live_section = {
        "status": str(live_operational.get("status") or "unavailable"),
        "orders": live_orders,
        "sales": live_sales,
        "stocks": live_stocks,
    }
    return {
        "meta": meta,
        "daily_kpi": daily_kpi,
        "order_kpi": order_kpi,
        "buyout_kpi": buyout_kpi,
        "financial_kpi": financial_kpi,
        "render_kpi": render_kpi,
        "event_date_model": event_date_model,
        "daily_status_matrix": daily_status_matrix,
        "data_quality": data_quality,
        "data_sources": data_sources,
        "source_flags": source_flags,
        "live_operational": live_section,
    }


def is_core_snapshot_usable(core_report_payload: Dict[str, Any]) -> bool:
    if not isinstance(core_report_payload, dict):
        return False
    meta = _safe_dict(core_report_payload.get("meta"))
    cabinet = _safe_dict(core_report_payload.get("cabinet_commerce"))
    finance = _safe_dict(core_report_payload.get("finance_final"))
    if not str(meta.get("seller_id") or "").strip():
        return False
    if not str(meta.get("report_date") or "").strip():
        return False
    return bool(cabinet.get("available", False) or finance.get("available", False))
