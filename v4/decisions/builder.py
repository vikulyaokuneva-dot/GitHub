"""Rule-based decisions builder over facts layer.

Input: FactsBundle.
Output: DecisionsBundle.
Does not recalculate KPI and does not render outputs.
"""

from __future__ import annotations

from ..core.contracts import (
    DecisionItem,
    DecisionPriority,
    DecisionStatus,
    DecisionsBundle,
    FactItem,
    FactsBundle,
)

WEAK_CONVERSION_THRESHOLD = 0.20
WEAK_CONVERSION_SEVERE_THRESHOLD = 0.10
LOW_BUSINESS_HEALTH_THRESHOLD = 50.0
LOW_BUSINESS_HEALTH_SEVERE_THRESHOLD = 35.0

LOW_COMPONENT_THRESHOLDS: dict[str, float] = {
    "component_profitability_score": 15.0,
    "component_ads_score": 10.0,
    "component_funnel_score": 10.0,
    "component_stock_score": 10.0,
    "component_data_quality_score": 6.0,
}


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _get_fact_item(facts_bundle: FactsBundle, section_name: str, fact_key: str) -> FactItem | None:
    section = facts_bundle.sections.get(section_name)
    if section is None:
        return None
    for item in section.items:
        if item.key == fact_key:
            return item
    return None


def _fact_evidence(section: str, key: str, fact_item: FactItem | None) -> dict[str, object]:
    if fact_item is None:
        return {
            "fact_section": section,
            "fact_key": key,
            "fact_value": None,
            "fact_status": DecisionStatus.UNAVAILABLE.value,
            "fact_source": None,
            "note": "fact is missing in facts bundle",
        }
    return {
        "fact_section": section,
        "fact_key": key,
        "fact_value": fact_item.value.value,
        "fact_status": fact_item.value.status,
        "fact_source": fact_item.value.source,
        "note": fact_item.value.note,
    }


def _status_from_fact_statuses(fact_statuses: list[str]) -> DecisionStatus:
    if not fact_statuses:
        return DecisionStatus.UNAVAILABLE
    if all(status == DecisionStatus.CONFIRMED.value for status in fact_statuses):
        return DecisionStatus.CONFIRMED
    if any(status in {DecisionStatus.PARTIAL.value, DecisionStatus.UNAVAILABLE.value} for status in fact_statuses):
        return DecisionStatus.PARTIAL
    return DecisionStatus.PARTIAL


def _build_negative_profit_decision(facts_bundle: FactsBundle) -> DecisionItem | None:
    primary = _get_fact_item(facts_bundle, "financial", "net_profit_like")
    fallback = _get_fact_item(facts_bundle, "financial", "gross_profit_like")
    fact = primary if primary is not None else fallback
    fact_key = "net_profit_like" if primary is not None else "gross_profit_like"
    evidence = [_fact_evidence("financial", fact_key, fact)]

    if fact is None:
        return DecisionItem(
            code="negative_profit",
            title="Negative profit",
            summary="Cannot evaluate negative profit: financial profit-like fact is missing.",
            priority=DecisionPriority.P1,
            status=DecisionStatus.UNAVAILABLE,
            section="financial",
            reason="required fact is unavailable",
            evidence=evidence,
            recommended_actions=["Verify financial contour availability before taking high-impact actions."],
            diagnostics={"rule": "negative_profit", "chosen_fact_key": fact_key},
        )

    profit_value = _to_float(fact.value.value)
    if profit_value is None:
        status = DecisionStatus.PARTIAL if fact.value.status == DecisionStatus.PARTIAL.value else DecisionStatus.UNAVAILABLE
        return DecisionItem(
            code="negative_profit",
            title="Negative profit",
            summary="Cannot confirm negative profit due to incomplete financial evidence.",
            priority=DecisionPriority.P1,
            status=status,
            section="financial",
            reason="profit-like value is unavailable",
            evidence=evidence,
            recommended_actions=["Collect complete financial inputs and re-run the cycle."],
            diagnostics={"rule": "negative_profit", "chosen_fact_key": fact_key},
        )

    if profit_value >= 0:
        return None

    status = DecisionStatus.CONFIRMED if fact.value.status == DecisionStatus.CONFIRMED.value else DecisionStatus.PARTIAL
    return DecisionItem(
        code="negative_profit",
        title="Negative profit",
        summary="Profit-like indicator is below zero.",
        priority=DecisionPriority.P1,
        status=status,
        section="financial",
        reason=f"{fact_key} is negative",
        evidence=evidence,
        recommended_actions=[
            "Review largest expense components and pause non-critical spend until profitability recovers.",
            "Validate realization completeness before irreversible decisions.",
        ],
        diagnostics={"rule": "negative_profit", "chosen_fact_key": fact_key},
    )


