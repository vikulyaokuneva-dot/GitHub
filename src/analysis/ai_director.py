from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple


_PRIORITY_RANK = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def _safe_int(value: Any) -> int:
    return int(round(_safe_float(value)))


def _extract_rows(payload: Any, keys: Tuple[str, ...]) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def _abc_map(abc_rows: List[Dict[str, Any]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not isinstance(abc_rows, list):
        return out
    for row in abc_rows:
        if not isinstance(row, dict):
            continue
        sku = str(row.get("sku") or "").strip()
        if not sku:
            continue
        out[sku] = str(row.get("abc_class") or "").strip().upper()
    return out


def _health_map(health_payload: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for row in _extract_rows(health_payload, ("items", "skus")):
        sku = str(row.get("sku") or "").strip()
        if not sku:
            continue
        status = str(row.get("status") or row.get("health_status") or "").strip().upper()
        if status:
            out[sku] = status
    return out


def _ktr_map(logistics_ktr: Dict[str, Any], territorial_distribution: Dict[str, Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}

    for row in _extract_rows(logistics_ktr, ("skus", "items")):
        sku = str(row.get("sku") or "").strip()
        if not sku:
            continue
        ktr = row.get("ktr")
        if ktr is None:
            continue
        out[sku] = _safe_float(ktr)

    for row in _extract_rows(territorial_distribution, ("skus", "items")):
        sku = str(row.get("sku") or "").strip()
        if not sku or sku in out:
            continue
        ktr = row.get("ktr")
        if ktr is None:
            continue
        out[sku] = _safe_float(ktr)
    return out


def _opportunity_map(opportunity_scores: Dict[str, Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    rows = _extract_rows(opportunity_scores, ("opportunities",))
    for row in rows:
        sku = str(row.get("sku") or "").strip()
        if not sku:
            continue
        out[sku] = _safe_float(row.get("score"))
    return out


def _growth_delta_map(growth_simulation: Dict[str, Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for row in _extract_rows(growth_simulation, ("skus", "items")):
        sku = str(row.get("sku") or "").strip()
        if not sku:
            continue
        best_delta = 0.0
        for sim in _extract_rows(row, ("simulations",)):
            best_delta = max(best_delta, _safe_float(sim.get("profit_delta")))
        out[sku] = best_delta
    return out


def _sort_skus(skus: Iterable[str], opp: Dict[str, float], growth: Dict[str, float]) -> List[str]:
    uniq = sorted({str(s).strip() for s in skus if str(s).strip()})
    return sorted(
        uniq,
        key=lambda sku: (
            -_safe_float(opp.get(sku)),
            -_safe_float(growth.get(sku)),
            sku,
        ),
    )


def _territorial_context(
    territorial_distribution: Dict[str, Any],
    data_quality: Dict[str, Any],
    territorial_analysis_enabled: bool,
) -> Dict[str, Any]:
    summary = territorial_distribution.get("summary", {}) if isinstance(territorial_distribution, dict) else {}
    if not isinstance(summary, dict):
        summary = {}

    analysis_mode = str(
        data_quality.get("territorial_analysis_mode")
        or summary.get("analysis_mode")
        or territorial_distribution.get("analysis_mode")
        or "disabled"
    ).strip().lower()
    recommendation_status = str(
        data_quality.get("territorial_recommendation_status")
        or summary.get("recommendation_status")
        or territorial_distribution.get("recommendation_status")
        or "blocked_by_data"
    ).strip().lower()
    suppressed_due_to_data_quality = bool(
        data_quality.get("territorial_suppressed_due_to_data_quality", summary.get("suppressed_due_to_data_quality", False))
    )
    confidence_level = str(
        data_quality.get("territorial_confidence_level")
        or summary.get("confidence_level")
        or territorial_distribution.get("confidence_level")
        or "low"
    ).strip().lower()
    demand_coverage_pct = _safe_float(summary.get("demand_coverage_pct", territorial_distribution.get("demand_coverage_pct", 0.0)))
    stock_coverage_pct = _safe_float(summary.get("stock_coverage_pct", territorial_distribution.get("stock_coverage_pct", 0.0)))
    coverage_pct = _safe_float(summary.get("coverage_pct", territorial_distribution.get("coverage_pct", 0.0)))

    territorial_actionable_enabled = bool(
        territorial_analysis_enabled
        and analysis_mode == "full"
        and recommendation_status == "actionable"
        and not suppressed_due_to_data_quality
    )

    return {
        "analysis_mode": analysis_mode,
        "recommendation_status": recommendation_status,
        "suppressed_due_to_data_quality": suppressed_due_to_data_quality,
        "confidence_level": confidence_level,
        "demand_coverage_pct": demand_coverage_pct,
        "stock_coverage_pct": stock_coverage_pct,
        "coverage_pct": coverage_pct,
        "territorial_actionable_enabled": territorial_actionable_enabled,
    }


def build_strategy_plan(
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

    if sku_attribution_status == "broken":
        return {
            "strategy": {"scale": [], "fix": [], "watch": [], "liquidate": []},
            "tasks": [],
            "signals": [
                {
                    "code": "data_quality_issue",
                    "message": "Director strategy suppressed due to broken SKU attribution.",
                }
            ],
            "territorial_analysis_enabled": territorial_analysis_enabled,
            "territorial_actionable_enabled": False,
            "sku_attribution_status": sku_attribution_status,
        }

    territorial_ctx = _territorial_context(territorial_distribution, data_quality, territorial_analysis_enabled)
    territorial_actionable_enabled = bool(territorial_ctx.get("territorial_actionable_enabled", False))

    metric_rows = _extract_rows(metrics, ("sku_metrics", "items", "skus"))
    abc_by_sku = _abc_map(abc_rows)
    health_by_sku = _health_map(health_payload)
    ktr_by_sku = _ktr_map(logistics_ktr, territorial_distribution)
    opportunity_by_sku = _opportunity_map(opportunity_scores)
    growth_delta_by_sku = _growth_delta_map(growth_simulation)

    strategy: Dict[str, List[str]] = {
        "scale": [],
        "fix": [],
        "watch": [],
        "liquidate": [],
    }
    tasks: List[Dict[str, Any]] = []
    task_seen: set[Tuple[str, str]] = set()

    for row in metric_rows:
        sku = str(row.get("sku") or "").strip()
        if not sku:
            continue

        profit = _safe_float(row.get("profit"))
        revenue = _safe_float(row.get("revenue"))
        orders = _safe_int(row.get("orders"))
        margin_pct = (profit / revenue) if revenue > 0 else 0.0

        abc_class = abc_by_sku.get(sku, "")
        health_status = health_by_sku.get(sku, "")

        group = ""
        action = ""
        priority = ""

        if abc_class == "A" and margin_pct > 0.3 and health_status == "SCALE":
            group, action, priority = "scale", "increase_ads", "P1"
        elif profit < 0 and orders > 5:
            group, action, priority = "fix", "improve_listing", "P2"
        elif profit < 0 and orders == 0:
            group, action, priority = "liquidate", "discount_or_remove", "P4"
        elif orders < 5 and profit > 0:
            group, action, priority = "watch", "monitor", "P3"

        if group:
            strategy[group].append(sku)
            task_key = (sku, action)
            if task_key not in task_seen:
                task_seen.add(task_key)
                tasks.append({"sku": sku, "task": action, "priority": priority})

        ktr = ktr_by_sku.get(sku)
        if territorial_actionable_enabled and ktr is not None and ktr > 1.3:
            task_key = (sku, "rebalance_stock")
            if task_key not in task_seen:
                task_seen.add(task_key)
                tasks.append({"sku": sku, "task": "rebalance_stock", "priority": "P2"})

    if not territorial_actionable_enabled and territorial_analysis_enabled:
        portfolio_tasks: List[Tuple[str, str, str]] = [
            ("PORTFOLIO", "collect_stock_distribution_data", "P1"),
        ]
        if _safe_float(territorial_ctx.get("stock_coverage_pct")) <= 0:
            portfolio_tasks.append(("PORTFOLIO", "connect_stock_source", "P1"))
        if _safe_float(territorial_ctx.get("demand_coverage_pct")) < 60.0:
            portfolio_tasks.append(("PORTFOLIO", "improve_regional_demand_attribution", "P2"))

        for sku, task_name, priority in portfolio_tasks:
            task_key = (sku, task_name)
            if task_key in task_seen:
                continue
            task_seen.add(task_key)
            tasks.append({"sku": sku, "task": task_name, "priority": priority})

    for key, rows in strategy.items():
        strategy[key] = _sort_skus(rows, opportunity_by_sku, growth_delta_by_sku)

    tasks.sort(
        key=lambda row: (
            _PRIORITY_RANK.get(str(row.get("priority") or "P9"), 9),
            -_safe_float(opportunity_by_sku.get(str(row.get("sku") or ""))),
            -_safe_float(growth_delta_by_sku.get(str(row.get("sku") or ""))),
            str(row.get("sku") or ""),
            str(row.get("task") or ""),
        )
    )

    signals: List[Dict[str, Any]] = []
    if territorial_analysis_enabled and not territorial_actionable_enabled:
        signals.append(
            {
                "code": "data_quality_issue",
                "message": "Territorial recommendations are preview-only; operational rebalance tasks are blocked until evidence improves.",
                "evidence": {
                    "analysis_mode": territorial_ctx.get("analysis_mode"),
                    "recommendation_status": territorial_ctx.get("recommendation_status"),
                    "confidence_level": territorial_ctx.get("confidence_level"),
                    "coverage_pct": territorial_ctx.get("coverage_pct"),
                    "demand_coverage_pct": territorial_ctx.get("demand_coverage_pct"),
                    "stock_coverage_pct": territorial_ctx.get("stock_coverage_pct"),
                },
            }
        )

    return {
        "strategy": strategy,
        "tasks": tasks,
        "signals": signals,
        "territorial_analysis_enabled": territorial_analysis_enabled,
        "territorial_actionable_enabled": territorial_actionable_enabled,
        "territorial_analysis_mode": str(territorial_ctx.get("analysis_mode") or "disabled"),
        "territorial_recommendation_status": str(territorial_ctx.get("recommendation_status") or "blocked_by_data"),
        "territorial_confidence_level": str(territorial_ctx.get("confidence_level") or "low"),
        "sku_attribution_status": sku_attribution_status,
    }
