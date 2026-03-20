"""Metrics engine foundation.

Input: NormalizedBundle.
Output: MetricsBundle (financial + daily + funnel + ads + stock).
Does not build facts/decisions/outputs.
"""

from __future__ import annotations

from ...core.contracts import MetricStatus, MetricsBundle, NormalizedBundle
from ...warnings_utils import dedupe_warnings
from ..ads.summary_assembler import assemble_ads_metrics
from ..daily.resolver import build_daily_metrics_from_financial
from ..financial.assembler import assemble_financial_metrics
from ..funnel.assembler import assemble_funnel_metrics
from ..health import assemble_health_metrics
from ..stock.assembler import assemble_stock_metrics


def _financial_status(financial) -> str:
    statuses = {
        financial.orders_count.status,
        financial.sales_count.status,
        financial.returns_count.status,
        financial.orders_amount.status,
        financial.sales_amount.status,
        financial.seller_payout.status,
        financial.revenue_gross.status,
        financial.commission_amount.status,
        financial.acquiring_amount.status,
        financial.pvz_amount.status,
        financial.penalties_amount.status,
        financial.other_costs_amount.status,
        financial.logistics_cost.status,
        financial.storage_cost.status,
        financial.deductions_amount.status,
        financial.net_realization_amount.status,
        financial.gross_profit_like.status,
        financial.net_profit_like.status,
        financial.margin.status,
    }
    if statuses == {MetricStatus.CONFIRMED.value}:
        return MetricStatus.CONFIRMED.value
    if MetricStatus.CONFIRMED.value in statuses or MetricStatus.PARTIAL.value in statuses:
        return MetricStatus.PARTIAL.value
    return MetricStatus.UNAVAILABLE.value


def _funnel_status(funnel) -> str:
    statuses = {
        funnel.impressions.status,
        funnel.opens.status,
        funnel.cart_adds.status,
        funnel.orders.status,
        funnel.buys.status,
        funnel.ctr_open_from_impressions.status,
        funnel.cr_cart_from_opens.status,
        funnel.cr_orders_from_cart.status,
        funnel.cr_buys_from_orders.status,
        funnel.cr_buys_from_impressions.status,
    }
    if statuses == {MetricStatus.CONFIRMED.value}:
        return MetricStatus.CONFIRMED.value
    if MetricStatus.CONFIRMED.value in statuses or MetricStatus.PARTIAL.value in statuses:
        return MetricStatus.PARTIAL.value
    return MetricStatus.UNAVAILABLE.value


def _ads_status(ads) -> str:
    statuses = {
        ads.campaigns_count.status,
        ads.active_campaigns_count.status,
        ads.impressions.status,
        ads.clicks.status,
        ads.spend.status,
        ads.ctr.status,
        ads.cpc.status,
        ads.orders.status,
        ads.revenue.status,
        ads.conversion_click_to_order.status,
    }
    if statuses == {MetricStatus.CONFIRMED.value}:
        return MetricStatus.CONFIRMED.value
    if MetricStatus.CONFIRMED.value in statuses or MetricStatus.PARTIAL.value in statuses:
        return MetricStatus.PARTIAL.value
    return MetricStatus.UNAVAILABLE.value


def _stock_status(stock) -> str:
    statuses = {
        stock.total_stock_units.status,
        stock.in_stock_items_count.status,
        stock.out_of_stock_items_count.status,
        stock.distinct_nm_ids_count.status,
        stock.distinct_warehouses_count.status,
    }
    if statuses == {MetricStatus.CONFIRMED.value}:
        return MetricStatus.CONFIRMED.value
    if MetricStatus.CONFIRMED.value in statuses or MetricStatus.PARTIAL.value in statuses:
        return MetricStatus.PARTIAL.value
    return MetricStatus.UNAVAILABLE.value


def _health_status(health) -> str:
    return str(health.business_health_score.status)


