"""Facts builder for metrics -> facts wiring.

Input: MetricsBundle.
Output: FactsBundle.
Does not recalculate KPI and does not render report payloads.
"""

from __future__ import annotations

from ...core.contracts import (
    FactItem,
    FactSection,
    FactsBundle,
    FactValue,
    MetricValue,
    MetricsBundle,
)
from ...warnings_utils import dedupe_warnings, extend_warnings


def _dedupe_keep_order(values: list[str]) -> list[str]:
    return dedupe_warnings(values)


def _metric_to_fact_value(metric: MetricValue | None) -> FactValue:
    if metric is None:
        return FactValue(
            value=None,
            status="unavailable",
            source=None,
            note="metric is missing in metrics section",
        )
    return FactValue(
        value=metric.value,
        status=str(metric.status),
        source=metric.source,
        note=metric.note,
    )


def _metric_to_fact_item(
    *,
    key: str,
    title: str,
    metric: MetricValue | None,
    section_name: str,
    source_quality: dict[str, str] | None = None,
    extra_diagnostics: dict[str, object] | None = None,
) -> FactItem:
    fact_value = _metric_to_fact_value(metric)
    diagnostics: dict[str, object] = {}
    if fact_value.note is not None:
        diagnostics["metric_note"] = fact_value.note
    if source_quality:
        diagnostics["source_quality"] = dict(source_quality)
    if extra_diagnostics:
        diagnostics.update(dict(extra_diagnostics))
    return FactItem(
        key=key,
        title=title,
        value=fact_value,
        category=section_name,
        tags=[section_name, "metric"],
        diagnostics=diagnostics,
    )


def _compute_section_status(items: list[FactItem], warnings: list[str]) -> str:
    if not items:
        return "unavailable"

    statuses = [item.value.status for item in items]
    confirmed_count = sum(1 for status in statuses if status == "confirmed")
    partial_count = sum(1 for status in statuses if status == "partial")
    available_count = confirmed_count + partial_count

    if available_count == 0:
        return "unavailable"
    if partial_count > 0 or available_count < len(items) or warnings:
        return "partial"
    return "confirmed"


def _build_financial_section(metrics_bundle: MetricsBundle) -> FactSection | None:
    section = metrics_bundle.financial
    if section is None:
        return None

    metric_map = [
        ("orders_count", "Orders count"),
        ("sales_count", "Sales count"),
        ("returns_count", "Returns count"),
        ("orders_amount", "Orders amount"),
        ("sales_amount", "Sales amount"),
        ("seller_payout", "Seller payout"),
        ("logistics_cost", "Logistics cost"),
        ("storage_cost", "Storage cost"),
        ("deductions_amount", "Deductions amount"),
        ("revenue_gross", "Revenue gross"),
        ("commission_amount", "Commission amount"),
        ("acquiring_amount", "Acquiring amount"),
        ("pvz_amount", "PVZ amount"),
        ("penalties_amount", "Penalties amount"),
        ("acceptance_amount", "Acceptance amount"),
        ("paid_acceptance_amount", "Paid acceptance amount"),
        ("other_costs_amount", "Other costs amount"),
        ("gross_profit_like", "Gross profit-like"),
        ("net_profit_like", "Net profit-like"),
        ("margin", "Margin-like"),
    ]

    items: list[FactItem] = []
    metric_provenance = (
        dict(section.metric_provenance)
        if isinstance(getattr(section, "metric_provenance", None), dict)
        else {}
    )
    for key, title in metric_map:
        metric = getattr(section, key, None)
        extra: dict[str, object] = {}
        if key in {"gross_profit_like", "net_profit_like"} and section.profit_formula_note:
            extra["profit_formula_note"] = section.profit_formula_note
        provenance = metric_provenance.get(key)
        if isinstance(provenance, dict):
            extra["provenance"] = dict(provenance)
        items.append(
            _metric_to_fact_item(
                key=key,
                title=title,
                metric=metric,
                section_name="financial",
                source_quality=section.source_quality,
                extra_diagnostics=extra,
            )
        )

    warnings = list(section.warnings)
    diagnostics = {
        "source_quality": dict(section.source_quality),
        "component_quality": dict(section.component_quality),
        "profit_formula_note": section.profit_formula_note,
        "realization_target_date": section.realization_target_date,
        "realization_actual_date": section.realization_actual_date,
        "fallback_used": section.fallback_used,
        "lag_days": section.lag_days,
        "financial_model_mode": section.financial_model_mode,
        "financial_confidence": section.financial_confidence,
        "financial_source_date": section.financial_source_date,
        "realization_rows_count": section.realization_rows_count,
        "realization_extraction_mode": section.realization_extraction_mode,
        "realization_detected_operations": list(section.realization_detected_operations),
        "financial_mode": section.financial_mode,
        "financial_missing_components": list(section.financial_missing_components),
        "financial_available_components": list(section.financial_available_components),
        "profitability_estimate_used": section.profitability_estimate_used,
        "profitability_estimate_method": section.profitability_estimate_method,
        "profitability_estimate_formula": section.profitability_estimate_formula,
        "profitability_estimate_dependencies": list(section.profitability_estimate_dependencies),
        "profitability_estimate_warning": section.profitability_estimate_warning,
        "profitability_method": section.profitability_method,
        "profitability_dependencies": list(section.profitability_dependencies),
        "profitability_blockers": list(section.profitability_blockers),
        "metric_provenance": metric_provenance,
    }

    return FactSection(
        section_name="financial",
        title="Financial",
        items=items,
        status=_compute_section_status(items, warnings),
        warnings=warnings,
        diagnostics=diagnostics,
    )


