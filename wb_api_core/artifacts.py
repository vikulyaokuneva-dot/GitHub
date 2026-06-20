from __future__ import annotations

import json
import os
import re
import time
from copy import deepcopy
from typing import Any, Dict


def _write_json(path: str, payload: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def _read_json(path: str) -> Dict[str, Any] | None:
    try:
        with open(path, "r", encoding="utf-8") as file:
            payload = json.load(file)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def latest_successful_snapshot_path(repo_root: str, seller_id: str) -> str:
    return os.path.join(
        repo_root,
        "cabinets",
        seller_id,
        "artifacts",
        "wb_api_core",
        "cache",
        "snapshots",
        "latest_successful.json",
    )


def read_latest_successful_snapshot(*, repo_root: str, seller_id: str) -> Dict[str, Any] | None:
    path = latest_successful_snapshot_path(repo_root, seller_id)
    payload = _read_json(path)
    if not isinstance(payload, dict):
        return None
    try:
        cache_age_seconds = max(0.0, time.time() - float(os.path.getmtime(path)))
    except Exception:
        cache_age_seconds = 0.0
    return {
        "path": path,
        "cache_age_seconds": round(cache_age_seconds, 2),
        "snapshot": payload,
    }


def _live_block_has_data(block: Dict[str, Any], live_key: str) -> bool:
    if not isinstance(block, dict) or not bool(block.get("available", False)):
        return False
    if live_key in {"orders", "sales"}:
        return block.get("count") is not None or block.get("amount") is not None
    if live_key == "stocks":
        return block.get("total_units") is not None
    if live_key == "ads":
        return block.get("count") is not None and int(block.get("count") or 0) > 0
    return False


def _live_block_is_stale(block: Dict[str, Any]) -> bool:
    return isinstance(block, dict) and bool(block.get("stale", False))


def _snapshot_has_stale_live_fallback(snapshot: Dict[str, Any]) -> bool:
    live = snapshot.get("live_operational", {}) if isinstance(snapshot, dict) else {}
    if not isinstance(live, dict):
        return False
    return any(_live_block_is_stale(live.get(key, {})) for key in ("orders", "sales", "stocks", "ads"))


def _snapshot_has_cacheable_live_data(snapshot: Dict[str, Any]) -> bool:
    live = snapshot.get("live_operational", {}) if isinstance(snapshot, dict) else {}
    if not isinstance(live, dict):
        return False
    return all(_live_block_has_data(live.get(key, {}), key) for key in ("orders", "sales", "stocks", "ads"))


def _debug_is_rate_limited(debug: Dict[str, Any]) -> bool:
    if not isinstance(debug, dict):
        return False
    try:
        if int(debug.get("status_code", 0) or 0) == 429:
            return True
    except Exception:
        pass
    text = " ".join(
        str(debug.get(key) or "")
        for key in ("error_text", "final_failure_reason")
    )
    return "429" in text


def _rate_limited_live_keys(raw_bundle: Dict[str, Any]) -> list[tuple[str, str]]:
    pairs = (("orders", "orders"), ("sales", "sales"), ("stocks", "stocks"), ("ads", "ads"))
    rate_limited: list[tuple[str, str]] = []
    for endpoint_key, live_key in pairs:
        debug = (raw_bundle.get(endpoint_key) or {}).get("debug", {}) if isinstance(raw_bundle, dict) else {}
        if _debug_is_rate_limited(debug if isinstance(debug, dict) else {}):
            rate_limited.append((endpoint_key, live_key))
    return rate_limited


def apply_latest_successful_live_fallback(
    *,
    reconcile_result: Dict[str, Any],
    raw_bundle: Dict[str, Any],
    latest_snapshot_cache: Dict[str, Any] | None,
) -> Dict[str, Any]:
    rate_limited = _rate_limited_live_keys(raw_bundle)
    if not rate_limited or not isinstance(latest_snapshot_cache, dict):
        return reconcile_result
    cached_snapshot = latest_snapshot_cache.get("snapshot")
    if not isinstance(cached_snapshot, dict):
        return reconcile_result
    if _snapshot_has_stale_live_fallback(cached_snapshot):
        return reconcile_result
    cached_live = cached_snapshot.get("live_operational", {})
    if not isinstance(cached_live, dict):
        return reconcile_result

    result = deepcopy(reconcile_result)
    live_operational = result.get("live_operational", {})
    if not isinstance(live_operational, dict):
        return result

    cache_path = str(latest_snapshot_cache.get("path") or "")
    cache_age_seconds = latest_snapshot_cache.get("cache_age_seconds")
    source_actual_date = str(cached_snapshot.get("operational_date") or cached_snapshot.get("run_date") or "").strip()
    used: list[str] = []

    for endpoint_key, live_key in rate_limited:
        current_block = live_operational.get(live_key, {})
        if _live_block_has_data(current_block if isinstance(current_block, dict) else {}, live_key):
            continue
        cached_block = cached_live.get(live_key, {})
        if not _live_block_has_data(cached_block if isinstance(cached_block, dict) else {}, live_key):
            continue

        fallback_block = dict(cached_block)
        if isinstance(current_block, dict):
            if live_key in {"orders", "sales"} and current_block.get("target_date") is not None:
                fallback_block["target_date"] = current_block.get("target_date")
            if live_key == "stocks" and current_block.get("operational_date_reference") is not None:
                fallback_block["operational_date_reference"] = current_block.get("operational_date_reference")
            cached_rows = list(cached_block.get("rows", []) or [])
            fallback_block["rows"] = cached_rows if cached_rows else list(current_block.get("rows", []) or [])
        fallback_block.update(
            {
                "available": True,
                "stale": True,
                "stale_reason": "rate_limited",
                "source_actual_date": source_actual_date,
                "cache_age_seconds": cache_age_seconds,
                "cache_path": cache_path,
                "cache_fallback_used": True,
            }
        )
        live_operational[live_key] = fallback_block
        used.append(endpoint_key)

    if used:
        warnings = list(result.get("warnings", []) or [])
        for endpoint_key in used:
            warnings.append(
                {
                    "code": f"{endpoint_key}_latest_successful_cache_fallback",
                    "message": (
                        f"{endpoint_key} returned 429; live_operational.{endpoint_key} "
                        "was filled from latest_successful snapshot and marked stale."
                    ),
                    "level": "warning",
                    "block": "live_operational",
                }
            )
        result["warnings"] = warnings
        result["cache_fallback"] = {
            "latest_successful_snapshot_used": True,
            "fallback_endpoints": used,
            "cache_path": cache_path,
            "cache_age_seconds": cache_age_seconds,
            "source_actual_date": source_actual_date,
        }

    return result


def write_latest_successful_snapshot(*, repo_root: str, seller_id: str, snapshot: Dict[str, Any]) -> str:
    if _snapshot_has_stale_live_fallback(snapshot) or not _snapshot_has_cacheable_live_data(snapshot):
        return ""
    path = latest_successful_snapshot_path(repo_root, seller_id)
    _write_json(path, snapshot)
    return path


def _row_date_iso(row: Dict[str, Any]) -> str:
    for key in ("date", "orderDate", "saleDate", "lastChangeDate", "order_dt", "sale_dt", "createdAt"):
        raw = str(row.get(key) or "").strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", raw):
            return raw[:10]
    return ""


def _build_orders_raw_inventory(rows_raw: Any, target_date: str) -> Dict[str, Any]:
    safe_rows = [row for row in list(rows_raw or []) if isinstance(row, dict)]
    projected_rows = []
    field_counts = {
        "quantity": 0,
        "totalPrice": 0,
        "priceWithDisc": 0,
        "discountPercent": 0,
        "warehouse": 0,
        "status": 0,
        "isCancel": 0,
        "cancelDate": 0,
        "date": 0,
        "lastChangeDate": 0,
    }
    for index, row in enumerate(safe_rows):
        row_day = _row_date_iso(row)
        if target_date and row_day and row_day != target_date:
            continue
        quantity = row.get("quantity")
        warehouse = row.get("warehouseName") or row.get("warehouse") or row.get("officeName")
        status = row.get("status") or row.get("orderStatus") or row.get("supplierStatus")
        if quantity not in (None, ""):
            field_counts["quantity"] += 1
        if row.get("totalPrice") not in (None, ""):
            field_counts["totalPrice"] += 1
        if row.get("priceWithDisc") not in (None, ""):
            field_counts["priceWithDisc"] += 1
        if row.get("discountPercent") not in (None, ""):
            field_counts["discountPercent"] += 1
        if warehouse not in (None, ""):
            field_counts["warehouse"] += 1
        if status not in (None, ""):
            field_counts["status"] += 1
        if row.get("isCancel") not in (None, ""):
            field_counts["isCancel"] += 1
        if row.get("cancelDate") not in (None, ""):
            field_counts["cancelDate"] += 1
        if row.get("date") not in (None, ""):
            field_counts["date"] += 1
        if row.get("lastChangeDate") not in (None, ""):
            field_counts["lastChangeDate"] += 1
        projected_rows.append(
            {
                "date": row.get("date"),
                "lastChangeDate": row.get("lastChangeDate"),
                "srid": row.get("srid") or row.get("odid") or row.get("orderId") or row.get("gNumber") or row.get("orderUID"),
                "quantity": quantity,
                "totalPrice": row.get("totalPrice"),
                "finishedPrice": row.get("finishedPrice"),
                "priceWithDisc": row.get("priceWithDisc"),
                "discountPercent": row.get("discountPercent"),
                "warehouse": warehouse,
                "status": status,
                "isCancel": row.get("isCancel"),
                "cancelDate": row.get("cancelDate"),
                "_raw_row_index": index,
            }
        )
    return {
        "rows_loaded": len(safe_rows),
        "rows_matching_operational_date": len(projected_rows),
        "requested_fields_present": field_counts,
        "rows": projected_rows,
    }


def build_debug(
    *,
    seller_id: str,
    run_date: str,
    operational_date: str,
    timezone_name: str,
    raw_bundle: Dict[str, Any],
    normalized_bundle: Dict[str, Any],
    reconcile_result: Dict[str, Any],
) -> Dict[str, Any]:
    endpoints = {}
    for key in ("cabinet_commerce", "finance_final", "orders", "sales", "stocks", "ads"):
        debug = dict((raw_bundle.get(key) or {}).get("debug", {}) or {})
        endpoints[key] = {
            "success": bool(debug.get("success", False)),
            "status_code": debug.get("status_code"),
            "attempts": int(debug.get("attempts", 0) or 0),
            "rows_loaded": int(debug.get("rows_loaded", 0) or 0),
            "error_text": str(debug.get("error_text") or ""),
            "base_url": str(debug.get("base_url") or ""),
            "cache_hit": bool(debug.get("cache_hit", False)),
            "retry_count": int(debug.get("retry_count", 0) or 0),
            "retry_delays": list(debug.get("retry_delays", []) or []),
            "final_failure_reason": str(debug.get("final_failure_reason") or ""),
            "retry_after": str(debug.get("retry_after") or ""),
            "x_ratelimit_retry": str(debug.get("x_ratelimit_retry") or ""),
            "x_ratelimit_reset": str(debug.get("x_ratelimit_reset") or ""),
            "x_ratelimit_remaining": str(debug.get("x_ratelimit_remaining") or ""),
            "rate_limit_delay_seconds": debug.get("rate_limit_delay_seconds"),
            "token_present": bool(debug.get("token_present", False)),
            "token_env_name_used": str(debug.get("token_env_name_used") or ""),
        }
        if key == "finance_final":
            endpoints[key]["finance_endpoint_used"] = str(debug.get("finance_endpoint_used") or "")
            endpoints[key]["finance_requested_fields_count"] = int(debug.get("finance_requested_fields_count", 0) or 0)
            endpoints[key]["finance_payload_incompatible"] = bool(debug.get("finance_payload_incompatible", False))
        if key == "cabinet_commerce":
            endpoints[key]["pages_loaded"] = int(debug.get("pages_loaded", 0) or 0)
            endpoints[key]["page_limit"] = int(debug.get("page_limit", 0) or 0)
            endpoints[key]["cache_mode"] = str(debug.get("cache_mode") or "")
            endpoints[key]["cache_path"] = str(debug.get("cache_path") or "")
            endpoints[key]["cache_age_seconds"] = debug.get("cache_age_seconds")
            endpoints[key]["cache_fallback_used"] = bool(debug.get("cache_fallback_used", False))

    raw_counts = {
        "cabinet_commerce": len(list((raw_bundle.get("cabinet_commerce") or {}).get("rows_raw", []))),
        "finance_final": len(list((raw_bundle.get("finance_final") or {}).get("rows_raw", []))),
        "orders": len(list((raw_bundle.get("orders") or {}).get("rows_raw", []))),
        "sales": len(list((raw_bundle.get("sales") or {}).get("rows_raw", []))),
        "stocks": len(list((raw_bundle.get("stocks") or {}).get("rows_raw", []))),
        "ads": len(list((raw_bundle.get("ads") or {}).get("rows_raw", []))),
    }
    normalized_counts = dict((normalized_bundle.get("debug") or {}).get("counts", {}) or {})
    reconciled_counts = dict((reconcile_result.get("counts") or {}).get("reconciled", {}) or {})
    finance_final = reconcile_result.get("finance_final_daily", {})
    live_operational = reconcile_result.get("live_operational", {})

    return {
        "seller_id": seller_id,
        "run_date": run_date,
        "operational_date": operational_date,
        "timezone": timezone_name,
        "source_mode": "wb_api_core_v2",
        "source_rules": dict(reconcile_result.get("source_rules", {}) or {}),
        "endpoints": endpoints,
        "counts": {
            "raw": raw_counts,
            "normalized": normalized_counts,
            "reconciled": reconciled_counts,
        },
        "reconcile": {
            "target_date": operational_date,
            "finance_final_actual_date": finance_final.get("actual_date"),
            "finance_final_date_aligned": finance_final.get("date_aligned"),
            "live_stocks_snapshot_date": str((((live_operational.get("stocks") or {}) if isinstance(live_operational, dict) else {}).get("snapshot_date") or "")),
            "selected_sources": {
                "cabinet_commerce_daily": str((reconcile_result.get("cabinet_commerce_daily") or {}).get("source") or ""),
                "finance_final_daily": str((reconcile_result.get("finance_final_daily") or {}).get("source") or ""),
                "live_orders": str(((live_operational.get("orders") or {}) if isinstance(live_operational, dict) else {}).get("source") or ""),
                "live_sales": str(((live_operational.get("sales") or {}) if isinstance(live_operational, dict) else {}).get("source") or ""),
                "live_stocks": str(((live_operational.get("stocks") or {}) if isinstance(live_operational, dict) else {}).get("source") or ""),
            },
        },
        "orders_raw_inventory": _build_orders_raw_inventory(
            (raw_bundle.get("orders") or {}).get("rows_raw", []),
            operational_date,
        ),
        "orders_semantics": dict(
            ((((reconcile_result.get("live_operational") or {}).get("orders") or {}).get("diagnostics")) or {})
        ),
        "finance_mapping": dict((normalized_bundle.get("debug") or {}).get("finance_mapping", {}) or {}),
        "cache_fallback": dict(reconcile_result.get("cache_fallback", {}) or {}),
        "warnings": list(reconcile_result.get("warnings", [])),
    }


def _merge_reconciled_rows_preserve_existing(new_payload: Dict[str, Any], existing_path: str, reconcile_result: Dict[str, Any]) -> Dict[str, Any]:
    live_operational = reconcile_result.get("live_operational", {})
    live_keys = ("orders", "sales", "stocks", "ads")
    all_rate_limited = all(
        not bool(live_operational.get(k, {}).get("rows", []))
        for k in live_keys
        if isinstance(live_operational, dict)
    )
    if all_rate_limited and os.path.isfile(existing_path):
        try:
            existing = _read_json(existing_path)
            if isinstance(existing, dict):
                row_keys = ("cabinet_commerce_rows", "live_orders_rows", "live_sales_rows", "live_stocks_rows", "live_ads_rows")
                for key in row_keys:
                    if existing.get(key):
                        new_payload[key] = existing[key]
        except Exception:
            pass
    return new_payload


def write_artifacts(
    *,
    repo_root: str,
    seller_id: str,
    run_date: str,
    snapshot: Dict[str, Any],
    debug: Dict[str, Any],
    reconcile_result: Dict[str, Any],
) -> str:
    out_dir = os.path.join(repo_root, "cabinets", seller_id, "artifacts", "wb_api_core", run_date)
    live_operational = reconcile_result.get("live_operational", {})
    new_rows_payload = {
        "seller_id": seller_id,
        "run_date": run_date,
        "operational_date": snapshot.get("operational_date"),
        "cabinet_commerce_rows": list((reconcile_result.get("cabinet_commerce_daily") or {}).get("rows", [])),
        "finance_final_rows": list((reconcile_result.get("finance_final_daily") or {}).get("rows", [])),
        "live_orders_rows": list((((live_operational.get("orders") or {}) if isinstance(live_operational, dict) else {})).get("rows", [])),
        "live_sales_rows": list((((live_operational.get("sales") or {}) if isinstance(live_operational, dict) else {})).get("rows", [])),
        "live_stocks_rows": list((((live_operational.get("stocks") or {}) if isinstance(live_operational, dict) else {})).get("rows", [])),
        "live_ads_rows": list((((live_operational.get("ads") or {}) if isinstance(live_operational, dict) else {})).get("rows", [])),
    }
    existing_reconciled_path = os.path.join(out_dir, "reconciled_rows.json")
    rows_payload = _merge_reconciled_rows_preserve_existing(new_rows_payload, existing_reconciled_path)
    _write_json(os.path.join(out_dir, "snapshot.json"), snapshot)
    _write_json(os.path.join(out_dir, "debug.json"), debug)
    _write_json(os.path.join(out_dir, "reconciled_rows.json"), rows_payload)
    write_latest_successful_snapshot(
        repo_root=repo_root,
        seller_id=seller_id,
        snapshot=snapshot,
    )
    return out_dir
