from __future__ import annotations

from typing import Any, Dict, List


def build_actions(facts: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate lightweight action list from facts.

    v2 goal: produce machine-readable actions for operator or future auto-execution.
    """
    actions: List[Dict[str, Any]] = []

    # --- Ads keywords actions ---
    ads_kw = (facts.get("ads_keywords") or {}).get("top_keywords") or []
    for r in ads_kw:
        label = (r or {}).get("label")
        kw = (r or {}).get("keyword")
        if not kw:
            continue

        if label == "low_ctr":
            actions.append({
                "type": "ADS_KEYWORD_OPTIMIZE",
                "priority": "medium",
                "title": f"Низкий CTR по ключу: {kw}",
                "recommendation": "Сузить ключ (добавить уточнение) или снизить ставку/показ.",
                "payload": {"keyword": kw, "action": "review_bid_or_match"},
            })
        elif label == "no_orders":
            actions.append({
                "type": "ADS_KEYWORD_DISABLE",
                "priority": "high",
                "title": f"Нет заказов при расходе по ключу: {kw}",
                "recommendation": "Отключить ключ или снизить ставку, протестировать другой вариант.",
                "payload": {"keyword": kw, "action": "disable_or_lower_bid"},
            })
        elif label == "high_drr":
            actions.append({
                "type": "ADS_KEYWORD_LOWER_BID",
                "priority": "high",
                "title": f"Высокий ДРР по ключу: {kw}",
                "recommendation": "Снизить ставку, проверить цену/конверсию карточки.",
                "payload": {"keyword": kw, "action": "lower_bid"},
            })

    # --- Stock signals (simple) ---
    stock = facts.get("stock_forecast") or {}
    if stock.get("deficit_skus"):
        actions.append({
            "type": "STOCK_REPLENISH",
            "priority": "high",
            "title": "Есть дефицит по складам",
            "recommendation": "Подготовить поставку по SKU в дефиците.",
            "payload": {"skus": stock.get("deficit_skus")},
        })

    # --- Portfolio strategy (AI директор ассортимента) ---
    portfolio = facts.get("portfolio_strategy") or {}

    def _priority_map(p: str) -> str:
        """Keep orchestrator priorities in the same 'high/medium/low' scale."""
        p = (p or "").strip().lower()
        if p in ("high", "p1", "1"):
            return "high"
        if p in ("medium", "p2", "2"):
            return "medium"
        if p in ("low", "p3", "3"):
            return "low"
        return "low"

    # Dead: ликвидация
    for s in (portfolio.get("top_dead") or [])[:10]:
        if not isinstance(s, dict):
            continue
        sku = s.get("sku")
        actions.append({
            "type": "SKU_PORTFOLIO_DEAD",
            "priority": _priority_map(str(s.get("priority") or "medium")),
            "title": f"SKU {sku}: Dead — ликвидация",
            "recommendation": "Остановить рекламу (если есть) и распродать/снизить остатки.",
            "payload": {
                "sku": sku,
                "category": "Dead",
                "primary_action": s.get("primary_action"),
                "reasons": s.get("reasons") or [],
                "numbers": s.get("numbers") or {},
            },
        })

    # Problem: оптимизация
    for s in (portfolio.get("top_problem") or [])[:10]:
        if not isinstance(s, dict):
            continue
        sku = s.get("sku")
        actions.append({
            "type": "SKU_PORTFOLIO_PROBLEM",
            "priority": _priority_map(str(s.get("priority") or "medium")),
            "title": f"SKU {sku}: Problem — оптимизация",
            "recommendation": "Проверить цену/маржу/рекламу/карточку, сократить убыточный трафик.",
            "payload": {
                "sku": sku,
                "category": "Problem",
                "primary_action": s.get("primary_action"),
                "reasons": s.get("reasons") or [],
                "numbers": s.get("numbers") or {},
            },
        })

    # Growth: масштабирование
    for s in (portfolio.get("top_growth") or [])[:10]:
        if not isinstance(s, dict):
            continue
        sku = s.get("sku")
        actions.append({
            "type": "SKU_PORTFOLIO_GROWTH",
            "priority": _priority_map(str(s.get("priority") or "medium")),
            "title": f"SKU {sku}: Growth — масштабирование",
            "recommendation": "Увеличить бюджет/ставки и обеспечить остатки.",
            "payload": {
                "sku": sku,
                "category": "Growth",
                "primary_action": s.get("primary_action"),
                "reasons": s.get("reasons") or [],
                "numbers": s.get("numbers") or {},
            },
        })

    # --- Growth Engine actions ---
    ge = facts.get("growth_engine_full") or facts.get("growth_engine") or {}
    decisions = ge.get("decisions") or []

    if isinstance(decisions, list):
        for d in decisions:
            if not isinstance(d, dict):
                continue

            sku = d.get("sku")
            decision = (d.get("decision") or "").upper()
            priority_raw = str(d.get("priority") or "P3")
            reason = (d.get("reason") or "").strip()
            reasons = d.get("reasons") or []
            numbers_compact = d.get("numbers_compact") or {}

            # Convert GrowthEngine priority (P1/P2/P3) to orchestrator priority (high/medium/low)
            priority = _priority_map(priority_raw)

            # compact, machine-readable
            if decision == "SCALE":
                actions.append({
                    "type": "SKU_GROWTH_SCALE",
                    "priority": priority,
                    "sku": sku,
                    "text": (f"Масштабировать SKU {sku}. {reason}".strip() + ("" if not reasons else " Причины: " + "; ".join(reasons[:3]))).strip(),
                    "payload": {"decision": "SCALE", "priority": priority_raw, "reasons": reasons, "numbers": numbers_compact},
                })
            elif decision == "OPTIMIZE":
                actions.append({
                    "type": "SKU_GROWTH_OPTIMIZE",
                    "priority": priority,
                    "sku": sku,
                    "text": (f"Оптимизировать SKU {sku}. {reason}".strip() + ("" if not reasons else " Причины: " + "; ".join(reasons[:3]))).strip(),
                    "payload": {"decision": "OPTIMIZE", "priority": priority_raw, "reasons": reasons, "numbers": numbers_compact},
                })
            elif decision == "LIQUIDATE":
                actions.append({
                    "type": "SKU_GROWTH_LIQUIDATE",
                    "priority": priority,
                    "sku": sku,
                    "text": (f"Ликвидировать SKU {sku}. {reason}".strip() + ("" if not reasons else " Причины: " + "; ".join(reasons[:3]))).strip(),
                    "payload": {"decision": "LIQUIDATE", "priority": priority_raw, "reasons": reasons, "numbers": numbers_compact},
                })

    return actions
