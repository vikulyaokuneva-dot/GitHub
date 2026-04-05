"""Report builder for Ozon express audit MVP."""

from __future__ import annotations

from typing import Any


def _fmt_int(value: Any) -> str:
    if value is None:
        return "РЅРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РґР°РЅРЅС‹С…"
    try:
        return str(int(float(value)))
    except Exception:
        return "РЅРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РґР°РЅРЅС‹С…"


def _fmt_money(value: Any) -> str:
    if value is None:
        return "РЅРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РґР°РЅРЅС‹С…"
    try:
        return f"{float(value):,.2f} RUB".replace(",", " ")
    except Exception:
        return "РЅРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РґР°РЅРЅС‹С…"


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "РЅРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РґР°РЅРЅС‹С…"
    try:
        return f"{float(value):.2f}%"
    except Exception:
        return "РЅРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РґР°РЅРЅС‹С…"


def _fmt_ratio_pct(value: Any) -> str:
    if value is None:
        return "РЅРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РґР°РЅРЅС‹С…"
    try:
        return f"{float(value) * 100.0:.2f}%"
    except Exception:
        return "РЅРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РґР°РЅРЅС‹С…"


def _safe_text(value: Any) -> str:
    text = str(value or "").strip()
    return text.replace("|", "/")


def _split_problem_types(problem_rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {
        "no_orders_with_stock": [],
        "high_cancellation_share": [],
        "high_drr": [],
        "bad_price_index_on_selling": [],
    }
    for row in problem_rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get("type") or "")
        if key in out:
            out[key].append(row)
    return out