def _build_low_margin_decision(facts_bundle: FactsBundle) -> DecisionItem | None:
    net_profit = _get_fact_item(facts_bundle, "financial", "net_profit_like")
    if net_profit is None:
        return DecisionItem(
            code="low_margin",
            title="Low margin risk",
            summary="Cannot evaluate low margin: net profit-like fact is missing.",
            priority=DecisionPriority.P2,
            status=DecisionStatus.UNAVAILABLE,
            section="financial",
            reason="required fact is unavailable",
            evidence=[_fact_evidence("financial", "net_profit_like", None)],
            recommended_actions=["Ensure financial fact mapping is complete."],
            diagnostics={"rule": "low_margin", "threshold_value": 50.0},
        )

    net_profit_value = _to_float(net_profit.value.value)
    evidence = [_fact_evidence("financial", "net_profit_like", net_profit)]
    if net_profit_value is None:
        status = DecisionStatus.PARTIAL if net_profit.value.status == DecisionStatus.PARTIAL.value else DecisionStatus.UNAVAILABLE
        return DecisionItem(
            code="low_margin",
            title="Low margin risk",
            summary="Cannot confirm margin level due to incomplete net profit-like evidence.",
            priority=DecisionPriority.P2,
            status=status,
            section="financial",
            reason="net profit-like value is unavailable",
            evidence=evidence,
            recommended_actions=["Verify profit-like components and re-run the report cycle."],
            diagnostics={"rule": "low_margin", "threshold_value": 50.0},
        )

    if net_profit_value < 0 or net_profit_value > 50.0:
        return None

    status = DecisionStatus.CONFIRMED if net_profit.value.status == DecisionStatus.CONFIRMED.value else DecisionStatus.PARTIAL
    return DecisionItem(
        code="low_margin",
        title="Low margin risk",
        summary="Net profit-like value is positive but near zero.",
        priority=DecisionPriority.P2,
        status=status,
        section="financial",
        reason="net_profit_like is within low-margin threshold",
        evidence=evidence,
        recommended_actions=[
            "Prioritize actions that improve unit economics before scaling spend.",
            "Monitor margin-sensitive cost components in the next cycle.",
        ],
        diagnostics={"rule": "low_margin", "threshold_value": 50.0},
    )


