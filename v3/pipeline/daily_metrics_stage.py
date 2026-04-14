from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from ..domain.event_model import (
    build_buyout_kpi,
    build_daily_status_matrix,
    build_event_date_model,
    build_event_ledger,
    build_financial_kpi_contract,
    build_order_kpi,
    build_render_kpi_values,
)
from ..analytics.sales_funnel import build_sales_funnel_metrics
from ..metrics import FinancialKernelInput, run_financial_kernel
from ..metrics.cabinet_funnel_builder import build_cabinet_funnel_core
from ..metrics.sku_daily_dynamics_builder import build_sku_daily_dynamics
from .daily_stage_support import sync_from_entry


def _safe_float_local(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_int_local(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return int(default)
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _kernel_row_to_dict(row: Any) -> Dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    if hasattr(row, "__dict__"):
        return dict(getattr(row, "__dict__", {}) or {})
    return {}


def _apply_kernel_totals_to_metrics_totals(
    *,
    base_totals: Dict[str, Any],
    account_totals: Dict[str, Any],
    ads_spend: float,
) -> Dict[str, Any]:
    out = dict(base_totals if isinstance(base_totals, dict) else {})
    gross_revenue = _safe_float_local(account_totals.get("gross_revenue"))
    payout = _safe_float_local(account_totals.get("payout"))
    commission = _safe_float_local(account_totals.get("commission"))
    logistics = _safe_float_local(account_totals.get("logistics"))
    storage = _safe_float_local(account_totals.get("storage"))
    penalties = _safe_float_local(account_totals.get("penalties"))
    tax = _safe_float_local(account_totals.get("tax"))
    cogs_total = _safe_float_local(account_totals.get("cogs_total"))
    net_profit = _safe_float_local(account_totals.get("profit"))
    margin = _safe_float_local(account_totals.get("margin"))
    profitability_pct = (net_profit / cogs_total * 100.0) if abs(cogs_total) > 1e-9 else None

    out.update(
        {
            "gross_revenue": round(gross_revenue, 2),
            "wb_realized_revenue": round(gross_revenue, 2),
            "seller_payout": round(payout, 2),
            "total_revenue": round(payout, 2),
            "revenue": round(payout, 2),
            "row_revenue_total": round(gross_revenue, 2),
            "cost_price": round(cogs_total, 2),
            "cogs": round(cogs_total, 2),
            "wb_commission": round(commission, 2),
            "logistics": round(logistics, 2),
            "storage": round(storage, 2),
            "penalties": round(penalties, 2),
            "tax": round(tax, 2),
            "net_profit": round(net_profit, 2),
            "profit": round(net_profit, 2),
            "total_profit": round(net_profit, 2),
            "margin_pct": round(margin * 100.0, 2),
            "profitability_pct": round(profitability_pct, 2) if profitability_pct is not None else None,
            "ads_spend": round(ads_spend, 2),
            "ads_spend_total": round(ads_spend, 2),
        }
    )
    return out


def _build_financial_kpi_from_kernel(
    *,
    account_totals: Dict[str, Any],
    cogs_diagnostics: Dict[str, Any],
    ads_spend: float,
) -> Dict[str, Any]:
    gross_revenue = _safe_float_local(account_totals.get("gross_revenue"))
    seller_payout = _safe_float_local(account_totals.get("payout"))
    commission = _safe_float_local(account_totals.get("commission"))
    logistics = _safe_float_local(account_totals.get("logistics"))
    storage = _safe_float_local(account_totals.get("storage"))
    penalties = _safe_float_local(account_totals.get("penalties"))
    tax = _safe_float_local(account_totals.get("tax"))
    cost_price = _safe_float_local(account_totals.get("cogs_total"))
    net_profit = _safe_float_local(account_totals.get("profit"))
    gross_profit = seller_payout - cost_price - commission
    margin_pct = (net_profit / seller_payout * 100.0) if abs(seller_payout) > 1e-9 else None
    profitability_pct = (net_profit / cost_price * 100.0) if abs(cost_price) > 1e-9 else None
    validation = cogs_diagnostics.get("validation") if isinstance(cogs_diagnostics, dict) else {}
    if not isinstance(validation, dict):
        validation = {}
    kernel_rows_total = _safe_int_local(validation.get("rows_total"), 0)
    missing_required_groups = [
        str(item).strip()
        for item in list(validation.get("missing_required_groups", []))
        if str(item).strip()
    ]
    semantic_mapping_missing = bool(kernel_rows_total > 0 and missing_required_groups)

    cogs_status = str(cogs_diagnostics.get("cogs_status") or "").strip().lower()
    cogs_coverage_pct = cogs_diagnostics.get("cogs_coverage_pct")
    completeness_pct = _safe_float_local(
        cogs_coverage_pct,
        default=100.0 if _safe_int_local(account_totals.get("rows_count"), 0) > 0 else 0.0,
    )
    if semantic_mapping_missing:
        completeness_pct = min(completeness_pct, 50.0)
    cost_price_missing = cogs_status in {"file_not_found", "file_found_not_read", "file_read_not_matched"}
    expense_attribution_partial = cogs_status == "partial_match"
    net_profit_partial = bool(cost_price_missing or expense_attribution_partial or semantic_mapping_missing)
    if semantic_mapping_missing:
        financial_status = "degraded"
        financial_finality_status = "unavailable"
    else:
        financial_status = "partial" if net_profit_partial else "ok"
        financial_finality_status = "partial" if net_profit_partial else "final"
    components = {
        "revenue": {"available": True},
        "seller_payout": {"available": True},
        "gross_revenue": {"available": True},
        "commission": {"available": True},
        "acquiring": {"available": True},
        "pvz_service": {"available": True},
        "logistics": {"available": True},
        "storage": {"available": True},
        "penalties": {"available": True},
        "deductions": {"available": True},
        "loyalty_program": {"available": True},
        "loyalty_points_withheld": {"available": True},
        "other_adjustments": {"available": True},
        "cost_price": {"available": not cost_price_missing},
        "tax": {"available": True},
        "ads_spend": {"available": True},
        "net_profit": {"available": True},
    }
    available_components = sum(1 for value in components.values() if bool((value or {}).get("available")))
    return {
        "revenue": round(seller_payout, 2),
        "gross_revenue": round(gross_revenue, 2),
        "wb_realized_revenue": round(gross_revenue, 2),
        "seller_payout": round(seller_payout, 2),
        "row_revenue_total": round(gross_revenue, 2),
        "revenue_basis": "seller_payout",
        "cost_price": round(cost_price, 2),
        "cogs": round(cost_price, 2),
        "wb_commission": round(commission, 2),
        "acquiring": 0.0,
        "pvz_service": 0.0,
        "logistics": round(logistics, 2),
        "storage": round(storage, 2),
        "penalties": round(penalties, 2),
        "deductions": 0.0,
        "loyalty_program": 0.0,
        "loyalty_points_withheld": 0.0,
        "loyalty_total": 0.0,
        "other_adjustments": 0.0,
        "tax": round(tax, 2),
        "ads_spend": round(_safe_float_local(ads_spend), 2),
        "gross_profit": round(gross_profit, 2),
        "net_profit": round(net_profit, 2),
        "margin_pct": round(margin_pct, 2) if margin_pct is not None else None,
        "profitability_pct": round(profitability_pct, 2) if profitability_pct is not None else None,
        "cost_price_missing": bool(cost_price_missing),
        "wb_commission_missing": False,
        "expense_attribution_partial": bool(expense_attribution_partial),
        "net_profit_partial": bool(net_profit_partial),
        "financial_margin_not_final": bool(net_profit_partial),
        "completeness_pct": round(completeness_pct, 2),
        "components": components,
        "available_components": int(available_components),
        "total_components": int(len(components)),
        "financial_finality_status": financial_finality_status,
        "financial_status": financial_status,
        "is_partial": bool(net_profit_partial),
        "financial_partial": bool(net_profit_partial),
        "kernel_semantic_mapping_missing": bool(semantic_mapping_missing),
        "kernel_semantic_missing_groups": missing_required_groups,
        "basis": "kernel",
        "source_priority": {
            "revenue": "financial_kernel",
            "seller_payout": "financial_kernel",
            "gross_revenue": "financial_kernel",
            "wb_commission": "financial_kernel",
            "logistics": "financial_kernel",
            "storage": "financial_kernel",
            "tax": "financial_kernel",
            "net_profit": "financial_kernel",
            "cost_price": "financial_kernel",
        },
    }


def run_daily_metrics_stage(context: Dict[str, Any]) -> Dict[str, Any]:
    sync_from_entry(globals())

    ctx: Dict[str, Any] = dict(context or {})
    repo_root = str(ctx.get("repo_root") or "")
    seller_id = str(ctx.get("seller_id") or "")
    run_date = str(ctx.get("run_date") or "")
    seller_name = str(ctx.get("seller_name") or seller_id)
    out_dir = str(ctx.get("out_dir") or "")
    token = str(ctx.get("token") or "")

    source_mode = str(ctx.get("source_mode") or "local_reports")
    cfg = ctx.get("cfg", {})
    if not isinstance(cfg, dict):
        cfg = {}
    sales_rows = list(ctx.get("sales_rows", []))
    ads_rows = list(ctx.get("ads_rows", []))
    stocks_rows = list(ctx.get("stocks_rows", []))
    api_orders_rows = list(ctx.get("api_orders_rows", []))
    api_sales_rows = list(ctx.get("api_sales_rows", []))
    api_realization_rows = list(ctx.get("api_realization_rows", []))
    api_stocks_rows = list(ctx.get("api_stocks_rows", []))
    local_financial_fallback_used = bool(ctx.get("local_financial_fallback_used", False))
    supplier_goods_daily = ctx.get("supplier_goods_daily", {})
    if not isinstance(supplier_goods_daily, dict):
        supplier_goods_daily = {}
    discovered_files = ctx.get("discovered_files", {})
    if not isinstance(discovered_files, dict):
        discovered_files = {}
    input_debug = ctx.get("input_debug", {})
    if not isinstance(input_debug, dict):
        input_debug = {}
    api_debug = ctx.get("api_debug", {})
    if not isinstance(api_debug, dict):
        api_debug = {}
    warnings_collector = ctx.get("warnings_collector")
    if not isinstance(warnings_collector, WarningsCollector):
        warnings_collector = WarningsCollector()
    analytics = ctx.get("analytics", {})
    if not isinstance(analytics, dict):
        analytics = {}
    ads_loaded_from_file = bool(ctx.get("ads_loaded_from_file", False))
    ads_source_file = str(ctx.get("ads_source_file") or "")

    raw_bundle = build_raw_bundle(
        source_mode=source_mode,
        sales_rows=sales_rows if isinstance(sales_rows, list) else [],
        ads_rows=ads_rows if isinstance(ads_rows, list) else [],
        stocks_rows=stocks_rows if isinstance(stocks_rows, list) else [],
        api_orders_rows=api_orders_rows if isinstance(api_orders_rows, list) else [],
        api_sales_rows=api_sales_rows if isinstance(api_sales_rows, list) else [],
        api_realization_rows=api_realization_rows if isinstance(api_realization_rows, list) else [],
        api_stocks_rows=api_stocks_rows if isinstance(api_stocks_rows, list) else [],
        supplier_goods_daily=supplier_goods_daily if isinstance(supplier_goods_daily, dict) else {},
        discovered_files=discovered_files if isinstance(discovered_files, dict) else {},
        input_debug=input_debug if isinstance(input_debug, dict) else {},
        api_debug=api_debug if isinstance(api_debug, dict) else {},
    )
    normalized_bundle = normalize_raw_bundle(raw_bundle)
    metrics = build_metrics_from_normalized(normalized_bundle)
    if isinstance(metrics, dict):
        diagnostics_payload = metrics.get("diagnostics", {})
        if not isinstance(diagnostics_payload, dict):
            diagnostics_payload = {}
        diagnostics_payload.update(
            {
                "realization_target_date": api_debug.get("realization_target_date"),
                "realization_actual_source_date": api_debug.get("realization_actual_source_date"),
                "realization_fallback_used": bool(api_debug.get("realization_fallback_used", False)),
                "realization_fallback_lag_days": int(api_debug.get("realization_fallback_lag_days", 0) or 0),
            }
        )
        metrics["diagnostics"] = diagnostics_payload
    if isinstance(input_debug, dict):
        input_debug["raw_layer"] = {
            "source_mode": raw_bundle.source_mode,
            "sales_rows": len(raw_bundle.sales_rows),
            "ads_rows": len(raw_bundle.ads_rows),
            "stocks_rows": len(raw_bundle.stocks_rows),
            "api_orders_rows": len(raw_bundle.api_orders_rows),
            "api_sales_rows": len(raw_bundle.api_sales_rows),
            "api_realization_rows": len(raw_bundle.api_realization_rows),
        }
        input_debug["normalization_layer"] = normalized_bundle.debug if isinstance(normalized_bundle.debug, dict) else {}
    metrics_data_quality = metrics.get("data_quality", {}) if isinstance(metrics, dict) else {}
    if not isinstance(metrics_data_quality, dict):
        metrics_data_quality = {}
    diagnostics_payload = metrics.get("diagnostics", {}) if isinstance(metrics, dict) else {}
    if not isinstance(diagnostics_payload, dict):
        diagnostics_payload = {}
    api_funnel_contract = diagnostics_payload.get("api_funnel_contract", {})
    if not isinstance(api_funnel_contract, dict):
        api_funnel_contract = {}
    geo_completeness = api_funnel_contract.get("geo_completeness", {})
    if not isinstance(geo_completeness, dict):
        geo_completeness = {}
    metrics_data_quality["funnel_contract_source"] = str(api_funnel_contract.get("source") or "missing")
    metrics_data_quality["funnel_lower_available"] = bool(api_funnel_contract.get("lower_funnel_available", False))
    metrics_data_quality["funnel_upper_available"] = bool(api_funnel_contract.get("upper_funnel_available", False))
    metrics_data_quality["funnel_upper_unavailable_from_api"] = bool(
        api_funnel_contract.get("upper_funnel_unavailable_from_api", False)
    )
    metrics_data_quality["orders_geo_coverage_pct"] = float(
        geo_completeness.get("demand_geography_coverage_pct", 0.0) or 0.0
    )

    totals_for_daily = metrics.get("totals", {}) if isinstance(metrics, dict) else {}
    if not isinstance(totals_for_daily, dict):
        totals_for_daily = {}

    tax_rate = _safe_float_local(
        cfg.get("tax_rate", cfg.get("financial_tax_rate", cfg.get("usn_tax_rate", 0.06))),
        default=0.06,
    )
    if tax_rate < 0:
        tax_rate = 0.0
    cogs_rows = ctx.get("cogs_rows")
    if not isinstance(cogs_rows, list):
        cogs_rows = None
    cogs_file_found_raw = ctx.get("cogs_file_found")
    cogs_file_found = cogs_file_found_raw if isinstance(cogs_file_found_raw, bool) else None

    kernel_output = run_financial_kernel(
        FinancialKernelInput(
            realization_rows=sales_rows if isinstance(sales_rows, list) else [],
            tax_rate=tax_rate,
            cogs_rows=cogs_rows,
            cogs_file_found=cogs_file_found,
            source_meta={
                "seller_id": seller_id,
                "run_date": run_date,
                "source_mode": source_mode,
                "financial_rows": len(sales_rows if isinstance(sales_rows, list) else []),
            },
        )
    )
    kernel_account_totals = _kernel_row_to_dict(getattr(kernel_output, "account_financial_totals", {}))
    kernel_sku_financials = {
        int(sku): _kernel_row_to_dict(row)
        for sku, row in (getattr(kernel_output, "sku_financials", {}) or {}).items()
    }
    kernel_cogs_diagnostics = (
        dict(getattr(kernel_output, "cogs_diagnostics", {}) or {})
        if isinstance(getattr(kernel_output, "cogs_diagnostics", {}), dict)
        else {}
    )
    kernel_warnings = [
        item for item in (getattr(kernel_output, "warnings", []) or []) if isinstance(item, dict)
    ]
    if kernel_warnings:
        warnings_collector.extend_warnings(kernel_warnings)

    ads_spend_total = _safe_float_local(
        totals_for_daily.get("ads_spend_total", totals_for_daily.get("ads_spend", 0.0))
    )
    totals_for_daily = _apply_kernel_totals_to_metrics_totals(
        base_totals=totals_for_daily,
        account_totals=kernel_account_totals,
        ads_spend=ads_spend_total,
    )
    metrics["totals"] = totals_for_daily

    financial_kpi = _build_financial_kpi_from_kernel(
        account_totals=kernel_account_totals,
        cogs_diagnostics=kernel_cogs_diagnostics,
        ads_spend=ads_spend_total,
    )
    if not isinstance(financial_kpi, dict):
        financial_kpi = {}
    financial_assembly = {"financial_kpi": financial_kpi, "warning_additions": []}
    metrics_data_quality.update(
        {
            "financial_status": str(financial_kpi.get("financial_status") or "degraded"),
            "financial_partial": bool(financial_kpi.get("is_partial", True)),
            "financial_finality_status": str(financial_kpi.get("financial_finality_status") or "unavailable"),
            "financial_completeness_pct": float(financial_kpi.get("completeness_pct", 0.0) or 0.0),
            "cost_price_missing": bool(financial_kpi.get("cost_price_missing", False)),
            "wb_commission_missing": bool(financial_kpi.get("wb_commission_missing", False)),
            "expense_attribution_partial": bool(financial_kpi.get("expense_attribution_partial", False)),
            "net_profit_partial": bool(financial_kpi.get("net_profit_partial", False)),
            "financial_margin_not_final": bool(financial_kpi.get("financial_margin_not_final", False)),
            "financial_kernel_status": str(getattr(kernel_output, "kernel_status", "") or ""),
        }
    )
    metrics["data_quality"] = metrics_data_quality
    metrics["financial_kpi"] = financial_kpi
    metrics["financial_kernel"] = {
        "kernel_status": str(getattr(kernel_output, "kernel_status", "") or ""),
        "account_financial_totals": kernel_account_totals,
        "sku_financials": kernel_sku_financials,
        "cogs_diagnostics": kernel_cogs_diagnostics,
        "warnings": kernel_warnings,
    }
    metrics["sku_financials"] = kernel_sku_financials

    daily_kpi = resolve_daily_kpi(
        totals_for_daily,
        supplier_goods_daily if isinstance(supplier_goods_daily, dict) else {},
        api_orders_rows if isinstance(api_orders_rows, list) else [],
        api_sales_rows if isinstance(api_sales_rows, list) else [],
        api_realization_rows if isinstance(api_realization_rows, list) else [],
    )
    ads_assembly = assemble_ads_summary(
        metrics=metrics if isinstance(metrics, dict) else {},
        input_debug=input_debug if isinstance(input_debug, dict) else {},
        ads_rows=ads_rows if isinstance(ads_rows, list) else [],
        source_mode=source_mode,
        ads_loaded_from_file=bool(ads_loaded_from_file),
        ads_source_file=str(ads_source_file or ""),
        financial_kpi=financial_kpi if isinstance(financial_kpi, dict) else {},
        has_ads_report_missing_warning=any(
            str(item.get("code") or "") == "ads_report_missing"
            for item in warnings_collector.export_warnings()
            if isinstance(item, dict)
        ),
    )
    ads_unpack = unpack_ads_assembly(ads_assembly if isinstance(ads_assembly, dict) else {})
    ads_summary = ads_unpack.get("ads_summary", {})
    if not isinstance(ads_summary, dict):
        ads_summary = {}
    ads_diagnostics_summary = ads_unpack.get("ads_diagnostics", {})
    if not isinstance(ads_diagnostics_summary, dict):
        ads_diagnostics_summary = {}
    ads_rows_count = int(ads_unpack.get("ads_rows_count", 0) or 0)
    ads_loaded_from_file = bool(ads_unpack.get("ads_loaded_from_file", False))
    ads_source_file = str(ads_unpack.get("ads_source_file") or "")
    ads_attribution_quality = str(ads_unpack.get("ads_attribution_quality") or "unknown")
    daily_kpi_assembly = assemble_daily_kpi(
        daily_kpi=daily_kpi if isinstance(daily_kpi, dict) else {},
        totals=totals_for_daily if isinstance(totals_for_daily, dict) else {},
        financial_kpi=financial_kpi if isinstance(financial_kpi, dict) else {},
        supplier_goods_daily=supplier_goods_daily if isinstance(supplier_goods_daily, dict) else {},
        api_debug=api_debug if isinstance(api_debug, dict) else {},
        input_debug=input_debug if isinstance(input_debug, dict) else {},
        source_mode=source_mode,
        ads_loaded_from_file=bool(ads_loaded_from_file),
        ads_rows_count=int(ads_rows_count),
    )
    daily_unpack = unpack_daily_kpi_assembly(
        daily_kpi_assembly if isinstance(daily_kpi_assembly, dict) else {},
        totals_for_daily if isinstance(totals_for_daily, dict) else {},
        _SOURCE_UNKNOWN,
    )
    daily_kpi = daily_unpack.get("daily_kpi", {})
    if not isinstance(daily_kpi, dict):
        daily_kpi = {}
    totals_for_daily = daily_unpack.get("totals", {})
    if not isinstance(totals_for_daily, dict):
        totals_for_daily = {}
    source_policy = daily_unpack.get("source_policy", {})
    if not isinstance(source_policy, dict):
        source_policy = {}
    source_map = daily_unpack.get("source_map", {})
    if not isinstance(source_map, dict):
        source_map = {}
    source_flags = daily_unpack.get("source_flags", {})
    if not isinstance(source_flags, dict):
        source_flags = {}
    data_source_orders_count = str(daily_unpack.get("data_source_orders_count") or _SOURCE_UNKNOWN)
    data_source_buyouts_count = str(daily_unpack.get("data_source_buyouts_count") or _SOURCE_UNKNOWN)
    data_source_orders_amount = str(daily_unpack.get("data_source_orders_amount") or _SOURCE_UNKNOWN)
    data_source_buyouts_amount = str(daily_unpack.get("data_source_buyouts_amount") or _SOURCE_UNKNOWN)
    data_source_revenue = str(daily_unpack.get("data_source_revenue") or _SOURCE_UNKNOWN)
    data_source_wb_commission = str(daily_unpack.get("data_source_wb_commission") or _SOURCE_UNKNOWN)
    data_source_logistics = str(daily_unpack.get("data_source_logistics") or _SOURCE_UNKNOWN)
    data_source_storage = str(daily_unpack.get("data_source_storage") or _SOURCE_UNKNOWN)
    data_source_ads_spend = str(daily_unpack.get("data_source_ads_spend") or _SOURCE_UNKNOWN)
    data_sources = daily_unpack.get("data_sources", {})
    if not isinstance(data_sources, dict):
        data_sources = {}

    event_date_model = ctx.get("event_date_model", {})
    if not isinstance(event_date_model, dict) or not event_date_model:
        event_date_model = build_event_date_model(
            run_date=run_date,
            api_debug=api_debug if isinstance(api_debug, dict) else {},
            timezone=str((ctx.get("cfg", {}) if isinstance(ctx.get("cfg"), dict) else {}).get("timezone") or "Europe/Berlin"),
        )
    order_kpi = build_order_kpi(
        event_date_model=event_date_model if isinstance(event_date_model, dict) else {},
        daily_kpi=daily_kpi if isinstance(daily_kpi, dict) else {},
    )
    buyout_kpi = build_buyout_kpi(
        event_date_model=event_date_model if isinstance(event_date_model, dict) else {},
        daily_kpi=daily_kpi if isinstance(daily_kpi, dict) else {},
    )
    financial_kpi_legacy = dict(financial_kpi if isinstance(financial_kpi, dict) else {})
    financial_contract = build_financial_kpi_contract(
        event_date_model=event_date_model if isinstance(event_date_model, dict) else {},
        financial_kpi=financial_kpi if isinstance(financial_kpi, dict) else {},
        data_sources=data_sources if isinstance(data_sources, dict) else {},
    )
    if isinstance(financial_contract, dict):
        financial_kpi["contract_date"] = financial_contract.get("date")
        financial_kpi["confirmed"] = bool(financial_contract.get("confirmed", False))

    metrics = apply_metrics_assembly_patches(
        metrics=metrics if isinstance(metrics, dict) else {},
        totals_for_daily=totals_for_daily if isinstance(totals_for_daily, dict) else {},
        ads_summary=ads_summary if isinstance(ads_summary, dict) else {},
        ads_diagnostics_summary=ads_diagnostics_summary if isinstance(ads_diagnostics_summary, dict) else {},
        source_policy=source_policy if isinstance(source_policy, dict) else {},
        source_map=source_map if isinstance(source_map, dict) else {},
        source_flags=source_flags if isinstance(source_flags, dict) else {},
        commerce_activity=daily_unpack.get("commerce_activity", {}),
        daily_kpi=daily_kpi if isinstance(daily_kpi, dict) else {},
        commerce_kpi=daily_unpack.get("commerce_kpi", {}),
    )
    daily_status_matrix = build_daily_status_matrix(
        order_kpi=order_kpi if isinstance(order_kpi, dict) else {},
        buyout_kpi=buyout_kpi if isinstance(buyout_kpi, dict) else {},
        financial_kpi=financial_kpi if isinstance(financial_kpi, dict) else {},
        ads_summary=ads_summary if isinstance(ads_summary, dict) else {},
        data_quality=metrics_data_quality if isinstance(metrics_data_quality, dict) else {},
    )
    render_kpi = build_render_kpi_values(
        order_kpi=order_kpi if isinstance(order_kpi, dict) else {},
        buyout_kpi=buyout_kpi if isinstance(buyout_kpi, dict) else {},
        financial_kpi=financial_kpi if isinstance(financial_kpi, dict) else {},
        daily_status_matrix=daily_status_matrix if isinstance(daily_status_matrix, dict) else {},
    )
    event_ledger = build_event_ledger(
        event_date_model=event_date_model if isinstance(event_date_model, dict) else {},
        order_kpi=order_kpi if isinstance(order_kpi, dict) else {},
        buyout_kpi=buyout_kpi if isinstance(buyout_kpi, dict) else {},
        financial_kpi=financial_kpi if isinstance(financial_kpi, dict) else {},
        api_debug=api_debug if isinstance(api_debug, dict) else {},
        data_sources=data_sources if isinstance(data_sources, dict) else {},
    )
    metrics["event_date_model"] = event_date_model if isinstance(event_date_model, dict) else {}
    metrics["order_kpi"] = order_kpi if isinstance(order_kpi, dict) else {}
    metrics["buyout_kpi"] = buyout_kpi if isinstance(buyout_kpi, dict) else {}
    metrics["financial_kpi"] = financial_kpi if isinstance(financial_kpi, dict) else {}
    metrics["financial_kpi_legacy"] = financial_kpi_legacy
    metrics["daily_status_matrix"] = daily_status_matrix if isinstance(daily_status_matrix, dict) else {}
    metrics["render_kpi"] = render_kpi if isinstance(render_kpi, dict) else {}
    metrics["event_ledger"] = event_ledger if isinstance(event_ledger, dict) else {}
    cabinet_funnel = build_cabinet_funnel_core(
        run_date=run_date,
        metrics=metrics if isinstance(metrics, dict) else {},
        ads_diagnostics=ads_diagnostics_summary if isinstance(ads_diagnostics_summary, dict) else {},
    )
    metrics["sales_funnel"] = cabinet_funnel if isinstance(cabinet_funnel, dict) else {}
    sales_funnel_diagnostics = build_sales_funnel_metrics(
        metrics=metrics if isinstance(metrics, dict) else {},
        run_date=run_date,
    )
    if isinstance(cabinet_funnel, dict):
        cabinet_funnel["sku_diagnostics"] = sales_funnel_diagnostics if isinstance(sales_funnel_diagnostics, dict) else {}
    metrics["sales_funnel_diagnostics"] = sales_funnel_diagnostics if isinstance(sales_funnel_diagnostics, dict) else {}
    if isinstance(sales_funnel_diagnostics, dict):
        warnings_collector.extend_warnings(sales_funnel_diagnostics.get("warnings", []))
    if isinstance(cabinet_funnel, dict) and isinstance(cabinet_funnel.get("sku_funnel"), list):
        metrics["sku_sales_funnel"] = cabinet_funnel.get("sku_funnel", [])
    keyword_monitoring = build_keyword_monitoring(
        {"ads_rows": ads_rows if isinstance(ads_rows, list) else []},
        run_date=run_date,
    )
    metrics["keyword_monitoring"] = keyword_monitoring if isinstance(keyword_monitoring, dict) else {}
    analytics["keyword_monitoring"] = keyword_monitoring if isinstance(keyword_monitoring, dict) else {}
    if isinstance(keyword_monitoring, dict):
        warnings_collector.extend_warnings(keyword_monitoring.get("warnings", []))
    advertising_efficiency = build_advertising_efficiency(
        metrics=metrics if isinstance(metrics, dict) else {},
        ads_rows=ads_rows if isinstance(ads_rows, list) else [],
        keyword_monitoring=keyword_monitoring if isinstance(keyword_monitoring, dict) else {},
        daily_kpi=daily_kpi if isinstance(daily_kpi, dict) else {},
        seller_id=seller_id,
        run_date=run_date,
        config=cfg if isinstance(cfg, dict) else {},
    )
    metrics["advertising_efficiency"] = advertising_efficiency if isinstance(advertising_efficiency, dict) else {}
    analytics["advertising_efficiency"] = advertising_efficiency if isinstance(advertising_efficiency, dict) else {}

    advertising_efficiency_analysis_mode = str(
        (advertising_efficiency.get("analysis_mode") if isinstance(advertising_efficiency, dict) else "") or "disabled"
    ).strip().lower()
    advertising_efficiency_enabled = bool(advertising_efficiency_analysis_mode != "disabled")
    metrics_data_quality["advertising_efficiency_analysis_mode"] = advertising_efficiency_analysis_mode
    metrics_data_quality["advertising_efficiency_enabled"] = advertising_efficiency_enabled

    if advertising_efficiency_analysis_mode == "disabled":
        warnings_collector.add_warning(
            "advertising_efficiency_disabled",
            "Advertising efficiency engine is disabled because ads data is missing.",
        )
    elif advertising_efficiency_analysis_mode == "preview":
        warnings_collector.add_warning(
            "advertising_efficiency_preview",
            "Advertising efficiency is preview-only because buyouts are not confirmed.",
        )

    if isinstance(advertising_efficiency, dict):
        warnings_collector.extend_warnings(advertising_efficiency.get("warnings", []))
    sku_daily_dynamics = build_sku_daily_dynamics(
        run_date=run_date,
        metrics=metrics if isinstance(metrics, dict) else {},
        sales_rows=sales_rows if isinstance(sales_rows, list) else [],
        ads_rows=ads_rows if isinstance(ads_rows, list) else [],
        stocks_rows=stocks_rows if isinstance(stocks_rows, list) else [],
        history_root=(Path(out_dir).parent / "history") if out_dir else None,
    )
    if isinstance(input_debug, dict):
        input_debug = apply_input_debug_assembly_patches(
            input_debug=input_debug if isinstance(input_debug, dict) else {},
            input_debug_patch=ads_unpack.get("input_debug_patch", {}),
            source_policy=source_policy if isinstance(source_policy, dict) else {},
        )
    warnings_collector.extend_warnings(daily_unpack.get("warning_additions", []))
    _append_daily_kpi_mismatch_warning(
        warnings_collector=warnings_collector,
        summary_daily_kpi=daily_kpi,
        supplier_goods_daily=supplier_goods_daily if isinstance(supplier_goods_daily, dict) else {},
    )
    financial_debug = metrics.get("financial_debug", []) if isinstance(metrics, dict) else []
    if not isinstance(financial_debug, list):
        financial_debug = []
    invalid_rows = int(metrics_data_quality.get("invalid_sku_rows", 0) or 0)
    if invalid_rows > 0:
        warnings_collector.add_warning("invalid_sku_filtered", f"Filtered invalid SKU rows: {invalid_rows}")
        invalid_reason_counts = metrics_data_quality.get("invalid_sku_reason_counts", {})
        if isinstance(invalid_reason_counts, dict) and invalid_reason_counts:
            breakdown = ", ".join(f"{k}={int(v)}" for k, v in sorted(invalid_reason_counts.items(), key=lambda x: str(x[0])))
            warnings_collector.add_warning("invalid_sku_reason_breakdown", f"Invalid SKU reason breakdown: {breakdown}")
    if bool(metrics_data_quality.get("unassigned_costs_present", False)):
        sku_attr_status_for_warning = str(metrics_data_quality.get("sku_attribution_status") or "ok").strip().lower()
        if sku_attr_status_for_warning == "broken":
            warnings_collector.add_warning(
                "sku_attribution_broken",
                "SKU attribution quality is broken; unassigned rows are treated as parser/data issue.",
            )
        else:
            warnings_collector.add_warning(
                "unassigned_costs_detected",
                "Part of costs is not assigned to SKU and stored in unassigned_costs.",
            )
    zero_revenue_activity_skus = metrics_data_quality.get("zero_revenue_activity_skus", [])
    if isinstance(zero_revenue_activity_skus, list) and zero_revenue_activity_skus:
        warnings_collector.add_warning(
            "sales_activity_zero_revenue",
            "sales activity exists but revenue attribution is zero: "
            + ", ".join(str(sku) for sku in zero_revenue_activity_skus[:10]),
        )
    assembly_warning_additions = extract_financial_ads_warning_additions(
        financial_assembly=financial_assembly if isinstance(financial_assembly, dict) else {},
        ads_assembly=ads_assembly if isinstance(ads_assembly, dict) else {},
    )
    warnings_collector.extend_warnings(assembly_warning_additions.get("financial_warning_additions", []))
    warnings_collector.extend_warnings(assembly_warning_additions.get("ads_warning_additions", []))
    api_financial_contour_missing = bool(token and not api_realization_rows)
    financial_data_missing_flag = len(sales_rows) == 0
    financial_data_degraded_flag = False
    if financial_data_missing_flag:
        if not any(
            str(item.get("code") or "") == "financial_data_missing"
            for item in warnings_collector.export_warnings()
            if isinstance(item, dict)
        ):
            warnings_collector.add_warning(
                "financial_data_missing",
                "Financial contour is missing: no realization rows and no local financial fallback.",
            )
        financial_data_degraded_flag = True
    elif api_financial_contour_missing:
        if local_financial_fallback_used:
            warnings_collector.add_warning(
                "wb_api_financial_degraded",
                "WB API realization data is empty; local financial fallback data was used.",
            )
            financial_data_degraded_flag = True
        else:
            warnings_collector.add_warning(
                "financial_contour_not_confirmed",
                "WB API realization data is empty; final financial contour is not confirmed.",
            )
            financial_data_degraded_flag = True

    facts = build_daily_facts_base(
        seller_id=seller_id,
        run_date=run_date,
        seller_name=seller_name,
        metrics=metrics if isinstance(metrics, dict) else {},
        discovered_files=discovered_files if isinstance(discovered_files, dict) else {},
        warnings=warnings_collector.export_warnings(),
        source_mode=source_mode,
        api_debug=api_debug if isinstance(api_debug, dict) else {},
        ads_summary=ads_summary if isinstance(ads_summary, dict) else {},
        ads_rows_count=ads_rows_count,
        financial_kpi=financial_kpi if isinstance(financial_kpi, dict) else {},
        ads_loaded_from_file=bool(ads_loaded_from_file),
        ads_source_file=ads_source_file,
        ads_attribution_quality=ads_attribution_quality,
        data_source_orders_count=data_source_orders_count,
        data_source_buyouts_count=data_source_buyouts_count,
        data_source_orders_amount=data_source_orders_amount,
        data_source_buyouts_amount=data_source_buyouts_amount,
        daily_kpi=daily_kpi if isinstance(daily_kpi, dict) else {},
        data_source_revenue=data_source_revenue,
        data_source_wb_commission=data_source_wb_commission,
        data_source_logistics=data_source_logistics,
        data_source_storage=data_source_storage,
        data_source_ads_spend=data_source_ads_spend,
        source_flags=source_flags if isinstance(source_flags, dict) else {},
        source_policy=source_policy if isinstance(source_policy, dict) else {},
        financial_data_degraded_flag=financial_data_degraded_flag,
        event_date_model=event_date_model if isinstance(event_date_model, dict) else {},
        order_kpi=order_kpi if isinstance(order_kpi, dict) else {},
        buyout_kpi=buyout_kpi if isinstance(buyout_kpi, dict) else {},
        daily_status_matrix=daily_status_matrix if isinstance(daily_status_matrix, dict) else {},
        event_ledger=event_ledger if isinstance(event_ledger, dict) else {},
        render_kpi=render_kpi if isinstance(render_kpi, dict) else {},
    )

    confidence = str(facts.get("data_confidence", "low"))
    input_summary = facts.get("input_summary", {}) if isinstance(facts, dict) else {}
    data_quality = facts.get("data_quality", {}) if isinstance(facts, dict) else {}
    facts_financial_status = str(data_quality.get("financial_status") or "ok") if isinstance(data_quality, dict) else "ok"
    unassigned_costs = metrics.get("unassigned_costs", {}) if isinstance(metrics, dict) else {}

    sku_metrics = _extract_sku_metrics(metrics)
    abc_rows = compute_abc(sku_metrics)
    abc_summary = {"A": 0, "B": 0, "C": 0}
    for row in abc_rows:
        cls = str(row.get("abc_class", ""))
        if cls in abc_summary:
            abc_summary[cls] += 1

    sku_attribution_status = str(metrics_data_quality.get("sku_attribution_status") or "ok").strip().lower()
    financial_finality_status = str(metrics_data_quality.get("financial_finality_status") or "unavailable").strip().lower()
    territorial_analysis_enabled = bool(metrics_data_quality.get("territorial_analysis_enabled", sku_attribution_status != "broken"))
    profit_contribution_enabled = bool(
        metrics_data_quality.get("profit_contribution_enabled", sku_attribution_status != "broken")
    )

    metrics_data_quality["territorial_analysis_enabled"] = territorial_analysis_enabled
    metrics_data_quality["profit_contribution_enabled"] = profit_contribution_enabled
    metrics["data_quality"] = metrics_data_quality

    if profit_contribution_enabled:
        profit_contribution = build_profit_contribution(metrics if isinstance(metrics, dict) else {})
        profit_contribution_status = str(
            (profit_contribution.get("status") if isinstance(profit_contribution, dict) else "") or ""
        ).strip().lower()
        if profit_contribution_status in {"partial", "insufficient_data"}:
            warnings_collector.add_warning(
                "profit_contribution_partial_data",
                f"Profit contribution computed with status={profit_contribution_status}.",
            )
    else:
        profit_contribution = {
            "status": "suppressed_due_to_data_quality",
            "summary": {"suppressed": True, "sku_count": 0},
            "items": [],
            "p1": [],
            "p2": [],
            "p3": [],
            "p4": [],
            "top_profit_skus": [],
            "warnings": ["suppressed_due_to_sku_attribution"],
            "signals": [
                {
                    "code": "technical_issue",
                    "message": "Profit contribution suppressed: SKU attribution is broken.",
                }
            ],
        }
        warnings_collector.add_warning(
            "profit_contribution_suppressed",
            "Profit contribution engine suppressed due to broken SKU attribution.",
        )
    metrics["profit_contribution"] = profit_contribution if isinstance(profit_contribution, dict) else {}
    analytics["profit_contribution"] = profit_contribution if isinstance(profit_contribution, dict) else {}

    p1_rows = profit_contribution.get("p1", []) if isinstance(profit_contribution, dict) else []
    p2_rows = profit_contribution.get("p2", []) if isinstance(profit_contribution, dict) else []
    p3_rows = profit_contribution.get("p3", []) if isinstance(profit_contribution, dict) else []
    top_profit_rows = profit_contribution.get("top_profit_skus", []) if isinstance(profit_contribution, dict) else []
    totals_payload = metrics.get("totals", {}) if isinstance(metrics, dict) else {}
    total_profit_overall = float(totals_payload.get("total_profit", totals_payload.get("profit", 0.0)) or 0.0)

    if total_profit_overall <= 0 and financial_finality_status == "final":
        warnings_collector.add_warning(
            "low_total_profit",
            "Total financial profit is non-positive; financial attribution may be incomplete.",
        )
    if profit_contribution_enabled and isinstance(top_profit_rows, list) and top_profit_rows:
        top_share = float((top_profit_rows[0] or {}).get("profit_share", 0.0) or 0.0)
        if top_share > 0.5:
            warnings_collector.add_warning(
                "profit_concentration_high",
                f"Top SKU contributes {round(top_share, 4)} of total profit.",
            )

    if territorial_analysis_enabled:
        territorial_input: Dict[str, Any] = dict(metrics if isinstance(metrics, dict) else {})
        orders_rows_from_api = metrics.get("orders_rows_from_api", []) if isinstance(metrics, dict) else []
        if not isinstance(orders_rows_from_api, list):
            orders_rows_from_api = []
        territorial_input["sales_rows"] = orders_rows_from_api if orders_rows_from_api else sales_rows
        territorial_input["orders_rows_from_api"] = orders_rows_from_api
        territorial_input["stocks_rows"] = stocks_rows
        territorial_distribution = build_territorial_distribution(
            territorial_input,
            stocks_raw=stocks_rows,
            seller_id=seller_id,
            run_date=run_date,
            config=cfg if isinstance(cfg, dict) else {},
        )
    else:
        territorial_distribution = {
            "status": "suppressed_due_to_data_quality",
            "summary": {"suppressed": True},
            "signals": [
                {"code": "data_quality_issue", "message": "Territorial engine suppressed: SKU attribution is broken."}
            ],
            "warnings": [
                {
                    "code": "territorial_analysis_suppressed",
                    "message": "Territorial distribution suppressed due to broken SKU attribution.",
                }
            ],
            "items": [],
            "skus": [],
        }
        warnings_collector.add_warning(
            "territorial_analysis_suppressed",
            "Territorial distribution engine suppressed due to broken SKU attribution.",
        )
    analytics["territorial_distribution"] = territorial_distribution if isinstance(territorial_distribution, dict) else {}
    metrics["territorial_distribution"] = territorial_distribution if isinstance(territorial_distribution, dict) else {}
    if isinstance(territorial_distribution, dict):
        warnings_collector.extend_warnings(territorial_distribution.get("warnings", []))
    territorial_summary = (
        territorial_distribution.get("summary", {}) if isinstance(territorial_distribution, dict) else {}
    )
    if not isinstance(territorial_summary, dict):
        territorial_summary = {}
    territorial_analysis_mode = str(
        territorial_summary.get("analysis_mode", territorial_distribution.get("analysis_mode", "disabled"))
        if isinstance(territorial_distribution, dict)
        else "disabled"
    ).strip().lower()
    territorial_recommendation_status = str(
        territorial_summary.get("recommendation_status", territorial_distribution.get("recommendation_status", "blocked_by_data"))
        if isinstance(territorial_distribution, dict)
        else "blocked_by_data"
    ).strip().lower()
    territorial_confidence_level = str(
        territorial_summary.get("confidence_level", territorial_distribution.get("confidence_level", "low"))
        if isinstance(territorial_distribution, dict)
        else "low"
    ).strip().lower()
    territorial_suppressed_due_to_data_quality = bool(
        territorial_summary.get("suppressed_due_to_data_quality", territorial_distribution.get("suppressed_due_to_data_quality", False))
        if isinstance(territorial_distribution, dict)
        else False
    )
    territorial_actionable_enabled = bool(
        territorial_analysis_enabled
        and territorial_analysis_mode == "full"
        and territorial_recommendation_status == "actionable"
        and not territorial_suppressed_due_to_data_quality
    )

    metrics_data_quality["territorial_analysis_enabled"] = bool(territorial_analysis_enabled and territorial_analysis_mode != "disabled")
    metrics_data_quality["territorial_actionable_enabled"] = territorial_actionable_enabled
    metrics_data_quality["territorial_analysis_mode"] = territorial_analysis_mode
    metrics_data_quality["territorial_analysis_status"] = str(
        territorial_summary.get("analysis_status", territorial_distribution.get("analysis_status", "blocked_by_data"))
        if isinstance(territorial_distribution, dict)
        else "blocked_by_data"
    ).strip().lower()
    metrics_data_quality["territorial_recommendation_status"] = territorial_recommendation_status
    metrics_data_quality["territorial_blocked_reasons"] = (
        [str(reason) for reason in list(territorial_summary.get("blocked_reasons", [])) if str(reason).strip()]
        if isinstance(territorial_summary.get("blocked_reasons"), list)
        else []
    )
    metrics_data_quality["territorial_confidence_level"] = territorial_confidence_level
    metrics_data_quality["territorial_suppressed_due_to_data_quality"] = territorial_suppressed_due_to_data_quality
    metrics["data_quality"] = metrics_data_quality

    logistics_summary: Dict[str, Any] = {}
    facts = attach_daily_facts_sections(
        facts=facts if isinstance(facts, dict) else {},
        p1_rows=p1_rows if isinstance(p1_rows, list) else [],
        p2_rows=p2_rows if isinstance(p2_rows, list) else [],
        p3_rows=p3_rows if isinstance(p3_rows, list) else [],
        top_profit_rows=top_profit_rows if isinstance(top_profit_rows, list) else [],
        territorial_summary=territorial_summary if isinstance(territorial_summary, dict) else {},
        logistics_summary=logistics_summary,
    )
    territorial_distribution_summary = (
        facts.get("territorial_distribution_summary", {}) if isinstance(facts.get("territorial_distribution_summary"), dict) else {}
    )
    sku_with_ktr = int(territorial_distribution_summary.get("sku_with_ktr", 0) or 0)
    insufficient_total_count = int(territorial_distribution_summary.get("insufficient_total_count", 0) or 0)

    if territorial_analysis_enabled:
        warnings_collector.add_warning(
            "territorial_distribution_built",
            f"Territorial distribution built for {sku_with_ktr} SKU with KTR",
        )
        if not territorial_actionable_enabled:
            warnings_collector.add_warning(
                "territorial_distribution_preview_only",
                "Territorial conclusions are preview-only due to limited evidence coverage.",
            )
        if insufficient_total_count > 0:
            warnings_collector.add_warning(
                "insufficient_warehouse_data",
                "Insufficient warehouse-level data for full territorial analysis",
            )
        high_ktr_count = int(territorial_summary.get("misallocated_count", 0) or 0)
        if territorial_actionable_enabled and high_ktr_count > 0:
            warnings_collector.add_warning("high_ktr_detected", f"High KTR detected for {high_ktr_count} SKU")

    write_daily_metrics_artifacts(
        out_dir=out_dir,
        metrics=metrics if isinstance(metrics, dict) else {},
        financial_debug=financial_debug if isinstance(financial_debug, list) else [],
        abc_rows=abc_rows if isinstance(abc_rows, list) else [],
        profit_contribution=profit_contribution if isinstance(profit_contribution, dict) else {},
        keyword_monitoring=keyword_monitoring if isinstance(keyword_monitoring, dict) else {},
        advertising_efficiency=advertising_efficiency if isinstance(advertising_efficiency, dict) else {},
        territorial_distribution=territorial_distribution if isinstance(territorial_distribution, dict) else {},
        event_ledger=event_ledger if isinstance(event_ledger, dict) else {},
        cabinet_funnel=cabinet_funnel if isinstance(cabinet_funnel, dict) else {},
        sku_daily_dynamics=sku_daily_dynamics if isinstance(sku_daily_dynamics, dict) else {},
    )

    logistics_ktr = build_logistics_ktr(seller_id=seller_id, run_date=run_date, repo_root=repo_root)
    logistics_summary = logistics_ktr.get("summary", {}) if isinstance(logistics_ktr, dict) else {}
    if not isinstance(logistics_summary, dict):
        logistics_summary = {}
    facts = attach_daily_facts_sections(
        facts=facts if isinstance(facts, dict) else {},
        p1_rows=p1_rows if isinstance(p1_rows, list) else [],
        p2_rows=p2_rows if isinstance(p2_rows, list) else [],
        p3_rows=p3_rows if isinstance(p3_rows, list) else [],
        top_profit_rows=top_profit_rows if isinstance(top_profit_rows, list) else [],
        territorial_summary=territorial_summary if isinstance(territorial_summary, dict) else {},
        logistics_summary=logistics_summary if isinstance(logistics_summary, dict) else {},
    )
    if isinstance(facts.get("data_quality"), dict):
        facts_data_quality = dict(facts.get("data_quality", {}))
        facts_data_quality.update(
            {
                "sku_attribution_status": sku_attribution_status,
                "financial_finality_status": financial_finality_status,
                "territorial_analysis_enabled": bool(metrics_data_quality.get("territorial_analysis_enabled", territorial_analysis_enabled)),
                "territorial_actionable_enabled": bool(metrics_data_quality.get("territorial_actionable_enabled", False)),
                "territorial_analysis_mode": str(metrics_data_quality.get("territorial_analysis_mode") or "disabled"),
                "territorial_analysis_status": str(metrics_data_quality.get("territorial_analysis_status") or "blocked_by_data"),
                "territorial_recommendation_status": str(metrics_data_quality.get("territorial_recommendation_status") or "blocked_by_data"),
                "territorial_blocked_reasons": (
                    [str(reason) for reason in list(metrics_data_quality.get("territorial_blocked_reasons", [])) if str(reason).strip()]
                    if isinstance(metrics_data_quality.get("territorial_blocked_reasons"), list)
                    else []
                ),
                "territorial_confidence_level": str(metrics_data_quality.get("territorial_confidence_level") or "low"),
                "territorial_suppressed_due_to_data_quality": bool(metrics_data_quality.get("territorial_suppressed_due_to_data_quality", False)),
                "profit_contribution_enabled": profit_contribution_enabled,
                "advertising_efficiency_enabled": bool(metrics_data_quality.get("advertising_efficiency_enabled", False)),
                "advertising_efficiency_analysis_mode": str(metrics_data_quality.get("advertising_efficiency_analysis_mode") or "disabled"),
                "report_reliability_level": str(metrics_data_quality.get("report_reliability_level") or "medium"),
            }
        )
        facts["data_quality"] = facts_data_quality
    data_quality = facts.get("data_quality", {}) if isinstance(facts, dict) else {}
    if not isinstance(data_quality, dict):
        data_quality = {}

    ctx.update(
        {
            "warnings_collector": warnings_collector,
            "analytics": analytics,
            "source_mode": source_mode,
            "input_debug": input_debug,
            "api_debug": api_debug,
            "metrics": metrics,
            "financial_kpi": financial_kpi,
            "financial_kernel": metrics.get("financial_kernel", {}) if isinstance(metrics, dict) else {},
            "kernel_sku_financials": kernel_sku_financials,
            "ads_summary": ads_summary,
            "ads_diagnostics_summary": ads_diagnostics_summary,
            "ads_rows_count": ads_rows_count,
            "ads_loaded_from_file": ads_loaded_from_file,
            "ads_source_file": ads_source_file,
            "ads_attribution_quality": ads_attribution_quality,
            "daily_kpi": daily_kpi,
            "totals_for_daily": totals_for_daily,
            "source_policy": source_policy,
            "source_map": source_map,
            "source_flags": source_flags,
            "data_sources": data_sources,
            "data_source_orders_count": data_source_orders_count,
            "data_source_buyouts_count": data_source_buyouts_count,
            "data_source_orders_amount": data_source_orders_amount,
            "data_source_buyouts_amount": data_source_buyouts_amount,
            "data_source_revenue": data_source_revenue,
            "data_source_wb_commission": data_source_wb_commission,
            "data_source_logistics": data_source_logistics,
            "data_source_storage": data_source_storage,
            "data_source_ads_spend": data_source_ads_spend,
            "financial_data_missing_flag": financial_data_missing_flag,
            "financial_data_degraded_flag": financial_data_degraded_flag,
            "event_date_model": event_date_model,
            "order_kpi": order_kpi,
            "buyout_kpi": buyout_kpi,
            "daily_status_matrix": daily_status_matrix,
            "render_kpi": render_kpi,
            "event_ledger": event_ledger,
            "cabinet_funnel": cabinet_funnel,
            "sales_funnel_diagnostics": sales_funnel_diagnostics,
            "sku_daily_dynamics": sku_daily_dynamics,
            "facts": facts,
            "confidence": confidence,
            "input_summary": input_summary,
            "data_quality": data_quality,
            "facts_financial_status": facts_financial_status,
            "unassigned_costs": unassigned_costs,
            "sku_metrics": sku_metrics,
            "abc_rows": abc_rows,
            "profit_contribution": profit_contribution,
            "keyword_monitoring": keyword_monitoring,
            "advertising_efficiency": advertising_efficiency if isinstance(advertising_efficiency, dict) else {},
            "query_profitability": (advertising_efficiency.get("query_profitability", {}) if isinstance(advertising_efficiency, dict) else {}),
            "portfolio_ads_summary": (advertising_efficiency.get("portfolio_ads_summary", {}) if isinstance(advertising_efficiency, dict) else {}),
            "p1_rows": p1_rows,
            "p2_rows": p2_rows,
            "p3_rows": p3_rows,
            "top_profit_rows": top_profit_rows,
            "territorial_distribution": territorial_distribution,
            "territorial_summary": territorial_summary,
            "logistics_summary": logistics_summary,
            "logistics_ktr": logistics_ktr,
        }
    )
    return ctx


