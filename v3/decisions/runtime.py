from __future__ import annotations

from typing import Any, Dict, List

from ..analysis.ai_director import build_strategy_plan
from ..analysis.decision_engine import build_decisions


def build_decisions_layer(
    *,
    metrics: Dict[str, Any],
    abc_rows: List[Dict[str, Any]],
    health_payload: Dict[str, Any],
    territorial_distribution: Dict[str, Any],
    logistics_ktr: Dict[str, Any],
    opportunity_scores: Dict[str, Any],
    growth_simulation: Dict[str, Any],
) -> Dict[str, Any]:
    safe_metrics = metrics if isinstance(metrics, dict) else {}
    data_quality = safe_metrics.get("data_quality", {})
    if not isinstance(data_quality, dict):
        data_quality = {}

    sku_attribution_status = str(data_quality.get("sku_attribution_status") or "ok").strip().lower()
    territorial_analysis_enabled = bool(data_quality.get("territorial_analysis_enabled", sku_attribution_status != "broken"))
    profit_contribution_enabled = bool(data_quality.get("profit_contribution_enabled", sku_attribution_status != "broken"))

    if sku_attribution_status == "broken":
        decisions_payload = {
            "summary": {"scale": [], "fix": [], "watch": [], "liquidate": []},
            "top_profit_skus": [],
            "top_risk_skus": [],
            "signals": [
                {
                    "code": "technical_issue",
                    "message": "Decision engine suppressed: SKU attribution is broken.",
                },
                {
                    "code": "data_quality_issue",
                    "message": "Operational actions are blocked until SKU attribution quality is restored.",
                },
            ],
            "sku_attribution_status": sku_attribution_status,
            "territorial_analysis_enabled": territorial_analysis_enabled,
            "profit_contribution_enabled": profit_contribution_enabled,
        }
        director_strategy = {
            "strategy": {"scale": [], "fix": [], "watch": [], "liquidate": []},
            "tasks": [],
            "signals": [
                {
                    "code": "data_quality_issue",
                    "message": "Director strategy tasks are suppressed due to broken SKU attribution.",
                }
            ],
            "sku_attribution_status": sku_attribution_status,
            "territorial_analysis_enabled": territorial_analysis_enabled,
            "profit_contribution_enabled": profit_contribution_enabled,
        }
    else:
        decisions_payload = build_decisions(metrics, abc_rows, health_payload, territorial_distribution, logistics_ktr)
        if isinstance(decisions_payload, dict):
            decisions_payload["sku_attribution_status"] = sku_attribution_status
            decisions_payload["territorial_analysis_enabled"] = territorial_analysis_enabled
            decisions_payload["profit_contribution_enabled"] = profit_contribution_enabled

        director_strategy = build_strategy_plan(
            metrics,
            abc_rows,
            health_payload,
            territorial_distribution,
            logistics_ktr,
            opportunity_scores,
            growth_simulation,
        )
        if isinstance(director_strategy, dict):
            director_strategy["sku_attribution_status"] = sku_attribution_status
            director_strategy["territorial_analysis_enabled"] = territorial_analysis_enabled
            director_strategy["profit_contribution_enabled"] = profit_contribution_enabled

    return {
        "decisions_payload": decisions_payload if isinstance(decisions_payload, dict) else {},
        "director_strategy": director_strategy if isinstance(director_strategy, dict) else {},
    }
