"""Metrics engine foundation.

Input: NormalizedBundle.
Output: MetricsBundle (financial + daily + funnel + ads).
Does not build facts/decisions/outputs.
"""

from __future__ import annotations

from ...core.contracts import MetricStatus, MetricsBundle, NormalizedBundle
from ..ads.summary_assembler import assemble_ads_metrics
from ..daily.resolver import build_daily_metrics_from_financial
from ..financial.assembler import assemble_financial_metrics
from ..funnel.assembler import assemble_funnel_metrics


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


def build_metrics_bundle(normalized_bundle: NormalizedBundle) -> MetricsBundle:
    financial = assemble_financial_metrics(normalized_bundle)
    daily = build_daily_metrics_from_financial(financial)
    funnel = assemble_funnel_metrics(normalized_bundle)
    ads = assemble_ads_metrics(normalized_bundle)

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

    diagnostics = dict(normalized_bundle.diagnostics)
    diagnostics.update(
        {
            "financial_status": _financial_status(financial),
            "realization_fallback_used": financial.fallback_used,
            "realization_target_date": financial.realization_target_date,
            "realization_actual_date": financial.realization_actual_date,
            "financial_component_quality": dict(financial.component_quality),
            "financial_profit_formula_used": financial.profit_formula_note,
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
            "metrics_sections_built": ["financial", "daily", "funnel", "ads"],
        }
    )

    return MetricsBundle(
        run_context=normalized_bundle.run_context,
        financial=financial,
        daily=daily,
        funnel=funnel,
        ads=ads,
        diagnostics=diagnostics,
        source_flags=source_flags,
        warnings=warnings,
        source_statuses=normalized_bundle.source_statuses,
    )


def build_metrics(bundle: NormalizedBundle) -> MetricsBundle:
    """Back-compat alias for stage-1 API."""

    return build_metrics_bundle(bundle)

