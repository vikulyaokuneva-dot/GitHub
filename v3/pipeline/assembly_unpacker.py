from __future__ import annotations

from typing import Any, Dict, List


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_warning_list(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def unpack_ads_assembly(ads_assembly: Dict[str, Any]) -> Dict[str, Any]:
    safe_ads_assembly = _as_dict(ads_assembly)
    ads_summary = _as_dict(safe_ads_assembly.get("ads_summary"))
    ads_diagnostics = _as_dict(safe_ads_assembly.get("ads_diagnostics"))

    ads_rows_count = int(ads_summary.get("ads_rows", 0) or 0)
    ads_loaded_from_file = bool(ads_summary.get("ads_loaded_from_file", False))
    ads_source_file = str(ads_summary.get("ads_source_file") or "")
    ads_attribution_quality = str(ads_summary.get("ads_attribution_quality") or "unknown")
    input_debug_patch = _as_dict(safe_ads_assembly.get("input_debug_patch"))
    warning_additions = _as_warning_list(safe_ads_assembly.get("warnings_additions"))

    return {
        "ads_summary": ads_summary,
        "ads_diagnostics": ads_diagnostics,
        "ads_rows_count": ads_rows_count,
        "ads_loaded_from_file": ads_loaded_from_file,
        "ads_source_file": ads_source_file,
        "ads_attribution_quality": ads_attribution_quality,
        "input_debug_patch": input_debug_patch,
        "warning_additions": warning_additions,
    }


def unpack_daily_kpi_assembly(
    daily_kpi_assembly: Dict[str, Any],
    totals_for_daily: Dict[str, Any],
    source_unknown: str,
) -> Dict[str, Any]:
    safe_daily_assembly = _as_dict(daily_kpi_assembly)
    daily_kpi = _as_dict(safe_daily_assembly.get("daily_kpi"))
    resolved_totals = safe_daily_assembly.get("totals", totals_for_daily)
    if not isinstance(resolved_totals, dict):
        resolved_totals = totals_for_daily if isinstance(totals_for_daily, dict) else {}
    source_policy = _as_dict(safe_daily_assembly.get("source_policy"))
    source_map = _as_dict(safe_daily_assembly.get("source_map"))
    source_flags = _as_dict(safe_daily_assembly.get("source_flags"))
    data_sources = _as_dict(safe_daily_assembly.get("data_sources"))
    commerce_activity = _as_dict(safe_daily_assembly.get("commerce_activity"))
    commerce_kpi = _as_dict(safe_daily_assembly.get("commerce_kpi"))
    warning_additions = _as_warning_list(safe_daily_assembly.get("warning_additions"))

    return {
        "daily_kpi": daily_kpi,
        "totals": resolved_totals,
        "source_policy": source_policy,
        "source_map": source_map,
        "source_flags": source_flags,
        "data_sources": data_sources,
        "data_source_orders_count": str(data_sources.get("orders_count") or source_unknown),
        "data_source_buyouts_count": str(data_sources.get("buyouts_count") or source_unknown),
        "data_source_orders_amount": str(data_sources.get("orders_amount") or source_unknown),
        "data_source_buyouts_amount": str(data_sources.get("buyouts_amount") or source_unknown),
        "data_source_revenue": str(data_sources.get("revenue") or source_unknown),
        "data_source_wb_commission": str(data_sources.get("wb_commission") or source_unknown),
        "data_source_logistics": str(data_sources.get("logistics") or source_unknown),
        "data_source_storage": str(data_sources.get("storage") or source_unknown),
        "data_source_ads_spend": str(data_sources.get("ads_spend") or source_unknown),
        "commerce_activity": commerce_activity,
        "commerce_kpi": commerce_kpi,
        "warning_additions": warning_additions,
    }


def apply_metrics_assembly_patches(
    *,
    metrics: Dict[str, Any],
    totals_for_daily: Dict[str, Any],
    ads_summary: Dict[str, Any],
    ads_diagnostics_summary: Dict[str, Any],
    source_policy: Dict[str, Any],
    source_map: Dict[str, Any],
    source_flags: Dict[str, Any],
    commerce_activity: Dict[str, Any],
    daily_kpi: Dict[str, Any],
    commerce_kpi: Dict[str, Any],
) -> Dict[str, Any]:
    safe_metrics = metrics if isinstance(metrics, dict) else {}
    safe_metrics["totals"] = totals_for_daily if isinstance(totals_for_daily, dict) else {}
    safe_metrics["ads_ingestion"] = dict(ads_summary if isinstance(ads_summary, dict) else {})
    safe_metrics["ads_diagnostics_summary"] = dict(
        ads_diagnostics_summary if isinstance(ads_diagnostics_summary, dict) else {}
    )
    safe_metrics["source_policy"] = source_policy if isinstance(source_policy, dict) else {}
    safe_metrics["data_sources"] = source_map if isinstance(source_map, dict) else {}
    safe_metrics["source_flags"] = source_flags if isinstance(source_flags, dict) else {}
    safe_metrics["commerce_activity"] = commerce_activity if isinstance(commerce_activity, dict) else {}
    if isinstance(safe_metrics.get("funnel"), dict):
        safe_metrics["funnel"]["orders"] = int(safe_metrics["totals"].get("orders", 0) or 0)
        safe_metrics["funnel"]["buys"] = int(safe_metrics["totals"].get("buys", 0) or 0)
        safe_metrics["funnel"]["orders_confirmed"] = bool(safe_metrics["totals"].get("orders_confirmed", False))
        safe_metrics["funnel"]["buys_confirmed"] = bool(safe_metrics["totals"].get("buys_confirmed", False))
        safe_metrics["funnel"]["item_qty"] = int(safe_metrics["totals"].get("item_qty", 0) or 0)
        safe_metrics["funnel"]["sales_activity_qty"] = int(safe_metrics["totals"].get("sales_activity_qty", 0) or 0)
        safe_metrics["funnel"]["sku_activity_count"] = int(safe_metrics["totals"].get("sku_activity_count", 0) or 0)
    safe_metrics["daily_kpi"] = daily_kpi if isinstance(daily_kpi, dict) else {}
    safe_metrics["commerce_kpi"] = commerce_kpi if isinstance(commerce_kpi, dict) else {}
    return safe_metrics


def apply_input_debug_assembly_patches(
    *,
    input_debug: Dict[str, Any],
    input_debug_patch: Dict[str, Any],
    source_policy: Dict[str, Any],
) -> Dict[str, Any]:
    safe_input_debug = input_debug if isinstance(input_debug, dict) else {}
    safe_patch = input_debug_patch if isinstance(input_debug_patch, dict) else {}
    for key, value in safe_patch.items():
        safe_input_debug[key] = value
    safe_input_debug["source_policy"] = source_policy if isinstance(source_policy, dict) else {}
    return safe_input_debug


def extract_financial_ads_warning_additions(
    *,
    financial_assembly: Dict[str, Any],
    ads_assembly: Dict[str, Any],
) -> Dict[str, List[Dict[str, Any]]]:
    safe_financial = _as_dict(financial_assembly)
    safe_ads = _as_dict(ads_assembly)
    return {
        "financial_warning_additions": _as_warning_list(safe_financial.get("warning_additions")),
        "ads_warning_additions": _as_warning_list(safe_ads.get("warnings_additions")),
    }
