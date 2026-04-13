"""Markdown renderer for file-based audit mode."""

from __future__ import annotations

import datetime as dt
import re
from typing import Any


def _to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _to_float_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _to_int(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        return int(float(value))
    except Exception:
        return 0


def _money(value: Any) -> str:
    number = _to_float(value)
    if number is None:
        return "н/д"
    return f"{number:,.2f} RUB".replace(",", " ")


def _pct_ratio(value: Any) -> str:
    number = _to_float(value)
    if number is None:
        return "н/д"
    return f"{number * 100:.2f}%"


def _fmt_pct(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "н/д"
    token = f"{value:.{digits}f}".rstrip("0").rstrip(".")
    return f"{token}%"



def _icon_green() -> str:
    return "\U0001F7E2"


def _icon_yellow() -> str:
    return "\U0001F7E1"


def _icon_red() -> str:
    return "\U0001F534"


def _icon_warn() -> str:
    return "\u26A0\ufe0f"


def _icon_point() -> str:
    return "\U0001F449"


def _status_icon(level: str) -> str:
    key = _text(level).lower()
    if key == "green":
        return _icon_green()
    if key == "yellow":
        return _icon_yellow()
    if key == "red":
        return _icon_red()
    return _icon_warn()


def _profit_status_level(profit: Any) -> str:
    value = _to_float(profit)
    if value is None:
        return "yellow"
    if value < 0:
        return "red"
    if value > 0:
        return "green"
    return "yellow"


def _margin_status_level_by_pct(margin_pct: Any) -> str:
    value = _to_float(margin_pct)
    if value is None:
        return "yellow"
    if value > 50.0:
        return "green"
    if value >= 30.0:
        return "yellow"
    return "red"


def _drr_status_level_by_pct(drr_pct: Any) -> str:
    value = _to_float(drr_pct)
    if value is None:
        return "yellow"
    if value < 10.0:
        return "green"
    if value > 20.0:
        return "red"
    return "yellow"


def _roas_status_level(value: Any) -> str:
    roas = _to_float(value)
    if roas is None:
        return "yellow"
    if roas > 5.0:
        return "green"
    if roas < 3.0:
        return "red"
    return "yellow"


def _ctr_benchmark_text(ctr_ratio: Any) -> str:
    ctr = _to_float(ctr_ratio)
    if ctr is None:
        return "CTR: н/д (норма: 1.5–3%)."
    ctr_pct = float(ctr) * 100.0
    if ctr_pct < 1.5:
        return f"CTR: {ctr_pct:.2f}% (ниже нормы: <1.5% — низкий уровень)."
    if ctr_pct <= 3.0:
        return f"CTR: {ctr_pct:.2f}% (норма 1.5–3% — средний уровень)."
    return f"CTR: {ctr_pct:.2f}% (>3% — хороший уровень)."


def _drr_benchmark_text(drr_ratio: Any) -> str:
    drr = _to_float(drr_ratio)
    if drr is None:
        return "ДРР: н/д (ориентир: <10% отлично, 10–20% нормально, >20% риск)."
    drr_pct = float(drr) * 100.0
    if drr_pct < 10.0:
        return f"ДРР: {drr_pct:.2f}% (<10% — отлично)."
    if drr_pct <= 20.0:
        return f"ДРР: {drr_pct:.2f}% (10–20% — нормально)."
    return f"ДРР: {drr_pct:.2f}% (>20% — риск)."


def _roas_benchmark_text(roas_value: Any) -> str:
    roas = _to_float(roas_value)
    if roas is None:
        return "ROAS: н/д (ориентир: <3 слабый, 3–5 нормальный, >5 хороший)."
    if roas < 3.0:
        return f"ROAS: {roas:.2f} (<3 — слабый)."
    if roas <= 5.0:
        return f"ROAS: {roas:.2f} (3–5 — нормальный)."
    return f"ROAS: {roas:.2f} (>5 — хороший)."


def _risk_status_level(value: Any) -> str:
    key = _text(value).lower()
    if key == "high":
        return "red"
    if key == "medium":
        return "yellow"
    if key == "low":
        return "green"
    return "yellow"


def _chunked_list(items: list[Any], size: int) -> list[list[Any]]:
    out: list[list[Any]] = []
    if size <= 0:
        return out
    for i in range(0, len(items), size):
        out.append(items[i : i + size])
    return out


def _append_kpi_cards(
    lines: list[str],
    cards: list[dict[str, Any]],
    *,
    columns: int = 4,
) -> None:
    normalized = [c for c in cards if isinstance(c, dict) and _text(c.get("title")) and _text(c.get("value"))]
    if not normalized:
        return
    for chunk in _chunked_list(normalized, columns):
        headers = [f"[ {_text(card.get('title'))} ]" for card in chunk]
        values = [
            f"**{_text(card.get('value'))}** {str(card.get('icon') or '').strip()}".strip()
            for card in chunk
        ]
        _append_markdown_table(lines, headers, [values], align_right=set(range(len(values))))

def _contains_cyrillic(text: str) -> bool:
    return bool(re.search(r"[А-Яа-яЁё]", text))


def _bad_marker_count(text: str) -> int:
    markers = (
        "РџС",
        "РЎ",
        "Р ",
        "СЃ",
        "вЂ",
        "Ð",
        "Ñ",
    )
    return sum(text.count(marker) for marker in markers)


def _looks_like_mojibake(text: str) -> bool:
    if not text:
        return False
    if _bad_marker_count(text) > 0:
        cyrillic_letters = re.findall(r"[А-Яа-яЁё]", text)
        if not cyrillic_letters:
            return True
        rs_letters = sum(1 for ch in cyrillic_letters if ch.lower() in {"р", "с"})
        diversity = len({ch.lower() for ch in cyrillic_letters})
        return diversity <= 8 or (rs_letters / max(len(cyrillic_letters), 1)) >= 0.45
    return False


def _repair_text(text: str) -> str:
    if not text or text.isascii():
        return text
    # Keep valid Cyrillic text untouched.
    cyr = re.findall(r"[А-Яа-яЁё]", text)
    if cyr:
        diversity = len({ch.lower() for ch in cyr})
        rs_letters = sum(1 for ch in cyr if ch.lower() in {"р", "с"})
        if diversity >= 10 and (rs_letters / max(len(cyr), 1)) < 0.35:
            return text
    if not _looks_like_mojibake(text):
        return text

    best = text
    best_bad = _bad_marker_count(text)
    for source_codec in ("cp1251", "latin1", "cp1252"):
        try:
            candidate = text.encode(source_codec, errors="strict").decode("utf-8", errors="strict")
        except Exception:
            continue
        if candidate == text:
            continue
        candidate_bad = _bad_marker_count(candidate)
        if candidate_bad < best_bad:
            best = candidate
            best_bad = candidate_bad
            continue
        if _contains_cyrillic(candidate) and not _looks_like_mojibake(candidate):
            best = candidate
            best_bad = candidate_bad
    return best


def _text(value: Any) -> str:
    if value is None:
        return ""
    return _repair_text(str(value)).strip()


def _kpi_state_text(*, profit: float, margin: float, profit_without_cogs: bool) -> str:
    profit = float(profit or 0.0)
    margin = float(margin or 0.0)

    if profit_without_cogs:
        if profit < 0:
            return (
                "Предварительный чистый убыток без COGS (с учетом рекламы): "
                f"{_money(profit)}, маржа: {_pct_ratio(margin)}."
            )
        if profit > 0:
            return (
                "Предварительная чистая прибыль без COGS (с учетом рекламы): "
                f"{_money(profit)}, маржа: {_pct_ratio(margin)}."
            )
        return f"Нулевая предварительная чистая прибыль без COGS (с учетом рекламы), маржа: {_pct_ratio(margin)}."

    if profit < 0:
        return f"Чистый убыток: {_money(profit)}, маржа: {_pct_ratio(margin)}."
    if profit > 0:
        return f"Чистая прибыль: {_money(profit)}, маржа: {_pct_ratio(margin)}."
    return f"Нулевая чистая прибыль, маржа: {_pct_ratio(margin)}."


def _expense_component_label(component: str) -> str:
    mapping = {
        "logistics": "Логистика",
        "commission": "Комиссия WB",
        "tax": "Налог",
        "storage": "Хранение",
        "penalties": "Штрафы",
        "cogs_total": "Себестоимость",
    }
    return mapping.get(component, component)


def _share_of_revenue(amount: float | None, revenue: float | None) -> str:
    if amount is None or revenue is None or revenue <= 0:
        return "н/д"
    return _fmt_pct((amount / revenue) * 100.0, digits=1)


def _money_or_label(
    amount: Any,
    *,
    threshold: float = 100.0,
    low_label: str = "нет значимых потерь",
) -> str:
    value = _to_float(amount)
    if value is None:
        return "н/д"
    if abs(float(value)) < float(threshold):
        return low_label
    return _money(value)


def _loss_reasons_human(decision: dict[str, Any], finance: dict[str, Any]) -> list[str]:
    reasons = decision.get("reasons_of_loss") or []
    revenue = _to_float(finance.get("gross_revenue"))
    lines: list[str] = []

    for item in reasons:
        reason_text = _text((item or {}).get("reason"))
        numbers = (item or {}).get("numbers") if isinstance((item or {}).get("numbers"), dict) else {}
        reason_norm = reason_text.lower()

        if reason_norm.startswith("высокий расход:"):
            component = reason_norm.split(":", 1)[1].strip()
            amount = _to_float(numbers.get("amount"))
            share = _share_of_revenue(amount, revenue)
            label = _expense_component_label(component)
            line = f"{label} составляет {_money(amount)} (~{share} от выручки)"
            if component == "logistics":
                line += " - значительная доля затрат."
            else:
                line += "."
            lines.append(line)
            continue

        if numbers.get("profit_without_cogs") or "без cogs" in reason_norm:
            lines.append(
                "Показатель прибыли рассчитан без учета себестоимости - фактическая чистая прибыль может быть ниже."
            )
            continue

        if "выручка по funnel и finance" in reason_norm:
            fin_rev = _to_float(numbers.get("finance_gross_revenue"))
            funnel_rev = _to_float(numbers.get("funnel_revenue_buyouts"))
            rel_diff = _to_float(numbers.get("relative_diff"))
            if fin_rev is not None and funnel_rev is not None:
                details = f" ({_money(fin_rev)} vs {_money(funnel_rev)})"
                if rel_diff is not None:
                    details += f", расхождение ~{_fmt_pct(rel_diff * 100.0, 1)}"
                lines.append(
                    "Выручка по данным WB finance и воронки расходится"
                    f"{details} - возможна ошибка периода или неполные файлы."
                )
            else:
                lines.append("Выручка по данным WB finance и воронки расходится - проверьте период и полноту файлов.")
            continue

        clean_reason = reason_text.rstrip(".")
        if clean_reason:
            lines.append(f"{clean_reason}.")

    if not lines:
        lines.append("Критичные причины потери прибыли не выявлены по текущим данным.")
    return lines


def _extract_funnel_impressions(facts: dict[str, Any], funnel: dict[str, Any]) -> int | None:
    candidates = [
        funnel.get("impressions"),
        funnel.get("shows"),
        funnel.get("show_count"),
    ]
    for value in candidates:
        parsed = _to_int(value)
        if parsed > 0:
            return parsed

    raw_rows = facts.get("funnel_raw")
    if not isinstance(raw_rows, list):
        return None

    total = 0
    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        total += max(
            _to_int(row.get("impressions"))
            or _to_int(row.get("shows"))
            or _to_int(row.get("showCount"))
            or 0,
            0,
        )
    if total > 0:
        return total

    ads_summary = facts.get("ads_summary") if isinstance(facts.get("ads_summary"), dict) else {}
    ads_impressions = _to_int(ads_summary.get("impressions"))
    return ads_impressions if ads_impressions > 0 else None


def _funnel_ctr_conclusion(ctr_ratio: Any) -> str:
    ctr = _to_float(ctr_ratio)
    if ctr is None:
        return "н/д (нет данных о показах)"
    ctr_pct = float(ctr) * 100.0
    if ctr_pct < 1.0:
        return "Низкий CTR — проблема в рекламе или обложке"
    if ctr_pct <= 3.0:
        return "CTR в норме"
    return "Хороший CTR — трафик качественный"


def _kpi_management_insights(
    *,
    decision: dict[str, Any],
    search: dict[str, Any],
    funnel: dict[str, Any],
    profit_view: dict[str, Any],
) -> list[str]:
    insights: list[str] = []

    leak_spend = _to_float(search.get("total_leak_spend"))
    if leak_spend is None or leak_spend <= 0:
        leak_spend = sum(
            _to_float(item.get("spend")) or 0.0
            for item in (decision.get("ads_leaks") or [])
            if isinstance(item, dict) and (_to_int(item.get("orders")) == 0) and (_to_float(item.get("spend")) or 0.0) > 0
        )
    if (leak_spend or 0.0) > 0:
        insights.append("\u0420\u0435\u043a\u043b\u0430\u043c\u0430 \u0441\u043b\u0438\u0432\u0430\u0435\u0442 \u0431\u044e\u0434\u0436\u0435\u0442: \u0435\u0441\u0442\u044c \u0440\u0430\u0441\u0445\u043e\u0434 \u0431\u0435\u0437 \u0437\u0430\u043a\u0430\u0437\u043e\u0432.")

    growth_hypotheses = search.get("growth_hypotheses") if isinstance(search.get("growth_hypotheses"), list) else []
    effective = search.get("effective") if isinstance(search.get("effective"), list) else []
    if growth_hypotheses:
        insights.append(
            "\u0415\u0441\u0442\u044c \u0441\u043f\u0440\u043e\u0441 \u0432 \u043f\u043e\u0438\u0441\u043a\u0435 \u0431\u0435\u0437 \u0440\u0435\u043a\u043b\u0430\u043c\u044b: \u0437\u0430\u043f\u0440\u043e\u0441\u044b \u0441 \u0432\u044b\u0441\u043e\u043a\u0438\u043c CTR \u0441\u0442\u043e\u0438\u0442 \u043f\u0440\u043e\u0442\u0435\u0441\u0442\u0438\u0440\u043e\u0432\u0430\u0442\u044c."
        )
    elif effective:
        insights.append("\u0415\u0441\u0442\u044c \u0442\u043e\u0447\u043a\u0438 \u0440\u043e\u0441\u0442\u0430 \u0432 \u043f\u043e\u0438\u0441\u043a\u0435: \u044d\u0444\u0444\u0435\u043a\u0442\u0438\u0432\u043d\u044b\u0435 \u0437\u0430\u043f\u0440\u043e\u0441\u044b \u043c\u043e\u0436\u043d\u043e \u043c\u0430\u0441\u0448\u0442\u0430\u0431\u0438\u0440\u043e\u0432\u0430\u0442\u044c.")

    impressions = _to_int(funnel.get("impressions"))
    clicks = _to_int(funnel.get("views"))
    ctr_ratio = _to_float(funnel.get("ctr"))
    if ctr_ratio is None and impressions > 0:
        ctr_ratio = float(clicks) / float(impressions)

    orders = _to_int(funnel.get("orders"))
    cr_click_to_order = (float(orders) / float(clicks)) if clicks > 0 else None

    if ctr_ratio is not None and ctr_ratio >= 0.03:
        if cr_click_to_order is not None and cr_click_to_order < 0.02:
            insights.append("\u0421\u043f\u0440\u043e\u0441 \u0435\u0441\u0442\u044c (CTR \u0432\u044b\u0441\u043e\u043a\u0438\u0439), \u043d\u043e \u0437\u0430\u043a\u0430\u0437\u043e\u0432 \u043c\u0430\u043b\u043e \u2014 \u043f\u0440\u043e\u0431\u043b\u0435\u043c\u0430 \u0432 \u043a\u0430\u0440\u0442\u043e\u0447\u043a\u0435.")
        else:
            insights.append("\u0421\u043f\u0440\u043e\u0441 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d: CTR \u0432\u044b\u0448\u0435 \u043d\u043e\u0440\u043c\u044b.")
    elif cr_click_to_order is not None and cr_click_to_order < 0.02:
        insights.append("\u041a\u043e\u043d\u0432\u0435\u0440\u0441\u0438\u044f \u0432 \u0437\u0430\u043a\u0430\u0437 \u043d\u0438\u0437\u043a\u0430\u044f \u2014 \u043d\u0443\u0436\u043d\u043e \u0443\u0441\u0438\u043b\u0438\u0442\u044c \u043a\u0430\u0440\u0442\u043e\u0447\u043a\u0443.")

    if len(insights) < 2:
        clean_profit = _to_float(profit_view.get("clean_profit"))
        clean_margin = _to_float(profit_view.get("clean_margin"))
        if clean_profit is not None and clean_profit < 0:
            insights.append("\u041f\u0440\u0438\u0431\u044b\u043b\u044c \u0432 \u043c\u0438\u043d\u0443\u0441\u0435 \u2014 \u0441\u043d\u0430\u0447\u0430\u043b\u0430 \u043d\u0443\u0436\u043d\u043e \u0441\u043e\u043a\u0440\u0430\u0442\u0438\u0442\u044c \u043f\u043e\u0442\u0435\u0440\u0438.")
        elif clean_margin is not None and clean_margin < 0.3:
            insights.append("\u041c\u0430\u0440\u0436\u0430 \u043d\u0438\u0437\u043a\u0430\u044f \u2014 \u043f\u0440\u0438\u0431\u044b\u043b\u044c \u043f\u043e\u0434 \u0434\u0430\u0432\u043b\u0435\u043d\u0438\u0435\u043c \u0440\u0430\u0441\u0445\u043e\u0434\u043e\u0432.")
        else:
            insights.append("\u041a\u0430\u0431\u0438\u043d\u0435\u0442 \u0441\u0442\u0430\u0431\u0438\u043b\u0435\u043d: \u043c\u043e\u0436\u043d\u043e \u0442\u043e\u0447\u0435\u0447\u043d\u043e \u0443\u0441\u0438\u043b\u0438\u0432\u0430\u0442\u044c \u0440\u0430\u0431\u043e\u0447\u0438\u0435 \u0441\u0432\u044f\u0437\u043a\u0438.")

    if len(insights) < 2:
        insights.append("\u041d\u0443\u0436\u043d\u043e \u0432\u044b\u0440\u0430\u0432\u043d\u0438\u0432\u0430\u0442\u044c \u0432\u043e\u0440\u043e\u043d\u043a\u0443 \u0438 \u0447\u0438\u0441\u0442\u0438\u0442\u044c \u0441\u043b\u0430\u0431\u0443\u044e \u0440\u0435\u043a\u043b\u0430\u043c\u0443.")

    unique: list[str] = []
    seen: set[str] = set()
    for insight in insights:
        key = _text(insight).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(insight)

    return unique[:4]


def _search_sku_label(row: dict[str, Any]) -> str:
    sku = _to_int(row.get("nmId"))
    if sku > 0:
        return str(sku)
    seller_article = _text(row.get("seller_article"))
    if seller_article:
        return seller_article
    return "н/д"


def _search_rk_label(row: dict[str, Any]) -> str:
    rk_keys = (
        "rk",
        "campaign_id",
        "campaignId",
        "advert_id",
        "advertId",
        "ad_id",
        "adId",
        "campaign",
        "campaign_name",
        "campaignName",
    )
    for key in rk_keys:
        value = _text(row.get(key))
        if value:
            return value
    return ""


def _search_cr_ratio(row: dict[str, Any]) -> float | None:
    clicks = _to_int(row.get("clicks"))
    if clicks <= 0:
        return None
    orders = _to_int(row.get("orders"))
    return float(orders) / float(clicks)


def _search_drr_ratio(row: dict[str, Any]) -> float | None:
    spend = _to_float(row.get("spend"))
    revenue = _to_float(row.get("revenue"))
    if spend is None or revenue is None or revenue <= 0:
        return None
    return float(spend) / float(revenue)


def _search_ctr_ratio(row: dict[str, Any]) -> float | None:
    ctr = _to_float(row.get("ctr"))
    if ctr is not None and ctr > 0:
        return ctr
    impressions = _to_int(row.get("impressions"))
    clicks = _to_int(row.get("clicks"))
    if impressions <= 0:
        return None
    return float(clicks) / float(impressions)


def _search_ctr_text(row: dict[str, Any]) -> str:
    ctr = _search_ctr_ratio(row)
    return _fmt_pct((ctr or 0.0) * 100.0, 2) if ctr is not None else "н/д"


def _search_ctr_level(row: dict[str, Any]) -> str:
    ctr = _search_ctr_ratio(row)
    if ctr is None:
        return "CTR н/д"
    ctr_pct = float(ctr) * 100.0
    if ctr_pct < 1.5:
        return "CTR низкий"
    if ctr_pct <= 3.0:
        return "CTR нормальный"
    return "CTR высокий"


def _search_bucket(row: dict[str, Any]) -> str:
    clicks = _to_int(row.get("clicks"))
    add_to_cart = _to_int(row.get("add_to_cart"))
    orders = _to_int(row.get("orders"))
    buyouts = _to_int(row.get("buyouts"))
    spend = _to_float(row.get("spend")) or 0.0
    buyouts_available = row.get("buyouts") not in (None, "")
    cr = _search_cr_ratio(row) or 0.0

    if spend > 0 and orders > 0 and cr > 0 and ((buyouts > 0) if buyouts_available else True):
        return "effective"
    if spend > 0 and clicks > 0 and add_to_cart > 0 and (orders == 0 or cr <= 0.02):
        return "potential"
    if spend > 0 and clicks > 0 and orders == 0:
        return "ineffective"
    if spend > 0 and orders > 0 and cr > 0:
        return "effective"
    return "other"


def _search_conclusion(row: dict[str, Any]) -> str:
    bucket = _search_bucket(row)
    ctr_mark = _search_ctr_level(row)
    if bucket == "effective":
        return f"работает ({ctr_mark})"
    if bucket == "ineffective":
        return f"сливает бюджет ({ctr_mark})"
    if bucket == "potential":
        return f"нужно улучшить карточку ({ctr_mark})"
    return f"данных недостаточно ({ctr_mark})"


def _search_cr_text(row: dict[str, Any]) -> str:
    cr = _search_cr_ratio(row)
    return _fmt_pct(cr * 100.0, 2) if cr is not None else "н/д"


def _search_drr_text(row: dict[str, Any]) -> str:
    drr = _search_drr_ratio(row)
    return _fmt_pct(drr * 100.0, 2) if drr is not None else "н/д"


def _search_margin_before_ads(finance: dict[str, Any]) -> float | None:
    revenue = _to_float(finance.get("gross_revenue"))
    profit_before_ads = _to_float(finance.get("profit"))
    if revenue is None or revenue <= 0 or profit_before_ads is None:
        return None
    return float(profit_before_ads) / float(revenue)


def _search_effective_benchmarks(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    effective = [row for row in rows if isinstance(row, dict) and _search_bucket(row) == "effective"]
    orders = sum(_to_int(row.get("orders")) for row in effective)
    carts = sum(_to_int(row.get("add_to_cart")) for row in effective if _to_int(row.get("add_to_cart")) > 0)
    revenue_total = sum(
        (_to_float(row.get("revenue")) or 0.0)
        for row in effective
        if (_to_float(row.get("revenue")) or 0.0) > 0
    )
    cart_to_order = (float(orders) / float(carts)) if carts > 0 else None
    aov = (float(revenue_total) / float(orders)) if orders > 0 and revenue_total > 0 else None
    return {
        "cart_to_order": cart_to_order,
        "aov": aov,
    }


def _search_money_snapshot(
    row: dict[str, Any],
    *,
    margin_before_ads: float | None,
    cart_to_order: float | None,
    aov: float | None,
) -> dict[str, float | None]:
    spend = _to_float(row.get("spend"))
    revenue_raw = _to_float(row.get("revenue"))
    revenue = revenue_raw if revenue_raw is not None and revenue_raw > 0 else None
    orders = _to_int(row.get("orders"))
    add_to_cart = _to_int(row.get("add_to_cart"))
    bucket = _search_bucket(row)

    potential_revenue: float | None = None
    if (
        bucket == "potential"
        and revenue is None
        and margin_before_ads is not None
        and cart_to_order is not None
        and aov is not None
        and add_to_cart > 0
    ):
        potential_revenue = float(add_to_cart) * float(cart_to_order) * float(aov)

    revenue_for_estimate = revenue if revenue is not None else potential_revenue
    if revenue is None and potential_revenue is not None:
        revenue = potential_revenue

    estimated_profit: float | None = None
    if revenue_for_estimate is not None and margin_before_ads is not None:
        estimated_profit = (float(revenue_for_estimate) * float(margin_before_ads)) - (
            float(spend) if spend is not None else 0.0
        )
    elif orders == 0 and spend is not None and spend > 0:
        estimated_profit = -float(spend)

    drr = (
        (float(spend) / float(revenue_for_estimate))
        if spend is not None and revenue_for_estimate and revenue_for_estimate > 0
        else None
    )
    return {
        "spend": float(spend) if spend is not None else None,
        "revenue": float(revenue) if revenue is not None else None,
        "estimated_profit": float(estimated_profit) if estimated_profit is not None else None,
        "drr": drr,
        "potential_revenue": potential_revenue,
    }


def _search_profit_text(snapshot: dict[str, float | None]) -> str:
    value = snapshot.get("estimated_profit")
    if value is None:
        return "н/д"
    return _money(value)


def _search_has_metric(rows: list[dict[str, Any]], key: str) -> bool:
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get(key) not in (None, ""):
            return True
    return False


def _search_target_labels(rows: list[dict[str, Any]], *, limit: int = 5) -> list[str]:
    labels: list[str] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        query = _text(row.get("query"))
        if not query:
            continue
        sku = _search_sku_label(row)
        key = (query.lower(), sku.lower())
        if key in seen:
            continue
        seen.add(key)
        labels.append(f'"{query}" (SKU {sku})' if sku != "н/д" else f'"{query}"')
        if len(labels) >= limit:
            break
    return labels


def _sanitize_table_cell(value: Any) -> str:
    text = _text(value)
    return text.replace("|", "/")


def _search_rows_for_table(search: dict[str, Any]) -> list[dict[str, Any]]:
    rows = search.get("base_rows") or []
    if not isinstance(rows, list):
        return []
    sorted_rows = sorted(
        [r for r in rows if isinstance(r, dict)],
        key=lambda r: (
            _to_int(r.get("clicks")),
            _to_int(r.get("orders")),
            _to_int(r.get("add_to_cart")),
            _to_int(r.get("impressions")),
        ),
        reverse=True,
    )
    return sorted_rows[:10]


def _file_name(path: Any) -> str:
    text = _text(path)
    if not text:
        return ""
    return text.replace("\\", "/").split("/")[-1]


def _source_file_cell(files: Any) -> str:
    if not isinstance(files, list) or not files:
        return "нет"
    names = [_file_name(item) for item in files if _file_name(item)]
    if not names:
        return "нет"
    if len(names) == 1:
        return names[0]
    return f"{names[0]} (+{len(names) - 1})"


def _period_text(value: Any) -> str:
    if isinstance(value, dict):
        label = _text(value.get("label"))
        days = _to_int(value.get("days"))
        if label and days > 0:
            return f"{label} ({days} дн.)"
        if label:
            return label
    return _text(value)


def _parse_iso_date(value: Any) -> dt.date | None:
    text = _text(value)
    if not text:
        return None
    try:
        return dt.date.fromisoformat(text)
    except Exception:
        return None


def _date_ru(value: Any) -> str:
    parsed = _parse_iso_date(value)
    if parsed is None:
        return _text(value)
    return parsed.strftime("%d.%m.%Y")


def _audit_kind_for_period(date_from: dt.date | None, date_to: dt.date | None) -> str:
    if not date_from or not date_to:
        return "Недельный аудит"
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    days = int((date_to - date_from).days) + 1
    return "Недельный аудит" if days <= 7 else "Периодический аудит"


def _audit_period_view(facts: dict[str, Any]) -> dict[str, Any]:
    period = facts.get("audit_period") if isinstance(facts.get("audit_period"), dict) else {}
    date_from = _text(period.get("date_from"))
    date_to = _text(period.get("date_to"))
    label_ru = _text(period.get("label_ru"))
    audit_kind = _text(period.get("audit_kind"))
    parsed_from = _parse_iso_date(date_from) or _parse_iso_date(facts.get("date"))
    parsed_to = _parse_iso_date(date_to) or _parse_iso_date(facts.get("date"))
    if not audit_kind:
        audit_kind = _audit_kind_for_period(parsed_from, parsed_to)
    if label_ru and date_from and date_to:
        return {"date_from": date_from, "date_to": date_to, "label_ru": label_ru, "audit_kind": audit_kind}

    fallback_label = _period_text(facts.get("period") or facts.get("date") or "\u043d/\u0434")
    if parsed_from and parsed_to:
        return {
            "date_from": parsed_from.isoformat(),
            "date_to": parsed_to.isoformat(),
            "label_ru": f"\u0441 {parsed_from.strftime('%d.%m.%Y')} \u043f\u043e {parsed_to.strftime('%d.%m.%Y')}",
            "audit_kind": audit_kind,
        }
    return {
        "date_from": _text(facts.get("date")),
        "date_to": _text(facts.get("date")),
        "label_ru": fallback_label or "\u043d/\u0434",
        "audit_kind": audit_kind,
    }


def _append_markdown_table(
    lines: list[str],
    headers: list[str],
    rows: list[list[Any]],
    *,
    align_right: set[int] | None = None,
) -> None:
    align_right = align_right or set()
    lines.append("| " + " | ".join(_sanitize_table_cell(h) for h in headers) + " |")
    sep_cells: list[str] = []
    for idx in range(len(headers)):
        sep_cells.append("---:" if idx in align_right else "---")
    lines.append("| " + " | ".join(sep_cells) + " |")
    for row in rows:
        cells = [_sanitize_table_cell(cell) for cell in row]
        while len(cells) < len(headers):
            cells.append("")
        lines.append("| " + " | ".join(cells[: len(headers)]) + " |")
    lines.append("")


def _page_break(lines: list[str]) -> None:
    lines.append("---PAGEBREAK---")
    lines.append("")


def _search_rows_sorted(rows: list[dict[str, Any]], *, mode: str) -> list[dict[str, Any]]:
    data = [row for row in rows if isinstance(row, dict)]
    if mode == "effective":
        data = [row for row in data if _search_bucket(row) == "effective"]
        return sorted(
            data,
            key=lambda row: (
                _to_int(row.get("orders")),
                _to_int(row.get("buyouts")),
                _to_int(row.get("clicks")),
            ),
            reverse=True,
        )
    if mode == "ineffective":
        data = [row for row in data if _search_bucket(row) == "ineffective"]
        return sorted(
            data,
            key=lambda row: (
                _to_int(row.get("clicks")),
                _to_int(row.get("add_to_cart")),
                _to_int(row.get("impressions")),
            ),
            reverse=True,
        )
    if mode == "potential":
        data = [row for row in data if _search_bucket(row) == "potential"]
        return sorted(
            data,
            key=lambda row: (
                _to_int(row.get("add_to_cart")),
                _to_int(row.get("clicks")),
                _to_int(row.get("orders")),
            ),
            reverse=True,
        )
    if mode == "orders":
        data = [row for row in data if _to_int(row.get("orders")) > 0]
        return sorted(
            data,
            key=lambda row: (
                _to_int(row.get("orders")),
                _to_int(row.get("clicks")),
                _to_int(row.get("add_to_cart")),
            ),
            reverse=True,
        )
    if mode == "no_orders_clicks":
        data = [row for row in data if _to_int(row.get("clicks")) > 0 and _to_int(row.get("orders")) == 0]
        return sorted(
            data,
            key=lambda row: (
                _to_int(row.get("clicks")),
                _to_int(row.get("add_to_cart")),
                _to_int(row.get("impressions")),
            ),
            reverse=True,
        )
    return sorted(
        data,
        key=lambda row: (
            _to_int(row.get("clicks")),
            _to_int(row.get("orders")),
            _to_int(row.get("add_to_cart")),
            _to_int(row.get("impressions")),
        ),
        reverse=True,
    )


def _local_orders_section_lines(local_orders_insights: dict[str, Any], *, total_buyouts: int = 0) -> list[str]:
    lines: list[str] = ["## 8. Локальные заказы и размещение товара"]

    available = bool(local_orders_insights.get("available"))
    if not available:
        message = _text(local_orders_insights.get("message") or "Данные по локальным заказам за период не найдены.")
        lines.append(f"- {message}")
        diagnostics = (
            local_orders_insights.get("diagnostics")
            if isinstance(local_orders_insights.get("diagnostics"), dict)
            else {}
        )
        source_hint = _text(diagnostics.get("required_source_hint") or "")
        if source_hint:
            lines.append(f"- Для расчета региональных рекомендаций нужна отдельная выгрузка: {source_hint}")
        lines.append("")
        return lines

    by_region = local_orders_insights.get("by_region") or []
    recommendations = local_orders_insights.get("recommendations") or []
    diagnostics = local_orders_insights.get("diagnostics") if isinstance(local_orders_insights.get("diagnostics"), dict) else {}

    lines.append("### Сводка по локальному спросу")
    lines.append("Распределение по регионам рассчитывается от выкупов.")
    lines.append("Если товар отсутствует на складе региона, но есть выкуп — заказ считается не локальным.")
    region_buyouts_total = _to_int(local_orders_insights.get("total_buyouts"))
    if region_buyouts_total <= 0 and isinstance(by_region, list):
        region_buyouts_total = sum(_to_int((item or {}).get("buyouts")) for item in by_region if isinstance(item, dict))
    if region_buyouts_total <= 0:
        region_buyouts_total = max(_to_int(total_buyouts), 0)
    lines.append(f"Всего выкупов: {region_buyouts_total}")
    lines.append("")
    buyouts_without_geo = _to_int(diagnostics.get("buyout_rows_without_geo"))
    if buyouts_without_geo > 0:
        lines.append(f"- Строк выкупов без региона: {buyouts_without_geo} (не учтены в распределении; см. diagnostics).")
    if by_region:
        rows: list[list[Any]] = []
        for item in by_region[:12]:
            stock_qty_raw = item.get("stock_qty")
            stock_text = "н/д" if stock_qty_raw is None else str(int(stock_qty_raw))
            region_buyouts = _to_int(item.get("buyouts"))
            region_share = (
                (float(region_buyouts) / float(region_buyouts_total))
                if region_buyouts_total > 0 and region_buyouts > 0
                else None
            )
            rows.append(
                [
                    _text(item.get("region") or "Не указан"),
                    region_buyouts,
                    (_fmt_pct(region_share * 100.0, 1) if region_share is not None else "н/д"),
                    stock_text,
                ]
            )
        _append_markdown_table(lines, ["Регион/город", "Выкупы, шт", "Доля", "Остаток, шт"], rows, align_right={1, 2, 3})
        lines.append("При небольшом количестве выкупов доли по регионам могут выглядеть завышенными.")
    else:
        lines.append("- Данные по регионам не обнаружены.")
        lines.append("")

    lines.append("### Рекомендации по размещению")
    if recommendations:
        for rec in recommendations[:10]:
            lines.append(f"- {_text(rec.get('message'))}")
    else:
        lines.append("- Спрос распределен равномерно, срочное перемещение не требуется.")
    lines.append("")
    return lines


def _logistics_class_label(value: Any) -> str:
    key = _text(value).lower()
    mapping = {
        "cheap": "\u0432\u044b\u0433\u043e\u0434\u043d\u0430\u044f",
        "normal": "\u0443\u043c\u0435\u0440\u0435\u043d\u043d\u0430\u044f",
        "expensive": "\u0434\u043e\u0440\u043e\u0433\u0430\u044f",
        "unknown": "\u043d\u0435\u0442 \u0434\u0430\u043d\u043d\u044b\u0445",
    }
    return mapping.get(key, key or "\u043d/\u0434")


def _coef_pct(value: Any) -> str:
    parsed = _to_float(value)
    if parsed is None:
        return "\u043d/\u0434"
    return _fmt_pct(parsed, 1)


def _cabinet_localization_comment(localization_pct: float | None) -> str:
    if localization_pct is None:
        return "Локализация не задана — точный расчет ограничен."
    if localization_pct < 50.0:
        return "Локализация низкая: значительная часть заказов едет не локально, это повышает расходы."
    if localization_pct <= 70.0:
        return "Локализация средняя: есть потенциал для улучшения."
    return "Локализация хорошая: логистика ближе к оптимальной."


def _cabinet_localization_recommendation(localization_pct: float | None) -> str | None:
    if localization_pct is None:
        return None
    if localization_pct <= 40.0:
        return (
            "Локализация низкая. Стоит перераспределять остатки в регионы с высоким спросом, "
            "чтобы снижать долю межрегиональных заказов."
        )
    if localization_pct < 70.0:
        return "Стоит усилить распределение остатков по ключевым регионам, чтобы приблизиться к цели 70%."
    return None


def _region_logistics_section_lines(facts: dict[str, Any]) -> list[str]:
    lines: list[str] = ["## 9. Логистика: где переплачиваете"]

    logistics_summary = facts.get("logistics_summary") if isinstance(facts.get("logistics_summary"), dict) else {}
    impact = facts.get("regional_logistics_impact") if isinstance(facts.get("regional_logistics_impact"), dict) else {}
    region_summary = facts.get("region_logistics_summary") if isinstance(facts.get("region_logistics_summary"), dict) else {}
    high_risk_regions = impact.get("high_risk_regions") if isinstance(impact.get("high_risk_regions"), list) else []
    top_sku_rows = impact.get("top_sku_by_regional_risk") if isinstance(impact.get("top_sku_by_regional_risk"), list) else []
    recommendations = impact.get("recommendations") if isinstance(impact.get("recommendations"), list) else []
    missing_inputs = impact.get("missing_inputs") if isinstance(impact.get("missing_inputs"), list) else []

    mode = _text(impact.get("mode") or "insufficient_data")
    total_overpay = _to_float(impact.get("total_estimated_overpay_rub"))
    weighted_coef = _to_float(impact.get("weighted_region_coef_pct"))
    routes_available = bool(impact.get("routes_available"))
    non_local_share = _to_float((facts.get("localization_loss") or {}).get("non_local_orders_share"))
    localization_pct = _to_float(logistics_summary.get("localization_pct"))
    avg_cost_est = _to_float(logistics_summary.get("avg_logistics_cost_est"))
    estimated_total = _to_float(logistics_summary.get("estimated_logistics_total"))
    orders_count = _to_int(logistics_summary.get("orders_count"))

    if not impact and not region_summary and not logistics_summary:
        lines.append("- Данные по региональной логистике не загружены; денежная оценка недоступна.")
        lines.append("")
        return lines

    lines.append("### Краткий вывод")
    if localization_pct is None:
        lines.append("- Локализация не задана — точный расчет ограничен.")
    else:
        lines.append(f"- Локализация по кабинету: **{_fmt_pct(localization_pct, 1)}**.")
    if avg_cost_est is not None:
        lines.append(f"- Средняя оценка логистики на заказ: **{_money(avg_cost_est)}**.")
    if estimated_total is not None:
        lines.append(f"- Оценка общей логистики за период: **{_money(estimated_total)}**.")
    if orders_count > 0:
        lines.append(f"- Заказов в расчете: **{orders_count}**.")
    lines.append(f"- {_cabinet_localization_comment(localization_pct)}")

    if mode == "full_rub" and total_overpay is not None:
        lines.append(f"- Оценочная переплата на логистике за период: **{_money(total_overpay)}**.")
        if weighted_coef is not None:
            lines.append(f"- Средневзвешенный региональный коэффициент: **{_fmt_pct(weighted_coef, 1)}**.")
        if high_risk_regions:
            lines.append(f"- Наибольший риск дают направления: **{', '.join(_text(x) for x in high_risk_regions[:3])}**.")
    elif mode == "risk_only":
        lines.append("- Точная рублевая оценка ограничена, но карта коэффициентов уже учтена в модели регионального риска.")
        if not routes_available:
            lines.append("- Маршруты заказов не загружены: выводы по направлениям носят эвристический характер.")
        if high_risk_regions:
            lines.append(f"- Регионы с повышенным риском удорожания: **{', '.join(_text(x) for x in high_risk_regions[:5])}**.")
    else:
        lines.append("- Данных недостаточно для денежной оценки влияния региональных направлений на логистику.")

    if non_local_share is not None:
        lines.append(f"- Доля нелокальных заказов: **{_fmt_pct(non_local_share * 100.0, 1)}**.")
    ads_spend = _to_float((facts.get("ads_summary") or {}).get("spend"))
    if total_overpay is not None and ads_spend is not None and ads_spend > 0:
        if total_overpay > ads_spend:
            lines.append("- В текущем срезе **география и размещение** влияют на потери сильнее рекламных расходов.")
        else:
            lines.append("- В текущем срезе **реклама и география** сопоставимо давят на маржу; контролировать нужно оба фактора.")
    elif non_local_share is not None and non_local_share > 0.4:
        lines.append("- Ключевой драйвер риска: **нелокальные заказы + дорогие направления**.")
    lines.append("")

    lines.append("### SKU в зоне регионального риска")
    if top_sku_rows:
        has_rub = any(_to_float((row or {}).get("overpay_rub")) is not None for row in top_sku_rows if isinstance(row, dict))
        table_rows: list[list[Any]] = []
        for row in top_sku_rows[:5]:
            if not isinstance(row, dict):
                continue
            sku_cell = f"{_to_int(row.get('sku'))} ({_text(row.get('abc') or 'N/A')})"
            if has_rub:
                table_rows.append(
                    [
                        sku_cell,
                        _to_int(row.get("orders")),
                        _money(row.get("logistics_per_order")),
                        _text(row.get("region_risk") or "н/д"),
                        _money(row.get("overpay_rub")),
                        _text(row.get("conclusion")),
                    ]
                )
            else:
                table_rows.append(
                    [
                        sku_cell,
                        _to_int(row.get("orders")),
                        _text(row.get("region_risk") or "н/д"),
                        _text(row.get("sensitivity") or "н/д"),
                        _text(row.get("conclusion")),
                    ]
                )
        if has_rub:
            _append_markdown_table(
                lines,
                ["SKU", "Заказы", "Логистика/заказ", "Риск региона", "Переплата", "Вывод"],
                table_rows,
                align_right={1, 2, 4},
            )
        else:
            _append_markdown_table(
                lines,
                ["SKU", "Заказы", "Риск региона", "Чувствительность", "Вывод"],
                table_rows,
                align_right={1},
            )
    else:
        lines.append("- SKU-level оценка пока ограничена: не хватает данных по объему/маршрутам/заказам.")
        volume_cov = facts.get("volume_coverage") if isinstance(facts.get("volume_coverage"), dict) else {}
        if _to_int(volume_cov.get("with_volume")) <= 0:
            expected_file = _file_name(volume_cov.get("expected_file"))
            if expected_file:
                lines.append(f"- Объем товара ожидался в файле остатков: {expected_file}.")
            else:
                lines.append("- Объем товара ожидался в файле остатков (stocks), но не был распознан.")
        lines.append("")

    lines.append("### Что делать practically")
    def _sentence(text: str) -> str:
        value = _text(text)
        if not value:
            return ""
        return value if value.endswith((".", "!", "?")) else f"{value}."

    rec_lines = 0
    for rec in recommendations[:4]:
        if not isinstance(rec, dict):
            continue
        action = _text(rec.get("action"))
        why = _sentence(_text(rec.get("why")))
        effect = _sentence(_text(rec.get("expected_effect")))
        if not action:
            continue
        lines.append(f"- **{_sentence(action)}** Причина: {why} Эффект: {effect}")
        rec_lines += 1

    if rec_lines == 0:
        if high_risk_regions:
            lines.append(
                "- **Сначала перераспределять A-SKU и сильные B-SKU** в направления с высоким спросом и меньшим коэффициентом."
            )
        if not routes_available:
            lines.append(
                "- **Загрузить географию заказов**: это переведет блок из risk-map в точную рублевую оценку по направлениям."
            )
        if not high_risk_regions and mode == "insufficient_data":
            lines.append("- Дополнительные прикладные рекомендации появятся после загрузки данных по маршрутам заказов.")

    if missing_inputs and mode != "full_rub":
        missing_preview = ", ".join(_text(x) for x in missing_inputs[:5] if _text(x))
        if missing_preview:
            lines.append(f"- Ограничения расчета: {missing_preview}.")
    lines.append("")
    return lines


def _localization_risk_from_share(localization_share_pct: Any) -> str:
    share = _to_float(localization_share_pct)
    if share is None:
        return "unknown"
    if share >= 70.0:
        return "low"
    if share >= 40.0:
        return "medium"
    return "high"


def _localization_risk_label(level: str) -> str:
    mapping = {
        "low": "low",
        "medium": "medium",
        "high": "high",
        "unknown": "unknown",
    }
    return mapping.get(_text(level).lower(), "unknown")


def _overpayment_conclusion(overpayment_pct: float | None) -> str:
    if overpayment_pct is None:
        return "Точная оценка переплаты в рублях недоступна."
    if overpayment_pct <= 5.0:
        return "Переплаты почти нет: влияние локализации на доставку ограничено."
    if overpayment_pct <= 20.0:
        return "Есть переплата за логистику: локализация увеличивает стоимость доставки."
    return "Критичная переплата: локализация существенно удорожает доставку и давит на маржу."


def _localization_human_message(
    *,
    localization_share_pct: float | None,
    localization_index: float | None,
    sales_distribution_index_pct: float | None,
) -> list[str]:
    lines: list[str] = []
    share = localization_share_pct
    il = localization_index
    irp = sales_distribution_index_pct

    if share is None:
        lines.append("Локализация не распознана автоматически, поэтому влияние ИЛ/ИРП оценено ограниченно.")
        return lines

    if share >= 70.0:
        lines.append("Локализация высокая: логистика получает скидку или нейтральные условия.")
    elif share >= 40.0:
        lines.append("Локализация нейтральная/средняя: значимого удорожания обычно нет, но нужен контроль динамики.")
    else:
        lines.append("Локализация слабая: логистика дорожает из-за повышенного ИЛ и ИРП.")

    if il is not None and il > 1.0:
        lines.append("ИЛ выше 1.0 повышает базовую логистическую часть тарифа.")
    if irp is not None and irp > 0:
        lines.append("Высокая цена товара усиливает влияние ИРП на итоговую стоимость доставки.")
    return lines


def _impact_label_from_row(row: dict[str, Any]) -> str:
    impact = _text(row.get("impact")).lower()
    if impact in {"низкое", "умеренное", "высокое", "критичное"}:
        return impact
    share = _to_float(row.get("localization_share_pct"))
    if share is None:
        return "н/д"
    if share >= 70.0:
        return "низкое"
    if share >= 40.0:
        return "умеренное"
    if share >= 20.0:
        return "высокое"
    return "критичное"


def _logistics_overpayment_section_lines(facts: dict[str, Any]) -> list[str]:
    lines: list[str] = ["## 10. Переплата за логистику"]
    model = facts.get("logistics_formula_model") if isinstance(facts.get("logistics_formula_model"), dict) else {}
    logistics_summary = facts.get("logistics_summary") if isinstance(facts.get("logistics_summary"), dict) else {}

    missing_inputs = model.get("missing_inputs") if isinstance(model.get("missing_inputs"), list) else []
    mode = _text(model.get("mode")).upper()
    if mode not in {"A", "B", "C"}:
        has_delivery = _to_float(model.get("estimated_delivery_cost")) is not None
        has_loc = _to_float(model.get("localization_share_pct")) is not None
        mode = "A" if has_delivery and has_loc else "B" if has_loc else "C"

    localization_share_pct = _to_float(model.get("localization_share_pct"))
    localization_index = _to_float(model.get("localization_index"))
    sales_distribution_index_pct = _to_float(model.get("sales_distribution_index_pct"))
    base_logistics = _to_float(model.get("base_logistics"))
    delivery_cost = _to_float(model.get("estimated_delivery_cost"))
    neutral_delivery_cost = _to_float(model.get("neutral_estimated_delivery_cost"))
    overpayment_abs = _to_float(model.get("overpayment_absolute"))
    overpayment_pct = _to_float(model.get("overpayment_pct_vs_neutral"))
    item_price = _to_float(model.get("item_price"))
    irp_is_estimated = False
    if sales_distribution_index_pct is None and item_price is not None and item_price > 0:
        # Fallback IRP estimate from item price scale when source metric is absent.
        sales_distribution_index_pct = round(max(min((float(item_price) / 1000.0) * 2.0, 12.0), 0.5), 2)
        irp_is_estimated = True
    risk_level = _localization_risk_label(
        model.get("risk_level") or _localization_risk_from_share(localization_share_pct)
    )
    cabinet_localization_pct = _to_float(logistics_summary.get("localization_pct"))
    cabinet_overpay = _to_float(logistics_summary.get("potential_overpay_due_localization"))
    cabinet_target_pct = _to_float(logistics_summary.get("target_localization_pct"))
    if cabinet_target_pct is None:
        cabinet_target_pct = 70.0

    lines.append("### Краткий вывод")
    if cabinet_localization_pct is None:
        lines.append("- Локализация не задана — точный расчет ограничен.")
    else:
        lines.append(
            f"- Текущая локализация: **{_fmt_pct(cabinet_localization_pct, 1)}**, целевая: **{_fmt_pct(cabinet_target_pct, 1)}**."
        )
        if cabinet_overpay is not None:
            lines.append(f"- Ориентировочная переплата за период: **{_money(cabinet_overpay)}**.")
            lines.append(
                f"- При локализации {_fmt_pct(cabinet_localization_pct, 1)} кабинет переплачивает за логистику ориентировочно "
                f"**{_money(cabinet_overpay)}** за период относительно сценария с локализацией {_fmt_pct(cabinet_target_pct, 1)}."
            )
        lines.append("- Это модельная оценка для приоритезации действий.")

    lines.append(f"- Риск влияния локализации: **{risk_level}**.")
    for msg in _localization_human_message(
        localization_share_pct=localization_share_pct,
        localization_index=localization_index,
        sales_distribution_index_pct=sales_distribution_index_pct,
    )[:3]:
        lines.append(f"- {msg}")
    lines.append("")

    if mode == "A":
        lines.append("### Расчет (полные данные)")
        rows = [
            ["Доля локализации", _fmt_pct(localization_share_pct, 2)],
            ["ИЛ", _sanitize_table_cell(localization_index)],
            ["ИРП (оценочный)" if irp_is_estimated else "ИРП", _fmt_pct(sales_distribution_index_pct, 2)],
            ["Базовая логистика", _money(base_logistics)],
            ["Итоговая расчетная логистика", _money(delivery_cost)],
            ["Нейтральный сценарий (ИЛ=1, ИРП=0)", _money(neutral_delivery_cost)],
            ["Оценка переплаты", _money(overpayment_abs)],
            ["Рост к нейтральному сценарию", _fmt_pct(overpayment_pct, 1)],
        ]
        _append_markdown_table(lines, ["Показатель", "Значение"], rows, align_right={1})
        if irp_is_estimated:
            lines.append("- ИРП рассчитан оценочно по цене товара, т.к. прямой показатель в исходных данных отсутствовал.")
        lines.append(f"- {_overpayment_conclusion(overpayment_pct)}")
        lines.append("")
    elif mode == "B":
        lines.append("### Оценка (частичные данные)")
        lines.append(
            f"- Доля локализации: {_fmt_pct(localization_share_pct, 2)}; применяется ИЛ={_sanitize_table_cell(localization_index)} и ИРП{(' (оценочный)' if irp_is_estimated else '')}={_fmt_pct(sales_distribution_index_pct, 2)}."
        )
        if irp_is_estimated:
            lines.append("- ИРП рассчитан оценочно по цене товара, т.к. прямой показатель в данных отсутствовал.")
        lines.append("- По этим параметрам логистика имеет риск удорожания, но точная сумма в рублях недоступна.")
        lines.append("- Для расчета в рублях нужны объем товара, цена и коэффициент склада.")
        lines.append("")
    else:
        lines.append("### Оценка недоступна")
        lines.append("- Точный расчет переплаты за логистику недоступен по текущим данным.")
        lines.append(
            "- Для расчета нужны: объем товара, цена товара, коэффициент склада и доля локализации."
        )
        if missing_inputs:
            lines.append("- Сейчас не хватает: " + ", ".join(_text(x) for x in missing_inputs if _text(x)) + ".")
        if "volume_liters" in [str(x) for x in missing_inputs]:
            volume_cov = facts.get("volume_coverage") if isinstance(facts.get("volume_coverage"), dict) else {}
            expected_file = _file_name(volume_cov.get("expected_file"))
            if expected_file:
                lines.append(f"- Объем товара ожидался в файле остатков: {expected_file}.")
            else:
                lines.append("- Объем товара ожидался в файле остатков (stocks).")
        lines.append("")

    if item_price is not None and sales_distribution_index_pct is not None and sales_distribution_index_pct > 0:
        lines.append("- Высокая цена товара усиливает влияние ИРП на итоговую стоимость доставки.")
        lines.append("")

    sku_risk_rows = model.get("sku_risk_rows") if isinstance(model.get("sku_risk_rows"), list) else []
    lines.append("### SKU с риском удорожания")
    if sku_risk_rows:
        table_rows: list[list[Any]] = []
        for row in sku_risk_rows[:5]:
            if not isinstance(row, dict):
                continue
            table_rows.append(
                [
                    row.get("sku"),
                    _fmt_pct(_to_float(row.get("localization_share_pct")), 2),
                    _sanitize_table_cell(row.get("localization_index")),
                    _fmt_pct(_to_float(row.get("sales_distribution_index_pct")), 2),
                    _impact_label_from_row(row),
                    _text(row.get("conclusion")),
                ]
            )
        if table_rows:
            _append_markdown_table(
                lines,
                ["SKU", "Доля локализации", "ИЛ", "ИРП", "Оценка влияния", "Вывод"],
                table_rows,
                align_right={1, 2, 3},
            )
        else:
            lines.append("- SKU-level данные по локализации не распознаны автоматически.")
            lines.append("")
    else:
        lines.append("- SKU-level данные по локализации не распознаны автоматически.")
        lines.append("")
    return lines


def _localization_loss_section_lines(facts: dict[str, Any]) -> list[str]:
    lines: list[str] = ["## 11. Потери из-за плохой локализации"]
    logistics_summary = facts.get("logistics_summary") if isinstance(facts.get("logistics_summary"), dict) else {}
    local_orders_insights = facts.get("local_orders_insights") if isinstance(facts.get("local_orders_insights"), dict) else {}
    funnel = facts.get("funnel_summary") if isinstance(facts.get("funnel_summary"), dict) else {}
    finance = facts.get("financial_summary") if isinstance(facts.get("financial_summary"), dict) else {}

    localization_pct = _to_float(logistics_summary.get("localization_pct"))
    buyouts_count = _to_int(funnel.get("buys"))
    if buyouts_count <= 0:
        buyouts_count = _to_int(finance.get("sales_qty"))
    local_cost = _to_float(logistics_summary.get("local_cost_per_order"))
    non_local_cost = _to_float(logistics_summary.get("non_local_cost_per_order"))
    target_localization_pct = _to_float(logistics_summary.get("target_localization_pct"))
    avg_logistics_cost_est = _to_float(logistics_summary.get("avg_logistics_cost_est"))
    target_avg_logistics_cost = _to_float(logistics_summary.get("target_avg_logistics_cost"))
    delta_vs_target = _to_float(logistics_summary.get("delta_vs_target_per_order"))
    potential_overpay = _to_float(logistics_summary.get("potential_overpay_due_localization"))

    if local_cost is None:
        local_cost = 50.0
    if non_local_cost is None:
        non_local_cost = 120.0
    if target_localization_pct is None:
        target_localization_pct = 70.0
    if target_avg_logistics_cost is None:
        target_share = max(0.0, min(1.0, float(target_localization_pct) / 100.0))
        target_avg_logistics_cost = (target_share * float(local_cost)) + ((1.0 - target_share) * float(non_local_cost))
    if delta_vs_target is None and avg_logistics_cost_est is not None and target_avg_logistics_cost is not None:
        delta_vs_target = float(avg_logistics_cost_est) - float(target_avg_logistics_cost)
    if (
        buyouts_count <= 0
        and potential_overpay is not None
        and delta_vs_target is not None
        and float(delta_vs_target) > 0
    ):
        buyouts_count = max(0, int(round(float(potential_overpay) / float(delta_vs_target))))
    if potential_overpay is None and delta_vs_target is not None and buyouts_count > 0:
        potential_overpay = max(0.0, float(delta_vs_target) * float(buyouts_count))

    lines.append("")
    if localization_pct is None:
        lines.append("Локализация кабинета: н/д")
    else:
        lines.append(f"Локализация кабинета: {_fmt_pct(localization_pct, 1)}")
    lines.append(f"Общее количество выкупов: {buyouts_count}")
    lines.append("")

    lines.append("### Расчет влияния локализации на логистику")
    lines.append("Используем модель:")
    lines.append("Средняя стоимость логистики = (localization × local_cost) + ((1 - localization) × non_local_cost)")
    lines.append("")

    if localization_pct is None:
        lines.append("Текущая локализация: н/д")
    else:
        lines.append(f"Текущая локализация: {_fmt_pct(localization_pct, 1)}")
    lines.append(f"Целевая локализация: {_fmt_pct(target_localization_pct, 1)}")
    lines.append(f"Локальная доставка: {_money(local_cost)}")
    lines.append(f"Межрегиональная доставка: {_money(non_local_cost)}")
    lines.append("")

    if avg_logistics_cost_est is None:
        lines.append("Текущая средняя стоимость: н/д")
    else:
        lines.append(f"Текущая средняя стоимость: {_money(avg_logistics_cost_est)}")
    lines.append(f"При локализации {_fmt_pct(target_localization_pct, 1)}: {_money(target_avg_logistics_cost)}")
    lines.append("")

    if delta_vs_target is None:
        lines.append("Разница: н/д на выкуп")
    else:
        lines.append(f"Разница: {_money(delta_vs_target)} на выкуп")
    if potential_overpay is None:
        lines.append("Итого влияние за период: н/д")
    elif delta_vs_target is None or buyouts_count <= 0:
        lines.append(f"Итого влияние за период: {_money(potential_overpay)}")
    else:
        lines.append(f"{_money(delta_vs_target)} × {buyouts_count} = {_money(potential_overpay)}")
    lines.append("")
    lines.append(
        "Расчет является модельной оценкой и показывает, насколько увеличивается стоимость логистики "
        "при текущем уровне локализации"
    )
    lines.append("")

    lines.append("### TOP-10 SKU: не локальные заказы")
    sku_actions = (
        local_orders_insights.get("sku_non_local_actions")
        if isinstance(local_orders_insights.get("sku_non_local_actions"), list)
        else []
    )
    sku_non_local_available = bool(local_orders_insights.get("sku_non_local_available"))
    if not sku_non_local_available:
        lines.append("Недостаточно данных по географии заказов для анализа локализации по SKU")
        lines.append("")
        return lines

    if not sku_actions:
        lines.append("Нелокальные заказы по SKU не выявлены за выбранный период.")
        lines.append("")
        return lines

    table_rows: list[list[Any]] = []
    for row in sku_actions[:10]:
        if not isinstance(row, dict):
            continue
        table_rows.append(
            [
                _to_int(row.get("sku")),
                _to_int(row.get("non_local_orders_count")),
                _text(row.get("top_region") or "н/д"),
                _text(row.get("recommendation")),
            ]
        )
    _append_markdown_table(
        lines,
        ["SKU", "Не локальные заказы", "Основной регион спроса", "Рекомендация"],
        table_rows,
        align_right={1},
    )
    lines.append("")
    return lines




def _where_money_lost_section_lines(
    *,
    decision: dict[str, Any],
    abc_layer: dict[str, Any],
    facts: dict[str, Any],
) -> list[str]:
    lines: list[str] = ["### 🚨 Где теряются деньги"]

    ads_leaks = decision.get("ads_leaks") if isinstance(decision.get("ads_leaks"), list) else []
    finance = facts.get("financial_summary") if isinstance(facts.get("financial_summary"), dict) else {}

    ads_loss_rub = 0.0
    for leak in ads_leaks:
        if not isinstance(leak, dict):
            continue
        spend = _to_float(leak.get("spend"))
        if spend is None or spend <= 0:
            continue
        if _to_int(leak.get("orders")) == 0:
            ads_loss_rub += float(spend)

    logistics_summary = facts.get("logistics_summary") if isinstance(facts.get("logistics_summary"), dict) else {}
    funnel = facts.get("funnel_summary") if isinstance(facts.get("funnel_summary"), dict) else {}
    buyouts_count = _to_int(funnel.get("buys"))
    if buyouts_count <= 0:
        buyouts_count = _to_int(finance.get("sales_qty"))
    delta_per_unit = _to_float(logistics_summary.get("delta_vs_target_per_order"))
    if delta_per_unit is None:
        avg_logistics_cost = _to_float(logistics_summary.get("avg_logistics_cost_est"))
        target_logistics_cost = _to_float(logistics_summary.get("target_avg_logistics_cost"))
        if avg_logistics_cost is not None and target_logistics_cost is not None:
            delta_per_unit = float(avg_logistics_cost) - float(target_logistics_cost)
    if delta_per_unit is None or delta_per_unit < 0:
        delta_per_unit = 0.0
    logistics_loss_rub = float(delta_per_unit) * float(max(buyouts_count, 0))
    top_losses = [
        ("Реклама без заказов", ads_loss_rub),
        ("Переплата за логистику", logistics_loss_rub),
    ]
    top_losses_sorted = sorted(top_losses, key=lambda item: float(item[1] or 0.0), reverse=True)

    lines.append("#### ТОП потерь")
    for idx, (title, amount) in enumerate(top_losses_sorted, start=1):
        lines.append(f"{idx}. {title} — **{_money(amount)}**")
    lines.append("")

    ads_loss_text = _money_or_label(ads_loss_rub, threshold=100.0, low_label="нет значимых потерь")
    lines.append(f"- 🚨 **Реклама без заказов:** {len(ads_leaks)} связок, потери: {ads_loss_text}.")
    if ads_leaks and ads_loss_rub >= 100.0:
        lines.append("- Нужна чистка неэффективных запросов и связок, которые расходуют бюджет без выкупа.")
    logistics_loss_text = _money_or_label(
        logistics_loss_rub,
        threshold=100.0,
        low_label="нет значимой переплаты",
    )
    lines.append(f"- 💸 **Переплата за логистику:** {logistics_loss_text}.")
    if logistics_loss_rub >= 100.0 and delta_per_unit > 0 and buyouts_count > 0:
        lines.append(
            f"- Расчет: {_money(delta_per_unit)} × {buyouts_count} выкупов = {_money(logistics_loss_rub)}."
        )

    lines.append("")
    return lines


def _money_losses_section_lines(money_losses: dict[str, Any]) -> list[str]:
    losses = money_losses if isinstance(money_losses, dict) else {}

    ads_waste_rub = _to_float(losses.get("ads_waste_rub")) or 0.0
    ads_waste_count = max(_to_int(losses.get("ads_waste_count")), 0)
    negative_profit_rub = _to_float(losses.get("negative_profit_rub")) or 0.0
    negative_profit_sku_count = max(_to_int(losses.get("negative_profit_sku_count")), 0)
    frozen_stock_value_rub = _to_float(losses.get("frozen_stock_value_rub"))
    frozen_stock_sku_count = max(_to_int(losses.get("frozen_stock_sku_count")), 0)
    frozen_stock_qty_units = max(_to_int(losses.get("frozen_stock_qty_units")), 0)
    storage_risk_sku_count = max(_to_int(losses.get("storage_risk_sku_count")), 0)

    total_direct_losses_rub = _to_float(losses.get("total_direct_losses_rub"))
    if total_direct_losses_rub is None:
        total_direct_losses_rub = float(ads_waste_rub) + float(negative_profit_rub)

    lines: list[str] = ["### Потери денег"]
    lines.append("- Прямые потери считаются отдельно от потенциальных рисков, чтобы не задваивать суммы.")
    lines.append("")

    lines.append("1. Слив бюджета на рекламе")
    lines.append(f"- {_money(ads_waste_rub)}")
    lines.append(f"- {ads_waste_count} запросов/кампаний без продаж")

    lines.append("2. Убыточные товары")
    lines.append(f"- {_money(negative_profit_rub)}")
    lines.append(f"- {negative_profit_sku_count} SKU в минусе")

    lines.append("3. Зависшие остатки")
    if frozen_stock_value_rub is not None:
        lines.append(f"- {_money(frozen_stock_value_rub)} заморожено в товаре")
    else:
        lines.append("- Оценка в рублях недоступна (нет COGS по части SKU)")
    lines.append(f"- {frozen_stock_sku_count} SKU без продаж/с медленной оборачиваемостью")
    if frozen_stock_qty_units > 0:
        lines.append(f"- Объем зависших остатков: {frozen_stock_qty_units} шт")

    lines.append("4. Избыточное хранение")
    lines.append(f"- Высокий риск доп. расходов на хранение у {storage_risk_sku_count} SKU")

    lines.append("Итого прямые потери:")
    lines.append(f"- {_money(total_direct_losses_rub)}")
    lines.append("")

    lines.append("Рекомендации:")
    lines.append("- Отключить неэффективные запросы/кампании без заказов.")
    lines.append("- Остановить или пересобрать убыточные SKU.")
    lines.append("- Распродать зависшие позиции или не дозакупать их.")
    lines.append("- Пересмотреть размещение остатков по складам и объемы поставок.")
    lines.append("")
    return lines


def _risk_label_ru(level: Any) -> str:
    key = _text(level).lower()
    mapping = {
        "high": "ВЫСОКИЙ",
        "medium": "СРЕДНИЙ",
        "low": "НИЗКИЙ",
    }
    return mapping.get(key, "Н/Д")


def _top5_comment_with_drr_signal(item: dict[str, Any]) -> str:
    base_comment = _text(item.get("comment"))
    drr_sku_pct = _to_float(item.get("drr_sku_pct"))
    if drr_sku_pct is None:
        return base_comment or "н/д"

    def _comment_tail_without_ads(text: str) -> str:
        parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text or "") if p and p.strip()]
        filtered = [p for p in parts if ("дрр" not in p.lower() and "реклам" not in p.lower())]
        return " ".join(filtered).strip()

    if drr_sku_pct > 25.0:
        signal = f"⚠️ **ДРР высокий ({drr_sku_pct:.2f}%)** — реклама начинает съедать прибыль."
        tail = _comment_tail_without_ads(base_comment)
        return f"{signal} {tail}".strip() if tail else signal

    if drr_sku_pct < 10.0:
        signal = f"✅ **ДРР низкий ({drr_sku_pct:.2f}%)** — реклама эффективна, можно масштабировать."
        tail = _comment_tail_without_ads(base_comment)
        return f"{signal} {tail}".strip() if tail else signal

    if drr_sku_pct >= 15.0:
        signal = f"⚠️ **ДРР повышенный ({drr_sku_pct:.2f}%)** — масштабировать рекламу нужно осторожно."
        tail = _comment_tail_without_ads(base_comment)
        return f"{signal} {tail}".strip() if tail else signal

    return base_comment or "н/д"


def _top5_unit_economics_section_lines(facts: dict[str, Any]) -> list[str]:
    lines: list[str] = ["## 7. ТОП-5 SKU: где зарабатываете и где теряете"]
    payload = facts.get("top5_sku_unit_economics") if isinstance(facts.get("top5_sku_unit_economics"), dict) else {}
    rows = payload.get("items") if isinstance(payload.get("items"), list) else []
    stock_summary = facts.get("stock_summary") if isinstance(facts.get("stock_summary"), dict) else {}
    sku_total_stocks = stock_summary.get("sku_total_stocks") if isinstance(stock_summary.get("sku_total_stocks"), dict) else {}
    sku_stocks_by_warehouse = (
        stock_summary.get("sku_stocks_by_warehouse")
        if isinstance(stock_summary.get("sku_stocks_by_warehouse"), dict)
        else {}
    )

    if not rows:
        message = _text(payload.get("message") or "Недостаточно данных для расчета ТОП-5 SKU по юнит-экономике.")
        lines.append(f"- {message}")
        lines.append("- Блок строится при наличии SKU с положительной выручкой и прибылью.")
        lines.append("")
        return lines

    lines.append(
        "- Блок показывает топ SKU по прибыли и оценивает, где логистика WB (ИЛ/ИРП) и реклама снижают итоговую маржу."
    )
    lines.append("")

    for index, item in enumerate(rows[:5]):
        if not isinstance(item, dict):
            continue
        if index > 0:
            lines.append("----------------------------------------")
            lines.append("")

        sku_int = _to_int(item.get("sku"))
        sku = _text(item.get("sku") or "н/д")
        category = _text(item.get("category") or "N/A")
        lines.append(f"### SKU: {sku} ({category})")

        stock_total_value = sku_total_stocks.get(str(sku_int))
        if stock_total_value is None:
            stock_total_value = sku_total_stocks.get(sku)
        stock_total = _to_int(stock_total_value) if stock_total_value is not None else None
        warehouses_raw = sku_stocks_by_warehouse.get(str(sku_int))
        if warehouses_raw is None:
            warehouses_raw = sku_stocks_by_warehouse.get(sku)
        warehouses = warehouses_raw if isinstance(warehouses_raw, list) else []
        top_warehouses: list[tuple[str, int]] = []
        for wh_item in warehouses:
            if not isinstance(wh_item, dict):
                continue
            wh_name = _text(wh_item.get("warehouse"))
            wh_qty = _to_int(wh_item.get("qty"))
            if not wh_name:
                continue
            top_warehouses.append((wh_name, wh_qty))
        top_warehouses = sorted(top_warehouses, key=lambda item: item[1], reverse=True)
        if stock_total is not None:
            lines.append(f"**Общий остаток:** {stock_total} шт")
            for wh_name, wh_qty in top_warehouses[:3]:
                lines.append(f"- {wh_name} — {wh_qty} шт")
            if len(top_warehouses) > 3:
                lines.append(f"- и еще {len(top_warehouses) - 3} складов")
            lines.append("")

        profit_icon = _status_icon(_profit_status_level(item.get("profit")))
        lines.append(f"**Выручка:** {_money(item.get('revenue'))}")
        lines.append(f"**Прибыль:** {_money(item.get('profit'))} {profit_icon}")
        lines.append("")

        lines.append(f"Заказов: {_to_int(item.get('orders'))}")
        lines.append(f"Выкупов: {_to_int(item.get('buyouts'))}")
        lines.append(f"Средняя цена: {_money(item.get('price_avg'))}")
        lines.append(f"Прибыль на заказ: {_money(item.get('profit_per_order'))}")

        margin_sku_pct = _to_float(item.get("margin_sku_pct"))
        margin_label = _text(item.get("margin_label") or "Маржа")
        if "без cogs" in margin_label.lower():
            margin_suffix = " (без COGS)"
        elif "частично" in margin_label.lower():
            margin_suffix = " (частично с COGS)"
        else:
            margin_suffix = ""
        margin_icon = _status_icon(_margin_status_level_by_pct(margin_sku_pct))
        if margin_sku_pct is not None:
            lines.append(f"**Маржа (доля прибыли от выручки):** {float(margin_sku_pct):.2f}%{margin_suffix} {margin_icon}")
        else:
            lines.append(f"**Маржа (доля прибыли от выручки):** н/д {margin_icon}")

        roi_sku_pct = _to_float(item.get("roi_sku_pct"))
        roi_available = bool(item.get("roi_available"))
        if roi_available and roi_sku_pct is not None:
            lines.append(f"**ROI:** {float(roi_sku_pct):.2f}%")
        else:
            lines.append("**ROI:** ROI не рассчитан (нет себестоимости)")

        lines.append("")
        logistics_current = _to_float(item.get("logistics_new"))
        logistics_base = _to_float(item.get("logistics_base"))
        logistics_old = _to_float(item.get("logistics_per_order"))
        if logistics_current is not None or logistics_base is not None or logistics_old is not None:
            lines.append("Логистика:")
            if logistics_old is not None:
                lines.append(f"- факт по finance: {_money(logistics_old)} на заказ")
            if logistics_current is not None:
                lines.append(f"- текущая расчетная: {_money(logistics_current)} на заказ")
            if logistics_base is not None:
                lines.append(f"- нормальная (ИЛ=1, ИРП=0): {_money(logistics_base)} на заказ")
        else:
            lines.append("Логистика: недостаточно данных для точной оценки.")

        overpay_per_order = _to_float(item.get("overpay_per_order"))
        total_overpay = _to_float(item.get("total_overpay"))
        if overpay_per_order is not None:
            lines.append(f"Переплата: {_money(overpay_per_order)} на заказ")
        else:
            lines.append("Переплата: н/д")
        if total_overpay is not None:
            lines.append(f"Потери: {_money(total_overpay)} за период")
        else:
            lines.append("Потери: н/д")

        ads_per_order = _to_float(item.get("ads_per_order"))
        drr_sku_pct = _to_float(item.get("drr_sku_pct"))
        ads_load = _text(item.get("ads_load") or "")
        drr_icon = _status_icon(_drr_status_level_by_pct(drr_sku_pct))
        lines.append("")
        lines.append("Реклама:")
        lines.append(f"- {_money(ads_per_order)} на заказ" if ads_per_order is not None else "- н/д на заказ")
        lines.append(
            f"- **ДРР SKU:** {float(drr_sku_pct):.2f}% {drr_icon}"
            if drr_sku_pct is not None
            else f"- **ДРР SKU:** н/д {drr_icon}"
        )
        if drr_sku_pct is not None and drr_sku_pct > 25.0:
            lines.append("- Интерпретация: реклама начинает съедать прибыль.")
        elif drr_sku_pct is not None and drr_sku_pct < 10.0:
            lines.append("- Интерпретация: реклама эффективна, можно масштабировать.")
        if ads_load:
            lines.append(f"- Нагрузка рекламы: {ads_load}")

        risk_label = _risk_label_ru(item.get("risk_level"))
        risk_icon = _status_icon(_risk_status_level(item.get("risk_level")))
        lines.append(f"Риск: {risk_label} {risk_icon}")
        lines.append(f"**Вывод:** {_top5_comment_with_drr_signal(item)}")
        lines.append(f"{_icon_point()} **Рекомендация:** {_text(item.get('recommendation'))}")
        lines.append("")

    return lines


def _safe_ratio(numerator: Any, denominator: Any) -> float | None:
    numerator_value = _to_float(numerator)
    denominator_value = _to_float(denominator)
    if numerator_value is None or denominator_value is None or denominator_value <= 0:
        return None
    return float(numerator_value) / float(denominator_value)


def _count_or_dash(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return str(max(_to_int(value), 0))


def _percent_or_dash(ratio: float | None) -> str:
    if ratio is None:
        return "-"
    return f"{float(ratio) * 100.0:.1f}%"


def _money_int_rub_or_dash(value: Any) -> str:
    parsed = _to_float(value)
    if parsed is None:
        return "-"
    rounded = int(round(float(parsed)))
    return f"{rounded:,} ₽".replace(",", " ")


def _unprofitable_reason(
    *,
    revenue_total: float | None,
    wb_commission_total: float | None,
    logistics_total: float | None,
    margin: float | None,
) -> str:
    if revenue_total is not None and revenue_total > 0:
        commission_pct = ((wb_commission_total or 0.0) / revenue_total) * 100.0
        logistics_pct = ((logistics_total or 0.0) / revenue_total) * 100.0
        if commission_pct > 30.0:
            return "Высокая комиссия"
        if logistics_pct > 25.0:
            return "Дорогая логистика"
    if margin is not None and margin < 0:
        return "Низкая цена"
    return "-"


def _unprofitable_sku_rows(finance: dict[str, Any]) -> list[dict[str, Any]]:
    sku_financials = finance.get("sku_financials") if isinstance(finance.get("sku_financials"), dict) else {}
    rows: list[dict[str, Any]] = []

    for raw_sku, raw_data in sku_financials.items():
        if not isinstance(raw_data, dict):
            continue
        sku = _to_int(raw_sku)
        if sku <= 0:
            continue
        profit = _to_float(raw_data.get("profit"))
        if profit is None or profit >= 0:
            continue

        revenue_total = _to_float(raw_data.get("revenue_total"))
        if revenue_total is None or revenue_total <= 0:
            revenue_total = _to_float(raw_data.get("net_revenue"))
        if revenue_total is None or revenue_total <= 0:
            revenue_total = _to_float(raw_data.get("sales_revenue"))

        cogs_total = _to_float(raw_data.get("cogs_total"))
        if cogs_total is None:
            cogs_total = _to_float(raw_data.get("cogs"))

        wb_commission_total = _to_float(raw_data.get("wb_commission_total"))
        if wb_commission_total is None:
            wb_commission_total = _to_float(raw_data.get("commission"))

        logistics_total = _to_float(raw_data.get("logistics_total"))
        if logistics_total is None:
            logistics_total = _to_float(raw_data.get("logistics"))

        margin = _to_float(raw_data.get("margin"))
        if margin is None and revenue_total is not None and revenue_total > 0:
            margin = float(profit) / float(revenue_total)

        rows.append(
            {
                "sku": int(sku),
                "revenue_total": revenue_total,
                "cogs_total": cogs_total,
                "wb_commission_total": wb_commission_total,
                "logistics_total": logistics_total,
                "profit": float(profit),
                "margin": margin,
                "reason": _unprofitable_reason(
                    revenue_total=revenue_total,
                    wb_commission_total=wb_commission_total,
                    logistics_total=logistics_total,
                    margin=margin,
                ),
            }
        )

    return sorted(rows, key=lambda item: (float(item.get("profit") or 0.0), int(item.get("sku") or 0)))


def _unprofitable_sku_section_lines(finance: dict[str, Any]) -> list[str]:
    lines: list[str] = ["## 🚨 Убыточные SKU"]
    rows = _unprofitable_sku_rows(finance)
    if not rows:
        lines.append("Убыточных SKU не выявлено")
        lines.append("")
        return lines

    table_rows = [
        [
            row.get("sku"),
            _money_int_rub_or_dash(row.get("revenue_total")),
            _money_int_rub_or_dash(row.get("cogs_total")),
            _money_int_rub_or_dash(row.get("wb_commission_total")),
            _money_int_rub_or_dash(row.get("logistics_total")),
            _money_int_rub_or_dash(row.get("profit")),
            _text(row.get("reason") or "-"),
        ]
        for row in rows
    ]
    _append_markdown_table(
        lines,
        ["SKU", "Выручка", "Себестоимость", "Комиссии WB", "Логистика", "Прибыль", "Причина убытка"],
        table_rows,
        align_right={1, 2, 3, 4, 5},
    )
    return lines


def _ratio_or_dash(value: float | None, *, digits: int = 2) -> str:
    if value is None:
        return "-"
    token = f"{float(value):.{digits}f}".rstrip("0").rstrip(".")
    return token if token else "0"


def _extract_sku_from_item(row: dict[str, Any]) -> int:
    if not isinstance(row, dict):
        return 0
    product = row.get("product")
    if isinstance(product, dict):
        product_sku = _to_int(product.get("nmId") or product.get("nm_id") or product.get("nmID") or product.get("sku"))
        if product_sku > 0:
            return product_sku
    return _to_int(row.get("nmId") or row.get("nm_id") or row.get("nmID") or row.get("sku"))


def _pick_funnel_stat_item(row: dict[str, Any]) -> dict[str, Any]:
    statistic = row.get("statistic")
    if isinstance(statistic, dict):
        selected = statistic.get("selected") or statistic.get("current") or statistic.get("now")
        if isinstance(selected, dict):
            return selected
    return row


def _funnel_sku_metrics(funnel_raw: Any) -> dict[int, dict[str, int]]:
    rows = funnel_raw if isinstance(funnel_raw, list) else []
    out: dict[int, dict[str, int]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        sku = _extract_sku_from_item(row)
        if sku <= 0:
            continue
        stat = _pick_funnel_stat_item(row)
        node = out.setdefault(
            sku,
            {
                "impressions": 0,
                "views": 0,
                "add_to_cart": 0,
                "orders": 0,
                "buyouts": 0,
            },
        )
        node["impressions"] += max(_to_int(stat.get("impressions") or stat.get("shows")), 0)
        node["views"] += max(_to_int(stat.get("views") or stat.get("openCount") or stat.get("openCardCount")), 0)
        node["add_to_cart"] += max(_to_int(stat.get("add_to_cart") or stat.get("cartCount") or stat.get("addToCartCount")), 0)
        node["orders"] += max(_to_int(stat.get("orders") or stat.get("orderCount")), 0)
        node["buyouts"] += max(_to_int(stat.get("buys") or stat.get("buyoutCount")), 0)
    return out


def _search_sku_metrics(search: dict[str, Any]) -> dict[int, dict[str, int]]:
    out: dict[int, dict[str, int]] = {}
    if not isinstance(search, dict):
        return out
    base_rows = search.get("base_rows") if isinstance(search.get("base_rows"), list) else []
    for row in base_rows:
        if not isinstance(row, dict):
            continue
        sku = _extract_sku_from_item(row)
        if sku <= 0:
            continue
        node = out.setdefault(
            sku,
            {
                "impressions": 0,
                "clicks": 0,
                "add_to_cart": 0,
                "orders": 0,
                "buyouts": 0,
            },
        )
        node["impressions"] += max(_to_int(row.get("impressions")), 0)
        node["clicks"] += max(_to_int(row.get("clicks")), 0)
        node["add_to_cart"] += max(_to_int(row.get("add_to_cart")), 0)
        node["orders"] += max(_to_int(row.get("orders")), 0)
        node["buyouts"] += max(_to_int(row.get("buyouts")), 0)
    return out


def _first_non_zero(primary: Any, fallback: Any) -> Any:
    primary_value = _to_int(primary)
    fallback_value = _to_int(fallback)
    if primary not in (None, "") and primary_value > 0:
        return primary_value
    if fallback not in (None, "") and fallback_value > 0:
        return fallback_value
    if primary not in (None, ""):
        return primary_value
    if fallback not in (None, ""):
        return fallback_value
    return None


def _sku_efficiency_section_lines(*, facts: dict[str, Any]) -> list[str]:
    lines: list[str] = ["## Эффективность товаров"]
    sku_profit = facts.get("sku_profit") if isinstance(facts.get("sku_profit"), list) else []
    if not sku_profit:
        lines.append("- Недостаточно данных для построения таблицы по SKU.")
        lines.append("")
        return lines

    sku_rows = [row for row in sku_profit if isinstance(row, dict) and _to_int(row.get("sku")) > 0]
    if not sku_rows:
        lines.append("- Нет валидных SKU в источнике `sku_profit`.")
        lines.append("")
        return lines

    sorted_by_profit = sorted(sku_rows, key=lambda row: (_to_float(row.get("profit")) or 0.0), reverse=True)

    ab_skus: set[int] = set()
    for row in sku_rows:
        category = _text(row.get("abc")).upper()
        sku = _to_int(row.get("sku"))
        if sku > 0 and category in {"A", "B"}:
            ab_skus.add(sku)

    if ab_skus:
        selected = [row for row in sorted_by_profit if _to_int(row.get("sku")) in ab_skus]
        selection_note = "- В таблицу включены SKU категорий A и B (ABC-анализ)."
    else:
        selected = sorted_by_profit
        selection_note = "- ABC-анализ недоступен: выбраны TOP SKU по прибыли."

    selected = selected[:20]
    if not selected:
        lines.append("- Для выбранного набора SKU нет данных.")
        lines.append("")
        return lines

    funnel_metrics = _funnel_sku_metrics(facts.get("funnel_raw"))
    search_metrics = _search_sku_metrics(facts.get("search_insights") if isinstance(facts.get("search_insights"), dict) else {})

    table_rows: list[tuple[float, list[Any]]] = []
    for row in selected:
        sku = _to_int(row.get("sku"))
        if sku <= 0:
            continue
        search_row = search_metrics.get(sku) or {}
        funnel_row = funnel_metrics.get(sku) or {}

        impressions = _first_non_zero(search_row.get("impressions"), funnel_row.get("impressions"))
        clicks = _first_non_zero(search_row.get("clicks"), funnel_row.get("views"))
        add_to_cart = _first_non_zero(search_row.get("add_to_cart"), funnel_row.get("add_to_cart"))

        orders = _to_int(row.get("orders"))
        if orders <= 0:
            orders = _to_int(_first_non_zero(funnel_row.get("orders"), search_row.get("orders")))

        buyouts = _to_int(row.get("buyouts"))
        if buyouts <= 0:
            buyouts = _to_int(_first_non_zero(funnel_row.get("buyouts"), search_row.get("buyouts")))

        revenue = _to_float(row.get("revenue"))
        ad_spend = _to_float(row.get("ad_spend"))
        profit = _to_float(row.get("profit"))

        ctr = _safe_ratio(clicks, impressions)
        cr_click_to_cart = _safe_ratio(add_to_cart, clicks)
        cr_cart_to_order = _safe_ratio(orders, add_to_cart)
        cr_order_to_buyout = _safe_ratio(buyouts, orders)
        drr = _safe_ratio(ad_spend, revenue)
        roi = _safe_ratio(profit, ad_spend)

        formatted = [
            sku,
            _count_or_dash(impressions),
            _count_or_dash(clicks),
            _percent_or_dash(ctr),
            _count_or_dash(add_to_cart),
            _percent_or_dash(cr_click_to_cart),
            _count_or_dash(orders),
            _percent_or_dash(cr_cart_to_order),
            _count_or_dash(buyouts),
            _percent_or_dash(cr_order_to_buyout),
            _percent_or_dash(drr),
            _money_int_rub_or_dash(profit),
            _ratio_or_dash(roi, digits=2),
        ]
        table_rows.append((float(profit or 0.0), formatted))

    table_rows = sorted(table_rows, key=lambda item: item[0], reverse=True)[:20]
    if not table_rows:
        lines.append("- Не удалось сформировать строки для таблицы SKU.")
        lines.append("")
        return lines

    headers = [
        "Артикул",
        "Показы",
        "Клики",
        "CTR",
        "В корзину (шт)",
        "CR (клик->корзина)",
        "Заказы (шт)",
        "CR (корзина->заказ)",
        "Выкупы (шт)",
        "CR (заказ->выкуп)",
        "ДРР",
        "Чистая прибыль (руб)",
        "ROI",
    ]
    _append_markdown_table(
        lines,
        headers,
        [row for _, row in table_rows],
        align_right=set(range(1, len(headers))),
    )
    lines.append(selection_note)
    lines.append("- Источники: funnel, sku_profit, search (если есть).")
    lines.append("")
    return lines


def _profit_view(finance: dict[str, Any], ads: dict[str, Any]) -> dict[str, Any]:
    revenue = _to_float(finance.get("gross_revenue")) or 0.0
    commission = _to_float(finance.get("commission")) or 0.0
    logistics = _to_float(finance.get("logistics")) or 0.0
    storage = _to_float(finance.get("storage")) or 0.0
    tax = _to_float(finance.get("tax")) or 0.0
    cogs_total = _to_float(finance.get("cogs_total")) or 0.0
    ads_spend = _to_float(ads.get("spend")) or 0.0
    profit_without_cogs = bool(finance.get("profit_without_cogs"))
    cogs_status = _text(finance.get("cogs_status") or "")

    clean_profit_without_cogs = revenue - commission - logistics - storage - tax - ads_spend
    clean_profit = clean_profit_without_cogs - cogs_total
    clean_margin = (clean_profit / revenue) if revenue > 0 else 0.0
    cogs_impact_pct = None
    if clean_profit_without_cogs > 0 and cogs_total > 0:
        cogs_impact_pct = -(float(cogs_total) / float(clean_profit_without_cogs)) * 100.0
    if cogs_status == "partial_match":
        clean_label = "Чистая прибыль (частично с COGS, с учетом рекламы)"
    elif profit_without_cogs:
        clean_label = "Чистая прибыль без учета себестоимости (с учетом рекламы)"
    else:
        clean_label = "Чистая прибыль"
    return {
        "clean_profit": float(clean_profit),
        "clean_profit_without_cogs": float(clean_profit_without_cogs),
        "clean_margin": float(clean_margin),
        "clean_label": clean_label,
        "profit_without_cogs": profit_without_cogs,
        "cogs_impact_pct": cogs_impact_pct,
        "cogs_total": float(cogs_total),
        "ads_spend": float(ads_spend),
    }


def _roi_line(finance: dict[str, Any], ads: dict[str, Any], *, clean_profit: float) -> tuple[str, list[str]]:
    profit_without_cogs = bool(finance.get("profit_without_cogs"))
    cogs_status = _text(finance.get("cogs_status") or "")
    cogs_total = _to_float(finance.get("cogs_total"))
    if cogs_status == "partial_match":
        return (
            "ROI: не рассчитан (COGS сопоставлен частично)",
            [
                "ROI на уровне кабинета будет корректным после полного сопоставления COGS по SKU.",
                "Сейчас прибыль учитывает только сопоставленную часть себестоимости.",
            ],
        )
    if profit_without_cogs or cogs_total is None or cogs_total <= 0:
        return (
            "ROI: не рассчитан (нет данных по себестоимости)",
            [
                "ROI будет доступен после загрузки себестоимости (COGS-файла).",
                "Этот показатель покажет реальную окупаемость бизнеса с учетом всех затрат.",
            ],
        )

    expense_fields = [
        _to_float(finance.get("commission")) or 0.0,
        _to_float(finance.get("logistics")) or 0.0,
        _to_float(finance.get("storage")) or 0.0,
        _to_float(finance.get("tax")) or 0.0,
        cogs_total,
        _to_float(ads.get("spend")) or 0.0,
    ]
    expenses = sum(x for x in expense_fields if x > 0)
    if expenses <= 0:
        return ("ROI: н/д", [])

    roi = (float(clean_profit) / expenses) * 100.0
    return (f"ROI: {_fmt_pct(roi, 1)}", [])


def _cogs_status_explanation(finance: dict[str, Any]) -> str:
    status = _text(finance.get("cogs_status") or "")
    mapping = {
        "file_not_found": "COGS не найден: прибыль и маржа без себестоимости.",
        "file_found_not_read": "COGS найден, но не прочитан: прибыль и маржа без себестоимости.",
        "file_read_not_matched": "COGS найден, но не сопоставлен с SKU продаж: прибыль и маржа без себестоимости.",
        "partial_match": "COGS сопоставлен частично: прибыль и маржа рассчитаны по сопоставленной части.",
        "full_match": "COGS применен полностью: прибыль и маржа учитывают себестоимость.",
    }
    return mapping.get(status, "")


def _build_abc_analysis(
    *,
    sku_profit: list[dict[str, Any]],
    profit_without_cogs: bool,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for item in sku_profit or []:
        if not isinstance(item, dict):
            continue
        sku = _to_int(item.get("sku"))
        if sku <= 0:
            continue
        rows.append(
            {
                "sku": sku,
                "revenue": _to_float(item.get("revenue")),
                "profit": _to_float(item.get("profit")),
                "stock_qty": _to_int(item.get("stock_qty")),
                "buyouts_qty": _to_int(item.get("buyouts")),
            }
        )

    if not rows:
        return {
            "available": False,
            "basis_note": "Недостаточно данных для ABC-анализа.",
            "summary_rows": [],
            "detail_rows": [],
            "insights": [],
            "basis_metric": "unknown",
            "counts": {"A": 0, "B": 0, "C": 0},
            "filtered_dead_sku_count": 0,
            "filtered_dead_skus": [],
            "input_sku_count": 0,
            "active_sku_count": 0,
        }

    dead_skus: list[int] = []
    live_rows: list[dict[str, Any]] = []
    for row in rows:
        revenue = _to_float(row.get("revenue"))
        profit = _to_float(row.get("profit"))
        stock_qty = _to_int(row.get("stock_qty"))
        if float(revenue or 0.0) <= 0 and float(profit or 0.0) <= 0 and stock_qty <= 0:
            dead_skus.append(_to_int(row.get("sku")))
            continue
        live_rows.append(row)
    rows = live_rows

    if not rows:
        return {
            "available": False,
            "basis_note": "\u041f\u043e\u0441\u043b\u0435 \u0438\u0441\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u044f \u043d\u0435\u0430\u043a\u0442\u0438\u0432\u043d\u044b\u0445 SKU \u043d\u0435\u0442 \u0434\u0430\u043d\u043d\u044b\u0445 \u0434\u043b\u044f ABC-\u0430\u043d\u0430\u043b\u0438\u0437\u0430.",
            "summary_rows": [],
            "detail_rows": [],
            "insights": [],
            "basis_metric": "unknown",
            "counts": {"A": 0, "B": 0, "C": 0},
            "filtered_dead_sku_count": len(dead_skus),
            "filtered_dead_skus": dead_skus,
            "input_sku_count": len(dead_skus),
            "active_sku_count": 0,
        }

    profit_non_null = sum(1 for row in rows if row["profit"] is not None)
    revenue_non_null = sum(1 for row in rows if row["revenue"] is not None)
    profit_total = sum(max(float(row["profit"] or 0.0), 0.0) for row in rows if row["profit"] is not None)
    revenue_total = sum(max(float(row["revenue"] or 0.0), 0.0) for row in rows if row["revenue"] is not None)

    metric_key = "profit"
    metric_total = profit_total
    basis_note = (
        "ABC построен по прибыли без учета себестоимости."
        if profit_without_cogs
        else "ABC построен по прибыли."
    )

    profit_usable = profit_non_null >= max(1, int(len(rows) * 0.8)) and profit_total > 0
    if not profit_usable:
        metric_key = "revenue"
        metric_total = revenue_total
        basis_note = "ABC построен по выручке."

    if metric_total <= 0:
        metric_key = "revenue"
        metric_total = float(len(rows))
        basis_note = "ABC построен по выручке (вклад SKU оценен равномерно из-за неполных данных)."
        for row in rows:
            row["_metric_value"] = 1.0
    else:
        for row in rows:
            metric_raw = row.get(metric_key)
            row["_metric_value"] = max(float(metric_raw or 0.0), 0.0)

    rows_sorted = sorted(
        rows,
        key=lambda row: (
            float(row.get("_metric_value") or 0.0),
            float(row.get("revenue") or 0.0),
            float(row.get("profit") or 0.0),
        ),
        reverse=True,
    )

    by_cat: dict[str, dict[str, Any]] = {
        "A": {"count": 0, "share": 0.0},
        "B": {"count": 0, "share": 0.0},
        "C": {"count": 0, "share": 0.0},
    }
    detail_rows: list[dict[str, Any]] = []
    cumulative = 0.0
    for row in rows_sorted:
        share = (float(row["_metric_value"]) / float(metric_total)) if metric_total > 0 else 0.0
        prev_cumulative = cumulative
        cumulative += share
        if prev_cumulative < 0.8:
            category = "A"
        elif prev_cumulative < 0.95:
            category = "B"
        else:
            category = "C"
        by_cat[category]["count"] += 1
        by_cat[category]["share"] += share
        detail_rows.append(
            {
                "sku": int(row["sku"]),
                "category": category,
                "revenue": row.get("revenue"),
                "profit": row.get("profit"),
                "share_pct": share * 100.0,
                "stock_qty": int(row.get("stock_qty") or 0),
                "buyouts_qty": int(row.get("buyouts_qty") or 0),
            }
        )

    summary_rows = [
        ["A", by_cat["A"]["count"], _fmt_pct(by_cat["A"]["share"] * 100.0, 1), "Основные драйверы"],
        ["B", by_cat["B"]["count"], _fmt_pct(by_cat["B"]["share"] * 100.0, 1), "Поддерживающая группа"],
        ["C", by_cat["C"]["count"], _fmt_pct(by_cat["C"]["share"] * 100.0, 1), "Слабый вклад"],
    ]

    a_count = int(by_cat["A"]["count"])
    b_share = float(by_cat["B"]["share"] or 0.0)
    c_share = float(by_cat["C"]["share"] or 0.0)
    ab_share_pct = (float(by_cat["A"]["share"] or 0.0) + b_share) * 100.0

    c_high_stock = [row for row in detail_rows if row["category"] == "C" and int(row.get("stock_qty") or 0) >= 50]
    a_low_stock = [row for row in detail_rows if row["category"] == "A" and int(row.get("stock_qty") or 0) > 0 and int(row.get("stock_qty") or 0) <= 5]

    insights = [
        f"Категория A: {a_count} SKU, вклад {_fmt_pct(by_cat['A']['share'] * 100.0, 1)} в выбранную метрику.",
        f"Группы A+B формируют {_fmt_pct(ab_share_pct, 1)} результата; группа C дает {_fmt_pct(c_share * 100.0, 1)}.",
    ]
    if c_high_stock:
        sample = ", ".join(str(item["sku"]) for item in c_high_stock[:3])
        insights.append(f"Есть SKU категории C с высокими остатками: {sample}.")
    if a_low_stock:
        sample = ", ".join(str(item["sku"]) for item in a_low_stock[:3])
        insights.append(f"Есть риск дефицита по SKU категории A: {sample}.")

    return {
        "available": True,
        "basis_note": basis_note,
        "summary_rows": summary_rows,
        "detail_rows": detail_rows,
        "insights": insights[:4],
        "basis_metric": metric_key,
        "counts": {k: int(v["count"]) for k, v in by_cat.items()},
        "filtered_dead_sku_count": len(dead_skus),
        "filtered_dead_skus": dead_skus,
        "input_sku_count": len(rows) + len(dead_skus),
        "active_sku_count": len(rows),
    }


def _build_abc_stock_ads_layer(
    *,
    abc_detail_rows: list[dict[str, Any]],
    finance: dict[str, Any],
    search: dict[str, Any],
) -> dict[str, Any]:
    sku_financials = finance.get("sku_financials") if isinstance(finance.get("sku_financials"), dict) else {}
    search_rows = search.get("base_rows") if isinstance(search.get("base_rows"), list) else []

    search_by_sku: dict[int, dict[str, Any]] = {}
    for row in search_rows:
        if not isinstance(row, dict):
            continue
        sku = _to_int(row.get("nmId"))
        if sku <= 0:
            continue
        bucket = search_by_sku.setdefault(
            sku,
            {
                "impressions": 0,
                "clicks": 0,
                "orders": 0,
                "spend": 0.0,
                "queries_no_orders": 0,
                "queries_with_orders": 0,
            },
        )
        impressions = _to_int(row.get("impressions"))
        clicks = _to_int(row.get("clicks"))
        orders = _to_int(row.get("orders"))
        spend = _to_float(row.get("spend")) or 0.0
        bucket["impressions"] += impressions
        bucket["clicks"] += clicks
        bucket["orders"] += orders
        bucket["spend"] += spend
        if clicks > 0 and orders == 0:
            bucket["queries_no_orders"] += 1
        if orders > 0:
            bucket["queries_with_orders"] += 1

    def _finance_sales_qty(sku: int) -> int:
        data = sku_financials.get(sku)
        if not isinstance(data, dict):
            data = sku_financials.get(str(sku))
        return _to_int((data or {}).get("sales_qty"))

    critical_a_rows: list[list[Any]] = []
    c_overstock_rows: list[list[Any]] = []
    c_ads_rows: list[list[Any]] = []
    ab_potential_rows: list[list[Any]] = []

    for row in abc_detail_rows:
        if not isinstance(row, dict):
            continue
        sku = _to_int(row.get("sku"))
        if sku <= 0:
            continue
        category = _text(row.get("category") or "")
        stock_qty = _to_int(row.get("stock_qty"))
        buyouts_qty = _to_int(row.get("buyouts_qty"))
        sales_qty = _finance_sales_qty(sku)
        if sales_qty <= 0:
            sales_qty = buyouts_qty
        revenue = _to_float(row.get("revenue")) or 0.0

        search_data = search_by_sku.get(sku, {})
        search_impressions = _to_int(search_data.get("impressions"))
        search_clicks = _to_int(search_data.get("clicks"))
        search_orders = _to_int(search_data.get("orders"))
        search_spend = _to_float(search_data.get("spend")) or 0.0
        queries_no_orders = _to_int(search_data.get("queries_no_orders"))
        queries_with_orders = _to_int(search_data.get("queries_with_orders"))

        if category == "A" and sales_qty > 0:
            high_risk_threshold = max(5, int(round(sales_qty * 0.5)))
            medium_risk_threshold = max(10, sales_qty)
            risk = ""
            if stock_qty <= 0:
                risk = "высокий (нет остатка)"
            elif stock_qty <= high_risk_threshold:
                risk = "высокий (низкий запас)"
            elif stock_qty <= medium_risk_threshold:
                risk = "средний (запас < 1 периода)"
            if risk:
                if search_clicks > 0 or search_orders > 0:
                    action = "пополнить остаток, рекламу не отключать"
                else:
                    action = "пополнить остаток и проверить видимость"
                critical_a_rows.append(
                    [sku, category, stock_qty, f"{sales_qty}/{buyouts_qty}", risk, action]
                )

        if category == "C":
            if stock_qty >= 50 and sales_qty <= 1:
                if sales_qty == 0:
                    rec = "распродать остаток и не пополнять"
                else:
                    rec = "снизить пополнение, проверить карточку"
                c_overstock_rows.append([sku, category, stock_qty, sales_qty, _money(revenue), rec])

            has_ads_signal = (
                search_impressions > 0
                or search_clicks > 0
                or search_spend > 0
                or queries_no_orders > 0
            )
            if has_ads_signal:
                signal_parts: list[str] = []
                if search_spend > 0:
                    signal_parts.append(f"расход {_money(search_spend)}")
                if search_clicks > 0:
                    signal_parts.append(f"клики {search_clicks}")
                if search_impressions > 0:
                    signal_parts.append(f"показы {search_impressions}")
                if queries_no_orders > 0:
                    signal_parts.append(f"запросы без заказов {queries_no_orders}")
                signal = ", ".join(signal_parts) if signal_parts else "есть активность"

                if search_orders == 0 and sales_qty <= 1:
                    conclusion = "сократить/отключить рекламу"
                elif queries_no_orders > queries_with_orders:
                    conclusion = "снизить ставки, оставить точечные запросы"
                else:
                    conclusion = "оставить только точечные и брендовые запросы"
                c_ads_rows.append([sku, category, signal, f"{sales_qty}/{search_orders}", conclusion])

        if category in {"A", "B"} and (sales_qty > 0 or search_orders > 0):
            reasons: list[str] = []
            if category == "A":
                reasons.append("высокий вклад в ABC")
            if sales_qty >= 2:
                reasons.append("стабильные продажи")
            if search_orders > 0:
                reasons.append(f"заказы из поиска {search_orders}")
            if search_clicks > 0 and search_orders > 0:
                reasons.append("есть конверсия запросов")
            basis = "; ".join(reasons[:3]) if reasons else "есть продажи"
            recommendation = (
                "усиливать рекламу и контролировать наличие"
                if category == "A"
                else "точечно усиливать рекламу по конверсионным запросам"
            )
            ab_potential_rows.append([sku, category, basis, recommendation])

    critical_a_rows = sorted(critical_a_rows, key=lambda row: (_to_int(row[2]),), reverse=False)[:10]
    c_overstock_rows = sorted(c_overstock_rows, key=lambda row: (_to_int(row[2]), _to_int(row[3])), reverse=True)[:10]
    c_ads_rows = sorted(
        c_ads_rows,
        key=lambda row: (
            _to_int(search_by_sku.get(_to_int(row[0]), {}).get("clicks")),
            _to_int(search_by_sku.get(_to_int(row[0]), {}).get("impressions")),
        ),
        reverse=True,
    )[:10]
    ab_potential_rows = sorted(
        ab_potential_rows,
        key=lambda row: (0 if _text(row[1]) == "A" else 1, _to_int(_finance_sales_qty(_to_int(row[0])))),
    )[:12]

    insight_lines: list[str] = []
    if critical_a_rows:
        insight_lines.append(
            f"Выявлены {len(critical_a_rows)} критичных SKU категории A с риском дефицита по текущему запасу."
        )
    if c_overstock_rows:
        insight_lines.append(
            f"{len(c_overstock_rows)} SKU категории C удерживают избыточные остатки при слабом движении."
        )
    if c_ads_rows:
        insight_lines.append(
            f"У {len(c_ads_rows)} SKU категории C есть рекламная активность, которую стоит пересмотреть."
        )
    if ab_potential_rows:
        insight_lines.append(
            "Рекламный фокус целесообразно концентрировать на SKU категорий A и сильных B."
        )
    insight_lines.append(
        "Риск по A-SKU оценен эвристикой: остаток сравнивается с продажами за период (без прогноза по дням)."
    )

    return {
        "critical_a_rows": critical_a_rows,
        "c_overstock_rows": c_overstock_rows,
        "c_ads_rows": c_ads_rows,
        "ab_potential_rows": ab_potential_rows,
        "insights": insight_lines[:6],
        "processed_sku": sorted(
            {
                sku
                for sku in (
                    _to_int(row[0])
                    for row in (critical_a_rows + c_overstock_rows + c_ads_rows)
                    if isinstance(row, list) and row
                )
                if sku > 0
            }
        ),
    }


def _top_skus_from_rows(rows: list[list[Any]], *, limit: int = 5) -> list[int]:
    skus: list[int] = []
    seen: set[int] = set()
    for row in rows:
        if not isinstance(row, list) or not row:
            continue
        sku = _to_int(row[0])
        if sku <= 0 or sku in seen:
            continue
        skus.append(sku)
        seen.add(sku)
        if len(skus) >= limit:
            break
    return skus


def _sku_csv(skus: list[int]) -> str:
    return ", ".join(str(sku) for sku in skus if _to_int(sku) > 0)


def _is_finance_funnel_action(action: dict[str, Any]) -> bool:
    blob = " ".join(
        _text(action.get(key) or "")
        for key in ("priority", "area", "action", "why", "expected_effect")
    ).lower()
    return ("finance" in blob and "funnel" in blob) or ("финанс" in blob and "воронк" in blob)


def build_audit_markdown(facts: dict[str, Any]) -> str:
    finance = facts.get("financial_summary") or {}
    funnel = facts.get("funnel_summary") or {}
    ads = facts.get("ads_summary") or {}
    stock = facts.get("stock_summary") or {}
    search = facts.get("search_insights") or {}
    local_orders_insights = facts.get("local_orders_insights") or {}
    decision = facts.get("decision_layer") or {}
    money_losses = facts.get("money_losses") if isinstance(facts.get("money_losses"), dict) else {}
    inputs = facts.get("inputs") or {}
    sku_profit = facts.get("sku_profit") or []
    actions = facts.get("actions") or []
    profit_view = _profit_view(finance, ads)
    abc = _build_abc_analysis(
        sku_profit=sku_profit,
        profit_without_cogs=bool(finance.get("profit_without_cogs")),
    )
    abc_layer = _build_abc_stock_ads_layer(
        abc_detail_rows=abc.get("detail_rows") or [],
        finance=finance,
        search=search,
    )

    source_label = _text(facts.get("source") or "wb").upper()
    audit_period = _audit_period_view(facts)
    period_label_ru = _text(audit_period.get("label_ru") or "н/д")
    audit_kind = _text(audit_period.get("audit_kind") or "")
    report_date = _date_ru(facts.get("date") or "")
    selected_files = inputs.get("selected_files") if isinstance(inputs.get("selected_files"), dict) else {}
    report_title = f"Аудит кабинета {source_label} за период {period_label_ru}"

    lines: list[str] = []
    lines.append("# Аудит кабинета WB" if source_label == "WB" else f"# Аудит кабинета {source_label}")
    lines.append(f"## за период {period_label_ru}")
    if audit_kind:
        lines.append(audit_kind)
    lines.append("")
    lines.append(f"Дата формирования отчета: {report_date}")
    lines.append(f"Источник: {source_label} (file-based audit)")
    lines.append("")
    _page_break(lines)

    # Executive summary page (after title page).
    lines.append("# КРАТКИЙ ИТОГ ПО КАБИНЕТУ")
    lines.append("")

    search_effective_items = search.get("effective") if isinstance(search.get("effective"), list) else []
    growth_hypotheses_items = search.get("growth_hypotheses") if isinstance(search.get("growth_hypotheses"), list) else []
    regions_over_150 = facts.get("logistics_regions_over_150")
    regions_over_150_count = len(regions_over_150) if isinstance(regions_over_150, list) else 0

    period_days = 0
    period_from = _parse_iso_date(audit_period.get("date_from"))
    period_to = _parse_iso_date(audit_period.get("date_to"))
    if period_from and period_to:
        period_days = abs((period_to - period_from).days) + 1
    if period_days <= 0:
        raw_period = facts.get("period") if isinstance(facts.get("period"), dict) else {}
        period_days = _to_int(raw_period.get("days"))
    if period_days <= 0:
        period_days = 7

    # Weekly audits are normalized to month by x4.
    month_multiplier = 4.0 if period_days <= 8 else (30.0 / float(period_days))

    ads_loss_period = _to_float(search.get("total_leak_spend"))
    if ads_loss_period is None or ads_loss_period <= 0:
        ads_loss_period = _to_float((money_losses or {}).get("ads_waste_rub")) or 0.0
    ads_loss_monthly = float(ads_loss_period) * float(month_multiplier)

    logistics_summary = facts.get("logistics_summary") if isinstance(facts.get("logistics_summary"), dict) else {}
    potential_overpay_due_localization = _to_float(logistics_summary.get("potential_overpay_due_localization"))
    delta_per_unit = _to_float(logistics_summary.get("delta_vs_target_per_order"))
    if delta_per_unit is None:
        avg_logistics_cost = _to_float(logistics_summary.get("avg_logistics_cost_est"))
        target_logistics_cost = _to_float(logistics_summary.get("target_avg_logistics_cost"))
        if avg_logistics_cost is not None and target_logistics_cost is not None:
            delta_per_unit = float(avg_logistics_cost) - float(target_logistics_cost)
    if delta_per_unit is None:
        delta_per_unit = 0.0
    if delta_per_unit < 0:
        delta_per_unit = 0.0

    buyouts_count = _to_int(funnel.get("buys"))
    if buyouts_count <= 0:
        buyouts_count = _to_int(finance.get("sales_qty"))
    if (
        buyouts_count <= 0
        and delta_per_unit is not None
        and delta_per_unit > 0
        and potential_overpay_due_localization is not None
        and potential_overpay_due_localization > 0
    ):
        buyouts_count = max(0, int(round(float(potential_overpay_due_localization) / float(delta_per_unit))))

    logistics_loss_period = float(delta_per_unit) * float(max(buyouts_count, 0))
    monthly_logistics_loss = float(logistics_loss_period) * float(month_multiplier)

    total_losses_monthly = float(ads_loss_monthly) + float(monthly_logistics_loss)
    yearly_loss = float(total_losses_monthly) * 12.0

    frozen_stock_value = _to_float((money_losses or {}).get("frozen_stock_value_rub")) or 0.0

    def _rub_short(amount: float) -> str:
        return f"{int(round(float(amount or 0.0))):,}".replace(",", " ")

    lines.append("## 💸 Потери")
    lines.append(f"Вы теряете ~{_rub_short(total_losses_monthly)} ₽ в месяц")
    lines.append(f"• Неэффективная реклама: {_rub_short(ads_loss_monthly)} ₽")
    lines.append(f"• Переплата за логистику: {_rub_short(monthly_logistics_loss)} ₽")
    lines.append("")
    lines.append("Расчет логистики:")
    lines.append(f"Разница: {_rub_short(delta_per_unit)} ₽ на выкуп")
    lines.append(f"{_rub_short(delta_per_unit)} × {buyouts_count} = {_rub_short(logistics_loss_period)} ₽ за период")
    multiplier_text = (
        str(int(round(month_multiplier)))
        if abs(float(month_multiplier) - float(round(month_multiplier))) < 1e-9
        else f"{month_multiplier:.2f}"
    )
    lines.append(f"{_rub_short(logistics_loss_period)} × {multiplier_text} = {_rub_short(monthly_logistics_loss)} ₽ в месяц")
    lines.append("")

    lines.append("## 📈 Точки роста")
    if len(search_effective_items) > 0:
        lines.append(
            "Есть запросы с подтвержденным спросом (заказы + низкий ДРР)"
        )
        lines.append("→ их можно масштабировать")
    if len(growth_hypotheses_items) > 0:
        lines.append("Найдены запросы с CTR > 15% без рекламы")
        lines.append("→ стоит протестировать")
    else:
        lines.append("Новые гипотезы роста не выявлены — требуется накопление данных")
    lines.append("")

    lines.append("## ⚠️ Риски")
    if frozen_stock_value > 0:
        lines.append(f"Заморожено в остатках: {_rub_short(frozen_stock_value)} ₽")
    elif _to_int((money_losses or {}).get("frozen_stock_sku_count")) > 0:
        lines.append(
            f"Есть залежавшиеся остатки: {_to_int((money_losses or {}).get('frozen_stock_sku_count'))} SKU без нормального движения"
        )
    if monthly_logistics_loss > 0:
        lines.append(f"Есть риск дорогой логистики: ~{_rub_short(monthly_logistics_loss)} ₽ потерь в месяц")
    elif regions_over_150_count > 0:
        lines.append(f"Есть дорогая логистика: {regions_over_150_count} регионов с повышенным коэффициентом")
    if frozen_stock_value <= 0 and monthly_logistics_loss <= 0 and regions_over_150_count <= 0:
        lines.append("Критичные риски по остаткам и логистике по текущим данным не выявлены.")
    lines.append("")

    lines.append("## 🎯 Главный вывод")
    if ads_loss_monthly > 0:
        main_problem = "слив бюджета на рекламе"
    elif frozen_stock_value > 0:
        main_problem = "замороженные деньги в остатках"
    elif monthly_logistics_loss > 0 or regions_over_150_count > 0:
        main_problem = "дорогая логистика"
    else:
        main_problem = "критичных потерь не выявлено"

    if len(growth_hypotheses_items) > 0:
        main_growth = "запуск тестов по запросам с высоким CTR без рекламы"
    elif len(search_effective_items) > 0:
        main_growth = "масштабирование эффективных поисковых запросов"
    else:
        main_growth = "накопление данных и тест новых гипотез"

    lines.append(f"Основная проблема — {main_problem}")
    lines.append(f"Основная точка роста — {main_growth}")
    lines.append("")

    lines.append("## 💡")
    lines.append("Если ничего не менять:")
    lines.append(f"→ за год это ~{_rub_short(yearly_loss)} ₽ потерь")
    lines.append("")
    _page_break(lines)

    lines.append("## Оглавление")
    lines.append(f"Период отчета: {period_label_ru}")
    if audit_kind:
        lines.append(f"Тип аудита: {audit_kind}")
    lines.append("")
    lines.append("- Executive Summary: краткий итог по кабинету")
    lines.append("- 1. KPI и инсайты")
    lines.append("- 2. 💰 Финансы: сколько реально зарабатываете")
    lines.append("- 3. 📊 Воронка продаж: путь до выкупа")
    lines.append("- 4. 📢 Реклама: платите - но не всегда за результат")
    lines.append("- 5. 📦 Остатки: деньги заморожены в складе")
    lines.append("- 6. Ассортимент / SKU")
    lines.append("- 7. ТОП-5 SKU: где зарабатываете и где теряете")
    lines.append("- 8. Локальные заказы и размещение товара")
    lines.append("- 9. Логистика: где переплачиваете")
    lines.append("- 10. Переплата за логистику")
    lines.append("- 11. Потери из-за плохой локализации")
    lines.append("- 12. Поисковые запросы")
    lines.append("- 13. План действий / рекомендации")
    lines.append("")

    lines.append("### Источники (файлы)")
    source_rows = [
        ["Финансы", _source_file_cell(selected_files.get("finance"))],
        ["Воронка", _source_file_cell(selected_files.get("funnel"))],
        ["Лента заказов", _source_file_cell(selected_files.get("orders"))],
        ["Реклама", _source_file_cell(selected_files.get("ads"))],
        ["Остатки", _source_file_cell(selected_files.get("stocks"))],
        ["Поиск", _source_file_cell(selected_files.get("search"))],
        ["COGS", _source_file_cell(selected_files.get("cogs"))],
    ]
    _append_markdown_table(lines, ["Блок", "Файл"], source_rows)

    _page_break(lines)

    lines.append(f"# {report_title}")
    lines.append("")
    lines.append("## 1. KPI и инсайты")
    revenue_kpi = _to_float(finance.get("gross_revenue"))
    clean_profit_kpi = _to_float(profit_view.get("clean_profit"))
    clean_margin_ratio_kpi = _to_float(profit_view.get("clean_margin"))
    roas_kpi = _to_float(ads.get("roas"))
    spend_kpi = _to_float(ads.get("spend"))
    sales_revenue_kpi = _to_float(funnel.get("revenue_orders"))
    if sales_revenue_kpi is None or sales_revenue_kpi <= 0:
        sales_revenue_kpi = _to_float(funnel.get("revenue_buyouts"))
    if sales_revenue_kpi is None or sales_revenue_kpi <= 0:
        sales_revenue_kpi = _to_float(finance.get("gross_revenue"))
    drr_ads_kpi = _to_float(ads.get("drr"))
    drr_ads_kpi_pct = (float(drr_ads_kpi) * 100.0) if drr_ads_kpi is not None else None
    drr_cabinet_kpi = (spend_kpi / sales_revenue_kpi) if spend_kpi is not None and sales_revenue_kpi and sales_revenue_kpi > 0 else None
    drr_cabinet_kpi_pct = (float(drr_cabinet_kpi) * 100.0) if drr_cabinet_kpi is not None else None
    roas_level = _roas_status_level(roas_kpi)
    kpi_cards = [
        {"title": "Выручка", "value": _money(revenue_kpi), "icon": _status_icon("green" if (revenue_kpi or 0) > 0 else "yellow")},
        {"title": "Прибыль", "value": _money(clean_profit_kpi), "icon": _status_icon(_profit_status_level(clean_profit_kpi))},
        {"title": "Маржа", "value": _pct_ratio(clean_margin_ratio_kpi), "icon": _status_icon(_margin_status_level_by_pct((clean_margin_ratio_kpi * 100.0) if clean_margin_ratio_kpi is not None else None))},
        {"title": "ROAS", "value": _sanitize_table_cell(ads.get("roas", "н/д")), "icon": _status_icon(roas_level)},
        {"title": "ДРР рекламы (РК)", "value": _fmt_pct(drr_ads_kpi_pct, 1), "icon": _status_icon(_drr_status_level_by_pct(drr_ads_kpi_pct))},
        {"title": "ДРР кабинета", "value": _fmt_pct(drr_cabinet_kpi_pct, 1), "icon": _status_icon(_drr_status_level_by_pct(drr_cabinet_kpi_pct))},
    ]
    lines.append("# \U0001F4CA KPI и инсайты")
    lines.append("### Короткий вывод")
    kpi_insights = _kpi_management_insights(
        decision=decision,
        search=search,
        funnel=funnel,
        profit_view=profit_view,
    )
    for insight in kpi_insights[:4]:
        lines.append(f"- {insight}")
    lines.append("")
    lines.append("Ключевые выводы сформированы на основе анализа данных ниже.")
    lines.append("")
    lines.append("### KPI в цифрах")
    _append_kpi_cards(lines, kpi_cards, columns=4)
    lines.append("")

    cogs_status_kpi = _text(finance.get("cogs_status") or "")
    cogs_total_kpi = _to_float(profit_view.get("cogs_total")) or 0.0
    clean_profit_wo_cogs = _to_float(profit_view.get("clean_profit_without_cogs"))
    cogs_impact_pct = _to_float(profit_view.get("cogs_impact_pct"))
    if cogs_status_kpi in {"full_match", "partial_match"} and clean_profit_wo_cogs is not None:
        lines.append("### Влияние себестоимости")
        lines.append(f"- Прибыль без себестоимости: {_money(clean_profit_wo_cogs)}")
        lines.append(f"- Себестоимость: {_money(cogs_total_kpi)}")
        lines.append(f"- Итоговая прибыль: {_money(profit_view.get('clean_profit'))}")
        lines.append(
            f"- Снижение прибыли: {_fmt_pct(cogs_impact_pct, 1)}"
            if cogs_impact_pct is not None
            else "- Снижение прибыли: н/д"
        )
        lines.append("")

    lines.extend(_where_money_lost_section_lines(decision=decision, abc_layer=abc_layer, facts=facts))
    lines.extend(_unprofitable_sku_section_lines(finance))

    _page_break(lines)

    lines.append("## 2. 💰 Финансы: сколько реально зарабатываете")
    sales_units = _to_int(funnel.get("orders"))
    if sales_units <= 0:
        sales_units = _to_int(finance.get("sales_qty"))
    buyouts_units = _to_int(funnel.get("buys"))
    if buyouts_units <= 0:
        buyouts_units = _to_int(finance.get("sales_qty"))

    roi_main, roi_extra = _roi_line(finance, ads, clean_profit=float(profit_view["clean_profit"]))
    finance_rows = [
        ["Продажи (шт)", sales_units],
        ["Продажи (сумма заказов)", _money(funnel.get("revenue_orders"))],
        ["Выкупы (шт)", buyouts_units],
        ["Выкупы (сумма)", _money(finance.get("gross_revenue"))],
        ["Комиссия WB", _money(finance.get("commission"))],
        ["Логистика", _money(finance.get("logistics"))],
        ["Хранение", _money(finance.get("storage"))],
        ["Себестоимость", _money(finance.get("cogs_total"))],
        ["Реклама", _money(ads.get("spend"))],
        ["Налог", _money(finance.get("tax"))],
        [_text(profit_view["clean_label"]), _money(profit_view.get("clean_profit"))],
        ["Маржа (доля прибыли от выручки)", _pct_ratio(profit_view.get("clean_margin"))],
        ["ROI", _text(roi_main.replace("ROI: ", ""))],
        ["К перечислению", _money(finance.get("payout"))],
    ]
    _append_markdown_table(lines, ["Метрика", "Значение"], finance_rows, align_right={1})
    lines.append("- Комиссия рассчитана по ВЫКУПАМ (данные finance), поэтому может отличаться от интерфейса WB.")
    commission_breakdown = finance.get("commission_breakdown") if isinstance(finance.get("commission_breakdown"), dict) else {}
    if commission_breakdown:
        lines.append("Комиссия WB включает:")
        lines.append(f"- базовое вознаграждение WB: {_money(commission_breakdown.get('base_commission'))}")
        lines.append(f"- выдачу/возврат на ПВЗ: {_money(commission_breakdown.get('pvz_compensation'))}")
        lines.append(
            f"- платежные сервисы / интеграцию: {_money(commission_breakdown.get('payment_services_compensation'))}"
        )
        lines.append(
            f"- дополнительные комиссионные компоненты weekly finance: {_money(commission_breakdown.get('payment_services_compensation_amount'))}"
        )
    cogs_note = _cogs_status_explanation(finance)
    if cogs_note:
        lines.append(f"- {cogs_note}")
    cogs_diag = finance.get("cogs_diagnostics") if isinstance(finance.get("cogs_diagnostics"), dict) else {}
    cogs_coverage = _to_float(cogs_diag.get("cogs_coverage_pct"))
    if cogs_coverage is not None:
        lines.append(f"- Покрытие COGS по SKU продаж: {_fmt_pct(cogs_coverage, 1)}.")
    lines.append("- Чистая прибыль и маржа в этом разделе рассчитаны с учетом рекламных расходов.")
    for extra in roi_extra:
        lines.append(f"- {extra}")
    if finance.get("profit_note"):
        lines.append(f"- {_text(finance.get('profit_note'))}")
    storage_value = _to_float(finance.get("storage"))
    if storage_value == 0.0 and _to_int(finance.get("rows_count")) > 0:
        lines.append("- По исходным строкам finance расход на хранение за период не обнаружен (0.00 RUB).")
    lines.append("- К перечислению — значение из финансового отчета WB (без перерасчета).")
    lines.append("")

    lines.extend(_money_losses_section_lines(money_losses))
    _page_break(lines)

    lines.append("## 3. 📊 Воронка продаж: путь до выкупа")
    impressions = _to_int(funnel.get("impressions"))
    if impressions <= 0:
        fallback_impressions = _extract_funnel_impressions(facts, funnel)
        impressions = _to_int(fallback_impressions)
    impressions_value = impressions if impressions > 0 else None
    clicks_count = _to_int(funnel.get("views"))
    add_to_cart_count = _to_int(funnel.get("add_to_cart"))
    orders_count = _to_int(funnel.get("orders"))
    buyouts_count = _to_int(funnel.get("buys"))
    ctr_ratio = _to_float(funnel.get("ctr"))
    if ctr_ratio is None and impressions_value is not None and impressions_value > 0:
        ctr_ratio = float(clicks_count) / float(impressions_value)
    impressions_text = _to_int(impressions_value) if impressions_value is not None else "н/д (нет данных о показах)"
    ctr_text = _pct_ratio(ctr_ratio) if ctr_ratio is not None else "н/д (нет данных о показах)"
    impressions_source = _text(funnel.get("impressions_source")).lower()
    lines.append("### Визуальная воронка")
    lines.append(f"Показы: **{impressions_text}**")
    lines.append(f"↓ CTR: **{ctr_text}**")
    lines.append(f"Клики: **{clicks_count}**")
    lines.append(f"↓ CR: **{_pct_ratio(funnel.get('cr_cart'))}**")
    lines.append(f"Корзина: **{add_to_cart_count}**")
    lines.append(f"↓ CR: **{_pct_ratio(funnel.get('cr_order'))}**")
    lines.append(f"Заказы: **{orders_count}**")
    lines.append(f"↓ % выкупа: **{_pct_ratio(funnel.get('buyout_rate'))}**")
    lines.append(f"Выкупы: **{buyouts_count}**")
    lines.append("")
    funnel_rows: list[list[Any]] = []
    funnel_rows.extend(
        [
            ["Показы", impressions_text],
            ["Клики (переходы в карточку)", clicks_count],
            ["CTR", ctr_text],
            ["В корзину", add_to_cart_count],
            ["Заказы", orders_count],
            ["Выкупы", buyouts_count],
            ["CR в корзину", _pct_ratio(funnel.get("cr_cart"))],
            ["CR в заказ", _pct_ratio(funnel.get("cr_order"))],
            ["% выкупа", _pct_ratio(funnel.get("buyout_rate"))],
            ["Заказы на сумму", _money(funnel.get("revenue_orders"))],
            ["Выкупы на сумму", _money(finance.get("gross_revenue"))],
        ]
    )
    _append_markdown_table(lines, ["Показатель", "Значение"], funnel_rows, align_right={1})
    if impressions_source == "ads":
        lines.append(
            "- Показы взяты из рекламного отчета (ads stats), т.к. в файле «Воронка продаж» они не найдены."
        )
    lines.append(f"- {_funnel_ctr_conclusion(ctr_ratio)}.")
    lines.append("- % выкупа = выкупы / заказы по данным отчета (может отличаться от WB).")
    lines.append(
        "- **Часть заказов не выкупается**: оборот по заказам обычно выше фактической выручки из finance."
    )
    lines.append("")

    _page_break(lines)

    lines.append("## 4. 📢 Реклама: платите - но не всегда за результат")
    drr_value = _to_float(ads.get("drr"))
    drr_text = _pct_ratio(drr_value) if drr_value is not None else "н/д"
    spend_value = _to_float(ads.get("spend"))
    sales_revenue = _to_float(funnel.get("revenue_orders"))
    if sales_revenue is None or sales_revenue <= 0:
        sales_revenue = _to_float(funnel.get("revenue_buyouts"))
    if sales_revenue is None or sales_revenue <= 0:
        sales_revenue = _to_float(finance.get("gross_revenue"))
    drr_cabinet = (spend_value / sales_revenue) if sales_revenue and sales_revenue > 0 else None
    drr_cabinet_text = _pct_ratio(drr_cabinet) if drr_cabinet is not None else "н/д"
    ads_rows = [
        ["Расход", _money(ads.get("spend"))],
        ["Показы", _to_int(ads.get("impressions"))],
        ["Клики", _to_int(ads.get("clicks"))],
        ["CTR", _pct_ratio(ads.get("ctr"))],
        ["CPC", _money(ads.get("cpc"))],
        ["CPM", _money(ads.get("cpm"))],
        ["Выручка от рекламы (по версии WB)", _money(ads.get("revenue_attr"))],
        ["ROAS", _sanitize_table_cell(ads.get("roas", "н/д"))],
        ["ДРР (по рекламной выручке)", drr_text],
        ["ДРР по кабинету", drr_cabinet_text],
    ]
    _append_markdown_table(lines, ["Метрика", "Значение"], ads_rows, align_right={1})
    drr_cabinet_pct = (float(drr_cabinet) * 100.0) if drr_cabinet is not None else None
    drr_signal = _status_icon(_drr_status_level_by_pct(drr_cabinet_pct))
    lines.append(f"- **ДРР по кабинету: {drr_cabinet_text} {drr_signal}**.")
    lines.append(f"- {_ctr_benchmark_text(ads.get('ctr'))}")
    lines.append(f"- {_drr_benchmark_text(drr_cabinet)}")
    lines.append(f"- {_roas_benchmark_text(ads.get('roas'))}")

    attributed_revenue = _to_float(ads.get("revenue_attr"))
    factual_revenue = _to_float(finance.get("gross_revenue"))
    lines.append(
        "- Выручка от рекламы (по версии WB): выручка, которую WB связывает с рекламой (это заказы, не все из них выкуплены)."
    )
    if attributed_revenue is not None and factual_revenue is not None and attributed_revenue > factual_revenue:
        lines.append(
            "- Она может быть выше фактической выручки, потому что часть заказов не была выкуплена."
        )
    leaks = decision.get("ads_leaks") or []
    leaks_spend = sum(
        (_to_float(item.get("spend")) or 0.0)
        for item in leaks
        if isinstance(item, dict) and _to_int(item.get("orders")) == 0
    )
    if (spend_value or 0.0) <= 0 or leaks_spend <= 0:
        lines.append("- Данные не подтверждают значимые потери рекламы в этом периоде.")
    else:
        lines.append(f"- **Найдено {len(leaks)} рекламных связок/запросов без заказов** (потери ~{_money(leaks_spend)}).")
    lines.append("")

    _page_break(lines)

    lines.append("## 5. 📦 Остатки: деньги заморожены в складе")
    stock_rows = [
        ["Остатки, шт", _to_int(stock.get("stock_units"))],
        ["SKU/позиций", _to_int(stock.get("sku_count"))],
        ["Дни покрытия", _sanitize_table_cell(stock.get("days_of_cover"))],
        ["Порог, дней", _sanitize_table_cell(stock.get("threshold_days"))],
        ["Риск дефицита", "да" if bool(stock.get("risk_of_oos")) else "нет"],
    ]
    _append_markdown_table(lines, ["Показатель", "Значение"], stock_rows, align_right={1})
    stock_risk_icon = _icon_red() if bool(stock.get("risk_of_oos")) else _icon_green()
    lines.append(f"- **Риск дефицита: {'да' if bool(stock.get('risk_of_oos')) else 'нет'} {stock_risk_icon}**.")

    dead_stock = decision.get("dead_stock") or []
    if dead_stock:
        dead_rows = [
            [
                item.get("sku"),
                _to_int(item.get("stock_qty")),
                _to_int(item.get("orders")),
                _to_int(item.get("buyouts")),
            ]
            for item in dead_stock[:10]
        ]
        lines.append("SKU с зависшими остатками (top-10):")
        _append_markdown_table(lines, ["SKU", "Остаток, шт", "Заказы", "Выкупы"], dead_rows, align_right={1, 2, 3})
    else:
        lines.append("- Зависшие остатки без продаж не обнаружены.")
        lines.append("")

    _page_break(lines)

    lines.append("## 6. Ассортимент / SKU")
    lines.append("### TOP вклад в прибыль")
    if sku_profit:
        sku_profit_label = "Прибыль без COGS" if finance.get("profit_without_cogs") else "Прибыль"
        top_profit_rows = [
            [
                item.get("sku"),
                _money(item.get("profit")),
                _money(item.get("revenue")),
                _to_int(item.get("stock_qty")),
            ]
            for item in sku_profit[:10]
        ]
        _append_markdown_table(
            lines,
            ["SKU", sku_profit_label, "Выручка", "Остаток, шт"],
            top_profit_rows,
            align_right={1, 2, 3},
        )
    else:
        lines.append("- Недостаточно данных для расчета TOP SKU по прибыли.")
        lines.append("")

    lines.append("### ABC-анализ")
    if abc.get("available"):
        lines.append(f"- {_text(abc.get('basis_note'))}")
        _append_markdown_table(
            lines,
            ["Категория", "SKU, шт", "Доля метрики", "Комментарий"],
            abc.get("summary_rows") or [],
            align_right={1, 2},
        )

        lines.append("### SKU по категориям ABC")
        detail_rows = [
            [
                row.get("sku"),
                row.get("category"),
                _money(row.get("revenue")),
                _money(row.get("profit")),
                _fmt_pct(_to_float(row.get("share_pct")), 2),
                _to_int(row.get("stock_qty")),
            ]
            for row in (abc.get("detail_rows") or [])
        ]
        _append_markdown_table(
            lines,
            ["SKU", "Категория", "Выручка", "Прибыль", "Доля", "Остаток, шт"],
            detail_rows,
            align_right={2, 3, 4, 5},
        )
        for insight in (abc.get("insights") or []):
            lines.append(f"- {insight}")
        if _to_int(abc.get("filtered_dead_sku_count")) > 0:
            lines.append("- Из ABC-анализа исключены SKU без продаж, прибыли и остатков (неактивные позиции).")
        lines.append("")
    else:
        lines.append("- Недостаточно данных для построения ABC-анализа.")
        lines.append("")

    lines.append("### ABC + остатки + реклама")
    lines.append("#### Критичные A-SKU")
    if abc_layer.get("critical_a_rows"):
        _append_markdown_table(
            lines,
            ["SKU", "Категория", "Остаток, шт", "Продажи/выкупы", "Риск", "Действие"],
            abc_layer.get("critical_a_rows") or [],
            align_right={2, 3},
        )
    else:
        lines.append("- Критичные A-SKU по текущей эвристике не выявлены.")
        lines.append("")

    lines.append("#### C-SKU с избыточными остатками")
    if abc_layer.get("c_overstock_rows"):
        _append_markdown_table(
            lines,
            ["SKU", "Категория", "Остаток, шт", "Заказы", "Выручка", "Рекомендация"],
            abc_layer.get("c_overstock_rows") or [],
            align_right={2, 3, 4},
        )
    else:
        lines.append("- C-SKU с избыточными остатками не выявлены.")
        lines.append("")

    lines.append("#### C-SKU с рекламной активностью")
    if abc_layer.get("c_ads_rows"):
        _append_markdown_table(
            lines,
            ["SKU", "Категория", "Рекламный сигнал", "Продажи/заказы", "Вывод"],
            abc_layer.get("c_ads_rows") or [],
            align_right={3},
        )
    else:
        lines.append("- C-SKU с заметной рекламной активностью не выявлены.")
        lines.append("")

    lines.append("#### SKU, которые можно усиливать рекламой")
    if abc_layer.get("ab_potential_rows"):
        _append_markdown_table(
            lines,
            ["SKU", "Категория", "Основание", "Рекомендация"],
            abc_layer.get("ab_potential_rows") or [],
        )
    else:
        lines.append("- Явных SKU A/B для усиления рекламы по доступным сигналам не найдено.")
        lines.append("")

    for item in (abc_layer.get("insights") or []):
        lines.append(f"- {item}")
    lines.append("")

    lines.append("### SKU с остатками и слабым движением")
    sku_without_sales = decision.get("sku_without_sales") or []
    processed_sku = {_to_int(sku) for sku in (abc_layer.get("processed_sku") or []) if _to_int(sku) > 0}
    filtered_sku_without_sales = [
        item
        for item in sku_without_sales
        if isinstance(item, dict) and _to_int(item.get("sku")) not in processed_sku
    ]
    if filtered_sku_without_sales:
        rows_without_sales = [
            [
                item.get("sku"),
                _to_int(item.get("stock_qty")),
                _to_int(item.get("orders")),
                _money(item.get("revenue")),
            ]
            for item in filtered_sku_without_sales[:10]
        ]
        _append_markdown_table(
            lines,
            ["SKU", "Остаток, шт", "Заказы", "Выручка"],
            rows_without_sales,
            align_right={1, 2, 3},
        )
    else:
        lines.append("- Дополнительные SKU со слабым движением не выявлены (основные случаи отражены выше).")
        lines.append("")

    lines.append("### SKU с низкой маржинальностью")
    unprofitable_sku = decision.get("unprofitable_sku") or []
    if unprofitable_sku:
        low_margin_rows = [
            [
                item.get("sku"),
                _money(item.get("profit")),
                _pct_ratio(item.get("margin")),
            ]
            for item in unprofitable_sku[:10]
        ]
        _append_markdown_table(lines, ["SKU", "Прибыль", "Маржа"], low_margin_rows, align_right={1, 2})
    else:
        lines.append("- SKU со сниженной маржинальностью не выявлены.")
        lines.append("")

    lines.extend(_sku_efficiency_section_lines(facts=facts))
    lines.extend(_top5_unit_economics_section_lines(facts))
    lines.append("")

    _page_break(lines)

    local_buyouts_total = _to_int(funnel.get("buys"))
    if local_buyouts_total <= 0:
        local_buyouts_total = _to_int(finance.get("sales_qty"))
    lines.extend(_local_orders_section_lines(local_orders_insights, total_buyouts=local_buyouts_total))

    _page_break(lines)

    lines.extend(_region_logistics_section_lines(facts))

    _page_break(lines)

    lines.extend(_logistics_overpayment_section_lines(facts))

    _page_break(lines)

    lines.extend(_localization_loss_section_lines(facts))

    _page_break(lines)

    search_effective_rows: list[dict[str, Any]] = []
    search_ineffective_rows: list[dict[str, Any]] = []
    search_potential_rows: list[dict[str, Any]] = []
    search_disable_targets: list[str] = []
    search_scale_targets: list[str] = []
    search_optimize_targets: list[str] = []
    search_growth_targets: list[str] = []
    search_ineffective_spend_total = 0.0
    search_scale_profit_total = 0.0
    search_potential_profit_total: float | None = None

    lines.append("## 12. Поисковые запросы")
    search_status = str(search.get("status") or "")
    if search_status == "ok":
        base_rows = search.get("base_rows") if isinstance(search.get("base_rows"), list) else []
        effective_rows = search.get("effective") if isinstance(search.get("effective"), list) else []
        weak_rows = search.get("weak") if isinstance(search.get("weak"), list) else []
        unprofitable_rows = search.get("unprofitable") if isinstance(search.get("unprofitable"), list) else []
        growth_rows = search.get("growth_hypotheses") if isinstance(search.get("growth_hypotheses"), list) else []

        search_effective_rows = [row for row in effective_rows if isinstance(row, dict)]
        search_potential_rows = [row for row in weak_rows if isinstance(row, dict)]
        search_ineffective_rows = [row for row in unprofitable_rows if isinstance(row, dict)]
        growth_rows = [row for row in growth_rows if isinstance(row, dict)]

        if not search_effective_rows and not search_potential_rows and not search_ineffective_rows:
            valid_rows = [row for row in base_rows if isinstance(row, dict)]
            search_effective_rows = [row for row in valid_rows if _text(row.get("bucket")) == "effective"]
            search_potential_rows = [row for row in valid_rows if _text(row.get("bucket")) == "weak"]
            search_ineffective_rows = [row for row in valid_rows if _text(row.get("bucket")) == "unprofitable"]

        query_to_sku: dict[str, str] = {}
        query_to_rk: dict[str, str] = {}
        for row in base_rows:
            if not isinstance(row, dict):
                continue
            query_norm = _text(row.get("query")).strip().lower()
            if not query_norm:
                continue
            sku_label = _search_sku_label(row)
            if query_norm not in query_to_sku and sku_label and sku_label.lower() != "н/д":
                query_to_sku[query_norm] = sku_label
            rk_label = _search_rk_label(row)
            if query_norm not in query_to_rk and rk_label:
                query_to_rk[query_norm] = rk_label

        orders_data = search.get("orders_data") if isinstance(search.get("orders_data"), dict) else {}
        orders_available = bool(orders_data.get("available"))
        orders_message = _text(orders_data.get("message"))
        orders_source = _text(orders_data.get("source"))

        rows_with_spend = [
            row
            for row in base_rows
            if isinstance(row, dict) and (_to_float(row.get("spend")) or 0.0) > 0
        ]

        search_ineffective_spend_total = round(
            sum(_to_float(row.get("spend")) for row in search_ineffective_rows),
            2,
        )
        search_scale_profit_total = round(
            sum(max(_to_float(row.get("revenue")) - _to_float(row.get("spend")), 0.0) for row in search_effective_rows),
            2,
        )
        # Потенциал экономии: довести слабые запросы до DRR 20%.
        search_potential_profit_total = round(
            sum(
                max(_to_float(row.get("spend")) - (_to_float(row.get("revenue")) * 0.20), 0.0)
                for row in search_potential_rows
                if _to_float(row.get("revenue")) > 0
            ),
            2,
        )

        summary_rows = [
            ["Всего запросов", len(base_rows)],
            ["С рекламным расходом (spend > 0)", len(rows_with_spend)],
            ["A. Убыточные (spend>0, orders=0)", len(search_ineffective_rows)],
            ["B. Слабые (spend>0, orders>0, DRR>25%)", len(search_potential_rows)],
            ["C. Эффективные (orders>0, DRR<20%)", len(search_effective_rows)],
            ["Потери на убыточных запросах", _money(search_ineffective_spend_total)],
        ]
        _append_markdown_table(lines, ["Показатель", "Значение"], summary_rows, align_right={1})

        lines.append(f"Найдено {len(search_ineffective_rows)} убыточных запросов:")
        lines.append(f"- Потери: ~{_money(search_ineffective_spend_total)}")
        lines.append("- Рекомендуется отключить")
        if not orders_available:
            lines.append("- нет данных о заказах по запросам")
        elif orders_source:
            lines.append(f"- Источник заказов по запросам: {orders_source}")
        lines.append("- Полный список запросов сохранен в JSON (search_insights).")
        lines.append("")

        def _group_rows_by_sku_cell(rows: list[dict[str, Any]]) -> tuple[list[tuple[dict[str, Any], str, str]], bool]:
            selected = [item for item in rows[:10] if isinstance(item, dict)]
            has_rk = any(_search_rk_label(item) for item in selected)
            seen_sku: set[str] = set()
            grouped: list[tuple[dict[str, Any], str, str]] = []
            for item in selected:
                sku_label = _search_sku_label(item)
                sku_cell = "" if sku_label in seen_sku else sku_label
                seen_sku.add(sku_label)
                grouped.append((item, sku_cell, _search_rk_label(item)))
            return grouped, has_rk

        def _growth_sku_label(item: dict[str, Any]) -> str:
            sku_label = _search_sku_label(item)
            if sku_label and sku_label.lower() != "н/д":
                return sku_label
            query_norm = _text(item.get("query")).strip().lower()
            return query_to_sku.get(query_norm) or "н/д"

        def _growth_rk_label(item: dict[str, Any]) -> str:
            direct = _search_rk_label(item)
            if direct:
                return direct
            query_norm = _text(item.get("query")).strip().lower()
            return query_to_rk.get(query_norm, "")

        def _render_unprofitable_table(rows: list[dict[str, Any]]) -> None:
            lines.append("### A. TOP-10 убыточных запросов")
            if not rows:
                lines.append("- Убыточные запросы не найдены.")
                lines.append("")
                return
            grouped_rows, has_rk = _group_rows_by_sku_cell(rows)
            table_rows: list[list[Any]] = []
            for item, sku_cell, rk_cell in grouped_rows:
                row_cells: list[Any] = [
                    sku_cell,
                    _text(item.get("query")),
                ]
                if has_rk:
                    row_cells.append(rk_cell)
                row_cells.extend(
                    [
                        _to_int(item.get("impressions")),
                        _to_int(item.get("clicks")),
                        _fmt_pct(_to_float_or_none(item.get("ctr")), 2),
                        _money(item.get("spend")),
                        _to_int(item.get("orders")),
                        _text(item.get("action") or "Отключить"),
                    ]
                )
                table_rows.append(row_cells)

            headers = ["Артикул", "Запрос"]
            if has_rk:
                headers.append("РК")
            headers.extend(["Показы", "Клики", "CTR", "Расход", "Заказы", "Действие"])
            start_num = 3 if has_rk else 2
            _append_markdown_table(
                lines,
                headers,
                table_rows,
                align_right={start_num, start_num + 1, start_num + 2, start_num + 3, start_num + 4},
            )

        def _render_bucket_table(title: str, rows: list[dict[str, Any]], default_action: str) -> None:
            lines.append(title)
            if not rows:
                lines.append("- Данных для таблицы нет.")
                lines.append("")
                return
            grouped_rows, has_rk = _group_rows_by_sku_cell(rows)
            table_rows: list[list[Any]] = []
            for item, sku_cell, rk_cell in grouped_rows:
                row_cells: list[Any] = [
                    sku_cell,
                    _text(item.get("query")),
                ]
                if has_rk:
                    row_cells.append(rk_cell)
                row_cells.extend(
                    [
                        _to_int(item.get("impressions")),
                        _to_int(item.get("clicks")),
                        _fmt_pct(_to_float_or_none(item.get("ctr")), 2),
                        _money(item.get("spend")),
                        _to_int(item.get("orders")),
                        _pct_ratio(item.get("drr")),
                        _text(item.get("action") or default_action),
                    ]
                )
                table_rows.append(row_cells)

            headers = ["Артикул", "Запрос"]
            if has_rk:
                headers.append("РК")
            headers.extend(["Показы", "Клики", "CTR", "Расход", "Заказы", "ДРР", "Действие"])
            start_num = 3 if has_rk else 2
            _append_markdown_table(
                lines,
                headers,
                table_rows,
                align_right={start_num, start_num + 1, start_num + 2, start_num + 3, start_num + 4, start_num + 5},
            )

        _render_unprofitable_table(search_ineffective_rows)
        lines.append("Слабые запросы — есть заказы, но высокая стоимость привлечения (высокий ДРР)")
        lines.append("")
        _render_bucket_table("### B. TOP-10 слабых запросов", search_potential_rows, "Снизить ставку")
        _render_bucket_table("### C. TOP-10 эффективных запросов", search_effective_rows, "Масштабировать")

        lines.append("### 🚀 D. Гипотезы роста")
        if growth_rows:
            lines.append("Найдены запросы с высоким CTR без рекламы:")
            lines.append("→ пользователи активно кликают")
            lines.append("→ спрос подтвержден")
            lines.append("")
            lines.append("Рекомендуется:")
            lines.append("запустить рекламу и протестировать эти запросы")
            lines.append("")

            selected_growth_rows = [item for item in growth_rows[:10] if isinstance(item, dict)]
            has_rk = any(_growth_rk_label(item) for item in selected_growth_rows)
            seen_sku: set[str] = set()
            growth_table_rows: list[list[Any]] = []
            for item in selected_growth_rows:
                sku_label = _growth_sku_label(item)
                sku_cell = "" if sku_label in seen_sku else sku_label
                seen_sku.add(sku_label)
                row_cells: list[Any] = [
                    sku_cell,
                    _text(item.get("query")),
                ]
                if has_rk:
                    row_cells.append(_growth_rk_label(item))
                row_cells.extend(
                    [
                        _to_int(item.get("impressions")),
                        _to_int(item.get("clicks")),
                        _fmt_pct(_to_float_or_none(item.get("ctr")), 2),
                        "нет",
                        "Протестировать",
                    ]
                )
                growth_table_rows.append(row_cells)

            headers = ["Артикул", "Запрос"]
            if has_rk:
                headers.append("РК")
            headers.extend(["Показы", "Клики", "CTR", "Реклама", "Действие"])
            start_num = 3 if has_rk else 2
            _append_markdown_table(
                lines,
                headers,
                growth_table_rows,
                align_right={start_num, start_num + 1, start_num + 2},
            )
        else:
            lines.append("Запросов с высоким CTR без рекламы не найдено")
            lines.append("")

        search_disable_targets = _search_target_labels(search_ineffective_rows, limit=7)
        search_scale_targets = _search_target_labels(search_effective_rows, limit=7)
        search_optimize_targets = _search_target_labels(search_potential_rows, limit=7)
        search_growth_targets = _search_target_labels(growth_rows, limit=7)
    elif search_status == "missing":
        lines.append("- Отчет поисковых запросов не предоставлен.")
        lines.append("- Блок не пустой: без search-файла невозможно построить классификацию A/B/C по запросам.")
        lines.append("")
    else:
        parse_diag = search.get("parse_diagnostics") or {}
        lines.append(
            f"- Файл search найден, но данные не разобраны: status={search_status}, message={_text(search.get('message'))}."
        )
        lines.append(
            f"- Диагностика parse: sheet={parse_diag.get('sheet')}, header_row={parse_diag.get('header_row')}, rows_parsed={parse_diag.get('rows_parsed')}."
        )
        lines.append("- Блок не пустой: исправьте формат search-файла, затем пересоберите аудит.")
        lines.append("")

    _page_break(lines)

    lines.append("## 13. План действий / рекомендации")
    action_rows: list[list[str]] = []

    def _append_action_row(priority: str, area: str, action_text: str, expected_effect: str) -> None:
        normalized_action = _text(action_text)
        if not normalized_action:
            return
        action_rows.append(
            [
                _text(priority),
                _text(area),
                normalized_action,
                _text(expected_effect),
            ]
        )

    c_overstock_skus = _top_skus_from_rows(abc_layer.get("c_overstock_rows") or [], limit=5)
    c_ads_skus = _top_skus_from_rows(abc_layer.get("c_ads_rows") or [], limit=5)
    ab_potential_skus = _top_skus_from_rows(abc_layer.get("ab_potential_rows") or [], limit=5)
    critical_a_skus = _top_skus_from_rows(abc_layer.get("critical_a_rows") or [], limit=5)

    if c_overstock_skus:
        _append_action_row(
            "P0",
            "stock",
            f"Распределить или распродать остатки по SKU: {_sku_csv(c_overstock_skus)}",
            "Снижение замороженных остатков и ускорение оборачиваемости.",
        )
    if c_ads_skus:
        _append_action_row(
            "P0",
            "ads",
            f"Отключить или снизить рекламу по SKU: {_sku_csv(c_ads_skus)}",
            "Сокращение рекламных расходов без заказов.",
        )
    if search_disable_targets:
        _append_action_row(
            "P0",
            "search",
            f"Отключить/снизить ставки по поисковым запросам: {', '.join(search_disable_targets[:5])}",
            (
                f"Сокращение расходов по запросам с кликами без заказов (~{_money(search_ineffective_spend_total)} за период)."
                if search_ineffective_spend_total >= 100.0
                else "Данные не подтверждают значимые потери по поисковым запросам (менее 100 RUB)."
            ),
        )

    for action in actions:
        if not isinstance(action, dict) or not _is_finance_funnel_action(action):
            continue
        _append_action_row(
            _text(action.get("priority") or ""),
            _text(action.get("area") or ""),
            _text(action.get("action") or ""),
            _text(action.get("expected_effect") or ""),
        )

    if ab_potential_skus:
        _append_action_row(
            "P1",
            "ads",
            f"Усилить рекламу по SKU: {_sku_csv(ab_potential_skus)}",
            "Рост заказов за счет SKU с подтвержденным потенциалом.",
        )
    if critical_a_skus:
        _append_action_row(
            "P1",
            "stock",
            f"Контролировать остатки и пополнение по SKU: {_sku_csv(critical_a_skus)}",
            "Снижение риска дефицита по ключевым SKU категории A.",
        )
    if search_scale_targets:
        _append_action_row(
            "P1",
            "search",
            f"Усилить ставки по поисковым запросам: {', '.join(search_scale_targets[:5])}",
            (
                f"Рост заказов и прибыли по уже конверсионным запросам (текущая оценка прибыли ~{_money(search_scale_profit_total)})."
                if search_scale_profit_total >= 100.0
                else "Запросы конверсионные, но значимый денежный эффект пока не подтвержден (менее 100 RUB)."
            ),
        )
    if search_optimize_targets:
        _append_action_row(
            "P1",
            "search",
            f"Снизить ставки по слабым поисковым запросам: {', '.join(search_optimize_targets[:5])}",
            (
                f"Снижение ДРР и экономия бюджета по слабым запросам (потенциал экономии ~{_money(search_potential_profit_total)})."
                if (search_potential_profit_total or 0.0) >= 100.0
                else "Слабые запросы выявлены, но значимая экономия пока не подтверждена (менее 100 RUB)."
            ),
        )
    if search_growth_targets:
        _append_action_row(
            "P1",
            "search",
            f"Протестировать новые поисковые запросы без рекламы: {', '.join(search_growth_targets[:5])}",
            "Найден подтвержденный спрос (высокий CTR без рекламы) — можно открыть новый источник заказов.",
        )

    for action in actions:
        if not isinstance(action, dict):
            continue
        area = _text(action.get("area") or "").lower()
        if area in {"ads", "stock"}:
            continue
        if _is_finance_funnel_action(action):
            continue
        _append_action_row(
            _text(action.get("priority") or ""),
            _text(action.get("area") or ""),
            _text(action.get("action") or ""),
            _text(action.get("expected_effect") or ""),
        )

    unique_action_rows: list[list[str]] = []
    seen_actions: set[str] = set()
    for row in action_rows:
        action_key = _text(row[2]).lower()
        if not action_key or action_key in seen_actions:
            continue
        seen_actions.add(action_key)
        unique_action_rows.append(row)

    if unique_action_rows:
        _append_markdown_table(
            lines,
            ["Приоритет", "Блок", "Действие", "Ожидаемый эффект"],
            unique_action_rows,
        )
    else:
        lines.append("- Рекомендации не сформированы: недостаточно данных.")
        lines.append("")

    lines.append("")
    lines.append("## 🚀 Итог: что делать")
    top5_payload = facts.get("top5_sku_unit_economics") if isinstance(facts.get("top5_sku_unit_economics"), dict) else {}
    top5_items = top5_payload.get("items") if isinstance(top5_payload.get("items"), list) else []
    dead_stock = decision.get("dead_stock") if isinstance(decision.get("dead_stock"), list) else []
    unprofitable_sku = decision.get("unprofitable_sku") if isinstance(decision.get("unprofitable_sku"), list) else []

    cut_ads_skus = _top_skus_from_rows(abc_layer.get("c_ads_rows") or [], limit=5)
    boost_ads_skus = _top_skus_from_rows(abc_layer.get("ab_potential_rows") or [], limit=5)
    sell_stock_skus = _top_skus_from_rows(abc_layer.get("c_overstock_rows") or [], limit=5)
    risk_skus = []

    for item in dead_stock[:20]:
        sku = _to_int((item or {}).get("sku"))
        if sku > 0 and sku not in sell_stock_skus:
            sell_stock_skus.append(sku)
        if len(sell_stock_skus) >= 5:
            break

    for item in top5_items[:20]:
        if not isinstance(item, dict):
            continue
        sku = _to_int(item.get("sku"))
        if sku <= 0:
            continue
        drr_sku_pct = _to_float(item.get("drr_sku_pct"))
        profit = _to_float(item.get("profit"))
        margin_sku_pct = _to_float(item.get("margin_sku_pct"))
        if drr_sku_pct is not None and drr_sku_pct > 25.0 and sku not in cut_ads_skus:
            cut_ads_skus.append(sku)
        if drr_sku_pct is not None and drr_sku_pct < 10.0 and (profit or 0.0) > 0 and sku not in boost_ads_skus:
            boost_ads_skus.append(sku)
        if ((drr_sku_pct is not None and drr_sku_pct > 20.0) or (margin_sku_pct is not None and margin_sku_pct < 20.0)) and sku not in risk_skus:
            risk_skus.append(sku)

    for item in unprofitable_sku[:20]:
        sku = _to_int((item or {}).get("sku"))
        if sku > 0 and sku not in risk_skus:
            risk_skus.append(sku)
        if len(risk_skus) >= 5:
            break

    cut_ads_skus = cut_ads_skus[:5]
    boost_ads_skus = boost_ads_skus[:5]
    sell_stock_skus = sell_stock_skus[:5]
    risk_skus = risk_skus[:5]
    ads_leak_spend_total = sum(
        (_to_float(item.get("spend")) or 0.0)
        for item in (decision.get("ads_leaks") or [])
        if isinstance(item, dict) and (_to_int(item.get("orders")) == 0)
    )

    lines.append("1. Сократить рекламу:")
    lines.append(f"SKU: {_sku_csv(cut_ads_skus) if cut_ads_skus else 'нет явных SKU'}")
    savings_estimate = max(ads_leak_spend_total, search_ineffective_spend_total)
    lines.append(
        "Причина: есть клики/рекламные расходы, но слабая отдача по заказам."
        if savings_estimate >= 100.0
        else "Причина: данные не подтверждают значимые потери на рекламе."
    )
    lines.append(
        f"Деньги: можно сэкономить ~{_money(savings_estimate)} за период."
        if savings_estimate >= 100.0
        else "Деньги: существенная экономия не подтверждена (менее 100 RUB)."
    )
    lines.append("")
    lines.append("2. Усилить рекламу:")
    lines.append(f"SKU: {_sku_csv(boost_ads_skus) if boost_ads_skus else 'нет явных SKU'}")
    lines.append("Причина: высокая прибыль + нормальный ДРР.")
    lines.append(
        f"Деньги: текущая оценка прибыли по этим запросам {_money(search_scale_profit_total)}."
        if search_scale_profit_total >= 100.0
        else "Деньги: значимый денежный эффект пока не подтвержден (менее 100 RUB)."
    )
    lines.append("")
    lines.append("3. Распродать остатки:")
    lines.append(f"SKU: {_sku_csv(sell_stock_skus) if sell_stock_skus else 'нет явных SKU'}")
    lines.append("Причина: нет заказов/слабое движение + остатки.")
    lines.append("")
    lines.append("4. Риск:")
    lines.append(f"SKU: {_sku_csv(risk_skus) if risk_skus else 'нет явных SKU'}")
    lines.append("Причина: высокий ДРР и/или падающая маржа.")
    lines.append("")
    lines.append("5. Поиск: отключить / снизить ставки:")
    lines.append(
        f"Запросы: {', '.join(search_disable_targets[:5]) if search_disable_targets else 'нет явных запросов'}"
    )
    lines.append(
        "Причина: клики есть, заказов нет -> сливается бюджет."
        if search_ineffective_spend_total >= 100.0
        else "Причина: данные не подтверждают значимые потери."
    )
    lines.append(
        f"Потери за период: {_money(search_ineffective_spend_total)}."
        if search_ineffective_spend_total >= 100.0
        else "Потери за период: нет значимых потерь."
    )
    lines.append("")
    lines.append("6. Поиск: масштабировать:")
    lines.append(
        f"Запросы: {', '.join(search_scale_targets[:5]) if search_scale_targets else 'нет явных запросов'}"
    )
    lines.append("Причина: запросы уже дают заказы и подтверждают спрос.")
    lines.append(
        f"Валовая отдача (revenue - spend): {_money(search_scale_profit_total)}."
        if (search_scale_profit_total or 0.0) >= 100.0
        else "Потенциал прибыли: значимый эффект пока не подтвержден (менее 100 RUB)."
    )
    lines.append("")
    lines.append("7. Поиск: гипотезы роста:")
    lines.append(
        f"Запросы: {', '.join(search_growth_targets[:5]) if search_growth_targets else 'Запросов с высоким CTR без рекламы не найдено'}"
    )
    lines.append(
        "Причина: высокий CTR при нулевом расходе — спрос есть, рекламу можно масштабировать тестом."
        if search_growth_targets
        else "Причина: в текущих данных не найдено запросов с высоким CTR без рекламы."
    )
    lines.append(
        "Действие: запустить тестовые кампании с небольшим бюджетом и оценить DRR/заказы."
        if search_growth_targets
        else "Действие: продолжить сбор данных и пересчитать блок на следующем периоде."
    )
    lines.append("")
    lines.append("## Почему цифры могут отличаться от WB")
    lines.append("- WB использует свою логику расчетов.")
    lines.append("- Отчет считает по выгрузкам (finance, funnel).")
    lines.append("- Часть заказов не выкупается.")
    lines.append("- Реклама учитывает атрибуцию WB.")
    lines.append("")

    missing_required = inputs.get("missing_required") or []
    missing_optional = inputs.get("missing_optional") or []
    lines.append("## Приложение: Диагностика входа")
    input_rows = [
        ["Найдено файлов", len(inputs.get("found_files") or [])],
        ["Собрано блоков", _text(", ".join(inputs.get("blocks_collected") or []) or "нет")],
        ["Пропущено блоков", _text(", ".join(inputs.get("blocks_skipped") or []) or "нет")],
        ["Не хватает обязательных", _text(", ".join(missing_required) or "нет")],
        ["Не хватает опциональных", _text(", ".join(missing_optional) or "нет")],
    ]
    _append_markdown_table(lines, ["Параметр", "Значение"], input_rows, align_right={1})

    return "\n".join(lines).strip() + "\n"
