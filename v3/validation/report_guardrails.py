from __future__ import annotations

from typing import Any, Dict, List

from .data_integrity import resolve_report_reliability_level


def _safe_int(value: Any) -> int:
    try:
        if value is None:
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def apply_report_guardrails(payload: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(payload if isinstance(payload, dict) else {})
    data_quality = out.get("data_quality", {})
    if not isinstance(data_quality, dict):
        data_quality = {}
    financial_kpi = out.get("financial_kpi", {})
    if not isinstance(financial_kpi, dict):
        financial_kpi = {}
    daily_kpi = out.get("daily_kpi", {})
    if not isinstance(daily_kpi, dict):
        daily_kpi = {}
    cabinet_funnel = out.get("cabinet_funnel", {})
    if not isinstance(cabinet_funnel, dict):
        cabinet_funnel = {}

    sku_attribution_status = str(data_quality.get("sku_attribution_status") or "ok").strip().lower()
    financial_finality_status = str(
        data_quality.get("financial_finality_status")
        or financial_kpi.get("financial_finality_status")
        or ("partial" if bool(financial_kpi.get("is_partial", False)) else "final")
    ).strip().lower()

    ads_rows = _safe_int(out.get("ads_rows_count", out.get("ads_rows", 0)))
    ads_source_file = str(out.get("ads_source_file") or "")
    ads_analysis_enabled = bool(ads_rows > 0 or ads_source_file)

    advertising_efficiency = out.get("advertising_efficiency", {})
    if not isinstance(advertising_efficiency, dict):
        advertising_efficiency = {}
    advertising_efficiency_analysis_mode = str(
        data_quality.get("advertising_efficiency_analysis_mode")
        or advertising_efficiency.get("analysis_mode")
        or ("disabled" if not ads_analysis_enabled else "preview")
    ).strip().lower()
    if not ads_analysis_enabled:
        advertising_efficiency_analysis_mode = "disabled"
    advertising_efficiency_enabled = bool(advertising_efficiency_analysis_mode != "disabled")

    funnel = cabinet_funnel.get("funnel", {}) if isinstance(cabinet_funnel.get("funnel"), dict) else {}
    views = funnel.get("views", funnel.get("impressions"))
    views_analysis_enabled = views is not None

    orders_confirmed = bool(daily_kpi.get("orders_count_confirmed", False))
    buyouts_confirmed = bool(daily_kpi.get("buyouts_count_confirmed", False))
    commerce_commentary_enabled = bool(orders_confirmed or buyouts_confirmed)
    profitability_commentary_enabled = bool(financial_finality_status == "final")

    territorial_analysis_enabled = bool(data_quality.get("territorial_analysis_enabled", sku_attribution_status != "broken"))
    territorial_actionable_enabled = bool(data_quality.get("territorial_actionable_enabled", territorial_analysis_enabled))
    profit_contribution_enabled = bool(sku_attribution_status != "broken")

    report_reliability_level = resolve_report_reliability_level(
        sku_attribution_status=sku_attribution_status,
        financial_finality_status=financial_finality_status,
        ads_analysis_enabled=ads_analysis_enabled,
    )

    notices: List[str] = []
    if financial_finality_status != "final":
        notices.append("Financial KPI are provisional and must not be interpreted as final daily profit.")
    if sku_attribution_status == "broken":
        notices.append("SKU-level analytics are disabled due to attribution quality issues.")
    if not ads_analysis_enabled:
        notices.append("Ads analysis is suppressed because ads source data is missing.")
    if advertising_efficiency_analysis_mode == "preview":
        notices.append("Advertising efficiency is preview-only until buyout confirmation is available.")
    if territorial_analysis_enabled and not territorial_actionable_enabled:
        notices.append("Territorial conclusions are preview-only due to insufficient demand/stock evidence.")
    if not views_analysis_enabled:
        notices.append("View-dependent conversion interpretation is suppressed because views are missing.")

    if not territorial_analysis_enabled:
        out["territorial_distribution"] = {
            "status": "suppressed_due_to_data_quality",
            "summary": {"suppressed": True},
            "signals": [{"code": "data_quality_issue", "message": "Territorial analysis disabled: broken SKU attribution."}],
            "warnings": [{"code": "territorial_analysis_suppressed", "message": "Territorial analysis disabled due to SKU attribution quality."}],
            "items": [],
            "skus": [],
        }
    if not profit_contribution_enabled:
        out["profit_contribution"] = {
            "status": "suppressed_due_to_data_quality",
            "summary": {"suppressed": True, "sku_count": 0},
            "signals": [{"code": "technical_issue", "message": "Profit contribution disabled: broken SKU attribution."}],
            "warnings": ["suppressed_due_to_sku_attribution"],
            "items": [],
            "p1": [],
            "p2": [],
            "p3": [],
            "p4": [],
            "top_profit_skus": [],
        }

    key_insights = out.get("key_insights", [])
    if isinstance(key_insights, list):
        filtered = [str(item) for item in key_insights if str(item).strip()]
        if sku_attribution_status == "broken":
            filtered = [
                line
                for line in filtered
                if "unassigned" not in line.lower()
                and "rows not assigned" not in line.lower()
                and "territorial risk" not in line.lower()
            ]
            filtered.insert(0, "Technical issue: parser/attribution quality degraded, SKU-level business conclusions are suppressed.")
        out["key_insights"] = filtered[:8]

    data_quality = dict(data_quality)
    data_quality.update(
        {
            "sku_attribution_status": sku_attribution_status,
            "financial_finality_status": financial_finality_status,
            "territorial_analysis_enabled": territorial_analysis_enabled,
            "territorial_actionable_enabled": territorial_actionable_enabled,
            "profit_contribution_enabled": profit_contribution_enabled,
            "ads_analysis_enabled": ads_analysis_enabled,
            "advertising_efficiency_enabled": advertising_efficiency_enabled,
            "advertising_efficiency_analysis_mode": advertising_efficiency_analysis_mode,
            "views_analysis_enabled": views_analysis_enabled,
            "report_reliability_level": report_reliability_level,
        }
    )
    out["data_quality"] = data_quality

    financial_kpi = dict(financial_kpi)
    financial_kpi["financial_finality_status"] = financial_finality_status
    out["financial_kpi"] = financial_kpi

    out["report_guardrails"] = {
        "notices": notices,
        "sku_attribution_status": sku_attribution_status,
        "financial_finality_status": financial_finality_status,
        "territorial_analysis_enabled": territorial_analysis_enabled,
        "territorial_actionable_enabled": territorial_actionable_enabled,
        "profit_contribution_enabled": profit_contribution_enabled,
        "ads_analysis_enabled": ads_analysis_enabled,
        "advertising_efficiency_enabled": advertising_efficiency_enabled,
        "advertising_efficiency_analysis_mode": advertising_efficiency_analysis_mode,
        "views_analysis_enabled": views_analysis_enabled,
        "commerce_commentary_enabled": commerce_commentary_enabled,
        "profitability_commentary_enabled": profitability_commentary_enabled,
        "report_reliability_level": report_reliability_level,
    }
    return out

