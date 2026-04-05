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
    if value > 40.0:
        return "green"
    if value >= 20.0:
        return "yellow"
    return "red"


def _drr_status_level_by_pct(drr_pct: Any) -> str:
    value = _to_float(drr_pct)
    if value is None:
        return "yellow"
    if value < 15.0:
        return "green"
    if value > 25.0:
        return "red"
    return "yellow"


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
    return total if total > 0 else None


def _search_conclusion(row: dict[str, Any]) -> str:
    impressions = _to_int(row.get("impressions"))
    clicks = _to_int(row.get("clicks"))
    orders = _to_int(row.get("orders"))
    buyouts = _to_int(row.get("buyouts"))

    if orders > 0 or buyouts > 0:
        return "работает: есть заказы"
    if clicks > 0 and orders == 0 and buyouts == 0:
        return "есть интерес, но нет заказов: проблема конверсии"
    if impressions > 0 and clicks == 0:
        return "низкий CTR: есть показы, но нет кликов"
    return "недостаточно данных"


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


def _local_orders_section_lines(local_orders_insights: dict[str, Any]) -> list[str]:
    lines: list[str] = ["## 7. Локальные заказы и размещение товара"]

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

    lines.append("### Сводка по локальному спросу")
    if by_region:
        rows: list[list[Any]] = []
        for item in by_region[:12]:
            stock_qty_raw = item.get("stock_qty")
            stock_text = "н/д" if stock_qty_raw is None else str(int(stock_qty_raw))
            rows.append(
                [
                    _text(item.get("region") or "Не указан"),
                    int(item.get("orders") or 0),
                    _fmt_pct(_to_float(item.get("share_pct")), 1),
                    stock_text,
                ]
            )
        _append_markdown_table(lines, ["Регион/город", "Заказы, шт", "Доля", "Остаток, шт"], rows, align_right={1, 2, 3})
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


