"""Metrics engine foundation.

Input: NormalizedBundle.
Output: MetricsBundle (financial + daily subset only).
Does not build facts/decisions/outputs.
"""

from __future__ import annotations

from ...core.contracts import MetricStatus, MetricsBundle, NormalizedBundle
from ..daily.resolver import build_daily_metrics_from_financial
from ..financial.assembler import assemble_financial_metrics


def _financial_status(financial) -> str:
    statuses = {
        financial.orders_count.status,
        financial.sales_count.status,
        financial.returns_count.status,
        financial.orders_amount.status,
        financial.sales_amount.status,
        financial.seller_payout.status,
        financial.logistics_cost.status,
        financial.storage_cost.status,
        financial.deductions_amount.status,
        financial.net_realization_amount.status,
    }
    if statuses == {MetricStatus.CONFIRMED.value}:
        return MetricStatus.CONFIRMED.value
    if MetricStatus.CONFIRMED.value in statuses or MetricStatus.PARTIAL.value in statuses:
        return MetricStatus.PARTIAL.value
    return MetricStatus.UNAVAILABLE.value


def build_metrics_bundle(normalized_bundle: NormalizedBundle) -> MetricsBundle:
    financial = assemble_financial_metrics(normalized_bundle)
    daily = build_daily_metrics_from_financial(financial)

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

    diagnostics = dict(normalized_bundle.diagnostics)
    diagnostics.update(
        {
            "financial_status": _financial_status(financial),
            "realization_fallback_used": financial.fallback_used,
            "realization_target_date": financial.realization_target_date,
            "realization_actual_date": financial.realization_actual_date,
            "metrics_sections_built": ["financial", "daily"],
        }
    )

    return MetricsBundle(
        run_context=normalized_bundle.run_context,
        financial=financial,
        daily=daily,
        diagnostics=diagnostics,
        source_flags=source_flags,
        warnings=warnings,
        source_statuses=normalized_bundle.source_statuses,
    )


def build_metrics(bundle: NormalizedBundle) -> MetricsBundle:
    """Back-compat alias for stage-1 API."""

    return build_metrics_bundle(bundle)
