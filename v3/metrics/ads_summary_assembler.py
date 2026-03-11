from __future__ import annotations

from typing import Any, Dict, List


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_str(value: Any) -> str:
    return str(value or "").strip()


def assemble_ads_summary(
    *,
    metrics: Dict[str, Any],
    input_debug: Dict[str, Any],
    ads_rows: List[Dict[str, Any]],
    source_mode: str,
    ads_loaded_from_file: bool,
    ads_source_file: str,
    financial_kpi: Dict[str, Any],
    has_ads_report_missing_warning: bool,
) -> Dict[str, Any]:
    safe_metrics = metrics if isinstance(metrics, dict) else {}
    safe_input_debug = input_debug if isinstance(input_debug, dict) else {}
    safe_financial_kpi = financial_kpi if isinstance(financial_kpi, dict) else {}

    ads_diagnostics = safe_metrics.get("ads_diagnostics", {})
    if not isinstance(ads_diagnostics, dict):
        ads_diagnostics = {}
    ads_metrics = safe_metrics.get("ads", {})
    if not isinstance(ads_metrics, dict):
        ads_metrics = {}

    ads_rows_count = int(ads_diagnostics.get("rows", ads_metrics.get("rows", len(ads_rows))) or 0)
    resolved_ads_source_file = _as_str(ads_source_file)
    if not resolved_ads_source_file:
        resolved_ads_source_file = _as_str(safe_input_debug.get("ads_source_file"))

    resolved_ads_loaded_from_file = bool(ads_loaded_from_file)
    if not resolved_ads_loaded_from_file:
        resolved_ads_loaded_from_file = bool(
            safe_input_debug.get("ads_loaded_from_file", False)
            or (source_mode == "local_reports" and ads_rows_count > 0)
        )

    ads_attribution_quality = _as_str(
        ads_diagnostics.get("attribution_quality", ads_metrics.get("attribution_quality", "unknown"))
    ) or "unknown"

    ads_file_candidates_found = int(safe_input_debug.get("ads_file_candidates_found", 0) or 0)
    ads_file_detected = bool(safe_input_debug.get("ads_file_detected", False))
    ads_sheet_found = _as_str(safe_input_debug.get("ads_sheet_found"))
    raw_columns = safe_input_debug.get("ads_columns_detected", [])
    ads_columns_detected = (
        [str(item) for item in raw_columns if str(item).strip()]
        if isinstance(raw_columns, list)
        else []
    )
    ads_rows_raw = int(safe_input_debug.get("ads_rows_raw", 0) or 0)
    ads_rows_usable = int(safe_input_debug.get("ads_rows_usable", ads_rows_count) or 0)
    ads_loader_error = _as_str(safe_input_debug.get("ads_loader_error"))

    campaign_totals = ads_diagnostics.get("campaign_totals", {})
    if not isinstance(campaign_totals, dict):
        campaign_totals = {}
    derived_totals = ads_diagnostics.get("derived_totals", {})
    if not isinstance(derived_totals, dict):
        derived_totals = {}
    selected_totals = ads_diagnostics.get("selected_totals", {})
    if not isinstance(selected_totals, dict):
        selected_totals = {}
    conversion_breakdown = ads_diagnostics.get("conversion_breakdown", {})
    if not isinstance(conversion_breakdown, dict):
        conversion_breakdown = {}

    ads_summary = {
        "ads_rows": int(ads_rows_count),
        "ads_spend": round(_safe_float(safe_financial_kpi.get("ads_spend", 0.0)), 2),
        "ads_loaded_from_file": bool(resolved_ads_loaded_from_file),
        "ads_source_file": resolved_ads_source_file,
        "ads_file_candidates_found": int(ads_file_candidates_found),
        "ads_file_detected": bool(ads_file_detected),
        "ads_sheet_found": ads_sheet_found,
        "ads_columns_detected": ads_columns_detected,
        "ads_rows_raw": int(ads_rows_raw),
        "ads_rows_usable": int(ads_rows_usable),
        "ads_loader_error": ads_loader_error,
        "ads_attribution_quality": ads_attribution_quality,
        "ads_campaign_totals": campaign_totals,
    }

    ads_diagnostics_summary = {
        "rows": int(ads_rows_count),
        "campaign_total_rows": int(ads_diagnostics.get("campaign_total_rows", 0) or 0),
        "campaign_totals": campaign_totals,
        "derived_totals": derived_totals,
        "selected_totals": selected_totals,
        "conversion_breakdown": conversion_breakdown,
        "attribution_quality": ads_attribution_quality,
    }

    warnings_additions: List[Dict[str, Any]] = []
    if resolved_ads_loaded_from_file:
        warnings_additions.append(
            {
                "code": "ads_file_loaded",
                "message": f"Ads report loaded from file: {resolved_ads_source_file or 'local_input'}",
            }
        )
    if ads_rows_count <= 0 and not has_ads_report_missing_warning:
        warnings_additions.append(
            {
                "code": "ads_report_missing",
                "message": "Ads report is missing or has zero usable rows.",
            }
        )
    if ads_attribution_quality in {"mixed_direct_and_associated", "associated_only"}:
        warnings_additions.append(
            {
                "code": "ads_attribution_partial",
                "message": f"Ads attribution includes associated conversions ({ads_attribution_quality}).",
            }
        )
    if _safe_float(safe_financial_kpi.get("ads_spend", 0.0)) > 0:
        warnings_additions.append(
            {
                "code": "ads_spend_applied_to_profit",
                "message": "Ads spend applied to net profit calculation.",
            }
        )
        warnings_additions.append(
            {
                "code": "net_profit_reduced_by_ads",
                "message": "Net profit reduced by ads spend.",
            }
        )

    input_debug_patch = {
        "ads_rows": int(ads_rows_count),
        "ads_rows_raw": int(max(ads_rows_raw, ads_rows_usable)),
        "ads_rows_usable": int(max(ads_rows_usable, ads_rows_count)),
        "ads_file_candidates_found": int(ads_file_candidates_found),
        "ads_file_detected": bool(ads_file_detected),
        "ads_sheet_found": ads_sheet_found,
        "ads_columns_detected": ads_columns_detected,
        "ads_loader_error": ads_loader_error,
        "ads_attribution_quality": ads_attribution_quality,
        "ads_loaded_from_file": bool(resolved_ads_loaded_from_file),
        "ads_source_file": resolved_ads_source_file,
    }

    return {
        "ads_summary": ads_summary,
        "ads_diagnostics": ads_diagnostics_summary,
        "warnings_additions": warnings_additions,
        "input_debug_patch": input_debug_patch,
    }