def _region_logistics_section_lines(facts: dict[str, Any]) -> list[str]:
    lines: list[str] = ["## 8. \u041b\u043e\u0433\u0438\u0441\u0442\u0438\u043a\u0430 \u043f\u043e \u0440\u0435\u0433\u0438\u043e\u043d\u0430\u043c \u0438 \u0440\u0430\u0437\u043c\u0435\u0449\u0435\u043d\u0438\u0435"]

    region_summary = facts.get("region_logistics_summary")
    top_expensive = facts.get("top_expensive_logistics_regions")
    potential_risk = facts.get("logistics_potential_risk_regions")
    regions_over_150 = facts.get("logistics_regions_over_150")
    low_coverage_regions = facts.get("logistics_regions_low_coverage")

    if not isinstance(region_summary, dict) or not region_summary:
        lines.append("- \u0421\u043f\u0440\u0430\u0432\u043e\u0447\u043d\u0438\u043a \u043b\u043e\u0433\u0438\u0441\u0442\u0438\u043a\u0438 \u043d\u0435 \u0437\u0430\u0433\u0440\u0443\u0436\u0435\u043d, \u0440\u0430\u0437\u0434\u0435\u043b \u0438\u043d\u0444\u043e\u0440\u043c\u0430\u0446\u0438\u043e\u043d\u043d\u044b\u0439.")
        lines.append("")
        return lines

    top_expensive = top_expensive if isinstance(top_expensive, list) else []
    potential_risk = potential_risk if isinstance(potential_risk, list) else []
    regions_over_150 = regions_over_150 if isinstance(regions_over_150, list) else []
    low_coverage_regions = low_coverage_regions if isinstance(low_coverage_regions, list) else []

    total_regions = len(region_summary)
    known_regions = 0
    expensive_regions_count = 0
    unknown_regions_count = 0
    for row in region_summary.values():
        if not isinstance(row, dict):
            continue
        if _to_int(row.get("known_count")) > 0:
            known_regions += 1
        cls = _text(row.get("class")).lower()
        if cls == "expensive":
            expensive_regions_count += 1
        elif cls == "unknown":
            unknown_regions_count += 1

    lines.append("### \u041a\u0440\u0430\u0442\u043a\u0438\u0439 \u0432\u044b\u0432\u043e\u0434")
    lines.append(
        f"- \u0412 \u0441\u043f\u0440\u0430\u0432\u043e\u0447\u043d\u0438\u043a\u0435: {total_regions} \u0440\u0435\u0433\u0438\u043e\u043d\u043e\u0432; \u0441 \u0438\u0437\u0432\u0435\u0441\u0442\u043d\u044b\u043c\u0438 \u043a\u043e\u044d\u0444\u0444\u0438\u0446\u0438\u0435\u043d\u0442\u0430\u043c\u0438: {known_regions}; \u0441 \u043d\u0435\u043f\u043e\u043b\u043d\u044b\u043c\u0438/\u043f\u0443\u0441\u0442\u044b\u043c\u0438 \u0434\u0430\u043d\u043d\u044b\u043c\u0438: {unknown_regions_count}."
    )
    lines.append(
        f"- \u0414\u043e\u0440\u043e\u0433\u0438\u0445 \u0440\u0435\u0433\u0438\u043e\u043d\u043e\u0432 \u043f\u043e \u0441\u0440\u0435\u0434\u043d\u0435\u043c\u0443 \u043a\u043e\u044d\u0444\u0444\u0438\u0446\u0438\u0435\u043d\u0442\u0443: {expensive_regions_count}; \u0440\u0435\u0433\u0438\u043e\u043d\u043e\u0432 \u0441\u043e \u0441\u0440\u0435\u0434\u043d\u0438\u043c >150%: {len(regions_over_150)}."
    )

    if top_expensive:
        top_tokens: list[str] = []
        for item in top_expensive[:3]:
            if not isinstance(item, dict):
                continue
            name = _text(item.get("region"))
            avg = _coef_pct(item.get("avg_coefficient"))
            if name:
                top_tokens.append(f"{name} ({avg})")
        if top_tokens:
            lines.append("- TOP \u0434\u043e\u0440\u043e\u0433\u0438\u0445 \u0440\u0435\u0433\u0438\u043e\u043d\u043e\u0432: " + ", ".join(top_tokens) + ".")

    if potential_risk:
        risky_labels = []
        for item in potential_risk[:3]:
            if not isinstance(item, dict):
                continue
            geo = _text(item.get("geo_region"))
            if geo:
                risky_labels.append(geo)
        if risky_labels:
            lines.append(
                "- \u0412 \u043b\u043e\u043a\u0430\u043b\u044c\u043d\u043e\u0441\u0442\u0438 \u0437\u0430\u043a\u0430\u0437\u043e\u0432 \u0432\u044b\u044f\u0432\u043b\u0435\u043d\u044b \u0437\u043e\u043d\u044b \u0440\u0438\u0441\u043a\u0430: " + ", ".join(risky_labels) + "."
            )
    elif low_coverage_regions:
        lines.append(
            "- \u0414\u043b\u044f \u0447\u0430\u0441\u0442\u0438 \u0440\u0435\u0433\u0438\u043e\u043d\u043e\u0432 \u043a\u043e\u044d\u0444\u0444\u0438\u0446\u0438\u0435\u043d\u0442\u044b \u043d\u0435\u043f\u043e\u043b\u043d\u044b\u0435, \u043f\u043e\u044d\u0442\u043e\u043c\u0443 \u0440\u0435\u043a\u043e\u043c\u0435\u043d\u0434\u0430\u0446\u0438\u0438 \u0434\u0430\u044e\u0442\u0441\u044f \u0432 \u043c\u044f\u0433\u043a\u043e\u043c \u0444\u043e\u0440\u043c\u0430\u0442\u0435."
        )
    lines.append("")

    lines.append("### \u0420\u0435\u0433\u0438\u043e\u043d\u044b \u0441 \u043f\u0440\u0438\u043e\u0440\u0438\u0442\u0435\u0442\u043e\u043c \u0430\u043d\u0430\u043b\u0438\u0437\u0430")
    risk_by_region: dict[str, dict[str, Any]] = {}
    for item in potential_risk:
        if not isinstance(item, dict):
            continue
        region = _text(item.get("logistics_region") or "")
        if not region:
            continue
        risk_by_region[region] = item

    ordered_regions: list[str] = []
    for region in risk_by_region:
        if region not in ordered_regions:
            ordered_regions.append(region)
    for item in top_expensive:
        if not isinstance(item, dict):
            continue
        region = _text(item.get("region"))
        if region and region not in ordered_regions:
            ordered_regions.append(region)
    for region in region_summary:
        if region not in ordered_regions:
            ordered_regions.append(region)

    table_rows: list[list[Any]] = []
    for region in ordered_regions[:7]:
        summary = region_summary.get(region) if isinstance(region_summary.get(region), dict) else {}
        cls = _text(summary.get("class") or "unknown").lower()
        signal = risk_by_region.get(region) or {}
        non_local_orders = _to_int(signal.get("non_local_orders"))
        comment = ""
        if cls == "expensive" and non_local_orders > 0:
            comment = "\u0415\u0441\u0442\u044c \u043d\u0435 \u043b\u043e\u043a\u0430\u043b\u044c\u043d\u044b\u0435 \u0437\u0430\u043a\u0430\u0437\u044b \u043f\u0440\u0438 \u0434\u043e\u0440\u043e\u0433\u043e\u0439 \u043b\u043e\u0433\u0438\u0441\u0442\u0438\u043a\u0435."
        elif cls == "unknown":
            comment = "\u041a\u043e\u044d\u0444\u0444\u0438\u0446\u0438\u0435\u043d\u0442\u044b \u0438\u0437\u0432\u0435\u0441\u0442\u043d\u044b \u0447\u0430\u0441\u0442\u0438\u0447\u043d\u043e."
        elif cls == "expensive":
            comment = "\u041b\u043e\u0433\u0438\u0441\u0442\u0438\u043a\u0430 \u0432\u044b\u0448\u0435 \u0431\u0430\u0437\u043e\u0432\u043e\u0439, \u043d\u0443\u0436\u043d\u043e \u0442\u0435\u0441\u0442\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u043f\u043e\u0441\u0442\u0430\u0432\u043a\u0438."
        else:
            comment = "\u041b\u043e\u0433\u0438\u0441\u0442\u0438\u043a\u0430 \u0431\u043b\u0438\u0436\u0435 \u043a \u0431\u0430\u0437\u043e\u0432\u043e\u0439, \u0441\u0446\u0435\u043d\u0430\u0440\u0438\u0439 \u043c\u043e\u0436\u043d\u043e \u0441\u043c\u044f\u0433\u0447\u0430\u0442\u044c."

        table_rows.append(
            [
                region,
                _coef_pct(summary.get("min_coefficient")),
                _coef_pct(summary.get("max_coefficient")),
                _coef_pct(summary.get("avg_coefficient")),
                _logistics_class_label(cls),
                comment,
            ]
        )

    if table_rows:
        _append_markdown_table(
            lines,
            [
                "\u0420\u0435\u0433\u0438\u043e\u043d",
                "\u041c\u0438\u043d %",
                "\u041c\u0430\u043a\u0441 %",
                "\u0421\u0440\u0435\u0434\u043d\u0438\u0439 %",
                "\u041a\u043b\u0430\u0441\u0441",
                "\u041a\u043e\u043c\u043c\u0435\u043d\u0442\u0430\u0440\u0438\u0439",
            ],
            table_rows,
            align_right={1, 2, 3},
        )
    else:
        lines.append("- \u0414\u0430\u043d\u043d\u044b\u0445 \u0434\u043b\u044f \u0442\u0430\u0431\u043b\u0438\u0446\u044b \u043f\u043e \u0440\u0435\u0433\u0438\u043e\u043d\u0430\u043c \u043f\u043e\u043a\u0430 \u043d\u0435\u0442.")
        lines.append("")

    lines.append("### \u041c\u044f\u0433\u043a\u0438\u0435 \u0440\u0435\u043a\u043e\u043c\u0435\u043d\u0434\u0430\u0446\u0438\u0438")
    if potential_risk:
        for item in potential_risk[:3]:
            if not isinstance(item, dict):
                continue
            geo_region = _text(item.get("geo_region") or "\u0440\u0435\u0433\u0438\u043e\u043d")
            lines.append(
                f"- \u0414\u043b\u044f \u0440\u0435\u0433\u0438\u043e\u043d\u0430 {geo_region} \u0435\u0441\u0442\u044c \u0441\u043f\u0440\u043e\u0441 \u0438 \u043d\u0435 \u043b\u043e\u043a\u0430\u043b\u044c\u043d\u044b\u0435 \u0437\u0430\u043a\u0430\u0437\u044b; \u0441\u0442\u043e\u0438\u0442 \u0442\u0435\u0441\u0442\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0440\u0430\u0437\u043c\u0435\u0449\u0435\u043d\u0438\u0435 \u0431\u043b\u0438\u0436\u0435 \u043a \u0441\u043f\u0440\u043e\u0441\u0443 \u043c\u0430\u043b\u044b\u043c\u0438 \u043f\u0430\u0440\u0442\u0438\u044f\u043c\u0438."
            )
    if regions_over_150:
        preview = ", ".join(_text(x) for x in regions_over_150[:5] if _text(x))
        if preview:
            lines.append(
                f"- \u041f\u043e \u0440\u0435\u0433\u0438\u043e\u043d\u0430\u043c \u0441\u043e \u0441\u0440\u0435\u0434\u043d\u0438\u043c \u043a\u043e\u044d\u0444\u0444\u0438\u0446\u0438\u0435\u043d\u0442\u043e\u043c >150% ({preview}) \u043b\u0443\u0447\u0448\u0435 \u0441\u043d\u0430\u0447\u0430\u043b\u0430 \u043f\u0440\u043e\u0432\u043e\u0434\u0438\u0442\u044c \u0442\u0435\u0441\u0442 \u043f\u043e\u0441\u0442\u0430\u0432\u043e\u043a \u043d\u0430 \u043e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u043d\u043e\u043c \u043e\u0431\u044a\u0435\u043c\u0435."
            )
    if low_coverage_regions:
        preview = ", ".join(_text(x) for x in low_coverage_regions[:5] if _text(x))
        if preview:
            lines.append(
                f"- \u041f\u043e \u0440\u0435\u0433\u0438\u043e\u043d\u0430\u043c \u0441 \u043d\u0435\u043f\u043e\u043b\u043d\u044b\u043c\u0438 \u0434\u0430\u043d\u043d\u044b\u043c\u0438 ({preview}) \u043d\u0443\u0436\u043d\u043e \u0443\u0442\u043e\u0447\u043d\u044f\u0442\u044c \u0444\u0430\u043a\u0442\u0438\u0447\u0435\u0441\u043a\u0438\u0435 \u0443\u0441\u043b\u043e\u0432\u0438\u044f \u0441\u043a\u043b\u0430\u0434\u043e\u0432 \u0434\u043e \u0436\u0435\u0441\u0442\u043a\u0438\u0445 \u0440\u0435\u0448\u0435\u043d\u0438\u0439 \u043f\u043e \u0440\u0430\u0441\u043f\u0440\u0435\u0434\u0435\u043b\u0435\u043d\u0438\u044e."
            )
    if not potential_risk and not regions_over_150 and not low_coverage_regions:
        lines.append("- \u042f\u0432\u043d\u044b\u0445 \u0437\u043e\u043d \u043b\u043e\u0433\u0438\u0441\u0442\u0438\u0447\u0435\u0441\u043a\u043e\u0433\u043e \u0440\u0438\u0441\u043a\u0430 \u043f\u043e \u0442\u0435\u043a\u0443\u0449\u0435\u0439 \u044d\u0432\u0440\u0438\u0441\u0442\u0438\u043a\u0435 \u043d\u0435 \u0432\u044b\u044f\u0432\u043b\u0435\u043d\u043e.")
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
    lines: list[str] = ["## 9. Переплата за логистику"]
    model = facts.get("logistics_formula_model") if isinstance(facts.get("logistics_formula_model"), dict) else {}

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
    risk_level = _localization_risk_label(
        model.get("risk_level") or _localization_risk_from_share(localization_share_pct)
    )

    lines.append("### Краткий вывод")
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
            ["ИРП", _fmt_pct(sales_distribution_index_pct, 2)],
            ["Базовая логистика", _money(base_logistics)],
            ["Итоговая расчетная логистика", _money(delivery_cost)],
            ["Нейтральный сценарий (ИЛ=1, ИРП=0)", _money(neutral_delivery_cost)],
            ["Оценка переплаты", _money(overpayment_abs)],
            ["Рост к нейтральному сценарию", _fmt_pct(overpayment_pct, 1)],
        ]
        _append_markdown_table(lines, ["Показатель", "Значение"], rows, align_right={1})
        lines.append(f"- {_overpayment_conclusion(overpayment_pct)}")
        lines.append("")
    elif mode == "B":
        lines.append("### Оценка (частичные данные)")
        lines.append(
            f"- Доля локализации: {_fmt_pct(localization_share_pct, 2)}; применяется ИЛ={_sanitize_table_cell(localization_index)} и ИРП={_fmt_pct(sales_distribution_index_pct, 2)}."
        )
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
    lines: list[str] = ["## 10. Потери из-за плохой локализации"]
    payload = facts.get("localization_loss") if isinstance(facts.get("localization_loss"), dict) else {}

    status = _text(payload.get("status") or "insufficient_data")
    estimation_mode = _text(payload.get("estimation_mode") or "insufficient_data")
    total_loss = _to_float(payload.get("total_estimated_loss_rub"))
    loss_share = _to_float(payload.get("loss_share_of_revenue"))
    non_local_share = _to_float(payload.get("non_local_orders_share"))
    affected = _to_int(payload.get("affected_sku_count"))
    missing_inputs = payload.get("missing_inputs") if isinstance(payload.get("missing_inputs"), list) else []
    top_rows = payload.get("top_loss_sku") if isinstance(payload.get("top_loss_sku"), list) else []
    recommendations = payload.get("recommendations") if isinstance(payload.get("recommendations"), list) else []

    lines.append("### Оценка за период")
    lines.append(f"- Режим оценки: **{estimation_mode}**.")
    if total_loss is not None:
        lines.append(f"- Оценка потерь из-за локализации: **{_money(total_loss)}** за период.")
    else:
        lines.append("- Точная рублевая оценка пока недоступна, используется качественная оценка риска.")
    if non_local_share is not None:
        lines.append(f"- Доля нелокальных заказов: **{_fmt_pct(non_local_share * 100.0, 1)}**.")
    if loss_share is not None:
        lines.append(f"- Давление на выручку: **{_fmt_pct(loss_share * 100.0, 2)}**.")
    lines.append(f"- SKU в зоне влияния: **{affected}**.")
    if status == "insufficient_data" and missing_inputs:
        lines.append("- Для точного расчета не хватает: " + ", ".join(_text(x) for x in missing_inputs if _text(x)) + ".")
    lines.append("")

    lines.append("### TOP SKU по потерям/риску")
    if top_rows:
        has_rub = any(_to_float((row or {}).get("total_loss_rub")) is not None for row in top_rows if isinstance(row, dict))
        table_rows: list[list[Any]] = []
        for row in top_rows[:10]:
            if not isinstance(row, dict):
                continue
            if has_rub:
                table_rows.append(
                    [
                        row.get("sku"),
                        _to_int(row.get("orders")),
                        _fmt_pct(_to_float(row.get("localization_share_pct")), 2),
                        _sanitize_table_cell(row.get("localization_index")),
                        _fmt_pct(_to_float(row.get("sales_distribution_index_pct")), 2),
                        _money(row.get("total_loss_rub")),
                        _text(row.get("conclusion")),
                    ]
                )
            else:
                table_rows.append(
                    [
                        row.get("sku"),
                        _to_int(row.get("orders")),
                        _fmt_pct(_to_float(row.get("localization_share_pct")), 2),
                        _sanitize_table_cell(row.get("localization_index")),
                        _fmt_pct(_to_float(row.get("sales_distribution_index_pct")), 2),
                        _text(row.get("risk_level") or "н/д"),
                        _text(row.get("conclusion")),
                    ]
                )
        if has_rub:
            _append_markdown_table(
                lines,
                ["SKU", "Заказы", "Доля локализации", "ИЛ", "ИРП", "Потери", "Вывод"],
                table_rows,
                align_right={1, 2, 3, 4, 5},
            )
        else:
            _append_markdown_table(
                lines,
                ["SKU", "Заказы", "Доля локализации", "ИЛ", "ИРП", "Risk", "Вывод"],
                table_rows,
                align_right={1, 2, 3, 4},
            )
    else:
        lines.append("- SKU-данные для оценки потерь не распознаны автоматически.")
        lines.append("")

    lines.append("### Рекомендации")
    if recommendations:
        for rec in recommendations[:5]:
            if not isinstance(rec, dict):
                continue
            action = _text(rec.get("action"))
            why = _text(rec.get("why"))
            effect = _text(rec.get("expected_effect"))
            if action:
                lines.append(f"- {action}. Причина: {why}. Ожидаемый эффект: {effect}.")
    else:
        lines.append("- Дополнительные рекомендации появятся после уточнения данных по локализации и маршрутам заказов.")
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
    dead_stock = decision.get("dead_stock") if isinstance(decision.get("dead_stock"), list) else []
    regions_over_150 = facts.get("logistics_regions_over_150") if isinstance(facts.get("logistics_regions_over_150"), list) else []
    c_overstock_rows = abc_layer.get("c_overstock_rows") if isinstance(abc_layer.get("c_overstock_rows"), list) else []
    c_ads_rows = abc_layer.get("c_ads_rows") if isinstance(abc_layer.get("c_ads_rows"), list) else []

    def _row_sku(value: Any) -> int:
        if isinstance(value, dict):
            return _to_int(value.get("sku"))
        if isinstance(value, (list, tuple)) and value:
            return _to_int(value[0])
        return 0

    top_dead_sku = []
    for item in dead_stock[:5]:
        sku = _row_sku(item)
        if sku > 0:
            top_dead_sku.append(str(sku))

    top_c_problem = []
    for row in (c_overstock_rows + c_ads_rows):
        sku = _row_sku(row)
        if sku > 0 and str(sku) not in top_c_problem:
            top_c_problem.append(str(sku))
        if len(top_c_problem) >= 5:
            break

    lines.append(f"1. **Реклама без заказов:** {len(ads_leaks)} связок {_icon_warn()}")
    if ads_leaks:
        lines.append("- Нужна чистка неэффективных запросов и связок, которые расходуют бюджет без выкупа.")

    lines.append(f"2. **Залежавшиеся остатки:** {len(dead_stock)} SKU {_icon_warn()}")
    if top_dead_sku:
        lines.append(f"- Кандидаты на разбор: **{', '.join(top_dead_sku)}**.")

    lines.append(f"3. **Дорогая логистика:** {len(regions_over_150)} регионов с коэффициентом >150% {_icon_red()}")
    if regions_over_150:
        lines.append(f"- Регионы риска: **{', '.join(str(x) for x in regions_over_150[:5])}**.")

    c_problem_count = len(c_overstock_rows) + len(c_ads_rows)
    lines.append(f"4. **Проблемные C-SKU:** {c_problem_count} кейсов {_icon_red() if c_problem_count > 0 else _icon_green()}")
    if top_c_problem:
        lines.append(f"- SKU категории C с риском: **{', '.join(top_c_problem)}**.")

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


