from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List


def load_decision_memory(memory_path: Path) -> List[Dict[str, Any]]:
    path = Path(memory_path)
    if not path.is_file():
        return []

    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            text = line.strip()
            if not text:
                continue
            try:
                item = json.loads(text)
            except Exception:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        if value is None:
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _pct_delta(current: float, base: float) -> float | None:
    if base > 0:
        return round((current - base) / base * 100.0, 4)
    return None


def _iso_to_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _metrics_by_sku(metrics: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    rows = metrics.get("sku_metrics", [])
    if not isinstance(rows, list):
        return {}
    result: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        sku = str(row.get("sku") or "").strip()
        if sku:
            result[sku] = row
    return result


def _classify_result(action: str, deltas: Dict[str, float], current: Dict[str, Any], snapshot: Dict[str, Any]) -> str:
    profit_delta = deltas["profit_delta"]
    buys_delta = deltas["buys_delta"]
    ads_spend_delta = deltas["ads_spend_delta"]
    margin_pct_delta = deltas["margin_pct_delta"]

    if action == "scale":
        if profit_delta > 0 or buys_delta > 0:
            return "success"
        if profit_delta < 0 and ads_spend_delta > 0:
            return "fail"
        return "neutral"

    if action == "fix":
        if margin_pct_delta > 0 or profit_delta > 0:
            return "success"
        if profit_delta < 0:
            return "fail"
        return "neutral"

    if action == "watch":
        if profit_delta > 0:
            return "success"
        if profit_delta < 0:
            return "fail"
        return "neutral"

    if action == "liquidate":
        prev_stock_raw = snapshot.get("stock")
        curr_stock_raw = current.get("stock")
        has_prev_stock = prev_stock_raw is not None
        has_curr_stock = curr_stock_raw is not None
        prev_stock = _safe_float(prev_stock_raw) if has_prev_stock else None
        curr_stock = _safe_float(curr_stock_raw) if has_curr_stock else None

        if prev_stock is not None and curr_stock is not None:
            if curr_stock < prev_stock:
                return "success"
            if profit_delta < 0 and curr_stock >= prev_stock:
                return "fail"
        if profit_delta >= 0:
            return "success"
        return "neutral"

    return "neutral"


def _save_memory(memory_path: Path, rows: List[Dict[str, Any]]) -> None:
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    with memory_path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def _memory_status_summary(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    summary = {"total_logged": 0, "pending": 0, "success": 0, "fail": 0, "neutral": 0}
    for row in rows:
        if not isinstance(row, dict):
            continue
        summary["total_logged"] += 1
        status = str(row.get("status") or "pending").strip().lower()
        if status in summary:
            summary[status] += 1
        else:
            summary["pending"] += 1
    return summary


def evaluate_decision_outcomes(seller_id: str, run_date: str, artifacts_dir: Path, memory_dir: Path) -> Dict[str, Any]:
    run_dt = _iso_to_date(run_date)
    artifacts = Path(artifacts_dir)
    memory_root = Path(memory_dir)
    memory_file = memory_root / "decision_memory.jsonl"
    rows = load_decision_memory(memory_file)

    metrics_payload = _load_json(artifacts / "metrics.json")
    metrics_map = _metrics_by_sku(metrics_payload)

    evaluated_items: List[Dict[str, Any]] = []
    results = {"success": 0, "fail": 0, "neutral": 0}
    changed = False

    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("seller_id") or "").strip() != seller_id:
            continue

        status = str(row.get("status") or "pending").strip().lower()
        if status != "pending":
            continue

        decision_dt = _iso_to_date(row.get("date"))
        if run_dt is None or decision_dt is None:
            continue

        window_days = (run_dt - decision_dt).days
        if window_days < 3:
            continue

        sku = str(row.get("sku") or "").strip()
        if not sku:
            continue

        snapshot = row.get("metrics_snapshot", {})
        if not isinstance(snapshot, dict):
            snapshot = {}
        current = metrics_map.get(sku, {})
        if not isinstance(current, dict):
            current = {}

        base_revenue = _safe_float(snapshot.get("revenue"))
        base_profit = _safe_float(snapshot.get("profit"))
        base_buys = float(_safe_int(snapshot.get("buys")))
        base_ads_spend = _safe_float(snapshot.get("ads_spend"))
        base_margin_pct = _safe_float(snapshot.get("margin_pct"))

        curr_revenue = _safe_float(current.get("revenue"))
        curr_profit = _safe_float(current.get("profit"))
        curr_buys = float(_safe_int(current.get("buys")))
        curr_ads_spend = _safe_float(current.get("ads_spend"))
        curr_margin_pct = _safe_float(current.get("margin_pct"))

        deltas = {
            "revenue_delta": round(curr_revenue - base_revenue, 4),
            "profit_delta": round(curr_profit - base_profit, 4),
            "buys_delta": round(curr_buys - base_buys, 4),
            "ads_spend_delta": round(curr_ads_spend - base_ads_spend, 4),
            "margin_pct_delta": round(curr_margin_pct - base_margin_pct, 4),
        }
        revenue_delta_pct = _pct_delta(curr_revenue, base_revenue)
        profit_delta_pct = _pct_delta(curr_profit, base_profit)
        buys_delta_pct = _pct_delta(curr_buys, base_buys)
        deltas["revenue_delta_pct"] = revenue_delta_pct
        deltas["profit_delta_pct"] = profit_delta_pct
        deltas["buys_delta_pct"] = buys_delta_pct

        action = str(row.get("action") or "").strip().lower()
        result = _classify_result(action, deltas, current=current, snapshot=snapshot)
        if result not in results:
            result = "neutral"

        row["status"] = result
        row["outcome"] = {
            "measured_at": run_date,
            "window_days": window_days,
            "current_metrics": {
                "revenue": round(curr_revenue, 4),
                "profit": round(curr_profit, 4),
                "margin_pct": round(curr_margin_pct, 4),
                "orders": _safe_int(current.get("orders")),
                "buys": _safe_int(current.get("buys")),
                "ads_spend": round(curr_ads_spend, 4),
                "stock": _safe_int(current.get("stock")) if current.get("stock") is not None else None,
            },
            "deltas": deltas,
            "result": result,
        }
        changed = True
        results[result] += 1

        evaluated_items.append(
            {
                "decision_id": str(row.get("decision_id") or ""),
                "sku": sku,
                "action": action,
                "window_days": window_days,
                "result": result,
                "deltas": deltas,
            }
        )

    if changed:
        _save_memory(memory_file, rows)

    summary = _memory_status_summary(rows)

    return {
        "run_date": run_date,
        "seller_id": seller_id,
        "evaluated": len(evaluated_items),
        "results": results,
        "items": evaluated_items,
        "decision_memory_summary": summary,
    }


def save_outcomes(seller_id: str, run_date: str, outcomes: Dict[str, Any], memory_dir: Path) -> Path:
    memory_root = Path(memory_dir)
    out_dir = memory_root / "outcomes"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{run_date}_outcomes.json"

    payload = {
        "run_date": run_date,
        "seller_id": seller_id,
        "evaluated": int(outcomes.get("evaluated", 0) or 0),
        "results": outcomes.get("results", {"success": 0, "fail": 0, "neutral": 0}),
        "items": outcomes.get("items", []),
    }
    with out_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    return out_path

