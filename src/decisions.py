from __future__ import annotations

from typing import Any, Dict, List


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
    if not b:
        return 0.0
    return float(a) / float(b)


def build_decision_signals(
    *,
    funnel: Dict[str, Any],
    finance: Dict[str, Any],
    ads: Dict[str, Any],
    stock: Dict[str, Any],
    sku_summary: Dict[str, Any] | None = None,
    scope: str = "daily",
) -> List[Dict[str, Any]]:
    """Детерминированные сигналы (правила) для LLM.

    scope: "daily" | "weekly"
    """
    sku_summary = sku_summary or {}
    out: List[Dict[str, Any]] = []

    # --- conversion ---
    views = _i(funnel.get("views"))
    carts = _i(funnel.get("cart"))
    orders = _i(funnel.get("orders"))
    buys = _i(funnel.get("buys"))  # может лагать
    cr_cart = _f(funnel.get("cr_cart")) or _safe_div(carts, views)
    cr_order = _f(funnel.get("cr_order")) or _safe_div(orders, carts)

    if views >= 200 and orders == 0:
        out.append({
            "type": "conversion",
            "severity": "high",
            "title": "Есть просмотры, нет заказов",
            "msg": "Просмотры есть, но заказов нет — чаще всего проблема цены/оффера/доставки или нерелевантного трафика.",
            "numbers": {"views": views, "orders": orders, "carts": carts, "cr_cart": round(cr_cart, 4), "cr_order": round(cr_order, 4)},
            "suggested_action": "Проверь цену относительно конкурентов, сроки/стоимость доставки, фото+первый экран, наличие вариантов. Если трафик из рекламы — чисти ключи.",
        })

    if cr_cart and cr_cart < 0.08 and views >= 200:
        out.append({
            "type": "conversion",
            "severity": "medium",
            "title": "Низкая конверсия в корзину",
            "msg": "CR в корзину ниже 8% — обычно проблема первого экрана, цены, оффера, фото/видео, отзывов.",
            "numbers": {"views": views, "carts": carts, "cr_cart": round(cr_cart, 4)},
            "suggested_action": "Усиль первый экран: главное фото, заголовок, УТП, цена/скидка. Проверь отзывы и соответствие ожиданиям.",
        })

    if cr_order and cr_order < 0.35 and carts >= 30:
        out.append({
            "type": "conversion",
            "severity": "medium",
            "title": "Низкая конверсия из корзины в заказ",
            "msg": "Много добавлений в корзину, но мало заказов — проблема доставки/цены/конкурентов.",
            "numbers": {"carts": carts, "orders": orders, "cr_order": round(cr_order, 4)},
            "suggested_action": "Проверь стоимость/срок доставки, цену в сравнении, конкурентов, условия скидок/купонов.",
        })

    # --- finance ---
    profit = _f(finance.get("profit"))
    margin = _f(finance.get("margin"))
    gross = _f(finance.get("gross_revenue"))

    if gross > 0 and profit < 0:
        out.append({
            "type": "finance",
            "severity": "high",
            "title": "День убыточный по кабинету",
            "msg": "По отчету реализации прибыль < 0 — нужно срочно найти источник убытка.",
            "numbers": {"revenue": round(gross, 2), "profit": round(profit, 2), "margin": round(margin, 4)},
            "suggested_action": "Проверь убыточные SKU, комиссию/логистику, штрафы, расходы на рекламу. Отключи убыточные кампании.",
        })

    # --- ads ---
    spend = _f(ads.get("spend"))
    roas = _f(ads.get("roas"))
    drr = _f(ads.get("drr"))
    ctr = _f(ads.get("ctr"))
    cpc = _f(ads.get("cpc"))
    cpm = _f(ads.get("cpm"))
    attr_available = bool(ads.get("attr_available"))

    if spend > 0 and (drr and drr > 0.35):
        out.append({
            "type": "ads",
            "severity": "high",
            "title": "Высокий ДРР",
            "msg": "ДРР выше 35% — реклама с высокой вероятностью съедает прибыль (если маржа не экстремально высокая).",
            "numbers": {"drr": round(drr, 4), "roas": round(roas, 3), "spend": round(spend, 2), "ctr": round(ctr, 4), "cpc": round(cpc, 2), "cpm": round(cpm, 2)},
            "suggested_action": "Урежь кампании с высоким расходом без выкупов, сузь ключи, добавь минус-слова, проверь ставки и релевантность.",
        })

    if spend > 0 and not attr_available:
        out.append({
            "type": "ads",
            "severity": "low",
            "title": "Нет атрибуции выручки по рекламе",
            "msg": "WB не отдал атрибуцию выручки (revenue_attr=0), поэтому прибыльность рекламы подтвердить нельзя — ориентируемся на CTR/CPC/ДРР и заказы.",
            "numbers": {"spend": round(spend, 2), "ctr": round(ctr, 4), "cpc": round(cpc, 2), "drr": round(drr, 4)},
            "suggested_action": "Оставь только ключи/кампании, где есть заказы/выкупы. Остальное урежь и пересобери семантику.",
        })

    # --- sku signals (from sku_summary) ---
    worst = sku_summary.get("high_return") or []
    if isinstance(worst, list) and worst:
        top = worst[:5]
        out.append({
            "type": "sku",
            "severity": "medium",
            "title": "Высокие возвраты по SKU",
            "msg": "Повышенные возвраты — возможная проблема ожиданий/качества/описания/размера.",
            "numbers": {"top5": [{"sku": x.get("sku"), "return_rate": x.get("return_rate"), "sales_qty": x.get("sales_qty"), "returns_qty": x.get("returns_qty")} for x in top]},
            "suggested_action": "Проверь фото/описание/размерность, добавь предупреждения, усили контроль качества/упаковки.",
        })

    no_sales = sku_summary.get("no_sales_with_stock") or []
    if isinstance(no_sales, list) and no_sales:
        top = no_sales[:5]
        out.append({
            "type": "sku",
            "severity": "medium",
            "title": "Есть товары с остатком без продаж",
            "msg": "Остаток есть, продаж нет — зависший склад или недостаточный трафик/конверсия.",
            "numbers": {"top5": top, "count": len(no_sales)},
            "suggested_action": "Проверь статус карточки (активна/видимость), индексацию, цену, фото/SEO, условия доставки. Запусти точечную рекламу на 1–2 релевантных запроса.",
        })

    # normalize order by severity
    severity_order = {"high": 0, "medium": 1, "low": 2}
    out.sort(key=lambda x: severity_order.get(x.get("severity", "medium"), 9))

    # add scope tag
    for s in out:
        s["scope"] = scope

    return out
