from __future__ import annotations

import json
import os
from typing import Any, Dict


def _write_json(path: str, payload: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


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
    for key in ("orders", "sales", "realization", "stocks"):
        debug = dict((raw_bundle.get(key) or {}).get("debug", {}) or {})
        endpoints[key] = {
            "success": bool(debug.get("success", False)),
            "status_code": debug.get("status_code"),
            "attempts": int(debug.get("attempts", 0) or 0),
            "rows_loaded": int(debug.get("rows_loaded", 0) or 0),
            "error_text": str(debug.get("error_text") or ""),
        }
        if key == "realization":
            endpoints[key]["finance_endpoint_used"] = str(debug.get("finance_endpoint_used") or "")
            endpoints[key]["finance_requested_fields_count"] = int(debug.get("finance_requested_fields_count", 0) or 0)
            endpoints[key]["finance_payload_incompatible"] = bool(debug.get("finance_payload_incompatible", False))

    raw_counts = {
        "orders": len(list((raw_bundle.get("orders") or {}).get("rows_raw", []))),
        "sales": len(list((raw_bundle.get("sales") or {}).get("rows_raw", []))),
        "realization": len(list((raw_bundle.get("realization") or {}).get("rows_raw", []))),
        "stocks": len(list((raw_bundle.get("stocks") or {}).get("rows_raw", []))),
    }
    normalized_counts = dict((normalized_bundle.get("debug") or {}).get("counts", {}) or {})
    reconciled_counts = dict((reconcile_result.get("counts") or {}).get("reconciled", {}) or {})
    financial = reconcile_result.get("financial", {})

    return {
        "seller_id": seller_id,
        "run_date": run_date,
        "operational_date": operational_date,
        "timezone": timezone_name,
        "source_mode": "wb_api_core_v1",
        "source_rules": dict(reconcile_result.get("source_rules", {}) or {}),
        "endpoints": endpoints,
        "counts": {
            "raw": raw_counts,
            "normalized": normalized_counts,
            "reconciled": reconciled_counts,
        },
        "reconcile": {
            "target_date": operational_date,
            "financial_actual_date": financial.get("actual_date"),
            "financial_date_aligned": financial.get("date_aligned"),
            "selected_sources": {
                "orders": str((reconcile_result.get("orders") or {}).get("source") or ""),
                "buyouts": str((reconcile_result.get("sales") or {}).get("source") or ""),
                "financial": str((reconcile_result.get("financial") or {}).get("source") or ""),
                "stock": str((reconcile_result.get("stock") or {}).get("source") or ""),
            },
        },
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
    rows_payload = {
        "seller_id": seller_id,
        "run_date": run_date,
        "operational_date": snapshot.get("operational_date"),
        "orders_rows": list((reconcile_result.get("orders") or {}).get("rows", [])),
        "sales_rows": list((reconcile_result.get("sales") or {}).get("rows", [])),
        "realization_rows": list((reconcile_result.get("financial") or {}).get("rows", [])),
        "stocks_rows": list((reconcile_result.get("stock") or {}).get("rows", [])),
    }
    _write_json(os.path.join(out_dir, "snapshot.json"), snapshot)
    _write_json(os.path.join(out_dir, "debug.json"), debug)
    _write_json(os.path.join(out_dir, "reconciled_rows.json"), rows_payload)
    return out_dir
