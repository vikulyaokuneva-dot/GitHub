from __future__ import annotations

from typing import Any, Dict, List

from .daily_stage_support import sync_from_entry


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
    sales_rows = list(ctx.get("sales_rows", []))
    ads_rows = list(ctx.get("ads_rows", []))
    stocks_rows = list(ctx.get("stocks_rows", []))
    api_orders_rows = list(ctx.get("api_orders_rows", []))
    api_sales_rows = list(ctx.get("api_sales_rows", []))
    api_realization_rows = list(ctx.get("api_realization_rows", []))
    api_stocks_rows = list(ctx.get("api_stocks_rows", []))
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
    totals_for_daily = metrics.get("totals", {}) if isinstance(metrics, dict) else {}
    if not isinstance(totals_for_daily, dict):
        totals_for_daily = {}
    daily_kpi = resolve_daily_kpi(
        totals_for_daily,
        supplier_goods_daily if isinstance(supplier_goods_daily, dict) else {},
        api_orders_rows if isinstance(api_orders_rows, list) else [],
        api_sales_rows if isinstance(api_sales_rows, list) else [],
        api_realization_rows if isinstance(api_realization_rows, list) else [],
    )
    metrics_data_quality = metrics.get("data_quality", {}) if isinstance(metrics, dict) else {}
    if not isinstance(metrics_data_quality, dict):
        metrics_data_quality = {}
    financial_assembly = assemble_financial_kpi(
        totals=totals_for_daily if isinstance(totals_for_daily, dict) else {},
        data_quality=metrics_data_quality if isinstance(metrics_data_quality, dict) else {},
    )
    financial_kpi = financial_assembly.get("financial_kpi", {}) if isinstance(financial_assembly, dict) else {}
    if not isinstance(financial_kpi, dict):
        financial_kpi = {}
    metrics["financial_kpi"] = financial_kpi
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
    api_financial_empty = bool(token and not api_realization_rows and not api_sales_rows)
    financial_data_missing_flag = len(sales_rows) == 0
    financial_data_degraded_flag = False
    if financial_data_missing_flag:
        if not any(
            str(item.get("code") or "") == "financial_data_missing"
            for item in warnings_collector.export_warnings()
            if isinstance(item, dict)
        ):
            warnings_collector.add_warning("financial_data_missing", "данные о продажах не получены")
        financial_data_degraded_flag = True
    elif api_financial_empty:
        warnings_collector.add_warning(
            "wb_api_financial_degraded",
            "WB API financial datasets are empty; local fallback data was used.",
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

    profit_contribution = build_profit_contribution(metrics if isinstance(metrics, dict) else {})
    p1_rows = profit_contribution.get("p1", []) if isinstance(profit_contribution, dict) else []
    p2_rows = profit_contribution.get("p2", []) if isinstance(profit_contribution, dict) else []
    p3_rows = profit_contribution.get("p3", []) if isinstance(profit_contribution, dict) else []
    top_profit_rows = profit_contribution.get("top_profit_skus", []) if isinstance(profit_contribution, dict) else []
    totals_payload = metrics.get("totals", {}) if isinstance(metrics, dict) else {}
    total_profit_overall = float(totals_payload.get("total_profit", totals_payload.get("profit", 0.0)) or 0.0)

    if total_profit_overall <= 0:
        warnings_collector.add_warning(
            "low_total_profit",
            "Total financial profit is non-positive; financial attribution may be incomplete.",
        )
    if isinstance(top_profit_rows, list) and top_profit_rows:
        top_share = float((top_profit_rows[0] or {}).get("profit_share", 0.0) or 0.0)
        if top_share > 0.5:
            warnings_collector.add_warning(
                "profit_concentration_high",
                f"Top SKU contributes {round(top_share, 4)} of total profit.",
            )

    territorial_input: Dict[str, Any] = dict(metrics if isinstance(metrics, dict) else {})
    territorial_input["sales_rows"] = sales_rows
    territorial_input["stocks_rows"] = stocks_rows
    territorial_distribution = build_territorial_distribution(
        territorial_input,
        stocks_raw=stocks_rows,
        seller_id=seller_id,
        run_date=run_date,
    )
    territorial_summary = (
        territorial_distribution.get("summary", {}) if isinstance(territorial_distribution, dict) else {}
    )
    if not isinstance(territorial_summary, dict):
        territorial_summary = {}
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

    warnings_collector.add_warning(
        "territorial_distribution_built",
        f"Territorial distribution built for {sku_with_ktr} SKU with KTR",
    )
    if insufficient_total_count > 0:
        warnings_collector.add_warning(
            "insufficient_warehouse_data",
            "Insufficient warehouse-level data for full territorial analysis",
        )
    high_ktr_count = int(territorial_summary.get("misallocated_count", 0) or 0)
    if high_ktr_count > 0:
        warnings_collector.add_warning("high_ktr_detected", f"High KTR detected for {high_ktr_count} SKU")

    write_daily_metrics_artifacts(
        out_dir=out_dir,
        metrics=metrics if isinstance(metrics, dict) else {},
        financial_debug=financial_debug if isinstance(financial_debug, list) else [],
        abc_rows=abc_rows if isinstance(abc_rows, list) else [],
        profit_contribution=profit_contribution if isinstance(profit_contribution, dict) else {},
        territorial_distribution=territorial_distribution if isinstance(territorial_distribution, dict) else {},
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

    ctx.update(
        {
            "warnings_collector": warnings_collector,
            "source_mode": source_mode,
            "input_debug": input_debug,
            "api_debug": api_debug,
            "metrics": metrics,
            "financial_kpi": financial_kpi,
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
            "facts": facts,
            "confidence": confidence,
            "input_summary": input_summary,
            "data_quality": data_quality,
            "facts_financial_status": facts_financial_status,
            "unassigned_costs": unassigned_costs,
            "sku_metrics": sku_metrics,
            "abc_rows": abc_rows,
            "profit_contribution": profit_contribution,
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
