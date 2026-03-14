from __future__ import annotations

from typing import Any, Dict, List, Mapping


def _as_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _signal(
    *,
    signal_type: str,
    entity_type: str,
    entity_id: str,
    severity: str,
    title: str,
    description: str,
    evidence: Dict[str, Any],
    recommendation: str,
    impact_score: float,
) -> Dict[str, Any]:
    return {
        "signal_type": signal_type,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "severity": severity,
        "title": title,
        "description": description,
        "evidence": evidence,
        "recommendation": recommendation,
        "impact_score": round(float(max(0.0, min(100.0, impact_score))), 2),
    }


def build_distribution_signals(
    sku_items: List[Dict[str, Any]],
    summary: Mapping[str, Any],
    *,
    profit_leak_threshold: float,
    weak_threshold: float,
    critical_threshold: float,
    min_orders_for_actionable: int,
) -> List[Dict[str, Any]]:
    signals: List[Dict[str, Any]] = []

    for row in sku_items:
        if not isinstance(row, dict):
            continue

        sku = str(row.get("sku") or "").strip()
        if not sku:
            continue

        state = str(row.get("distribution_state") or "").strip().lower()
        localization_share = row.get("localization_share")
        ktr = row.get("ktr")
        krp = row.get("krp")
        irp_penalty_total = _as_float(row.get("estimated_irp_penalty_total"))

        valid_sku_attribution = bool(row.get("valid_sku_attribution", True))
        order_count_available = bool(row.get("order_count_available", _as_float(row.get("total_orders")) > 0))
        demand_geography_available = bool(row.get("demand_geography_available", False))
        stock_geography_available = bool(row.get("stock_geography_available", False))
        minimum_sample_met = bool(
            row.get("minimum_sample_met", _as_float(row.get("total_orders")) >= max(1, int(min_orders_for_actionable)))
        )
        analysis_mode = str(row.get("analysis_mode") or "disabled").strip().lower()
        recommendation_status = str(row.get("recommendation_status") or "blocked_by_data").strip().lower()
        localization_known = localization_share is not None

        evidence = {
            "sku": sku,
            "localization_share": localization_share,
            "ktr": ktr,
            "krp": krp,
            "estimated_irp_penalty_total": irp_penalty_total,
            "valid_sku_attribution": valid_sku_attribution,
            "order_count_available": order_count_available,
            "demand_geography_available": demand_geography_available,
            "stock_geography_available": stock_geography_available,
            "minimum_sample_met": minimum_sample_met,
            "analysis_mode": analysis_mode,
            "recommendation_status": recommendation_status,
        }

        if (not valid_sku_attribution) or (not order_count_available) or (not demand_geography_available) or (not localization_known):
            signals.append(
                _signal(
                    signal_type="distribution_insufficient_data",
                    entity_type="sku",
                    entity_id=sku,
                    severity="low",
                    title="Territorial analysis unavailable for SKU",
                    description="Insufficient evidence to confirm territorial risk for this SKU.",
                    evidence=evidence,
                    recommendation="Collect demand/stock geography and restore SKU attribution quality before rebalancing.",
                    impact_score=20.0,
                )
            )
            continue

        if (not stock_geography_available) or (not minimum_sample_met) or analysis_mode != "full" or recommendation_status != "actionable":
            signals.append(
                _signal(
                    signal_type="distribution_low_confidence",
                    entity_type="sku",
                    entity_id=sku,
                    severity="low",
                    title="Territorial signal is low-confidence",
                    description="Preliminary logistics risk is detected, but evidence is not sufficient for strong action.",
                    evidence=evidence,
                    recommendation="Improve stock geography coverage and increase sample before operational rebalancing.",
                    impact_score=30.0,
                )
            )
            continue

        loc = _as_float(localization_share)
        ktr_value = _as_float(ktr)
        krp_value = _as_float(krp)

        if state == "critical":
            signals.append(
                _signal(
                    signal_type="distribution_critical_sku",
                    entity_type="sku",
                    entity_id=sku,
                    severity="high",
                    title="Confirmed critical territorial distribution risk",
                    description="Territorial mismatch is confirmed with sufficient evidence.",
                    evidence=evidence,
                    recommendation="Rebalance stock toward demand-dominant warehouses.",
                    impact_score=max(0.0, 100.0 - loc),
                )
            )
        elif state == "weak":
            signals.append(
                _signal(
                    signal_type="distribution_weak_sku",
                    entity_type="sku",
                    entity_id=sku,
                    severity="medium",
                    title="Confirmed territorial distribution mismatch",
                    description="Territorial mismatch is confirmed; relocation optimization is recommended.",
                    evidence=evidence,
                    recommendation="Increase stock in demand-heavy regions.",
                    impact_score=max(0.0, weak_threshold - loc + 20.0),
                )
            )
        elif state == "watch":
            signals.append(
                _signal(
                    signal_type="distribution_watch_sku",
                    entity_type="sku",
                    entity_id=sku,
                    severity="low",
                    title="Territorial distribution watch",
                    description="Localization is below target and should be monitored.",
                    evidence=evidence,
                    recommendation="Monitor and tune stock placement gradually.",
                    impact_score=max(0.0, 60.0 - loc),
                )
            )

        if irp_penalty_total >= float(profit_leak_threshold) and krp_value > 0 and ktr_value > 0:
            signals.append(
                _signal(
                    signal_type="distribution_profit_leak",
                    entity_type="sku",
                    entity_id=sku,
                    severity="high",
                    title="Confirmed IRP profit leak risk",
                    description="Estimated IRP load is above threshold with sufficient territorial evidence.",
                    evidence=evidence,
                    recommendation="Prioritize relocation for this SKU.",
                    impact_score=min(100.0, irp_penalty_total / max(1.0, float(profit_leak_threshold)) * 40.0 + 40.0),
                )
            )

    suppressed_due_to_data_quality = bool(summary.get("suppressed_due_to_data_quality", False))
    coverage_pct = _as_float(summary.get("coverage_pct"))
    confidence_level = str(summary.get("confidence_level") or "low")
    recommendation_status = str(summary.get("recommendation_status") or "blocked_by_data")

    if suppressed_due_to_data_quality or recommendation_status != "actionable":
        signals.append(
            _signal(
                signal_type="distribution_insufficient_data",
                entity_type="portfolio",
                entity_id="seller",
                severity="low",
                title="Portfolio territorial conclusions are downgraded",
                description="Portfolio-level territorial risk is preview-only due to low evidence coverage.",
                evidence={
                    "coverage_pct": coverage_pct,
                    "confidence_level": confidence_level,
                    "suppressed_due_to_data_quality": suppressed_due_to_data_quality,
                    "recommendation_status": recommendation_status,
                    "suppression_reasons": summary.get("suppression_reasons", []),
                },
                recommendation="Connect stock and demand geography sources to unlock actionable territorial recommendations.",
                impact_score=max(15.0, min(40.0, 100.0 - coverage_pct)),
            )
        )
        return sorted(signals, key=lambda row: _as_float(row.get("impact_score")), reverse=True)[:40]

    weighted_localization = _as_float(summary.get("weighted_average_localization_share"))
    problematic = int(summary.get("skus_below_60_localization", 0) or 0)
    sku_total = int(summary.get("total_skus_analyzed", 0) or 0)
    aggregate_penalty = _as_float(summary.get("aggregate_estimated_irp_penalty_total"))
    problematic_share = (problematic / sku_total) if sku_total > 0 else 0.0

    portfolio_risk = (
        weighted_localization < weak_threshold
        or problematic_share >= 0.50
        or aggregate_penalty >= float(profit_leak_threshold) * 3.0
    )
    if portfolio_risk:
        signals.append(
            _signal(
                signal_type="distribution_portfolio_risk",
                entity_type="portfolio",
                entity_id="seller",
                severity="high" if weighted_localization < critical_threshold else "medium",
                title="Confirmed portfolio territorial distribution risk",
                description="Portfolio shows confirmed territorial mismatch and IRP pressure.",
                evidence={
                    "weighted_average_localization_share": weighted_localization,
                    "problematic_skus": problematic,
                    "total_skus": sku_total,
                    "problematic_share": round(problematic_share, 4),
                    "aggregate_estimated_irp_penalty_total": aggregate_penalty,
                    "coverage_pct": coverage_pct,
                    "confidence_level": confidence_level,
                },
                recommendation="Rebalance high-demand SKU stock and monitor regional demand drift daily.",
                impact_score=min(100.0, max(40.0, (100.0 - weighted_localization) + problematic_share * 30.0)),
            )
        )

    return sorted(signals, key=lambda row: _as_float(row.get("impact_score")), reverse=True)[:40]
