# src/growth_engine.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from src.reasons import build_reasons_for_decision

@dataclass
class GrowthEngineConfig:
    # сколько заказов/продаж нужно, чтобы уверенно судить "убыток"
    min_orders_for_judgement: int = 2

    # масштабирование
    min_margin_for_scale: float = 0.18        # 18%
    target_roi: float = 0.20                  # 20%

    # склад
    overstock_days: int = 45                  # >45 дней = явный перезапас
    low_velocity_threshold: float = 0.15      # ~0.15 заказа/день = почти нет продаж

    # “плохая конверсия” (для OPTIMIZE)
    low_cart_cr: float = 0.06                 # 6%


def analyze_growth_engine(
    sku_performance: Dict[str, Any],
    portfolio_strategy: Dict[str, Any],
    config: Optional[GrowthEngineConfig] = None,
) -> Dict[str, Any]:
    cfg = config or GrowthEngineConfig()

    rows = (sku_performance or {}).get("rows") or []
    if not isinstance(rows, list) or not rows:
        return {
            "error": "no_sku_rows",
            "summary": {},
            "decisions": [],
            "top_scale": [],
            "top_optimize": [],
            "top_liquidate": [],
            "top_contribution": [],
        }

    # total profit for contribution
    total_profit = 0.0
    for r in rows:
        try:
            total_profit += float((r or {}).get("profit", 0) or 0)
        except Exception:
            pass

    # portfolio role lookup
    role_map: Dict[int, str] = {}
    try:
        by_role = (portfolio_strategy or {}).get("by_sku") or {}
        # ожидаем формат {sku: {"role": "Growth"}}
        if isinstance(by_role, dict):
            for k, v in by_role.items():
                sku = int(k)
                role = (v or {}).get("role")
                if sku and role:
                    role_map[sku] = str(role)
    except Exception:
        role_map = {}

    decisions: List[Dict[str, Any]] = []

    for r in rows:
        if not isinstance(r, dict):
            continue

        sku = int(r.get("sku") or r.get("nmId") or 0)
        if not sku:
            continue

        profit = _f(r.get("profit"))
        margin = _f(r.get("margin"))
        orders = _i(r.get("orders") or r.get("sales_qty") or 0)

        # если нет готовой скорости — оценим грубо
        velocity = _f(r.get("orders_per_day") or r.get("sales_velocity") or 0)

        stock_days = _f(r.get("days_of_stock") or r.get("turnover_days") or 0)
        cart_cr = _f(r.get("cart_cr") or 0)
        roi = _f(r.get("roi") or r.get("ROI") or 0)
        ad_spend = _f(r.get("ad_spend") or 0)

        role = role_map.get(sku) or (r.get("portfolio_role") or None)

        contrib = (profit / total_profit) if total_profit > 0 else 0.0

        decision, priority, reason = _decide(
            cfg=cfg,
            profit=profit,
            margin=margin,
            orders=orders,
            velocity=velocity,
            stock_days=stock_days,
            cart_cr=cart_cr,
            roi=roi,
            ad_spend=ad_spend,
            role=role,
            contrib=contrib,
        )

        # Explainable AI: причины + ключевые цифры для доверия
        reasons, numbers_compact = build_reasons_for_decision(decision, {
            "profit": profit,
            "margin": margin,
            "orders": orders,
            "velocity": velocity,
            "stock_days": stock_days,
            "cart_cr": cart_cr,
            "roi": roi,
            "ad_spend": ad_spend,
            "contribution_share": contrib,
        })

        decisions.append({
            "sku": sku,
            "decision": decision,      # SCALE/OPTIMIZE/LIQUIDATE/HOLD
            "priority": priority,      # P1/P2/P3
            "reason": reason,
            "reasons": reasons,
            "numbers_compact": numbers_compact,
            "numbers": {
                "profit": round(profit, 2),
                "margin": round(margin, 4),
                "orders": int(orders),
                "velocity": round(velocity, 4),
                "stock_days": round(stock_days, 2),
                "cart_cr": round(cart_cr, 4),
                "roi": round(roi, 4),
                "ad_spend": round(ad_spend, 2),
                "contribution_share": round(contrib, 4),
            },
            "role": role,
        })

    # сортировки для витрины
    top_contribution = sorted(decisions, key=lambda d: d["numbers"]["contribution_share"], reverse=True)[:10]
    top_scale = [d for d in decisions if d["decision"] == "SCALE"]
    top_optimize = [d for d in decisions if d["decision"] == "OPTIMIZE"]
    top_liquidate = [d for d in decisions if d["decision"] == "LIQUIDATE"]

    # приоритет внутри категорий: contribution + severity
    top_scale = sorted(top_scale, key=lambda d: (d["priority"], -d["numbers"]["contribution_share"], -d["numbers"]["profit"]))[:10]
    top_optimize = sorted(top_optimize, key=lambda d: (d["priority"], -d["numbers"]["contribution_share"]))[:10]
    top_liquidate = sorted(top_liquidate, key=lambda d: (d["priority"], -abs(d["numbers"]["profit"]), -d["numbers"]["stock_days"]))[:10]

    summary = {
        "counts": {
            "scale": len([d for d in decisions if d["decision"] == "SCALE"]),
            "optimize": len([d for d in decisions if d["decision"] == "OPTIMIZE"]),
            "liquidate": len([d for d in decisions if d["decision"] == "LIQUIDATE"]),
            "hold": len([d for d in decisions if d["decision"] == "HOLD"]),
        }
    }

    return {
        "summary": summary,
        "decisions": decisions,
        "top_scale": top_scale,
        "top_optimize": top_optimize,
        "top_liquidate": top_liquidate,
        "top_contribution": top_contribution,
    }


