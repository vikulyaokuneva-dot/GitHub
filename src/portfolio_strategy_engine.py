# src/portfolio_strategy_engine.py
from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple


def _f(x: Any) -> float:
    try:
        if x is None or x == "":
            return 0.0
        return float(x)
    except Exception:
        return 0.0


def _i(x: Any) -> int:
    try:
        if x is None or x == "":
            return 0
        return int(float(x))
    except Exception:
        return 0


def _safe_div(a: float, b: float) -> float:
    return float(a) / float(b) if b else 0.0


def _cfg_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


def _cfg_int(name: str, default: int) -> int:
    try:
        return int(float(os.getenv(name, str(default))))
    except Exception:
        return default


def classify_sku(
    row: Dict[str, Any],
    cfg: Dict[str, Any],
    finance_status: str = "ok",
) -> Tuple[str, str, List[str], str]:
    """
    Returns:
      category: "Growth" | "Stable" | "Problem" | "Dead"
      priority: "high" | "medium" | "low"
      reasons: list[str]
      primary_action: short text (machine-friendly)
    """
    sku = _i(row.get("sku"))
    revenue = _f(row.get("revenue"))
    profit = _f(row.get("profit"))
    margin = _f(row.get("margin"))
    orders = _i(row.get("orders"))
    buyouts = _i(row.get("buyouts"))
    ad_spend = _f(row.get("ad_spend"))
    ad_roi = _f(row.get("ad_roi"))
    stock_qty = _i(row.get("stock_qty"))
    turnover_days = _f(row.get("turnover_days"))
    abc = str(row.get("abc") or "")

    margin_growth = float(cfg["margin_growth"])
    margin_problem = float(cfg["margin_problem"])
    ad_roi_growth = float(cfg["ad_roi_growth"])
    turnover_slow_days = float(cfg["turnover_slow_days"])
    min_buyouts_growth = int(cfg["min_buyouts_growth"])

    reasons: List[str] = []
    finance_status_norm = str(finance_status or "").strip().lower()

    # When WB finance rows are delayed, avoid hard profit/dead conclusions.
    if finance_status_norm == "delayed":
        reasons.append("Финансовые строки WB за дату задерживаются; статус SKU предварительный.")
        if orders > 0 or buyouts > 0:
            return "Stable", "medium", reasons, "wait_finance_refresh"
        if stock_qty > 0:
            return "Problem", "low", reasons, "check_listing_and_wait_finance"
        return "Problem", "low", reasons, "wait_finance_refresh"

    # --- DEAD ---
    if buyouts == 0 and orders == 0 and stock_qty > 0:
        reasons.append("Нет продаж (buyouts=0, orders=0) при наличии остатков")
        if ad_spend > 0:
            reasons.append("Есть расход на рекламу при отсутствии продаж")
            return "Dead", "high", reasons, "stop_ads_and_liquidate"
        return "Dead", "medium", reasons, "liquidate_stock"

    # If no sales and no stock -> nothing to act today, but still not Growth
    if buyouts == 0 and orders == 0 and stock_qty == 0 and revenue == 0:
        reasons.append("Нет продаж и нет остатков (возможно товар выключен/нет данных)")
        return "Problem", "low", reasons, "check_listing_and_data"

    # --- PROBLEM ---
    problem_flags = 0

    if revenue > 0 and profit <= 0:
        problem_flags += 1
        reasons.append("Выручка есть, но прибыль <= 0")

    if buyouts > 0 and margin < margin_problem:
        problem_flags += 1
        reasons.append(f"Низкая маржа < {margin_problem:.2f}")

    if ad_spend > 0 and ad_roi < 0:
        problem_flags += 1
        reasons.append("Реклама убыточна (ad_roi < 0)")

    if stock_qty > 0 and buyouts > 0 and turnover_days > turnover_slow_days:
        problem_flags += 1
        reasons.append(f"Слабая оборачиваемость > {turnover_slow_days:.0f} дней")

    if problem_flags >= 1:
        # choose primary action
        if ad_spend > 0 and ad_roi < 0:
            primary = "cut_or_fix_ads"
        elif margin < margin_problem:
            primary = "optimize_price_and_costs"
        elif turnover_days > turnover_slow_days:
            primary = "stimulate_sales_or_reduce_stock"
        else:
            primary = "optimize_listing"
        # priority
        pr = "high" if problem_flags >= 2 or (profit < 0 and revenue > 0) else "medium"
        return "Problem", pr, reasons, primary

    # --- GROWTH ---
    growth_ok = (
        profit > 0
        and margin >= margin_growth
        and buyouts >= min_buyouts_growth
        and (ad_spend == 0 or ad_roi >= ad_roi_growth)
    )

    if growth_ok:
        reasons.append("Положительная прибыль + высокая маржа + есть продажи")
        if ad_spend > 0:
            reasons.append(f"Хороший ROI рекламы (ad_roi >= {ad_roi_growth:.2f})")
        else:
            reasons.append("Реклама не используется или расход = 0 (есть потенциал масштабирования)")

        # If too few days of cover (turnover_days very small), advise replenish, but keep Growth role
        if turnover_days and turnover_days < 7 and stock_qty > 0:
            reasons.append("Риск дефицита (оборачиваемость высокая, запас мал)")
            return "Growth", "high", reasons, "scale_sales_and_replenish"
        return "Growth", "medium", reasons, "scale_ads_and_sales"

    # --- STABLE ---
    if buyouts > 0 and profit >= 0:
        reasons.append("Стабильные продажи, прибыль не отрицательная")
        if margin < margin_growth:
            reasons.append("Маржа средняя (удерживаем и контролируем)")
        if abc in ("A", "B"):
            reasons.append(f"ABC={abc} (вклад в прибыль заметный)")
        return "Stable", "low", reasons, "maintain_and_monitor"

    # fallback
    reasons.append("Не хватает сигналов для Growth/Stable — требуется проверка")
    return "Problem", "low", reasons, "check_listing_and_economics"