def _build_ad_inefficiency_decision(facts_bundle: FactsBundle) -> DecisionItem | None:
    spend = _get_fact_item(facts_bundle, "ads", "spend")
    revenue = _get_fact_item(facts_bundle, "ads", "revenue")
    conversion = _get_fact_item(facts_bundle, "ads", "conversion_click_to_order")

    evidence = [
        _fact_evidence("ads", "spend", spend),
        _fact_evidence("ads", "revenue", revenue),
        _fact_evidence("ads", "conversion_click_to_order", conversion),
    ]

    if spend is None:
        return DecisionItem(
            code="ad_inefficiency",
            title="Ad inefficiency",
            summary="Cannot evaluate ad efficiency: spend fact is missing.",
            priority=DecisionPriority.P2,
            status=DecisionStatus.UNAVAILABLE,
            section="ads",
            reason="required ads spend fact is unavailable",
            evidence=evidence,
            recommended_actions=["Verify ads source completeness before optimization actions."],
            diagnostics={"rule": "ad_inefficiency", "conversion_threshold": 0.02},
        )

    spend_value = _to_float(spend.value.value)
    if spend_value is None:
        status = DecisionStatus.PARTIAL if spend.value.status == DecisionStatus.PARTIAL.value else DecisionStatus.UNAVAILABLE
        return DecisionItem(
            code="ad_inefficiency",
            title="Ad inefficiency",
            summary="Cannot confirm ad efficiency due to unavailable spend value.",
            priority=DecisionPriority.P2,
            status=status,
            section="ads",
            reason="ads spend value is unavailable",
            evidence=evidence,
            recommended_actions=["Ensure ads stats contain reliable spend values."],
            diagnostics={"rule": "ad_inefficiency", "conversion_threshold": 0.02},
        )

    if spend_value <= 0:
        return None

    revenue_value = _to_float(revenue.value.value) if revenue is not None else None
    conversion_value = _to_float(conversion.value.value) if conversion is not None else None

    inefficient = False
    reason = ""
    if revenue_value is not None and revenue_value < spend_value:
        inefficient = True
        reason = "ads spend exceeds ads-attributed revenue"
    elif conversion_value is not None and conversion_value < 0.02:
        inefficient = True
        reason = "click-to-order conversion is below threshold"

    if not inefficient:
        if revenue_value is None and conversion_value is None:
            return DecisionItem(
                code="ad_inefficiency",
                title="Ad inefficiency",
                summary="Cannot evaluate ad efficiency because revenue and conversion evidence are unavailable.",
                priority=DecisionPriority.P2,
                status=DecisionStatus.UNAVAILABLE,
                section="ads",
                reason="insufficient ads efficiency evidence",
                evidence=evidence,
                recommended_actions=["Enable complete ads stats collection for efficiency checks."],
                diagnostics={"rule": "ad_inefficiency", "conversion_threshold": 0.02},
            )
        return None

    statuses = [spend.value.status]
    if revenue is not None:
        statuses.append(revenue.value.status)
    if conversion is not None:
        statuses.append(conversion.value.status)
    status = _status_from_fact_statuses(statuses)

    return DecisionItem(
        code="ad_inefficiency",
        title="Ad inefficiency",
        summary="Ads performance indicates inefficiency risk.",
        priority=DecisionPriority.P2,
        status=status,
        section="ads",
        reason=reason,
        evidence=evidence,
        recommended_actions=[
            "Reallocate spend from low-efficiency campaigns.",
            "Validate attribution coverage before major budget changes.",
        ],
        diagnostics={"rule": "ad_inefficiency", "conversion_threshold": 0.02},
    )


def _build_out_of_stock_risk_decision(facts_bundle: FactsBundle) -> DecisionItem | None:
    out_of_stock = _get_fact_item(facts_bundle, "stock", "out_of_stock_items_count")
    in_stock = _get_fact_item(facts_bundle, "stock", "in_stock_items_count")
    evidence = [
        _fact_evidence("stock", "out_of_stock_items_count", out_of_stock),
        _fact_evidence("stock", "in_stock_items_count", in_stock),
    ]

    if out_of_stock is None:
        return DecisionItem(
            code="out_of_stock_risk",
            title="Out-of-stock risk",
            summary="Cannot evaluate stock risk: out-of-stock fact is missing.",
            priority=DecisionPriority.P1,
            status=DecisionStatus.UNAVAILABLE,
            section="stock",
            reason="required stock fact is unavailable",
            evidence=evidence,
            recommended_actions=["Verify stock source and fact mapping integrity."],
            diagnostics={"rule": "out_of_stock_risk"},
        )

    out_value = _to_float(out_of_stock.value.value)
    if out_value is None:
        status = DecisionStatus.PARTIAL if out_of_stock.value.status == DecisionStatus.PARTIAL.value else DecisionStatus.UNAVAILABLE
        return DecisionItem(
            code="out_of_stock_risk",
            title="Out-of-stock risk",
            summary="Cannot confirm stock risk due to unavailable out-of-stock value.",
            priority=DecisionPriority.P1,
            status=status,
            section="stock",
            reason="out_of_stock_items_count value is unavailable",
            evidence=evidence,
            recommended_actions=["Improve stock quantity completeness and re-run."],
            diagnostics={"rule": "out_of_stock_risk"},
        )

    if out_value <= 0:
        return None

    statuses = [out_of_stock.value.status]
    if in_stock is not None:
        statuses.append(in_stock.value.status)
    status = _status_from_fact_statuses(statuses)

    return DecisionItem(
        code="out_of_stock_risk",
        title="Out-of-stock risk",
        summary="Some stock entities are currently out of stock.",
        priority=DecisionPriority.P1,
        status=status,
        section="stock",
        reason="out_of_stock_items_count is above zero",
        evidence=evidence,
        recommended_actions=[
            "Prioritize replenishment planning for out-of-stock entities.",
            "Track stock recovery in the next operational cycle.",
        ],
        diagnostics={"rule": "out_of_stock_risk"},
    )


