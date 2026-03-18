"""Funnel metrics assembler.

Input: NormalizedBundle.
Output: FunnelMetricsSection.
Does not depend on financial contour and does not render outputs.
"""

from __future__ import annotations

from ...core.contracts import FunnelMetricsSection, MetricStatus, NormalizedBundle
from .cabinet_builder import build_run_funnel_records
from .helpers import (
    aggregate_volume_metric,
    funnel_source_state,
    make_metric,
    safe_ratio_metric,
    source_is_usable,
)


def _source_warnings(normalized_bundle: NormalizedBundle) -> list[str]:
    warnings: list[str] = []

    source_status = normalized_bundle.source_statuses.get("funnel")
    if source_status is not None:
        warnings.extend([f"funnel: {msg}" for msg in source_status.warnings])

    warnings.extend(
        warning
        for warning in normalized_bundle.warnings
        if "funnel" in str(warning).lower()
    )
    return warnings


def _section_note(source_state: str, warnings: list[str], statuses: list[str]) -> str | None:
    if not source_is_usable(source_state):
        return "funnel source unavailable; metrics are not computed"
    if any(status == MetricStatus.UNAVAILABLE.value for status in statuses):
        return "funnel metrics are partially unavailable due to missing source fields"
    if any(status == MetricStatus.PARTIAL.value for status in statuses):
        return "funnel metrics are partial due to source incompleteness or denominator constraints"
    if warnings:
        return "funnel metrics are available with warnings"
    return None


def assemble_funnel_metrics(normalized_bundle: NormalizedBundle) -> FunnelMetricsSection:
    """Aggregate run-level funnel records into funnel metrics section.

    Aggregation rule:
    - volume metrics are sums over available numeric values only;
      missing values are not converted to zero.
    Conversion rule:
    - ratio is emitted only when denominator is positive and both operands are
      available; otherwise ratio value is None with partial/unavailable status.
    """

    source_state = funnel_source_state(normalized_bundle)
    warnings = _source_warnings(normalized_bundle)
    source_quality = {"funnel": source_state}

    if not source_is_usable(source_state):
        unavailable = make_metric(
            None,
            status=MetricStatus.UNAVAILABLE,
            source="funnel",
            note="funnel source is unavailable",
        )
        statuses = [MetricStatus.UNAVAILABLE.value]
        note = _section_note(source_state, warnings, statuses)
        return FunnelMetricsSection(
            impressions=unavailable,
            opens=unavailable,
            cart_adds=unavailable,
            orders=unavailable,
            buys=unavailable,
            ctr_open_from_impressions=unavailable,
            cr_cart_from_opens=unavailable,
            cr_orders_from_cart=unavailable,
            cr_buys_from_orders=unavailable,
            cr_buys_from_impressions=unavailable,
            source_quality=source_quality,
            warnings=warnings,
            note=note,
        )

    records = build_run_funnel_records(normalized_bundle)

    impressions, warn = aggregate_volume_metric(records=records, field_name="impressions", source_state=source_state)
    warnings.extend(warn)
    opens, warn = aggregate_volume_metric(records=records, field_name="opens", source_state=source_state)
    warnings.extend(warn)
    cart_adds, warn = aggregate_volume_metric(records=records, field_name="cart_adds", source_state=source_state)
    warnings.extend(warn)
    orders, warn = aggregate_volume_metric(records=records, field_name="orders", source_state=source_state)
    warnings.extend(warn)
    buys, warn = aggregate_volume_metric(records=records, field_name="buys", source_state=source_state)
    warnings.extend(warn)

    ctr_open_from_impressions, warn = safe_ratio_metric(
        numerator=opens,
        denominator=impressions,
        source_state=source_state,
        ratio_name="ctr_open_from_impressions",
    )
    warnings.extend(warn)
    cr_cart_from_opens, warn = safe_ratio_metric(
        numerator=cart_adds,
        denominator=opens,
        source_state=source_state,
        ratio_name="cr_cart_from_opens",
    )
    warnings.extend(warn)
    cr_orders_from_cart, warn = safe_ratio_metric(
        numerator=orders,
        denominator=cart_adds,
        source_state=source_state,
        ratio_name="cr_orders_from_cart",
    )
    warnings.extend(warn)
    cr_buys_from_orders, warn = safe_ratio_metric(
        numerator=buys,
        denominator=orders,
        source_state=source_state,
        ratio_name="cr_buys_from_orders",
    )
    warnings.extend(warn)
    cr_buys_from_impressions, warn = safe_ratio_metric(
        numerator=buys,
        denominator=impressions,
        source_state=source_state,
        ratio_name="cr_buys_from_impressions",
    )
    warnings.extend(warn)

    statuses = [
        impressions.status,
        opens.status,
        cart_adds.status,
        orders.status,
        buys.status,
        ctr_open_from_impressions.status,
        cr_cart_from_opens.status,
        cr_orders_from_cart.status,
        cr_buys_from_orders.status,
        cr_buys_from_impressions.status,
    ]

    note = _section_note(source_state, warnings, statuses)

    return FunnelMetricsSection(
        impressions=impressions,
        opens=opens,
        cart_adds=cart_adds,
        orders=orders,
        buys=buys,
        ctr_open_from_impressions=ctr_open_from_impressions,
        cr_cart_from_opens=cr_cart_from_opens,
        cr_orders_from_cart=cr_orders_from_cart,
        cr_buys_from_orders=cr_buys_from_orders,
        cr_buys_from_impressions=cr_buys_from_impressions,
        source_quality=source_quality,
        warnings=warnings,
        note=note,
    )


def build(payload: NormalizedBundle | None = None) -> FunnelMetricsSection:
    """Back-compat alias for stage-1 naming."""

    if payload is None:
        return FunnelMetricsSection()
    return assemble_funnel_metrics(payload)