def analyze_portfolio_strategy(
    *,
    sku_performance: Dict[str, Any],
    finance_status: str = "ok",
) -> Dict[str, Any]:
    """
    Input: facts_json.sku_performance (output of analyze_sku_performance)
    Output:
      {
        "config": {...},
        "summary": {...},
        "sku_strategies": [ ... top items only ... ],
        "sku_strategies_full": [ ... optional (can be large) ... ],
        "top_growth": [...],
        "top_problem": [...],
        "top_dead": [...],
      }
    """
    rows = (sku_performance or {}).get("rows") or []
    if not isinstance(rows, list):
        rows = []

    cfg = {
        "margin_growth": _cfg_float("WB_PORTFOLIO_MARGIN_GROWTH", 0.25),
        "margin_problem": _cfg_float("WB_PORTFOLIO_MARGIN_PROBLEM", 0.15),
        "ad_roi_growth": _cfg_float("WB_PORTFOLIO_AD_ROI_GROWTH", 0.20),
        "turnover_slow_days": _cfg_float("WB_PORTFOLIO_TURNOVER_SLOW_DAYS", 60),
        "min_buyouts_growth": _cfg_int("WB_PORTFOLIO_MIN_BUYOUTS_GROWTH", 1),
    }

    classified: List[Dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        cat, pr, reasons, primary = classify_sku(r, cfg, finance_status=finance_status)
        classified.append({
            "sku": _i(r.get("sku")),
            "category": cat,
            "priority": pr,
            "primary_action": primary,
            "reasons": reasons[:4],
            "numbers": {
                "revenue": _f(r.get("revenue")),
                "profit": _f(r.get("profit")),
                "margin": _f(r.get("margin")),
                "buyouts": _i(r.get("buyouts")),
                "orders": _i(r.get("orders")),
                "ad_spend": _f(r.get("ad_spend")),
                "ad_roi": _f(r.get("ad_roi")),
                "stock_qty": _i(r.get("stock_qty")),
                "turnover_days": _f(r.get("turnover_days")),
                "abc": r.get("abc"),
            }
        })

    # summary counts + profit/revenue by category
    summary = {
        "counts": {"Growth": 0, "Stable": 0, "Problem": 0, "Dead": 0},
        "revenue": {"Growth": 0.0, "Stable": 0.0, "Problem": 0.0, "Dead": 0.0},
        "profit": {"Growth": 0.0, "Stable": 0.0, "Problem": 0.0, "Dead": 0.0},
    }

    for x in classified:
        cat = x["category"]
        summary["counts"][cat] += 1
        summary["revenue"][cat] += _f(x["numbers"].get("revenue"))
        summary["profit"][cat] += _f(x["numbers"].get("profit"))

    for cat in summary["revenue"]:
        summary["revenue"][cat] = round(summary["revenue"][cat], 2)
        summary["profit"][cat] = round(summary["profit"][cat], 2)

    # rankings for report
    def key_profit(x: Dict[str, Any]) -> float:
        return _f(x.get("numbers", {}).get("profit"))

    def key_spend(x: Dict[str, Any]) -> float:
        return _f(x.get("numbers", {}).get("ad_spend"))

    top_growth = sorted([x for x in classified if x["category"] == "Growth"], key=key_profit, reverse=True)[:10]
    top_problem = sorted([x for x in classified if x["category"] == "Problem"], key=key_profit)[:10]  # worst profit
    top_dead = sorted([x for x in classified if x["category"] == "Dead"], key=key_spend, reverse=True)[:10]  # wasted spend first

    # keep small list for LLM (avoid huge payload)
    sku_strategies_for_llm = sorted(classified, key=lambda x: (x["category"], x["priority"]))[:60]

    return {
        "config": cfg,
        "finance_status": str(finance_status),
        "summary": summary,
        "sku_strategies": sku_strategies_for_llm,
        # full list can be heavy; включай только если нужно
        # "sku_strategies_full": classified,
        "top_growth": top_growth,
        "top_problem": top_problem,
        "top_dead": top_dead,
    }
