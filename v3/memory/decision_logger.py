from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Set


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _normalize_action(action: str) -> str:
    normalized = (action or "").strip().lower()
    if normalized in {"scale", "fix", "watch", "liquidate"}:
        return normalized
    return ""


def _goal_by_action(action: str) -> str:
    if action == "scale":
        return "increase_profit"
    if action == "fix":
        return "improve_unit_economics"
    if action == "watch":
        return "collect_more_data"
    if action == "liquidate":
        return "reduce_losses"
    return "unknown"


def _existing_ids(memory_file: Path) -> Set[str]:
    if not memory_file.is_file():
        return set()
    seen: Set[str] = set()
    with memory_file.open("r", encoding="utf-8") as file:
        for line in file:
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except Exception:
                continue
            if isinstance(row, dict):
                decision_id = str(row.get("decision_id") or "").strip()
                if decision_id:
                    seen.add(decision_id)
    return seen


def _metrics_by_sku(metrics: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    rows = metrics.get("sku_metrics", [])
    if not isinstance(rows, list):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        sku = str(row.get("sku") or "").strip()
        if not sku:
            continue
        out[sku] = row
    return out


def log_decisions(
    seller_id: str,
    run_date: str,
    metrics: Dict[str, Any],
    decisions: Dict[str, Any],
    artifacts_dir: Path,
) -> int:
    artifacts = Path(artifacts_dir)
    decisions_payload = _load_json(artifacts / "decisions.json")
    metrics_payload = _load_json(artifacts / "metrics.json")

    if not decisions_payload:
        decisions_payload = decisions if isinstance(decisions, dict) else {}
    if not metrics_payload:
        metrics_payload = metrics if isinstance(metrics, dict) else {}

    summary = decisions_payload.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}

    metrics_map = _metrics_by_sku(metrics_payload)
    memory_root = artifacts.parent / "memory"
    memory_root.mkdir(parents=True, exist_ok=True)
    memory_file = memory_root / "decision_memory.jsonl"
    seen_ids = _existing_ids(memory_file)

    date_token = run_date.replace("-", "_")
    rows_to_append: List[str] = []

    for action in ("scale", "fix", "watch", "liquidate"):
        entries = summary.get(action, [])
        if not isinstance(entries, list):
            continue
        for item in entries:
            if not isinstance(item, dict):
                continue
            sku = str(item.get("sku") or "").strip()
            if not sku:
                continue

            decision_id = f"dec_{date_token}_{sku}"
            if decision_id in seen_ids:
                continue

            metric = metrics_map.get(sku, {})
            action_text = str(item.get("action") or "")
            normalized_action = _normalize_action(action) or _normalize_action(action_text) or action

            payload = {
                "decision_id": decision_id,
                "date": run_date,
                "seller_id": seller_id,
                "sku": sku,
                "action": normalized_action,
                "action_text": action_text,
                "metrics_snapshot": {
                    "revenue": float(metric.get("revenue", 0.0) or 0.0),
                    "profit": float(metric.get("profit", 0.0) or 0.0),
                    "margin_pct": float(metric.get("margin_pct", 0.0) or 0.0),
                    "orders": int(metric.get("orders", 0) or 0),
                    "buys": int(metric.get("buys", 0) or 0),
                    "ads_spend": float(metric.get("ads_spend", 0.0) or 0.0),
                },
                "context": {
                    "abc_class": str(item.get("abc_class") or ""),
                    "health_status": str(item.get("health_status") or ""),
                    "territorial_status": str(item.get("territorial_status") or ""),
                    "territorial_ktr": float(item.get("territorial_ktr", 0.0) or 0.0),
                    "territorial_reasons": (
                        [str(reason) for reason in item.get("territorial_reasons", []) if str(reason).strip()]
                        if isinstance(item.get("territorial_reasons"), list)
                        else []
                    ),
                },
                "expected_effect": {
                    "goal": _goal_by_action(normalized_action),
                },
                "status": "pending",
            }
            rows_to_append.append(json.dumps(payload, ensure_ascii=False))
            seen_ids.add(decision_id)

    if rows_to_append:
        with memory_file.open("a", encoding="utf-8") as file:
            file.write("\n".join(rows_to_append) + "\n")

    return len(rows_to_append)
