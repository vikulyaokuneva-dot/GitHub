from __future__ import annotations

from typing import Any, Dict, List


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
    entity: str,
    severity: str,
    impact: float,
    confidence: str,
    evidence: Dict[str, Any],
    recommendation: str,
) -> Dict[str, Any]:
    return {
        "type": signal_type,
        "entity": entity,
        "severity": severity,
        "impact": round(max(0.0, min(100.0, float(impact))), 2),
        "confidence": confidence,
        "evidence": evidence,
        "recommendation": recommendation,
    }


def build_ads_signals(
    *,
    analysis_mode: str,
    summary: Dict[str, Any],
    sku_rows: List[Dict[str, Any]],
    query_rows: List[Dict[str, Any]],
    high_romi_threshold_pct: float,
    budget_leak_spend_threshold: float,
) -> List[Dict[str, Any]]:
    if str(analysis_mode or "disabled") == "disabled":
        return []

    out: List[Dict[str, Any]] = []

    portfolio_romi = summary.get("portfolio_ROMI")
    portfolio_profit = _as_float(summary.get("portfolio_profit_from_ads"))
    portfolio_spend = _as_float(summary.get("portfolio_ad_spend"))

    if portfolio_romi is not None and _as_float(portfolio_romi) >= float(high_romi_threshold_pct):
        out.append(
            _signal(
                signal_type="ads_high_romi",
                entity="portfolio",
                severity="medium",
                impact=min(100.0, _as_float(portfolio_romi)),
                confidence="high" if analysis_mode == "full" else "medium",
                evidence={
                    "portfolio_ROMI": portfolio_romi,
                    "portfolio_ad_spend": portfolio_spend,
                },
                recommendation="Scale winning campaigns while keeping CPO within target.",
            )
        )

    if portfolio_profit < 0 and portfolio_spend > 0:
        out.append(
            _signal(
                signal_type="ads_negative_profit",
                entity="portfolio",
                severity="high",
                impact=min(100.0, abs(portfolio_profit) / max(1.0, portfolio_spend) * 100.0),
                confidence="high" if analysis_mode == "full" else "medium",
                evidence={
                    "portfolio_profit_from_ads": portfolio_profit,
                    "portfolio_ad_spend": portfolio_spend,
                },
                recommendation="Cut or rebuild loss-making traffic sources and tighten query filters.",
            )
        )

    for row in query_rows:
        if not isinstance(row, dict):
            continue
        query = str(row.get("query") or "").strip()
        if not query:
            continue

        classification = str(row.get("classification") or "insufficient_data")
        confidence = str(row.get("confidence") or "low")
        orders = _as_float(row.get("orders"))
        profit = _as_float(row.get("profit"))
        romi = row.get("ROMI")
        cpo = row.get("CPO")
        spend = _as_float(row.get("ad_spend"))
        if spend <= 0 and cpo is not None and orders > 0:
            spend = _as_float(cpo) * orders

        evidence = {
            "query": query,
            "sku": row.get("sku"),
            "ad_spend": round(spend, 2),
            "orders": row.get("orders"),
            "buyouts": row.get("buyouts"),
            "revenue": row.get("revenue"),
            "profit": row.get("profit"),
            "ROMI": romi,
            "CPO": cpo,
            "classification": classification,
        }

        if classification == "profitable":
            out.append(
                _signal(
                    signal_type="ads_profitable_query",
                    entity=f"query:{query}",
                    severity="medium",
                    impact=min(95.0, max(20.0, profit)),
                    confidence=confidence,
                    evidence=evidence,
                    recommendation="Increase controlled budget on this query and monitor buyout profitability.",
                )
            )
            if romi is not None and _as_float(romi) >= max(20.0, float(high_romi_threshold_pct) * 0.6) and orders <= 5:
                out.append(
                    _signal(
                        signal_type="ads_scaling_opportunity",
                        entity=f"query:{query}",
                        severity="medium",
                        impact=min(90.0, _as_float(romi)),
                        confidence=confidence,
                        evidence=evidence,
                        recommendation="Scale this query gradually; efficiency is strong with low current volume.",
                    )
                )
        elif classification == "unprofitable":
            out.append(
                _signal(
                    signal_type="ads_unprofitable_query",
                    entity=f"query:{query}",
                    severity="high" if profit < -50 else "medium",
                    impact=min(95.0, max(25.0, abs(profit))),
                    confidence=confidence,
                    evidence=evidence,
                    recommendation="Reduce bids or pause the query until economics become positive.",
                )
            )
            if spend >= float(budget_leak_spend_threshold):
                out.append(
                    _signal(
                        signal_type="ads_budget_leak",
                        entity=f"query:{query}",
                        severity="high",
                        impact=min(100.0, spend / max(1.0, float(budget_leak_spend_threshold)) * 40.0 + 30.0),
                        confidence=confidence,
                        evidence=evidence,
                        recommendation="Budget leak detected: cap spend and fix targeting for this query.",
                    )
                )

    for row in sku_rows:
        if not isinstance(row, dict):
            continue
        sku = str(row.get("sku") or "").strip()
        if not sku:
            continue

        romi = row.get("ROMI")
        profit = _as_float(row.get("profit_from_ads"))
        if romi is not None and _as_float(romi) >= float(high_romi_threshold_pct):
            out.append(
                _signal(
                    signal_type="ads_high_romi",
                    entity=f"sku:{sku}",
                    severity="low",
                    impact=min(85.0, _as_float(romi)),
                    confidence=str(row.get("confidence") or "medium"),
                    evidence={
                        "sku": sku,
                        "ROMI": romi,
                        "orders_from_ads": row.get("orders_from_ads"),
                        "buyouts_from_ads": row.get("buyouts_from_ads"),
                    },
                    recommendation="Scale ad budget for this SKU with buyout-rate guardrails.",
                )
            )
        if profit < 0 and _as_float(row.get("ad_spend")) > 0:
            out.append(
                _signal(
                    signal_type="ads_negative_profit",
                    entity=f"sku:{sku}",
                    severity="medium",
                    impact=min(85.0, abs(profit)),
                    confidence=str(row.get("confidence") or "medium"),
                    evidence={
                        "sku": sku,
                        "profit_from_ads": row.get("profit_from_ads"),
                        "ad_spend": row.get("ad_spend"),
                    },
                    recommendation="Review targeting and bids; this SKU is ad-loss-making.",
                )
            )

    out.sort(key=lambda item: (_as_float(item.get("impact")), str(item.get("entity") or "")), reverse=True)
    return out[:80]