def _build_weak_conversion_decision(facts_bundle: FactsBundle) -> DecisionItem | None:
    primary = _get_fact_item(facts_bundle, "funnel", "cr_buys_from_orders")
    fallback = _get_fact_item(facts_bundle, "funnel", "cr_orders_from_cart")
    fact = primary if primary is not None else fallback
    fact_key = "cr_buys_from_orders" if primary is not None else "cr_orders_from_cart"
    evidence = [_fact_evidence("funnel", fact_key, fact)]

    if fact is None:
        return DecisionItem(
            code="weak_conversion",
            title="Weak conversion",
            summary="Cannot evaluate conversion quality: required funnel conversion fact is missing.",
            priority=DecisionPriority.P2,
            status=DecisionStatus.UNAVAILABLE,
            section="funnel",
            reason="required funnel conversion fact is unavailable",
            evidence=evidence,
            recommended_actions=["Verify funnel source and conversion mapping before optimization actions."],
            diagnostics={"rule": "weak_conversion", "threshold": WEAK_CONVERSION_THRESHOLD},
        )

    conversion = _to_float(fact.value.value)
    if conversion is None:
        status = DecisionStatus.PARTIAL if fact.value.status == DecisionStatus.PARTIAL.value else DecisionStatus.UNAVAILABLE
        return DecisionItem(
            code="weak_conversion",
            title="Weak conversion",
            summary="Cannot confirm conversion weakness due to incomplete funnel evidence.",
            priority=DecisionPriority.P2,
            status=status,
            section="funnel",
            reason="conversion value is unavailable",
            evidence=evidence,
            recommended_actions=["Collect complete funnel conversion evidence and re-run the cycle."],
            diagnostics={"rule": "weak_conversion", "threshold": WEAK_CONVERSION_THRESHOLD},
        )

    if conversion >= WEAK_CONVERSION_THRESHOLD:
        return None

    priority = DecisionPriority.P1 if conversion < WEAK_CONVERSION_SEVERE_THRESHOLD else DecisionPriority.P2
    status = DecisionStatus.CONFIRMED if fact.value.status == DecisionStatus.CONFIRMED.value else DecisionStatus.PARTIAL
    return DecisionItem(
        code="weak_conversion",
        title="Weak conversion",
        summary="Funnel conversion is below the policy threshold.",
        priority=priority,
        status=status,
        section="funnel",
        reason=f"{fact_key}={conversion:.4f} is below threshold {WEAK_CONVERSION_THRESHOLD:.2f}",
        evidence=evidence,
        recommended_actions=[
            "Review low-performing funnel stages and remove high-friction steps.",
            "Validate traffic quality before scaling acquisition.",
        ],
        diagnostics={
            "rule": "weak_conversion",
            "threshold": WEAK_CONVERSION_THRESHOLD,
            "severe_threshold": WEAK_CONVERSION_SEVERE_THRESHOLD,
        },
    )