def _top5_unit_economics_section_lines(facts: dict[str, Any]) -> list[str]:
    lines: list[str] = ["## ТОП-5 SKU: где зарабатываете и где теряете"]
    payload = facts.get("top5_sku_unit_economics") if isinstance(facts.get("top5_sku_unit_economics"), dict) else {}
    rows = payload.get("items") if isinstance(payload.get("items"), list) else []

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
            lines.append("---")
            lines.append("")

        sku = _text(item.get("sku") or "н/д")
        category = _text(item.get("category") or "N/A")
        lines.append(f"### SKU: {sku} ({category})")

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
        margin_suffix = " (без COGS)" if "без cogs" in margin_label.lower() else ""
        margin_icon = _status_icon(_margin_status_level_by_pct(margin_sku_pct))
        if margin_sku_pct is not None:
            lines.append(f"**Маржа:** {float(margin_sku_pct):.2f}%{margin_suffix} {margin_icon}")
        else:
            lines.append(f"**Маржа:** н/д {margin_icon}")

        roi_sku_pct = _to_float(item.get("roi_sku_pct"))
        roi_available = bool(item.get("roi_available"))
        if roi_available and roi_sku_pct is not None:
            lines.append(f"**ROI:** {float(roi_sku_pct):.2f}%")
        else:
            lines.append("**ROI:** н/д (нет себестоимости)")

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
            f"- ДРР SKU: {float(drr_sku_pct):.2f}% {drr_icon}" if drr_sku_pct is not None else f"- ДРР SKU: н/д {drr_icon}"
        )
        if ads_load:
            lines.append(f"- Нагрузка рекламы: {ads_load}")

        risk_label = _risk_label_ru(item.get("risk_level"))
        risk_icon = _status_icon(_risk_status_level(item.get("risk_level")))
        lines.append(f"Риск: {risk_label} {risk_icon}")
        lines.append(f"{_icon_warn()} **Вывод:** {_text(item.get('comment'))}")
        lines.append(f"{_icon_point()} **Рекомендация:** {_text(item.get('recommendation'))}")
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

    clean_profit = revenue - commission - logistics - storage - tax - cogs_total - ads_spend
    clean_margin = (clean_profit / revenue) if revenue > 0 else 0.0
    clean_label = (
        "Чистая прибыль без учета себестоимости (с учетом рекламы)"
        if profit_without_cogs
        else "Чистая прибыль"
    )
    return {
        "clean_profit": float(clean_profit),
        "clean_margin": float(clean_margin),
        "clean_label": clean_label,
        "profit_without_cogs": profit_without_cogs,
        "ads_spend": float(ads_spend),
    }


