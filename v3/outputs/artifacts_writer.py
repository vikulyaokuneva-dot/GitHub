from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from ..analytics.profit_contribution import save_profit_contribution
from ..analytics.territorial_distribution import save_territorial_distribution
from ..storage import write_json


def write_daily_metrics_artifacts(
    *,
    out_dir: str,
    metrics: Dict[str, Any],
    financial_debug: List[Dict[str, Any]],
    abc_rows: List[Dict[str, Any]],
    profit_contribution: Dict[str, Any],
    keyword_monitoring: Dict[str, Any] | None = None,
    advertising_efficiency: Dict[str, Any] | None = None,
    territorial_distribution: Dict[str, Any],
    event_ledger: Dict[str, Any] | None = None,
    cabinet_funnel: Dict[str, Any] | None = None,
    sku_daily_dynamics: Dict[str, Any] | None = None,
) -> None:
    metrics_payload = dict(metrics if isinstance(metrics, dict) else {})
    snapshot = metrics_payload.get("financial_snapshot")
    if snapshot is not None and hasattr(snapshot, "to_dict"):
        try:
            metrics_payload["financial_snapshot"] = snapshot.to_dict()
        except Exception:
            metrics_payload["financial_snapshot"] = {}
    write_json(os.path.join(out_dir, "metrics.json"), metrics_payload)
    if isinstance(event_ledger, dict) and event_ledger:
        write_json(os.path.join(out_dir, "event_ledger.json"), event_ledger)
    if isinstance(cabinet_funnel, dict) and cabinet_funnel:
        write_json(os.path.join(out_dir, "cabinet_funnel.json"), cabinet_funnel)
    if isinstance(sku_daily_dynamics, dict) and sku_daily_dynamics:
        write_json(os.path.join(out_dir, "sku_daily_dynamics.json"), sku_daily_dynamics)
    write_json(os.path.join(out_dir, "financial_debug.json"), financial_debug)
    write_json(os.path.join(out_dir, "abc_analysis.json"), abc_rows)
    save_profit_contribution(os.path.join(out_dir, "profit_contribution.json"), profit_contribution)
    if isinstance(keyword_monitoring, dict) and keyword_monitoring:
        write_json(os.path.join(out_dir, "keyword_monitoring.json"), keyword_monitoring)

    if isinstance(advertising_efficiency, dict) and advertising_efficiency:
        write_json(os.path.join(out_dir, "advertising_efficiency.json"), advertising_efficiency)
        query_payload = advertising_efficiency.get("query_profitability", {})
        if not isinstance(query_payload, dict):
            query_payload = {
                "analysis_mode": str(advertising_efficiency.get("analysis_mode") or "disabled"),
                "status": str(advertising_efficiency.get("status") or "disabled"),
                "summary": {"query_count": len(advertising_efficiency.get("query_performance", []))},
                "items": advertising_efficiency.get("query_performance", []),
            }
        write_json(os.path.join(out_dir, "query_profitability.json"), query_payload)

        portfolio_summary = advertising_efficiency.get("portfolio_ads_summary")
        if not isinstance(portfolio_summary, dict):
            portfolio_summary = advertising_efficiency.get("summary", {})
        if not isinstance(portfolio_summary, dict):
            portfolio_summary = {}
        write_json(os.path.join(out_dir, "portfolio_ads_summary.json"), portfolio_summary)
        write_json(os.path.join(out_dir, "advertising_efficiency_summary.json"), portfolio_summary)

    save_territorial_distribution(Path(out_dir) / "territorial_distribution.json", territorial_distribution)
    if isinstance(territorial_distribution, dict):
        territorial_summary = territorial_distribution.get("summary", {})
        if not isinstance(territorial_summary, dict):
            territorial_summary = {}
        territorial_items = territorial_distribution.get("items")
        if not isinstance(territorial_items, list):
            territorial_items = territorial_distribution.get("skus", [])
        if not isinstance(territorial_items, list):
            territorial_items = []
        write_json(
            os.path.join(out_dir, "territorial_distribution_summary.json"),
            {
                "status": str(territorial_distribution.get("status") or ""),
                "warnings": territorial_distribution.get("warnings", []),
                "summary": territorial_summary,
            },
        )
        write_json(
            os.path.join(out_dir, "territorial_distribution_metrics.json"),
            {
                "status": str(territorial_distribution.get("status") or ""),
                "warnings": territorial_distribution.get("warnings", []),
                "items": territorial_items,
            },
        )


def write_daily_ai_artifacts(
    *,
    out_dir: str,
    health_payload: Dict[str, Any],
    decisions_payload: Dict[str, Any],
    growth_simulation: Dict[str, Any],
    opportunity_scores: Dict[str, Any],
    director_strategy: Dict[str, Any],
    api_debug: Dict[str, Any],
    sku_alerts: Dict[str, Any] | None = None,
    sku_watchlists: Dict[str, Any] | None = None,
) -> None:
    write_json(os.path.join(out_dir, "health_score.json"), health_payload)
    if isinstance(sku_alerts, dict) and sku_alerts:
        write_json(os.path.join(out_dir, "sku_alerts.json"), sku_alerts)
    if isinstance(sku_watchlists, dict) and sku_watchlists:
        write_json(os.path.join(out_dir, "sku_watchlists.json"), sku_watchlists)
    write_json(os.path.join(out_dir, "decisions.json"), decisions_payload)
    write_json(os.path.join(out_dir, "growth_simulation.json"), growth_simulation)
    write_json(os.path.join(out_dir, "opportunity_scores.json"), opportunity_scores)
    write_json(os.path.join(out_dir, "director_strategy.json"), director_strategy)
    write_json(os.path.join(out_dir, "api_debug.json"), api_debug if isinstance(api_debug, dict) else {})


def write_facts_and_warnings(*, out_dir: str, facts: Dict[str, Any], warnings: List[Dict[str, Any]]) -> None:
    write_json(os.path.join(out_dir, "facts.json"), facts)
    write_json(os.path.join(out_dir, "warnings.json"), warnings)


def write_report_meta(*, out_dir: str, report_meta: Dict[str, Any]) -> None:
    write_json(os.path.join(out_dir, "report_meta.json"), report_meta)


def write_job(*, out_dir: str, job: Dict[str, Any]) -> None:
    write_json(os.path.join(out_dir, "job.json"), job)


def write_weekly_facts_and_warnings(
    *,
    out_dir: str,
    weekly_facts: Dict[str, Any],
    warnings: List[Dict[str, Any]],
) -> None:
    write_json(os.path.join(out_dir, "weekly_facts.json"), weekly_facts)
    write_json(os.path.join(out_dir, "warnings.json"), warnings)
