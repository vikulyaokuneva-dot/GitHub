from __future__ import annotations

import json
import math
import os
from typing import Any, Dict, List


DEFAULT_PROFIT_THRESHOLDS: Dict[str, float] = {
    "p1_cumulative_share": 0.80,
    "p2_cumulative_share": 0.95,
    "neutral_abs_profit": 1.0,
    "high_concentration_top20_share": 0.80,
    "medium_concentration_top20_share": 0.60,
}


def _as_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if isinstance(value, str):
            token = value.strip().replace(" ", "").replace(",", ".")
            if token == "":
                return None
            return float(token)
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any, default: float = 0.0) -> float:
    parsed = _as_float_or_none(value)
    if parsed is None:
        return float(default)
    return float(parsed)


def _append_warning(bucket: List[str], code: str) -> None:
    token = str(code or "").strip()
    if token and token not in bucket:
        bucket.append(token)


def _extract_sku_metrics(metrics: Any) -> List[Dict[str, Any]]:
    if isinstance(metrics, list):
        return [item for item in metrics if isinstance(item, dict)]
    if isinstance(metrics, dict):
        rows = metrics.get("sku_metrics")
        if isinstance(rows, list):
            return [item for item in rows if isinstance(item, dict)]
        metrics_by_sku = metrics.get("metrics_by_sku")
        if isinstance(metrics_by_sku, dict):
            out: List[Dict[str, Any]] = []
            for sku, payload in metrics_by_sku.items():
                if not isinstance(payload, dict):
                    continue
                row = dict(payload)
                row.setdefault("sku", str(sku))
                out.append(row)
            return out
    return []


def _resolve_revenue(row: Dict[str, Any]) -> float | None:
    for key in ("revenue", "buyouts_amount", "orders_amount", "sales_amount"):
        parsed = _as_float_or_none(row.get(key))
        if parsed is not None:
            return float(parsed)
    return None


def _resolve_profit(row: Dict[str, Any]) -> float | None:
    for key in ("profit", "net_profit", "total_profit"):
        parsed = _as_float_or_none(row.get(key))
        if parsed is not None:
            return float(parsed)
    return None


def _resolve_group(
    *,
    profit: float | None,
    cumulative_positive_share: float,
    positive_total_profit: float,
    thresholds: Dict[str, float],
) -> str:
    neutral_abs = float(thresholds.get("neutral_abs_profit", 1.0))
    if profit is None:
        return "P3"
    if profit < -neutral_abs:
        return "P4"
    if abs(profit) <= neutral_abs:
        return "P3"
    if positive_total_profit <= 0:
        return "P2"
    if cumulative_positive_share < float(thresholds.get("p1_cumulative_share", 0.80)):
        return "P1"
    if cumulative_positive_share < float(thresholds.get("p2_cumulative_share", 0.95)):
        return "P2"
    return "P2"


def _resolve_concentration_label(top_20_profit_share: float | None, thresholds: Dict[str, float]) -> str:
    if top_20_profit_share is None:
        return "insufficient_data"
    if top_20_profit_share >= float(thresholds.get("high_concentration_top20_share", 0.80)):
        return "high"
    if top_20_profit_share >= float(thresholds.get("medium_concentration_top20_share", 0.60)):
        return "medium"
    return "low"


