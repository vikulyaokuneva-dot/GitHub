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

    # fallback to territorial distribution if logistics_ktr misses some SKUs
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


def build_strategy_plan(
    metrics: Dict[str, Any],
    abc_rows: List[Dict[str, Any]],
    health_payload: Dict[str, Any],
    territorial_distribution: Dict[str, Any],
    logistics_ktr: Dict[str, Any],
    opportunity_scores: Dict[str, Any],
    growth_simulation: Dict[str, Any],
) -> Dict[str, Any]:
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

        # Primary strategy bucket (deterministic precedence)
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
        if ktr is not None and ktr > 1.3:
            task_key = (sku, "rebalance_stock")
            if task_key not in task_seen:
                task_seen.add(task_key)
                tasks.append({"sku": sku, "task": "rebalance_stock", "priority": "P2"})

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

    return {
        "strategy": strategy,
        "tasks": tasks,
    }