def _build_daily_section(metrics_bundle: MetricsBundle) -> FactSection | None:
    section = metrics_bundle.daily
    if section is None:
        return None

    metric_map = [
        ("orders_count", "Orders count"),
        ("sales_count", "Sales count"),
        ("returns_count", "Returns count"),
        ("orders_amount", "Orders amount"),
        ("sales_amount", "Sales amount"),
    ]
    items = [
        _metric_to_fact_item(
            key=key,
            title=title,
            metric=getattr(section, key, None),
            section_name="daily",
        )
        for key, title in metric_map
    ]
    warnings: list[str] = []
    return FactSection(
        section_name="daily",
        title="Daily",
        items=items,
        status=_compute_section_status(items, warnings),
        warnings=warnings,
        diagnostics={},
    )


def _build_funnel_section(metrics_bundle: MetricsBundle) -> FactSection | None:
    section = metrics_bundle.funnel
    if section is None:
        return None

    metric_map = [
        ("impressions", "Impressions"),
        ("opens", "Opens"),
        ("cart_adds", "Cart adds"),
        ("orders", "Orders"),
        ("buys", "Buys"),
        ("ctr_open_from_impressions", "CTR open from impressions"),
        ("cr_cart_from_opens", "CR cart from opens"),
        ("cr_orders_from_cart", "CR orders from cart"),
        ("cr_buys_from_orders", "CR buys from orders"),
        ("cr_buys_from_impressions", "CR buys from impressions"),
    ]
    items = [
        _metric_to_fact_item(
            key=key,
            title=title,
            metric=getattr(section, key, None),
            section_name="funnel",
            source_quality=section.source_quality,
        )
        for key, title in metric_map
    ]
    warnings = list(section.warnings)
    bundle_diag = metrics_bundle.diagnostics if isinstance(metrics_bundle.diagnostics, dict) else {}
    diagnostics = {
        "source_quality": dict(section.source_quality),
        "note": section.note,
        "funnel_compat_used": bundle_diag.get("funnel_compat_used"),
        "funnel_payload_shape": bundle_diag.get("funnel_payload_shape"),
        "funnel_payload_origin": bundle_diag.get("funnel_payload_origin"),
        "funnel_extraction_mode": bundle_diag.get("funnel_extraction_mode"),
    }
    return FactSection(
        section_name="funnel",
        title="Funnel",
        items=items,
        status=_compute_section_status(items, warnings),
        warnings=warnings,
        diagnostics=diagnostics,
    )