def build_metrics_bundle(normalized_bundle: NormalizedBundle) -> MetricsBundle:
    financial = assemble_financial_metrics(normalized_bundle)
    daily = build_daily_metrics_from_financial(financial)
    funnel = assemble_funnel_metrics(normalized_bundle)
    ads = assemble_ads_metrics(normalized_bundle)
    stock = assemble_stock_metrics(normalized_bundle)
    health = assemble_health_metrics(
        normalized_bundle=normalized_bundle,
        financial=financial,
        funnel=funnel,
        ads=ads,
        stock=stock,
    )

    source_flags = {
        source_name: (
            status.status.value
            if hasattr(status.status, "value")
            else str(status.status)
        )
        for source_name, status in normalized_bundle.source_statuses.items()
    }

    warnings = list(normalized_bundle.warnings)
    warnings.extend(financial.warnings)
    warnings.extend(funnel.warnings)
    warnings.extend(ads.warnings)
    warnings.extend(stock.warnings)
    warnings.extend(health.warnings)
    warnings = dedupe_warnings(warnings)

    diagnostics = dict(normalized_bundle.diagnostics)
    source_reason_map = diagnostics.get("source_reason_map", {})
    source_reason_map = dict(source_reason_map) if isinstance(source_reason_map, dict) else {}
    diagnostics.update(
        {
            "financial_status": _financial_status(financial),
            "realization_fallback_used": financial.fallback_used,
            "realization_target_date": financial.realization_target_date,
            "realization_actual_date": financial.realization_actual_date,
            "financial_component_quality": dict(financial.component_quality),
            "financial_profit_formula_used": financial.profit_formula_note,
            "financial_model_mode": financial.financial_model_mode,
            "financial_confidence": financial.financial_confidence,
            "financial_source_date": financial.financial_source_date,
            "financial_mode": financial.financial_mode,
            "financial_missing_components": list(financial.financial_missing_components),
            "financial_available_components": list(financial.financial_available_components),
            "profitability_estimate_used": financial.profitability_estimate_used,
            "profitability_estimate_method": financial.profitability_estimate_method,
            "profitability_estimate_formula": financial.profitability_estimate_formula,
            "profitability_estimate_dependencies": list(financial.profitability_estimate_dependencies),
            "profitability_estimate_warning": financial.profitability_estimate_warning,
            "profitability_method": financial.profitability_method,
            "profitability_dependencies": list(financial.profitability_dependencies),
            "profitability_blockers": list(financial.profitability_blockers),
            "realization_lag_days": financial.lag_days,
            "realization_warnings_count": sum(
                1 for warning in financial.warnings if "realization" in str(warning).lower()
            ),
            "fallback_used": financial.fallback_used,
            "funnel_status": _funnel_status(funnel),
            "funnel_records_count": len(normalized_bundle.funnel),
            "funnel_warnings_count": len(funnel.warnings),
            "ads_status": _ads_status(ads),
            "ads_campaigns_status": ads.source_quality.get("campaigns", "missing"),
            "ads_stats_status": ads.source_quality.get("stats", "missing"),
            "ads_warnings_count": len(ads.warnings),
            "stock_status": _stock_status(stock),
            "stock_records_count": len(normalized_bundle.stocks),
            "stock_warnings_count": len(stock.warnings),
            "health_status": _health_status(health),
            "health_business_score": health.business_health_score.value,
            "health_problematic_sku_count": health.problematic_sku_count.value,
            "health_warnings_count": len(health.warnings),
            "realization_reason": source_reason_map.get("realization"),
            "funnel_reason": source_reason_map.get("funnel"),
            "source_reason_map": source_reason_map,
            "metrics_sections_built": ["financial", "daily", "funnel", "ads", "stock", "health"],
        }
    )

    return MetricsBundle(
        run_context=normalized_bundle.run_context,
        financial=financial,
        daily=daily,
        funnel=funnel,
        ads=ads,
        stock=stock,
        health=health,
        diagnostics=diagnostics,
        source_flags=source_flags,
        warnings=warnings,
        source_statuses=normalized_bundle.source_statuses,
    )


def build_metrics(bundle: NormalizedBundle) -> MetricsBundle:
    """Back-compat alias for stage-1 API."""

    return build_metrics_bundle(bundle)
