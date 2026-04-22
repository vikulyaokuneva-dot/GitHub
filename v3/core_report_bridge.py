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
            "buyouts_count": None,
            "buyouts_amount": None,
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
            "seller_payout": finance.get("seller_payout"),
            "wb_commission": finance.get("wb_commission"),
            "logistics": finance.get("logistics"),
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
