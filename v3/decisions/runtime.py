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
    decisions_payload = build_decisions(metrics, abc_rows, health_payload, territorial_distribution, logistics_ktr)
    director_strategy = build_strategy_plan(
        metrics,
        abc_rows,
        health_payload,
        territorial_distribution,
        logistics_ktr,
        opportunity_scores,
        growth_simulation,
    )
    return {
        "decisions_payload": decisions_payload if isinstance(decisions_payload, dict) else {},
        "director_strategy": director_strategy if isinstance(director_strategy, dict) else {},
    }
