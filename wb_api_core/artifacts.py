from __future__ import annotations

import json
import os
import re
from typing import Any, Dict


def _write_json(path: str, payload: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


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
    for key in ("cabinet_commerce", "finance_final", "orders", "sales", "stocks"):
        debug = dict((raw_bundle.get(key) or {}).get("debug", {}) or {})
        endpoints[key] = {
            "success": bool(debug.get("success", False)),
            "status_code": debug.get("status_code"),
            "attempts": int(debug.get("attempts", 0) or 0),
            "rows_loaded": int(debug.get("rows_loaded", 0) or 0),
            "error_text": str(debug.get("error_text") or ""),
            "base_url": str(debug.get("base_url") or ""),
        }
        if key == "finance_final":
            endpoints[key]["finance_endpoint_used"] = str(debug.get("finance_endpoint_used") or "")
            endpoints[key]["finance_requested_fields_count"] = int(debug.get("finance_requested_fields_count", 0) or 0)
            endpoints[key]["finance_payload_incompatible"] = bool(debug.get("finance_payload_incompatible", False))
        if key == "cabinet_commerce":
            endpoints[key]["pages_loaded"] = int(debug.get("pages_loaded", 0) or 0)
            endpoints[key]["page_limit"] = int(debug.get("page_limit", 0) or 0)

    raw_counts = {
        "cabinet_commerce": len(list((raw_bundle.get("cabinet_commerce") or {}).get("rows_raw", []))),
        "finance_final": len(list((raw_bundle.get("finance_final") or {}).get("rows_raw", []))),
        "orders": len(list((raw_bundle.get("orders") or {}).get("rows_raw", []))),
        "sales": len(list((raw_bundle.get("sales") or {}).get("rows_raw", []))),
        "stocks": len(list((raw_bundle.get("stocks") or {}).get("rows_raw", []))),
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
        "warnings": list(reconcile_result.get("warnings", [])),
    }


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
    rows_payload = {
        "seller_id": seller_id,
        "run_date": run_date,
        "operational_date": snapshot.get("operational_date"),
        "cabinet_commerce_rows": list((reconcile_result.get("cabinet_commerce_daily") or {}).get("rows", [])),
        "finance_final_rows": list((reconcile_result.get("finance_final_daily") or {}).get("rows", [])),
        "live_orders_rows": list((((live_operational.get("orders") or {}) if isinstance(live_operational, dict) else {})).get("rows", [])),
        "live_sales_rows": list((((live_operational.get("sales") or {}) if isinstance(live_operational, dict) else {})).get("rows", [])),
        "live_stocks_rows": list((((live_operational.get("stocks") or {}) if isinstance(live_operational, dict) else {})).get("rows", [])),
    }
    _write_json(os.path.join(out_dir, "snapshot.json"), snapshot)
    _write_json(os.path.join(out_dir, "debug.json"), debug)
    _write_json(os.path.join(out_dir, "reconciled_rows.json"), rows_payload)
    return out_dir