def _build_overstock_decision(facts_bundle: FactsBundle) -> DecisionItem | None:
    overstock = _get_fact_item(facts_bundle, "health", "overstock_risk_count")
    problematic = _get_fact_item(facts_bundle, "health", "problematic_sku_count")
    evidence = [
        _fact_evidence("health", "overstock_risk_count", overstock),
        _fact_evidence("health", "problematic_sku_count", problematic),
    ]

    if overstock is None:
        return DecisionItem(
            code="overstock",
            title="Overstock risk",
            summary="Cannot evaluate overstock risk: health overstock fact is missing.",
            priority=DecisionPriority.P2,
            status=DecisionStatus.UNAVAILABLE,
            section="health",
            reason="required overstock fact is unavailable",
            evidence=evidence,
            recommended_actions=["Verify health/stock evidence completeness before inventory actions."],
            diagnostics={"rule": "overstock"},
        )

    overstock_count = _to_float(overstock.value.value)
    if overstock_count is None:
        status = DecisionStatus.PARTIAL if overstock.value.status == DecisionStatus.PARTIAL.value else DecisionStatus.UNAVAILABLE
        return DecisionItem(
            code="overstock",
            title="Overstock risk",
            summary="Cannot confirm overstock risk due to incomplete stock movement evidence.",
            priority=DecisionPriority.P2,
            status=status,
            section="health",
            reason="overstock_risk_count value is unavailable",
            evidence=evidence,
            recommended_actions=["Collect complete stock movement evidence and re-run."],
            diagnostics={"rule": "overstock"},
        )

    if overstock_count <= 0:
        return None

    priority = DecisionPriority.P1 if overstock_count >= 5 else DecisionPriority.P2
    status = DecisionStatus.CONFIRMED if overstock.value.status == DecisionStatus.CONFIRMED.value else DecisionStatus.PARTIAL
    return DecisionItem(
        code="overstock",
        title="Overstock risk",
        summary="Stock turnover indicates overstock risk.",
        priority=priority,
        status=status,
        section="health",
        reason=f"overstock_risk_count={int(round(overstock_count))} is above zero",
        evidence=evidence,
        recommended_actions=[
            "Reduce replenishment pace for slow-moving stock entities.",
            "Prioritize sell-through actions for high-cover inventory.",
        ],
        diagnostics={"rule": "overstock"},
    )


def _build_dead_sku_decision(facts_bundle: FactsBundle) -> DecisionItem | None:
    dead = _get_fact_item(facts_bundle, "health", "dead_stock_risk_count")
    problematic = _get_fact_item(facts_bundle, "health", "problematic_sku_count")
    evidence = [
        _fact_evidence("health", "dead_stock_risk_count", dead),
        _fact_evidence("health", "problematic_sku_count", problematic),
    ]

    if dead is None:
        return DecisionItem(
            code="dead_sku",
            title="Dead SKU risk",
            summary="Cannot evaluate dead SKU risk: dead stock fact is missing.",
            priority=DecisionPriority.P2,
            status=DecisionStatus.UNAVAILABLE,
            section="health",
            reason="required dead stock fact is unavailable",
            evidence=evidence,
            recommended_actions=["Verify stock/funnel entity mapping before SKU-level actions."],
            diagnostics={"rule": "dead_sku"},
        )

    dead_count = _to_float(dead.value.value)
    if dead_count is None:
        status = DecisionStatus.PARTIAL if dead.value.status == DecisionStatus.PARTIAL.value else DecisionStatus.UNAVAILABLE
        return DecisionItem(
            code="dead_sku",
            title="Dead SKU risk",
            summary="Cannot confirm dead SKU risk due to incomplete movement evidence.",
            priority=DecisionPriority.P2,
            status=status,
            section="health",
            reason="dead_stock_risk_count value is unavailable",
            evidence=evidence,
            recommended_actions=["Collect complete movement evidence and re-run the health stage."],
            diagnostics={"rule": "dead_sku"},
        )

    if dead_count <= 0:
        return None

    priority = DecisionPriority.P1 if dead_count >= 5 else DecisionPriority.P2
    status = DecisionStatus.CONFIRMED if dead.value.status == DecisionStatus.CONFIRMED.value else DecisionStatus.PARTIAL
    return DecisionItem(
        code="dead_sku",
        title="Dead SKU risk",
        summary="Health signals indicate dead stock / zero movement risk.",
        priority=priority,
        status=status,
        section="health",
        reason=f"dead_stock_risk_count={int(round(dead_count))} is above zero",
        evidence=evidence,
        recommended_actions=[
            "Trigger markdown/promo scenarios for dead stock entities.",
            "Review assortment and disable replenishment for persistently dead SKU.",
        ],
        diagnostics={"rule": "dead_sku"},
    )