def classify_profit_groups(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = {"p1": [], "p2": [], "p3": [], "p4": []}
    for row in rows:
        label = str(row.get("profit_group") or row.get("class") or "").upper()
        if label == "P1":
            groups["p1"].append(row)
        elif label == "P2":
            groups["p2"].append(row)
        elif label == "P4":
            groups["p4"].append(row)
        else:
            groups["p3"].append(row)
    return groups


def build_profit_contribution(metrics: Dict[str, Any]) -> Dict[str, Any]:
    thresholds = dict(DEFAULT_PROFIT_THRESHOLDS)
    sku_rows = _extract_sku_metrics(metrics)

    normalized: List[Dict[str, Any]] = []
    skipped_rows = 0
    for row in sku_rows:
        sku = str(row.get("sku") or row.get("nm_id") or row.get("offer_id") or "").strip()
        if not sku:
            skipped_rows += 1
            continue
        revenue = _resolve_revenue(row)
        profit = _resolve_profit(row)
        warnings: List[str] = []
        status = "ok"
        if profit is None:
            status = "insufficient_data"
            _append_warning(warnings, "profit_missing")
        if revenue is None:
            _append_warning(warnings, "revenue_missing")

        normalized.append(
            {
                "sku": sku,
                "revenue": round(float(revenue), 2) if revenue is not None else None,
                "profit": round(float(profit), 2) if profit is not None else None,
                "status": status,
                "warnings": warnings[:8],
            }
        )

    normalized.sort(
        key=lambda item: (
            _as_float(item.get("profit"), default=-10**15),
            str(item.get("sku") or ""),
        ),
        reverse=True,
    )

    known_profit_rows = [item for item in normalized if item.get("profit") is not None]
    total_profit = sum(_as_float(item.get("profit")) for item in known_profit_rows)
    known_revenue_rows = [item for item in normalized if item.get("revenue") is not None]
    total_revenue = (
        round(sum(_as_float(item.get("revenue")) for item in known_revenue_rows), 2)
        if known_revenue_rows
        else None
    )
    positive_rows = [item for item in known_profit_rows if _as_float(item.get("profit")) > float(thresholds["neutral_abs_profit"])]
    loss_rows = [item for item in known_profit_rows if _as_float(item.get("profit")) < -float(thresholds["neutral_abs_profit"])]
    positive_total_profit = sum(_as_float(item.get("profit")) for item in positive_rows)

    denominator_profit_share = total_profit if total_profit > 0 else None
    ranked_items: List[Dict[str, Any]] = []
    cumulative_positive_share = 0.0
    profit_rank = 0
    top_level_warnings: List[str] = []
    if skipped_rows > 0:
        _append_warning(top_level_warnings, "sku_missing")

    for item in normalized:
        sku = str(item.get("sku") or "")
        profit_value = _as_float_or_none(item.get("profit"))
        revenue_value = _as_float_or_none(item.get("revenue"))
        item_warnings = list(item.get("warnings", [])) if isinstance(item.get("warnings"), list) else []

        if profit_value is not None:
            profit_rank += 1
            rank_value: int | None = profit_rank
        else:
            rank_value = None
            _append_warning(item_warnings, "profit_missing")

        if denominator_profit_share is None or profit_value is None:
            profit_share = None
            if denominator_profit_share is None and profit_value is not None:
                _append_warning(item_warnings, "total_profit_non_positive")
        else:
            profit_share = round(profit_value / denominator_profit_share, 6)

        cumulative_for_group = cumulative_positive_share
        profit_group = _resolve_group(
            profit=profit_value,
            cumulative_positive_share=cumulative_for_group,
            positive_total_profit=positive_total_profit,
            thresholds=thresholds,
        )
        if profit_value is not None and profit_value > float(thresholds["neutral_abs_profit"]) and positive_total_profit > 0:
            cumulative_positive_share += profit_value / positive_total_profit
        status = str(item.get("status") or "ok")

        ranked_item = {
            "sku": sku,
            "revenue": round(float(revenue_value), 2) if revenue_value is not None else None,
            "profit": round(float(profit_value), 2) if profit_value is not None else None,
            "profit_share": profit_share,
            "profit_rank": rank_value,
            "profit_group": profit_group,
            "status": status,
            "warnings": item_warnings[:8],
            "cumulative_profit_share": round(cumulative_positive_share, 6) if positive_total_profit > 0 else None,
            "class": profit_group,
        }
        ranked_items.append(ranked_item)
        for code in item_warnings:
            _append_warning(top_level_warnings, code)

    grouped = classify_profit_groups(ranked_items)
    top_profit_sku = [row for row in ranked_items if _as_float_or_none(row.get("profit")) is not None][:5]
    top_loss_sku = sorted(
        [row for row in ranked_items if _as_float_or_none(row.get("profit")) is not None and _as_float(row.get("profit")) < 0],
        key=lambda row: (_as_float(row.get("profit")), str(row.get("sku") or "")),
    )[:5]

    if positive_rows:
        top_n = max(1, int(math.ceil(len(positive_rows) * 0.2)))
        top_positive = sorted(positive_rows, key=lambda row: _as_float(row.get("profit")), reverse=True)[:top_n]
        top_20_profit_share = round(
            sum(_as_float(row.get("profit")) for row in top_positive) / positive_total_profit,
            6,
        ) if positive_total_profit > 0 else None
    else:
        top_20_profit_share = None

    concentration_label = _resolve_concentration_label(top_20_profit_share, thresholds)

    if not ranked_items:
        status = "insufficient_data"
        _append_warning(top_level_warnings, "sku_metrics_missing")
    elif any(str(row.get("status") or "") == "insufficient_data" for row in ranked_items):
        status = "partial"
    else:
        status = "ok"

    summary = {
        "sku_count": len(ranked_items),
        "profit_sku_count": len(positive_rows),
        "loss_sku_count": len(loss_rows),
        "total_profit": round(total_profit, 2),
        "total_revenue": total_revenue,
        "top_profit_sku": top_profit_sku,
        "top_loss_sku": top_loss_sku,
        "profit_concentration": concentration_label,
        "top_20_profit_share": top_20_profit_share,
        "status": status,
    }

    out: Dict[str, Any] = {
        "status": status,
        "warnings": top_level_warnings,
        "summary": summary,
        "items": ranked_items,
        "p1": grouped.get("p1", []),
        "p2": grouped.get("p2", []),
        "p3": grouped.get("p3", []),
        "p4": grouped.get("p4", []),
        "top_profit_skus": top_profit_sku,
        "meta": {
            "total_profit": round(total_profit, 2),
            "total_revenue": total_revenue,
            "sku_count": len(ranked_items),
        },
    }
    return out


def save_profit_contribution(output_path: str, data: Dict[str, Any]) -> None:
    directory = os.path.dirname(output_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