def _build_ads_section(metrics_bundle: MetricsBundle) -> FactSection | None:
    section = metrics_bundle.ads
    if section is None:
        return None

    metric_map = [
        ("campaigns_count", "Campaigns count"),
        ("active_campaigns_count", "Active campaigns count"),
        ("impressions", "Impressions"),
        ("clicks", "Clicks"),
        ("spend", "Spend"),
        ("ctr", "CTR"),
        ("cpc", "CPC"),
        ("orders", "Orders"),
        ("revenue", "Revenue"),
        ("conversion_click_to_order", "Conversion click to order"),
    ]
    items = [
        _metric_to_fact_item(
            key=key,
            title=title,
            metric=getattr(section, key, None),
            section_name="ads",
            source_quality=section.source_quality,
        )
        for key, title in metric_map
    ]
    warnings = list(section.warnings)
    diagnostics = {
        "source_quality": dict(section.source_quality),
        "note": section.note,
    }
    return FactSection(
        section_name="ads",
        title="Ads",
        items=items,
        status=_compute_section_status(items, warnings),
        warnings=warnings,
        diagnostics=diagnostics,
    )


def _build_stock_section(metrics_bundle: MetricsBundle) -> FactSection | None:
    section = metrics_bundle.stock
    if section is None:
        return None

    metric_map = [
        ("total_stock_units", "Stock units"),
        ("in_stock_items_count", "In-stock items count"),
        ("out_of_stock_items_count", "Out-of-stock items count"),
        ("distinct_nm_ids_count", "Distinct nm_id count"),
        ("distinct_warehouses_count", "Distinct warehouses count"),
    ]
    items = [
        _metric_to_fact_item(
            key=key,
            title=title,
            metric=getattr(section, key, None),
            section_name="stock",
            source_quality=section.source_quality,
        )
        for key, title in metric_map
    ]
    warnings = list(section.warnings)
    diagnostics = {
        "source_quality": dict(section.source_quality),
        "stock_coverage_note": section.stock_coverage_note,
        "note": section.note,
    }
    return FactSection(
        section_name="stock",
        title="Stock",
        items=items,
        status=_compute_section_status(items, warnings),
        warnings=warnings,
        diagnostics=diagnostics,
    )


def _build_health_section(metrics_bundle: MetricsBundle) -> FactSection | None:
    section = metrics_bundle.health
    if section is None:
        return None

    metric_map = [
        ("business_health_score", "Business health score"),
        ("sku_health_signals_count", "SKU health signals count"),
        ("problematic_sku_count", "Problematic SKU count"),
        ("dead_stock_risk_count", "Dead stock risk count"),
        ("overstock_risk_count", "Overstock risk count"),
    ]

    items = [
        _metric_to_fact_item(
            key=key,
            title=title,
            metric=getattr(section, key, None),
            section_name="health",
            source_quality=section.source_quality,
        )
        for key, title in metric_map
    ]

    score_status = str(section.business_health_score.status)
    items.append(
        FactItem(
            key="score_status",
            title="Score status",
            value=FactValue(
                value=score_status,
                status=score_status,
                source=section.business_health_score.source,
                note=section.business_health_score.note,
            ),
            category="health",
            tags=["health", "status"],
            diagnostics={"source_quality": dict(section.source_quality)},
        )
    )

    status_note = str(section.business_health_status_note or "").strip()
    if status_note:
        items.append(
            FactItem(
                key="business_health_status_note",
                title="Business health status note",
                value=FactValue(
                    value=status_note,
                    status=score_status if score_status in {"confirmed", "partial", "unavailable"} else "partial",
                    source="health_policy_v1",
                    note=None,
                ),
                category="health",
                tags=["health", "note"],
                diagnostics={"source_quality": dict(section.source_quality)},
            )
        )

    for component_name in sorted(section.component_scores.keys()):
        component_metric = section.component_scores[component_name]
        items.append(
            _metric_to_fact_item(
                key=f"component_{component_name}_score",
                title=f"Component {component_name} score",
                metric=component_metric,
                section_name="health",
                source_quality=section.source_quality,
            )
        )

    warnings = list(section.warnings)
    diagnostics = {
        "source_quality": dict(section.source_quality),
        "component_statuses": {name: metric.status for name, metric in section.component_scores.items()},
        "policy_version": (
            section.diagnostics.get("policy", {}).get("version")
            if isinstance(section.diagnostics.get("policy"), dict)
            else None
        ),
        "note": section.note,
        "diagnostics": dict(section.diagnostics),
    }
    return FactSection(
        section_name="health",
        title="Health",
        items=items,
        status=_compute_section_status(items, warnings),
        warnings=warnings,
        diagnostics=diagnostics,
    )