def _build_low_business_health_decision(facts_bundle: FactsBundle) -> DecisionItem | None:
    score = _get_fact_item(facts_bundle, "health", "business_health_score")
    component_items: list[FactItem] = []
    section = facts_bundle.sections.get("health")
    if section is not None:
        component_items = [
            item
            for item in section.items
            if item.key.startswith("component_") and item.key.endswith("_score")
        ]

    evidence: list[dict[str, object]] = [_fact_evidence("health", "business_health_score", score)]
    for component in component_items:
        evidence.append(_fact_evidence("health", component.key, component))

    if score is None:
        return DecisionItem(
            code="low_business_health",
            title="Low business health",
            summary="Cannot evaluate business health score: health score fact is missing.",
            priority=DecisionPriority.P2,
            status=DecisionStatus.UNAVAILABLE,
            section="health",
            reason="business_health_score fact is unavailable",
            evidence=evidence,
            recommended_actions=["Verify health section mapping before score-based actions."],
            diagnostics={"rule": "low_business_health", "threshold": LOW_BUSINESS_HEALTH_THRESHOLD},
        )

    score_value = _to_float(score.value.value)
    if score_value is None:
        status = DecisionStatus.PARTIAL if score.value.status == DecisionStatus.PARTIAL.value else DecisionStatus.UNAVAILABLE
        return DecisionItem(
            code="low_business_health",
            title="Low business health",
            summary="Cannot confirm low health due to incomplete score evidence.",
            priority=DecisionPriority.P2,
            status=status,
            section="health",
            reason="business_health_score value is unavailable",
            evidence=evidence,
            recommended_actions=["Collect complete health components and re-run."],
            diagnostics={"rule": "low_business_health", "threshold": LOW_BUSINESS_HEALTH_THRESHOLD},
        )

    if score_value >= LOW_BUSINESS_HEALTH_THRESHOLD:
        return None

    weak_components: list[str] = []
    for component in component_items:
        threshold = LOW_COMPONENT_THRESHOLDS.get(component.key)
        if threshold is None:
            continue
        component_value = _to_float(component.value.value)
        if component_value is None:
            continue
        if component_value < threshold:
            weak_components.append(component.key)

    priority = DecisionPriority.P1 if score_value < LOW_BUSINESS_HEALTH_SEVERE_THRESHOLD else DecisionPriority.P2
    status = DecisionStatus.CONFIRMED if score.value.status == DecisionStatus.CONFIRMED.value else DecisionStatus.PARTIAL
    return DecisionItem(
        code="low_business_health",
        title="Low business health",
        summary="Business health score is below policy threshold.",
        priority=priority,
        status=status,
        section="health",
        reason=(
            f"business_health_score={score_value:.2f} < {LOW_BUSINESS_HEALTH_THRESHOLD:.0f}; "
            f"weak_components={weak_components or ['none_detected']}"
        ),
        evidence=evidence,
        recommended_actions=[
            "Prioritize actions that improve weakest health components first.",
            "Treat high-impact decisions conservatively while health score is low/partial.",
        ],
        diagnostics={
            "rule": "low_business_health",
            "threshold": LOW_BUSINESS_HEALTH_THRESHOLD,
            "severe_threshold": LOW_BUSINESS_HEALTH_SEVERE_THRESHOLD,
            "weak_components": weak_components,
        },
    )


