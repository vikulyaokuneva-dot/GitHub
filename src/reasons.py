# src/reasons.py
from __future__ import annotations

from typing import Any, Dict, List, Tuple


def _to_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def _to_int(x: Any, default: int = 0) -> int:
    try:
        if x is None:
            return default
        return int(float(x))
    except Exception:
        return default


def _pct(value: Any, digits: int = 1) -> str:
    v = _to_float(value, default=float("nan"))
    if v != v:  # nan
        return "нет данных"
    if 0 <= v <= 1:
        v *= 100.0
    return f"{round(v, digits)}%"


def build_reasons_for_decision(decision: str, metrics: Dict[str, Any]) -> Tuple[List[str], Dict[str, Any]]:
    """Формирует объяснения решения Growth Engine: действие + причины + цифры.

    decision: SCALE/OPTIMIZE/LIQUIDATE/HOLD
    metrics: словарь метрик по SKU (можно передавать любой набор — функция возьмёт то, что найдёт)
    """
    d = (decision or "").upper().strip()

    margin = metrics.get("margin")
    cart_cr = metrics.get("cart_cr") or metrics.get("cr_cart") or metrics.get("CR_cart")
    orders = metrics.get("orders") or metrics.get("sales_qty")
    profit = metrics.get("profit")
    roi = metrics.get("roi") or metrics.get("ROAS") or metrics.get("roas")
    ad_spend = metrics.get("ad_spend") or metrics.get("spend")
    stock_days = metrics.get("stock_days") or metrics.get("days_of_stock") or metrics.get("turnover_days")
    stock_units = metrics.get("stock_units") or metrics.get("stock") or metrics.get("quantity")

    # numbers_compact — то, что удобно показывать рядом с причинами
    numbers_compact: Dict[str, Any] = {
        "margin": margin,
        "cart_cr": cart_cr,
        "orders": orders,
        "profit": profit,
        "roi": roi,
        "ad_spend": ad_spend,
        "stock_days": stock_days,
        "stock_units": stock_units,
    }

    reasons: List[str] = []

    if d == "SCALE":
        if margin is not None:
            reasons.append(f"маржа: {_pct(margin, 0)}")
        o = _to_int(orders, 0)
        if o > 0:
            reasons.append("стабильные продажи/заказы")
        if roi is not None and _to_float(ad_spend, 0.0) > 0:
            reasons.append(f"высокий ROI рекламы: {_to_float(roi, 0.0):.2f}")
        su = _to_int(stock_units, 0)
        if su > 0:
            reasons.append(f"достаточный остаток: {su} шт")

    elif d == "OPTIMIZE":
        if cart_cr is not None:
            reasons.append(f"CR_cart = {_pct(cart_cr, 1)} (ниже нормы)")
        if metrics.get("views") is not None:
            reasons.append(f"просмотры: {_to_int(metrics.get('views'))}")
        if metrics.get("add_to_cart") is not None:
            reasons.append(f"добавления в корзину: {_to_int(metrics.get('add_to_cart'))}")
        # универсальные объяснения
        reasons.append("просмотры есть, но мало добавлений в корзину")
        reasons.append("вероятная проблема первого экрана")

        if _to_float(ad_spend, 0.0) > 0 and roi is not None and _to_float(roi, 0.0) <= 0:
            reasons.append("расход на рекламу есть, отдачи нет — проверить ключи/ставки/цену")

    elif d == "LIQUIDATE":
        o = _to_int(orders, 0)
        if o == 0:
            reasons.append("0 продаж")
        su = _to_int(stock_units, 0)
        if su > 0:
            reasons.append(f"остаток {su} шт")
        if margin is not None:
            reasons.append(f"маржа: {_pct(margin, 0)}")

    else:
        # HOLD и прочее — даём минимум, чтобы не раздувать
        if margin is not None:
            reasons.append(f"маржа: {_pct(margin, 0)}")
        o = _to_int(orders, 0)
        if o > 0:
            reasons.append(f"заказы: {o}")

    # убираем пустое/нет данных
    reasons = [r for r in reasons if r and "нет данных" not in r]

    return reasons, numbers_compact
