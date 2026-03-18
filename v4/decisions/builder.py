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