def build_facts_bundle(metrics_bundle: MetricsBundle) -> FactsBundle:
    sections: dict[str, FactSection] = {}

    financial = _build_financial_section(metrics_bundle)
    if financial is not None:
        sections["financial"] = financial

    daily = _build_daily_section(metrics_bundle)
    if daily is not None:
        sections["daily"] = daily

    funnel = _build_funnel_section(metrics_bundle)
    if funnel is not None:
        sections["funnel"] = funnel

    ads = _build_ads_section(metrics_bundle)
    if ads is not None:
        sections["ads"] = ads

    stock = _build_stock_section(metrics_bundle)
    if stock is not None:
        sections["stock"] = stock

    health = _build_health_section(metrics_bundle)
    if health is not None:
        sections["health"] = health

    section_names = list(sections.keys())
    partial_sections = [name for name, section in sections.items() if section.status == "partial"]
    unavailable_sections = [name for name, section in sections.items() if section.status == "unavailable"]
    available_sections = [name for name, section in sections.items() if section.status != "unavailable"]

    source_quality_summary: dict[str, object] = {}
    for section_name, section in sections.items():
        source_quality = section.diagnostics.get("source_quality")
        if isinstance(source_quality, dict):
            source_quality_summary[section_name] = dict(source_quality)

    warnings: list[str] = list(metrics_bundle.warnings)
    for section_name, section in sections.items():
        extend_warnings(warnings, section.warnings, namespace=section_name)
    warnings = dedupe_warnings(warnings)

    diagnostics = dict(metrics_bundle.diagnostics)
    diagnostics.update(
        {
            "metrics_sections_built": metrics_bundle.diagnostics.get("metrics_sections_built"),
            "facts_sections_built": section_names,
            "build_timestamp": None,
            "build_timestamp_note": "deterministic stage: timestamp omitted by design",
            "propagated_diagnostics_summary": {
                "metrics_warnings_count": len(metrics_bundle.warnings),
                "metrics_source_flags_count": len(metrics_bundle.source_flags),
                "facts_warnings_count": len(warnings),
            },
        }
    )

    data_quality = {
        "available_sections": available_sections,
        "partial_sections": partial_sections,
        "unavailable_sections": unavailable_sections,
        "source_quality_summary": source_quality_summary,
        "warnings_count": len(warnings),
        "source_flags": dict(metrics_bundle.source_flags),
    }

    return FactsBundle(
        run_context=metrics_bundle.run_context,
        sections=sections,
        data_quality=data_quality,
        warnings=warnings,
        diagnostics=diagnostics,
    )


def build(metrics: MetricsBundle) -> FactsBundle:
    """Back-compat alias for stage-1 naming."""

    return build_facts_bundle(metrics)