def _build_partial_data_warning_decision(facts_bundle: FactsBundle) -> DecisionItem | None:
    partial_sections = list(facts_bundle.data_quality.get("partial_sections", []))
    unavailable_sections = list(facts_bundle.data_quality.get("unavailable_sections", []))
    if not partial_sections and not unavailable_sections:
        return None

    evidence: list[dict[str, object]] = []
    for section_name in partial_sections:
        section = facts_bundle.sections.get(section_name)
        evidence.append(
            {
                "fact_section": section_name,
                "fact_key": "section_status",
                "fact_value": section.status if section is not None else "partial",
                "fact_status": "partial",
                "fact_source": None,
                "note": "section has partial data",
            }
        )
    for section_name in unavailable_sections:
        section = facts_bundle.sections.get(section_name)
        evidence.append(
            {
                "fact_section": section_name,
                "fact_key": "section_status",
                "fact_value": section.status if section is not None else "unavailable",
                "fact_status": "unavailable",
                "fact_source": None,
                "note": "section is unavailable",
            }
        )

    return DecisionItem(
        code="partial_data_warning",
        title="Partial data warning",
        summary="Report contains partial or unavailable sections; high-impact actions should be conservative.",
        priority=DecisionPriority.P3,
        status=DecisionStatus.INFO,
        section="data_quality",
        reason="facts data quality indicates incomplete evidence",
        evidence=evidence,
        recommended_actions=[
            "Re-check missing sections on the next cycle before irreversible decisions.",
            "Treat current recommendations as hypotheses where data is partial.",
        ],
        diagnostics={
            "rule": "partial_data_warning",
            "partial_sections": partial_sections,
            "unavailable_sections": unavailable_sections,
        },
    )


def build_decisions_bundle(facts_bundle: FactsBundle) -> DecisionsBundle:
    items: list[DecisionItem] = []
    rules = [
        _build_negative_profit_decision,
        _build_low_margin_decision,
        _build_ad_inefficiency_decision,
        _build_out_of_stock_risk_decision,
        _build_weak_conversion_decision,
        _build_overstock_decision,
        _build_dead_sku_decision,
        _build_low_business_health_decision,
        _build_partial_data_warning_decision,
    ]

    for rule in rules:
        item = rule(facts_bundle)
        if item is not None:
            items.append(item)

    by_priority = {
        DecisionPriority.P1.value: 0,
        DecisionPriority.P2.value: 0,
        DecisionPriority.P3.value: 0,
    }
    by_status = {
        DecisionStatus.CONFIRMED.value: 0,
        DecisionStatus.PARTIAL.value: 0,
        DecisionStatus.UNAVAILABLE.value: 0,
        DecisionStatus.INFO.value: 0,
    }
    for item in items:
        by_priority[item.priority.value] = by_priority.get(item.priority.value, 0) + 1
        by_status[item.status.value] = by_status.get(item.status.value, 0) + 1

    summary = {
        "total_decisions": len(items),
        "by_priority": by_priority,
        "by_status": by_status,
        "decision_codes": [item.code for item in items],
    }

    diagnostics = {
        "rules_evaluated": [rule.__name__ for rule in rules],
        "facts_sections_available": list(facts_bundle.sections.keys()),
        "facts_partial_sections": list(facts_bundle.data_quality.get("partial_sections", [])),
        "facts_unavailable_sections": list(facts_bundle.data_quality.get("unavailable_sections", [])),
    }

    return DecisionsBundle(
        run_context=facts_bundle.run_context,
        items=items,
        summary=summary,
        warnings=list(facts_bundle.warnings),
        diagnostics=diagnostics,
    )


def build_decisions(facts: FactsBundle) -> DecisionsBundle:
    """Back-compat alias for stage-1 naming."""

    return build_decisions_bundle(facts)
