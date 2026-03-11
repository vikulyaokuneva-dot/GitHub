from __future__ import annotations

from typing import Any, Dict, List


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return int(default)
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    return bool(value)


def _as_str(value: Any) -> str:
    return str(value or "").strip()


def _normalize_discovered(discovered_files: Dict[str, Any]) -> Dict[str, List[str]]:
    default = {"sales": [], "ads": [], "stocks": [], "unknown": []}
    if not isinstance(discovered_files, dict):
        return default
    out: Dict[str, List[str]] = {}
    for key in ("sales", "ads", "stocks", "unknown"):
        value = discovered_files.get(key, [])
        if isinstance(value, list):
            out[key] = [str(item) for item in value if str(item).strip()]
        else:
            out[key] = []
    return out


def build_input_debug(
    *,
    source_mode: str,
    input_debug: Dict[str, Any],
    local_input_debug: Dict[str, Any],
    discovered_files: Dict[str, Any],
    api_debug: Dict[str, Any],
    supplier_goods_daily: Dict[str, Any],
    sales_rows_count: int,
    ads_rows: List[Dict[str, Any]],
    ads_rows_count: int,
    stocks_rows_count: int,
    ads_loaded_from_file: bool,
    ads_source_file: str,
) -> Dict[str, Any]:
    safe_input_debug = input_debug if isinstance(input_debug, dict) else {}
    safe_local_debug = local_input_debug if isinstance(local_input_debug, dict) else {}
    safe_supplier_goods_daily = supplier_goods_daily if isinstance(supplier_goods_daily, dict) else {"found": False}
    safe_api_debug = api_debug if isinstance(api_debug, dict) else {}
    safe_discovered = _normalize_discovered(discovered_files)

    out: Dict[str, Any] = {}
    out.update(safe_local_debug)
    out.update(safe_input_debug)

    out["source_mode"] = str(source_mode or out.get("source_mode") or "")
    out["api_debug"] = safe_api_debug
    out["loaded_rows"] = {
        "sales": int(sales_rows_count),
        "ads": int(ads_rows_count),
        "stocks": int(stocks_rows_count),
    }
    out["discovered"] = safe_discovered

    if "input_files_detected" not in out:
        out["input_files_detected"] = sum(len(value) for value in safe_discovered.values())
    out["input_files_detected"] = _as_int(out.get("input_files_detected"), sum(len(value) for value in safe_discovered.values()))

    details = out.get("details", {})
    out["details"] = details if isinstance(details, dict) else {}

    supplier_candidates = out.get("supplier_goods_candidates", [])
    out["supplier_goods_candidates"] = (
        [item for item in supplier_candidates if isinstance(item, dict)]
        if isinstance(supplier_candidates, list)
        else []
    )
    ads_candidates = out.get("ads_candidates", [])
    out["ads_candidates"] = (
        [item for item in ads_candidates if isinstance(item, dict)]
        if isinstance(ads_candidates, list)
        else []
    )
    out["detection_reason"] = _as_str(out.get("detection_reason"))
    out["primary_sales_source"] = _as_str(out.get("primary_sales_source"))
    primary_sales_columns = out.get("primary_sales_columns", {})
    out["primary_sales_columns"] = primary_sales_columns if isinstance(primary_sales_columns, dict) else {}

    ads_rows_usable_current = sum(
        1
        for row in ads_rows
        if isinstance(row, dict) and not bool(row.get("_is_campaign_total", False))
    )
    ads_columns_detected = out.get("ads_columns_detected", [])
    if not isinstance(ads_columns_detected, list):
        ads_columns_detected = []

    out["ads_file_candidates_found"] = _as_int(out.get("ads_file_candidates_found"), 0)
    out["ads_file_detected"] = _as_bool(out.get("ads_file_detected"), False)
    out["ads_sheet_found"] = _as_str(out.get("ads_sheet_found"))
    out["ads_columns_detected"] = [str(item) for item in ads_columns_detected if str(item).strip()]
    out["ads_rows_raw"] = _as_int(out.get("ads_rows_raw"), 0)
    out["ads_rows_usable"] = _as_int(out.get("ads_rows_usable"), ads_rows_usable_current)
    out["ads_loader_error"] = _as_str(out.get("ads_loader_error"))
    out["ads_rows"] = int(ads_rows_count)
    out["ads_loaded_from_file"] = bool(ads_loaded_from_file or _as_bool(out.get("ads_loaded_from_file"), False))
    out["ads_source_file"] = _as_str(ads_source_file or out.get("ads_source_file"))

    out["source_priority"] = {
        "sales": "api.realization -> api.sales -> local.sales",
        "orders_kpi_count": "supplier_goods_confirmed_count -> api.orders -> api.sales -> unknown",
        "buyouts_kpi_count": "supplier_goods_confirmed_count -> api.sales -> api.realization -> unknown",
        "stocks": "api.stocks -> local.stocks",
        "ads": "api.ads_legacy -> local.ads",
        "supplier_goods_daily": "local_excel_financial_source",
    }
    out["supplier_goods_daily"] = safe_supplier_goods_daily

    warnings_additions: List[Dict[str, Any]] = []
    if bool(safe_supplier_goods_daily.get("found")):
        warnings_additions.append(
            {
                "code": "supplier_goods_report_detected",
                "message": "Supplier goods report detected: " + _as_str(safe_supplier_goods_daily.get("source_file")),
            }
        )

    return {
        "input_debug": out,
        "warnings_additions": warnings_additions,
    }