def _decide(
    cfg: GrowthEngineConfig,
    profit: float,
    margin: float,
    orders: int,
    velocity: float,
    stock_days: float,
    cart_cr: float,
    roi: float,
    ad_spend: float,
    role: Optional[str],
    contrib: float,
) -> Tuple[str, str, str]:
    role_s = (role or "").strip()

    # --- 1) LIQUIDATE (жёсткие правила) ---
    # a) роль Dead
    if role_s.lower() == "dead":
        return "LIQUIDATE", _p("P1", contrib), "Роль портфеля: Dead → ликвидировать (не держать остатки, выключить рекламу)."

    # b) убыток при достаточном объёме
    if profit < 0 and orders >= cfg.min_orders_for_judgement:
        return "LIQUIDATE", _p("P1", contrib), f"Убыток {profit:.0f} ₽ при {orders} заказах → остановить рекламу/распродать остатки."

    # c) залежалый склад + почти нет продаж
    if stock_days >= cfg.overstock_days and velocity <= cfg.low_velocity_threshold and profit <= 0:
        return "LIQUIDATE", _p("P2", contrib), f"Залежалый остаток ~{stock_days:.0f} дней и продаж почти нет → распродажа/снижение цены."

    # --- 2) SCALE ---
    # прибыль + норм маржа + (ROI ок или рекламы нет/минимум) + не явный перезапас
    ads_ok = (ad_spend <= 0) or (roi >= cfg.target_roi)
    if profit > 0 and margin >= cfg.min_margin_for_scale and ads_ok:
        # если Growth роль — чуть увереннее
        base = "Прибыльный SKU и маржа выше порога."
        if role_s.lower() == "growth":
            base = "Роль Growth + прибыльность подтверждена."
        return "SCALE", _p("P2", contrib), f"{base} Усилить трафик/рекламу, контролировать остатки."

    # --- 3) OPTIMIZE ---
    # проблема: низкий CR корзины или реклама есть, но ROI не дотягивает, или есть склад, но скорость слабая
    if role_s.lower() == "problem":
        return "OPTIMIZE", _p("P1", contrib), "Роль Problem → оптимизировать карточку/цену/рекламу."

    if cart_cr > 0 and cart_cr < cfg.low_cart_cr:
        return "OPTIMIZE", _p("P2", contrib), f"Низкий CR в корзину {cart_cr*100:.1f}% → улучшить first screen/заголовок/УТП."

    if ad_spend > 0 and roi < cfg.target_roi:
        return "OPTIMIZE", _p("P2", contrib), "Реклама расходуется, ROI ниже цели → почистить ключи/ставки, проверить цену и конверсию."

    if stock_days > cfg.overstock_days and velocity > cfg.low_velocity_threshold and profit > 0:
        # ВАЖНО: прибыльный SKU с перезапасом — НЕ ликвидация, а оптимизация распродажи/цены/трафика
        return "OPTIMIZE", _p("P2", contrib), f"Прибыльный SKU, но перезапас (~{stock_days:.0f} дней) → ускорить продажи (цена/акции/трафик)."

    # --- 4) HOLD ---
    return "HOLD", "P3", "Метрики без критических сигналов → удерживать стратегию."


def _p(base: str, contrib: float) -> str:
    # повышаем приоритет, если SKU сильно влияет на прибыль
    if contrib >= 0.25:
        return "P1"
    if contrib >= 0.10 and base == "P3":
        return "P2"
    return base


def _f(x: Any) -> float:
    try:
        if x is None:
            return 0.0
        return float(x)
    except Exception:
        return 0.0


def _i(x: Any) -> int:
    try:
        if x is None:
            return 0
        return int(float(x))
    except Exception:
        return 0