def _build_actions(facts: dict[str, Any]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []

    top_a = ((facts.get("abc_like_summary") or {}).get("top_a") or [])[:5]
    problems = _split_problem_types(facts.get("problem_sku") or [])

    bad_price = [str(x.get("label") or "").strip() for x in problems.get("bad_price_index_on_selling") or [] if str(x.get("label") or "").strip()][:5]
    if bad_price:
        actions.append(
            {
                "priority": "P0",
                "action": f"РџРµСЂРµСЃРјРѕС‚СЂРµС‚СЊ С†РµРЅС‹ РїРѕ SKU СЃ РЅРµРІС‹РіРѕРґРЅС‹Рј РёРЅРґРµРєСЃРѕРј: {', '.join(bad_price)}.",
                "why": "Р§Р°СЃС‚СЊ РїСЂРѕРґР°СЋС‰РёС… SKU РёРјРµРµС‚ СЂРёСЃРє РїРѕ С†РµРЅРµ Рё РјР°СЂР¶Рµ.",
            }
        )

    if top_a:
        actions.append(
            {
                "priority": "P0",
                "action": f"РЎС„РѕРєСѓСЃРёСЂРѕРІР°С‚СЊ Р°СЃСЃРѕСЂС‚РёРјРµРЅС‚ Рё РѕРїРµСЂР°С†РёРѕРЅРЅРѕРµ РІРЅРёРјР°РЅРёРµ РЅР° РіСЂСѓРїРїРµ A: {', '.join(top_a)}.",
                "why": "Р­С‚Рё С‚РѕРІР°СЂС‹ С„РѕСЂРјРёСЂСѓСЋС‚ РѕСЃРЅРѕРІРЅСѓСЋ РґРѕР»СЋ РІС‹СЂСѓС‡РєРё.",
            }
        )

    high_cancel = [str(x.get("label") or "").strip() for x in problems.get("high_cancellation_share") or [] if str(x.get("label") or "").strip()][:5]
    if high_cancel:
        actions.append(
            {
                "priority": "P1",
                "action": f"РџСЂРѕРІРµСЂРёС‚СЊ РїСЂРёС‡РёРЅС‹ РѕС‚РјРµРЅ РїРѕ SKU: {', '.join(high_cancel)}.",
                "why": "Р’С‹СЃРѕРєР°СЏ РґРѕР»СЏ РѕС‚РјРµРЅ СЃРЅРёР¶Р°РµС‚ СЂРµР°Р»СЊРЅС‹Р№ РѕР±РѕСЂРѕС‚ Рё РІС‹РєСѓРї.",
            }
        )

    high_drr = [str(x.get("label") or "").strip() for x in problems.get("high_drr") or [] if str(x.get("label") or "").strip()][:5]
    if high_drr:
        actions.append(
            {
                "priority": "P1",
                "action": f"Р Р°Р·РѕР±СЂР°С‚СЊ СЌС„С„РµРєС‚РёРІРЅРѕСЃС‚СЊ РїСЂРѕРґРІРёР¶РµРЅРёСЏ РїРѕ SKU СЃ РІС‹СЃРѕРєРёРј Р”Р Р : {', '.join(high_drr)}.",
                "why": "Р•СЃС‚СЊ СЂРёСЃРє РЅРµСЌС„С„РµРєС‚РёРІРЅРѕРіРѕ СЂР°СЃС…РѕРґРѕРІР°РЅРёСЏ Р±СЋРґР¶РµС‚Р° РїСЂРѕРґРІРёР¶РµРЅРёСЏ.",
            }
        )

    no_orders_with_stock = [str(x.get("label") or "").strip() for x in problems.get("no_orders_with_stock") or [] if str(x.get("label") or "").strip()][:7]
    if no_orders_with_stock:
        actions.append(
            {
                "priority": "P1",
                "action": f"РџСЂРѕРІРµСЃС‚Рё СЂРµРІРёР·РёСЋ С…РІРѕСЃС‚Р° Р°СЃСЃРѕСЂС‚РёРјРµРЅС‚Р° (Р±РµР· Р·Р°РєР°Р·РѕРІ РїСЂРё РЅР°Р»РёС‡РёРё РѕСЃС‚Р°С‚РєР°): {', '.join(no_orders_with_stock)}.",
                "why": "РќРµР»РёРєРІРёРґ СЃРІСЏР·С‹РІР°РµС‚ РѕСЃС‚Р°С‚РєРё Рё РЅРµ СѓС‡Р°СЃС‚РІСѓРµС‚ РІ РѕР±РѕСЂРѕС‚Рµ.",
            }
        )

    if not actions:
        actions.append(
            {
                "priority": "P1",
                "action": "РЎРѕР±СЂР°С‚СЊ СЂР°СЃС€РёСЂРµРЅРЅС‹Р№ РїР°РєРµС‚ РґР°РЅРЅС‹С… (С„РёРЅР°РЅСЃС‹, СЂРµРєР»Р°РјР°, РїРѕР»РЅС‹Рµ РѕСЃС‚Р°С‚РєРё, unit-СЌРєРѕРЅРѕРјРёРєР°).",
                "why": "РџРѕ РѕРґРЅРѕРјСѓ С„Р°Р№Р»Сѓ РІС‹РІРѕРґС‹ РѕРіСЂР°РЅРёС‡РµРЅС‹ Рё С‚СЂРµР±СѓСЋС‚ РїСЂРѕРІРµСЂРєРё РЅР° РїРѕР»РЅРѕРј РєРѕРЅС‚СѓСЂРµ.",
            }
        )
    return actions


def build_ozon_report(facts: dict[str, Any]) -> dict[str, Any]:
    summary = facts.get("summary") or {}
    top_sku = facts.get("top_sku") or []
    problem_rows = facts.get("problem_sku") or []
    assortment = facts.get("assortment_summary") or {}
    price_index = facts.get("price_index_summary") or {}
    promo = facts.get("promotion_summary") or {}
    abc_like = facts.get("abc_like_summary") or {}
    period_hint = facts.get("period_hint") or {}
    quality = facts.get("data_quality") or {}

    problem_groups = _split_problem_types(problem_rows)
    actions = _build_actions(facts)

    lines: list[str] = []
    lines.append("# Р­РєСЃРїСЂРµСЃСЃ-Р°СѓРґРёС‚ Ozon")
    lines.append("")

    lines.append("## РћРіСЂР°РЅРёС‡РµРЅРёРµ РґР°РЅРЅС‹С…")
    lines.append("- РђРЅР°Р»РёР· РІС‹РїРѕР»РЅРµРЅ РЅР° РѕСЃРЅРѕРІРµ РѕРґРЅРѕРіРѕ С„Р°Р№Р»Р°.")
    lines.append("- Р’С‹РІРѕРґС‹ РїСЂРµРґРІР°СЂРёС‚РµР»СЊРЅС‹Рµ.")
    lines.append("- Р”Р»СЏ РїРѕР»РЅРѕРіРѕ Р°СѓРґРёС‚Р° РЅСѓР¶РЅС‹ С„РёРЅР°РЅСЃС‹, СЂРµРєР»Р°РјР°, РѕСЃС‚Р°С‚РєРё Рё unit-СЌРєРѕРЅРѕРјРёРєР° (РµСЃР»Рё РёС… РЅРµС‚ РѕС‚РґРµР»СЊРЅРѕ).")
    lines.append("")

    lines.append("## РџРµСЂРёРѕРґ")
    if str(period_hint.get("status") or "") == "ok" and str(period_hint.get("label") or ""):
        lines.append(f"- {period_hint.get('label')}")
    else:
        lines.append("- РїРµСЂРёРѕРґ РЅРµ СЂР°СЃРїРѕР·РЅР°РЅ Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРё")
    lines.append("")

    lines.append("## Р“Р»Р°РІРЅС‹Рµ РїРѕРєР°Р·Р°С‚РµР»Рё")
    lines.append(f"- SKU: {_fmt_int(summary.get('sku_count'))}")
    lines.append(f"- SKU СЃ Р·Р°РєР°Р·Р°РјРё: {_fmt_int(summary.get('sku_with_orders_count'))}")
    lines.append(f"- SKU Р±РµР· Р·Р°РєР°Р·РѕРІ: {_fmt_int(summary.get('sku_without_orders_count'))}")
    lines.append(f"- Р—Р°РєР°Р·С‹: {_fmt_int(summary.get('total_orders'))}")
    lines.append(f"- Р’С‹СЂСѓС‡РєР°: {_fmt_money(summary.get('total_revenue'))}")
    if quality.get("has_buyouts"):
        lines.append(f"- Р’С‹РєСѓРї: {_fmt_int(summary.get('total_buyouts'))}")
    if quality.get("has_cancellations"):
        lines.append(f"- РћС‚РјРµРЅС‹: {_fmt_int(summary.get('total_cancellations'))}")
    if quality.get("has_stock"):
        lines.append(f"- РћСЃС‚Р°С‚РѕРє: {_fmt_int(summary.get('total_stock'))}")
    lines.append("")

    lines.append("## РљР»СЋС‡РµРІС‹Рµ РІС‹РІРѕРґС‹")
    top10_share = assortment.get("top_10_revenue_share_pct")
    if top10_share is not None:
        if float(top10_share) >= 85:
            lines.append("- РџСЂРѕРґР°Р¶Рё СЃРёР»СЊРЅРѕ СЃРѕСЃСЂРµРґРѕС‚РѕС‡РµРЅС‹ РІ РѕРіСЂР°РЅРёС‡РµРЅРЅРѕРј С‡РёСЃР»Рµ SKU.")
        elif float(top10_share) >= 65:
            lines.append("- РџСЂРѕРґР°Р¶Рё СѓРјРµСЂРµРЅРЅРѕ СЃРѕСЃСЂРµРґРѕС‚РѕС‡РµРЅС‹ РІ РІРµСЂС…РЅРµР№ С‡Р°СЃС‚Рё Р°СЃСЃРѕСЂС‚РёРјРµРЅС‚Р°.")
        else:
            lines.append("- Р’С‹СЂСѓС‡РєР° СЂР°СЃРїСЂРµРґРµР»РµРЅР° РѕС‚РЅРѕСЃРёС‚РµР»СЊРЅРѕ СЂР°РІРЅРѕРјРµСЂРЅРѕ РїРѕ Р°СЃСЃРѕСЂС‚РёРјРµРЅС‚Сѓ.")

    sku_count = summary.get("sku_count")
    sku_without = summary.get("sku_without_orders_count")
    if sku_count is not None and sku_without is not None and int(sku_count or 0) > 0:
        ratio = float(sku_without) / float(sku_count)
        if ratio >= 0.5:
            lines.append("- Р‘РѕР»СЊС€Р°СЏ С‡Р°СЃС‚СЊ Р°СЃСЃРѕСЂС‚РёРјРµРЅС‚Р° РЅРµ СѓС‡Р°СЃС‚РІСѓРµС‚ РІ РѕР±РѕСЂРѕС‚Рµ (orders <= 0).")
        elif ratio >= 0.25:
            lines.append("- РЎСѓС‰РµСЃС‚РІРµРЅРЅР°СЏ С‡Р°СЃС‚СЊ Р°СЃСЃРѕСЂС‚РёРјРµРЅС‚Р° РёРјРµРµС‚ РЅСѓР»РµРІС‹Рµ РїСЂРѕРґР°Р¶Рё.")

    unprofitable_count = int(price_index.get("unprofitable") or 0)
    total_price_rows = sum(int(price_index.get(k) or 0) for k in ("super_profitable", "profitable", "neutral", "unprofitable"))
    if total_price_rows > 0 and unprofitable_count > 0:
        lines.append("- РЈ С‡Р°СЃС‚Рё SKU РёРЅРґРµРєСЃ С†РµРЅС‹ РЅРµРІС‹РіРѕРґРЅС‹Р№, СЌС‚Рѕ РѕРіСЂР°РЅРёС‡РёРІР°РµС‚ СЂРµР·СѓР»СЊС‚Р°С‚ РїСЂРѕРґР°СЋС‰РёС… РєР°СЂС‚РѕС‡РµРє.")

    promoted = promo.get("promoted_sku_count")
    if promoted is not None:
        if int(promoted) <= 0:
            lines.append("- РџСЂРѕРґРІРёР¶РµРЅРёРµ РІ С„Р°Р№Р»Рµ РЅРµ РІС‹СЂР°Р¶РµРЅРѕ РёР»Рё РЅРµ Р·Р°РїРѕР»РЅРµРЅРѕ.")
        else:
            lines.append("- РџСЂРѕРґРІРёР¶РµРЅРёРµ РёСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ С‚РѕС‡РµС‡РЅРѕ, РµСЃС‚СЊ Р·РѕРЅР° РґР»СЏ РїРѕРІС‹С€РµРЅРёСЏ СЌС„С„РµРєС‚РёРІРЅРѕСЃС‚Рё.")

    if problem_groups.get("high_cancellation_share"):
        lines.append("- Р•СЃС‚СЊ SKU СЃ СЂРёСЃРєРѕРј РїРѕ РѕС‚РјРµРЅР°Рј, СЌС‚Рѕ СЃРЅРёР¶Р°РµС‚ РґРѕР»СЋ РІС‹РєСѓРїР° Рё РёС‚РѕРіРѕРІСѓСЋ РІС‹СЂСѓС‡РєСѓ.")

    strong_cards = [str(x.get("label") or "").strip() for x in top_sku[:3] if str(x.get("label") or "").strip()]
    if strong_cards:
        lines.append(f"- Р•СЃС‚СЊ СЃРёР»СЊРЅС‹Рµ РєР°СЂС‚РѕС‡РєРё, РЅР° РєРѕС‚РѕСЂС‹С… РґРµСЂР¶РёС‚СЃСЏ РѕР±РѕСЂРѕС‚: {', '.join(strong_cards)}.")
    if len(lines) > 0 and lines[-1] == "## РљР»СЋС‡РµРІС‹Рµ РІС‹РІРѕРґС‹":
        lines.append("- РќРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РґР°РЅРЅС‹С… РґР»СЏ СѓРІРµСЂРµРЅРЅС‹С… РІС‹РІРѕРґРѕРІ.")
    lines.append("")

    lines.append("## РўРѕРї SKU")
    if top_sku:
        lines.append("| SKU / РўРѕРІР°СЂ | Р—Р°РєР°Р·С‹ | Р’С‹СЂСѓС‡РєР° | РћСЃС‚Р°С‚РѕРє |")
        lines.append("| --- | ---: | ---: | ---: |")
        for row in top_sku[:10]:
            label = _safe_text(row.get("label") or row.get("sku") or row.get("name") or "")
            if not label:
                continue
            lines.append(
                "| "
                + " | ".join(
                    [
                        label,
                        _fmt_int(row.get("orders")),
                        _fmt_money(row.get("revenue")),
                        _fmt_int(row.get("stock")),
                    ]
                )
                + " |"
            )
    else:
        lines.append("- РќРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РґР°РЅРЅС‹С… РґР»СЏ РїРѕСЃС‚СЂРѕРµРЅРёСЏ top-10.")
    lines.append("")

    lines.append("## РџСЂРѕР±Р»РµРјРЅС‹Рµ SKU")
    if problem_groups.get("no_orders_with_stock"):
        lines.append("### Р‘РµР· Р·Р°РєР°Р·РѕРІ, РЅРѕ СЃ РѕСЃС‚Р°С‚РєРѕРј")
        for row in problem_groups.get("no_orders_with_stock")[:10]:
            lines.append(f"- {_safe_text(row.get('label'))}: Р·Р°РєР°Р·С‹={_fmt_int(row.get('orders'))}, РѕСЃС‚Р°С‚РѕРє={_fmt_int(row.get('stock'))}")

    if problem_groups.get("high_cancellation_share"):
        lines.append("### Р’С‹СЃРѕРєР°СЏ РґРѕР»СЏ РѕС‚РјРµРЅ")
        for row in problem_groups.get("high_cancellation_share")[:10]:
            lines.append(f"- {_safe_text(row.get('label'))}: РѕС‚РјРµРЅС‹={_fmt_int(row.get('cancellations'))}, РґРѕР»СЏ={_fmt_pct(row.get('cancel_share_pct'))}")

    if problem_groups.get("high_drr"):
        lines.append("### Р’С‹СЃРѕРєРёР№ Р”Р Р ")
        for row in problem_groups.get("high_drr")[:10]:
            lines.append(f"- {_safe_text(row.get('label'))}: Р”Р Р ={_fmt_pct(row.get('drr_pct'))}")

    if problem_groups.get("bad_price_index_on_selling"):
        lines.append("### РџР»РѕС…РѕР№ РёРЅРґРµРєСЃ С†РµРЅС‹ СЃСЂРµРґРё РїСЂРѕРґР°СЋС‰РёС…")
        for row in problem_groups.get("bad_price_index_on_selling")[:10]:
            lines.append(f"- {_safe_text(row.get('label'))}: Р·Р°РєР°Р·С‹={_fmt_int(row.get('orders'))}")

    if not any(problem_groups.values()):
        lines.append("- РЇРІРЅС‹Рµ РїСЂРѕР±Р»РµРјРЅС‹Рµ SKU РїРѕ С‚РµРєСѓС‰РёРј СЃРёРіРЅР°Р»Р°Рј РЅРµ РІС‹СЏРІР»РµРЅС‹ РёР»Рё РЅРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РґР°РЅРЅС‹С….")
    lines.append("")

    lines.append("## Р¦РµРЅР° Рё РїСЂРѕРґРІРёР¶РµРЅРёРµ")
    if total_price_rows > 0:
        lines.append(
            "- РРЅРґРµРєСЃ С†РµРЅС‹: "
            f"super-РІС‹РіРѕРґРЅС‹Р№={_fmt_int(price_index.get('super_profitable'))}, "
            f"РІС‹РіРѕРґРЅС‹Р№={_fmt_int(price_index.get('profitable'))}, "
            f"РЅРµР№С‚СЂР°Р»СЊРЅС‹Р№={_fmt_int(price_index.get('neutral'))}, "
            f"РЅРµРІС‹РіРѕРґРЅС‹Р№={_fmt_int(price_index.get('unprofitable'))}."
        )
    else:
        lines.append("- РРЅРґРµРєСЃ С†РµРЅС‹: РЅРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РґР°РЅРЅС‹С….")

    if promo:
        lines.append(f"- SKU СЃ РїСЂРѕРґРІРёР¶РµРЅРёРµРј: {_fmt_int(promo.get('promoted_sku_count'))}")
        lines.append(f"- SKU СЃ Р”Р Р : {_fmt_int(promo.get('sku_with_drr_count'))}")
        lines.append(f"- РЎСЂРµРґРЅРёР№ Р”Р Р : {_fmt_ratio_pct(promo.get('avg_drr'))}")
        lines.append(f"- РњР°РєСЃРёРјР°Р»СЊРЅС‹Р№ Р”Р Р : {_fmt_ratio_pct(promo.get('max_drr'))}")
        top_drr = promo.get("top_drr_sku") or []
        if top_drr:
            labels = [str(x.get("label") or "").strip() for x in top_drr if str(x.get("label") or "").strip()]
            if labels:
                lines.append(f"- РўРѕРї SKU РїРѕ Р”Р Р : {', '.join(labels[:5])}.")
    else:
        lines.append("- Р”Р°РЅРЅС‹Рµ РїРѕ РїСЂРѕРґРІРёР¶РµРЅРёСЋ РѕС‚СЃСѓС‚СЃС‚РІСѓСЋС‚.")
    lines.append("")

    lines.append("## Р РµРєРѕРјРµРЅРґР°С†РёРё")
    for action in actions:
        lines.append(f"- [{action.get('priority')}] {action.get('action')} ({action.get('why')})")
    lines.append("")

    lines.append("## Р”РёР°РіРЅРѕСЃС‚РёРєР°")
    lines.append(f"- Р’С‹Р±СЂР°РЅ Р»РёСЃС‚: {_safe_text(facts.get('chosen_sheet') or 'РЅРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РґР°РЅРЅС‹С…')}")
    lines.append(f"- Р’С‹Р±СЂР°РЅ header_row: {_safe_text(facts.get('chosen_header_row') if facts.get('chosen_header_row') is not None else 'РЅРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РґР°РЅРЅС‹С…')}")
    lines.append(f"- РЎС‚СЂРѕРє РїРѕСЃР»Рµ РЅРѕСЂРјР°Р»РёР·Р°С†РёРё: {_fmt_int(facts.get('row_count'))}")

    detected = facts.get("detected_columns") or {}
    lines.append("- Р Р°СЃРїРѕР·РЅР°РЅРЅС‹Рµ РєРѕР»РѕРЅРєРё:")
    for key in ("sku", "product_name", "orders", "revenue", "buyouts", "cancellations", "stock", "price_index", "drr"):
        lines.append(f"  - {key}: {_safe_text(detected.get(key) or 'РЅ/Рґ')}")
    lines.append("")

    return {
        "pdf_markdown": "\n".join(lines).strip() + "\n",
        "actions": actions,
    }