def _roi_line(finance: dict[str, Any], ads: dict[str, Any], *, clean_profit: float) -> tuple[str, list[str]]:
    profit_without_cogs = bool(finance.get("profit_without_cogs"))
    cogs_total = _to_float(finance.get("cogs_total"))
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

    lines.append("## Оглавление")
    lines.append(f"Период отчета: {period_label_ru}")
    if audit_kind:
        lines.append(f"Тип аудита: {audit_kind}")
    lines.append("")
    lines.append("- 1. KPI и инсайты")
    lines.append("- 2. 💰 Финансы: сколько реально зарабатываете")
    lines.append("- 3. 📊 Воронка продаж: путь до выкупа")
    lines.append("- 4. 📢 Реклама: платите - но не всегда за результат")
    lines.append("- 5. 📦 Остатки: деньги заморожены в складе")
    lines.append("- 6. Ассортимент / SKU")
    lines.append("- ТОП-5 SKU: где зарабатываете и где теряете")
    lines.append("- 7. Локальные заказы и размещение товара")
    lines.append("- 8. Логистика по регионам и размещение")
    lines.append("- 9. Переплата за логистику")
    lines.append("- 10. Потери из-за плохой локализации")
    lines.append("- 11. Поисковые запросы")
    lines.append("- 12. План действий / рекомендации")
    lines.append("")

    lines.append("### Источники (файлы)")
    source_rows = [
        ["Финансы", _source_file_cell(selected_files.get("finance"))],
        ["Воронка", _source_file_cell(selected_files.get("funnel"))],
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
    drr_cabinet_kpi = (spend_kpi / sales_revenue_kpi) if spend_kpi is not None and sales_revenue_kpi and sales_revenue_kpi > 0 else None
    drr_cabinet_kpi_pct = (float(drr_cabinet_kpi) * 100.0) if drr_cabinet_kpi is not None else None
    roas_level = "green" if roas_kpi is not None and roas_kpi >= 4 else ("yellow" if roas_kpi is not None and roas_kpi >= 2 else ("red" if roas_kpi is not None else "yellow"))
    kpi_cards = [
        {"title": "Выручка", "value": _money(revenue_kpi), "icon": _status_icon("green" if (revenue_kpi or 0) > 0 else "yellow")},
        {"title": "Прибыль", "value": _money(clean_profit_kpi), "icon": _status_icon(_profit_status_level(clean_profit_kpi))},
        {"title": "Маржа", "value": _pct_ratio(clean_margin_ratio_kpi), "icon": _status_icon(_margin_status_level_by_pct((clean_margin_ratio_kpi * 100.0) if clean_margin_ratio_kpi is not None else None))},
        {"title": "ROAS", "value": _sanitize_table_cell(ads.get("roas", "н/д")), "icon": _status_icon(roas_level)},
        {"title": "ДРР кабинета", "value": _fmt_pct(drr_cabinet_kpi_pct, 1), "icon": _status_icon(_drr_status_level_by_pct(drr_cabinet_kpi_pct))},
    ]
    _append_kpi_cards(lines, kpi_cards, columns=4)
    lines.append("### Ключевые выводы")
    insights: list[str] = [
        _kpi_state_text(
            profit=profit_view["clean_profit"],
            margin=profit_view["clean_margin"],
            profit_without_cogs=bool(profit_view["profit_without_cogs"]),
        ),
        f"Выручка за период: {_money(finance.get('gross_revenue'))}.",
        f"ROAS рекламы: {_sanitize_table_cell(ads.get('roas', 'н/д'))}.",
        f"ДРР по кабинету: {_fmt_pct(drr_cabinet_kpi_pct, 1)}.",
    ]
    for reason in _loss_reasons_human(decision, finance)[:2]:
        insights.append(reason)
    for insight in insights[:5]:
        lines.append(f"- **{insight}**")
    lines.append("")
    lines.extend(_where_money_lost_section_lines(decision=decision, abc_layer=abc_layer, facts=facts))

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
        ["Маржа", _pct_ratio(profit_view.get("clean_margin"))],
        ["ROI", _text(roi_main.replace("ROI: ", ""))],
        ["К перечислению", _money(finance.get("payout"))],
    ]
    _append_markdown_table(lines, ["Метрика", "Значение"], finance_rows, align_right={1})
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

    _page_break(lines)

    lines.append("## 3. 📊 Воронка продаж: путь до выкупа")
    impressions = _extract_funnel_impressions(facts, funnel)
    views_count = _to_int(funnel.get("views"))
    add_to_cart_count = _to_int(funnel.get("add_to_cart"))
    orders_count = _to_int(funnel.get("orders"))
    buyouts_count = _to_int(funnel.get("buys"))
    cr_to_card = (float(views_count) / float(impressions)) if impressions is not None and impressions > 0 else None
    lines.append("### Визуальная воронка")
    lines.append(f"**{_to_int(impressions) if impressions is not None else 'н/д'}** показов")
    lines.append(f"↓ в карточку: **{views_count}** (CR: **{_pct_ratio(cr_to_card)}**)")
    lines.append(f"↓ в корзину: **{add_to_cart_count}** (CR: **{_pct_ratio(funnel.get('cr_cart'))}**)")
    lines.append(f"↓ заказов: **{orders_count}** (CR: **{_pct_ratio(funnel.get('cr_order'))}**)")
    lines.append(f"↓ выкупов: **{buyouts_count}** (% выкупа: **{_pct_ratio(funnel.get('buyout_rate'))}**)")
    lines.append("")
    funnel_rows: list[list[Any]] = []
    if impressions is not None:
        funnel_rows.append(["Показы", _to_int(impressions)])
    funnel_rows.extend(
        [
            ["Переходы в карточку", views_count],
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
        ["Атрибутированная выручка", _money(ads.get("revenue_attr"))],
        ["ROAS", _sanitize_table_cell(ads.get("roas", "н/д"))],
        ["ДРР (по рекламной выручке)", drr_text],
        ["ДРР по кабинету", drr_cabinet_text],
    ]
    _append_markdown_table(lines, ["Метрика", "Значение"], ads_rows, align_right={1})
    drr_cabinet_pct = (float(drr_cabinet) * 100.0) if drr_cabinet is not None else None
    drr_signal = _status_icon(_drr_status_level_by_pct(drr_cabinet_pct))
    lines.append(f"- **ДРР по кабинету: {drr_cabinet_text} {drr_signal}**.")

    attributed_revenue = _to_float(ads.get("revenue_attr"))
    factual_revenue = _to_float(finance.get("gross_revenue"))
    lines.append(
        "- Атрибутированная выручка показывает заказы, которые WB относит к рекламным касаниям, а не факт оплат из finance."
    )
    if attributed_revenue is not None and factual_revenue is not None and attributed_revenue > factual_revenue:
        lines.append(
            "- Она может быть выше фактической выручки, потому что часть заказов не была выкуплена."
        )
    leaks = decision.get("ads_leaks") or []
    lines.append(
        f"- **Найдено {len(leaks)} рекламных связок/запросов без заказов**."
        if leaks
        else "- Связки без заказов не обнаружены."
    )
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

    lines.extend(_top5_unit_economics_section_lines(facts))
    lines.append("")

    _page_break(lines)

    lines.extend(_local_orders_section_lines(local_orders_insights))

    _page_break(lines)

    lines.extend(_region_logistics_section_lines(facts))

    _page_break(lines)

    lines.extend(_logistics_overpayment_section_lines(facts))

    _page_break(lines)

    lines.extend(_localization_loss_section_lines(facts))

    _page_break(lines)

    lines.append("## 11. Поисковые запросы")
    search_status = str(search.get("status") or "")
    if search_status == "ok":
        base_rows = search.get("base_rows") if isinstance(search.get("base_rows"), list) else []
        summary = search.get("summary") if isinstance(search.get("summary"), dict) else {}
        rows_count = _to_int(summary.get("rows_count") or len(base_rows))
        rows_with_orders = _to_int(summary.get("profitable_count") or len(search.get("profitable") or []))
        rows_without_orders = _to_int(summary.get("unprofitable_count") or len(search.get("unprofitable") or []))
        rows_with_potential = _to_int(summary.get("potential_count") or len(search.get("potential") or []))

        summary_rows = [
            ["Всего строк в search-отчете", rows_count],
            ["Связки query+SKU с заказами", rows_with_orders],
            ["Связки query+SKU без заказов", rows_without_orders],
            ["Связки query+SKU с потенциалом", rows_with_potential],
        ]
        _append_markdown_table(lines, ["Показатель", "Значение"], summary_rows, align_right={1})

        def _render_search_table(title: str, rows: list[dict[str, Any]]) -> None:
            lines.append(title)
            if not rows:
                lines.append("- Данных для таблицы нет.")
                lines.append("")
                return
            table_rows = [
                [
                    _text(item.get("query")),
                    _to_int(item.get("nmId")),
                    _to_int(item.get("clicks")),
                    _to_int(item.get("add_to_cart")),
                    _to_int(item.get("orders")),
                    _search_conclusion(item),
                ]
                for item in rows[:10]
            ]
            _append_markdown_table(
                lines,
                ["Запрос", "SKU", "Клики", "В корзину", "Заказы", "Вывод"],
                table_rows,
                align_right={2, 3, 4},
            )

        _render_search_table("TOP-10 запросов по кликам", _search_rows_sorted(base_rows, mode="clicks"))
        _render_search_table("TOP-10 запросов с заказами", _search_rows_sorted(base_rows, mode="orders"))
        _render_search_table(
            "TOP-10 запросов без заказов, но с кликами",
            _search_rows_sorted(base_rows, mode="no_orders_clicks"),
        )
        lines.append("- Search-отчет отражает связки «поисковый запрос + SKU», а не все заказы кабинета.")
        lines.append("")
    elif search_status == "missing":
        lines.append("- Отчет поисковых запросов не предоставлен.")
        lines.append("")
    else:
        parse_diag = search.get("parse_diagnostics") or {}
        lines.append(
            f"- Файл search найден, но данные не разобраны: status={search_status}, message={_text(search.get('message'))}."
        )
        lines.append(
            f"- Диагностика parse: sheet={parse_diag.get('sheet')}, header_row={parse_diag.get('header_row')}, rows_parsed={parse_diag.get('rows_parsed')}."
        )
        lines.append("")

    _page_break(lines)

    lines.append("## 12. План действий / рекомендации")
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
