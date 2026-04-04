"""Markdown renderer for file-based audit mode."""

from __future__ import annotations

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


def _contains_cyrillic(text: str) -> bool:
    return bool(re.search(r"[А-Яа-яЁё]", text))


def _bad_marker_count(text: str) -> int:
    markers = ("Гђ", "Г‘", "Г‚", "Гѓ", "Гў", "пїЅ", "Р В ")
    return sum(text.count(marker) for marker in markers)


def _looks_like_mojibake(text: str) -> bool:
    if not text:
        return False
    if _bad_marker_count(text) > 0:
        return True
    cyrillic_letters = len(re.findall(r"[Р-Яа-яЁё]", text))
    if cyrillic_letters < 6:
        return False
    upper_rs = text.count("Р") + text.count("С")
    return upper_rs >= 4 and (upper_rs / max(cyrillic_letters, 1)) >= 0.22


def _repair_text(text: str) -> str:
    if not text or text.isascii():
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
    return _repair_text(str(value or "")).strip()


def _kpi_state_text(decision_layer: dict[str, Any], finance: dict[str, Any]) -> str:
    kpi = decision_layer.get("kpi") or {}
    profit = _to_float(kpi.get("profit")) or 0.0
    margin = _to_float(kpi.get("margin")) or 0.0
    profit_without_cogs = bool(finance.get("profit_without_cogs"))

    if profit_without_cogs:
        if profit < 0:
            return f"Предварительный убыток без COGS: {_money(profit)}, маржа: {_pct_ratio(margin)}."
        if profit > 0:
            return f"Предварительная прибыль без COGS: {_money(profit)}, маржа: {_pct_ratio(margin)}."
        return f"Нулевая предварительная прибыль без COGS, маржа: {_pct_ratio(margin)}."

    if profit < 0:
        return f"Убыток: {_money(profit)}, маржа: {_pct_ratio(margin)}."
    if profit > 0:
        return f"Прибыль: {_money(profit)}, маржа: {_pct_ratio(margin)}."
    return f"Нулевая прибыль, маржа: {_pct_ratio(margin)}."


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
            lines.append("Прибыль рассчитана без учета себестоимости - фактическая прибыль может быть ниже.")
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


def _roi_line(finance: dict[str, Any], ads: dict[str, Any]) -> tuple[str, list[str]]:
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
        _to_float(finance.get("penalties")) or 0.0,
        _to_float(finance.get("tax")) or 0.0,
        cogs_total,
        _to_float(ads.get("spend")) or 0.0,
    ]
    expenses = sum(x for x in expense_fields if x > 0)
    profit = _to_float(finance.get("profit"))
    if expenses <= 0 or profit is None:
        return ("ROI: н/д", [])

    roi = (profit / expenses) * 100.0
    return (f"ROI: {_fmt_pct(roi, 1)}", [])


def build_audit_markdown(facts: dict[str, Any]) -> str:
    finance = facts.get("financial_summary") or {}
    funnel = facts.get("funnel_summary") or {}
    ads = facts.get("ads_summary") or {}
    stock = facts.get("stock_summary") or {}
    search = facts.get("search_insights") or {}
    decision = facts.get("decision_layer") or {}
    inputs = facts.get("inputs") or {}
    sku_profit = facts.get("sku_profit") or []
    actions = facts.get("actions") or []

    lines: list[str] = []
    lines.append("# АУДИТ WB КАБИНЕТА")
    lines.append("")

    lines.append("## 1. KPI")
    lines.append(f"- {_kpi_state_text(decision, finance)}")
    lines.append(f"- Выручка: {_money(finance.get('gross_revenue'))}")
    lines.append(f"- ROI/ROAS рекламы: {_sanitize_table_cell(ads.get('roas', '?/?'))}")
    if finance.get("profit_note"):
        lines.append(f"- Примечание: {_text(finance.get('profit_note'))}")
    lines.append("")

    lines.append("## 2. Причины потери прибыли")
    for reason_line in _loss_reasons_human(decision, finance):
        lines.append(f"- {reason_line}")
    lines.append("")

    lines.append("## 3. Финансы")
    lines.append(f"- Выручка: {_money(finance.get('gross_revenue'))}")
    lines.append(f"- Комиссия WB: {_money(finance.get('commission'))}")
    lines.append(f"- Логистика: {_money(finance.get('logistics'))}")
    lines.append(f"- Хранение: {_money(finance.get('storage'))}")
    lines.append(f"- Себестоимость: {_money(finance.get('cogs_total'))}")
    lines.append(f"- Налог: {_money(finance.get('tax'))}")
    profit_label = _text(finance.get("profit_label") or "Прибыль")
    lines.append(f"- {profit_label}: {_money(finance.get('profit'))}")
    lines.append(f"- Маржа: {_pct_ratio(finance.get('margin'))}")

    roi_main, roi_extra = _roi_line(finance, ads)
    lines.append(f"- {roi_main}")
    for extra in roi_extra:
        lines.append(f"- {extra}")
    lines.append("")

    lines.append("## 4. Реклама")
    attributed_revenue = _to_float(ads.get("revenue_attr"))
    factual_revenue = _to_float(finance.get("gross_revenue"))
    lines.append(f"- Расход: {_money(ads.get('spend'))}")
    lines.append(f"- Атрибутированная выручка: {_money(ads.get('revenue_attr'))}")
    lines.append(
        "- Атрибутированная выручка - это выручка, которую Wildberries относит к рекламным касаниям. "
        "Она не равна фактической выручке из финансового отчета."
    )
    if attributed_revenue is not None and factual_revenue is not None and attributed_revenue > factual_revenue:
        lines.append(
            "- Атрибутированная выручка включает заказы, которые могли не быть выкуплены. "
            "Поэтому она может быть выше фактической выручки из финансового отчета."
        )
    lines.append(f"- ROAS: {_sanitize_table_cell(ads.get('roas', 0))}")
    leaks = decision.get("ads_leaks") or []
    if leaks:
        lines.append(f"- Найдено {len(leaks)} рекламных связок/запросов без заказов.")
    else:
        lines.append("- Рекламные связки/запросы без заказов не обнаружены.")
    lines.append("")

    lines.append("## 5. Воронка")
    impressions = _extract_funnel_impressions(facts, funnel)
    if impressions is not None:
        lines.append(f"- Показы: {_to_int(impressions)}")
    lines.append(f"- Переходы в карточку: {_to_int(funnel.get('views'))}")
    lines.append(f"- В корзину: {_to_int(funnel.get('add_to_cart'))}")
    lines.append(f"- Заказы: {_to_int(funnel.get('orders'))}")
    lines.append(f"- Выкупы: {_to_int(funnel.get('buys'))}")
    lines.append(f"- CR в корзину: {_pct_ratio(funnel.get('cr_cart'))}")
    lines.append(f"- CR в заказ: {_pct_ratio(funnel.get('cr_order'))}")
    lines.append(f"- % выкупа: {_pct_ratio(funnel.get('buyout_rate'))}")
    lines.append("")
    lines.append("Продажи (заказы):")
    lines.append(f"- Количество заказов: {_to_int(funnel.get('orders'))}")
    lines.append(f"- Сумма заказов (оборот до выкупа): {_money(funnel.get('revenue_orders'))}")
    lines.append("Выкупы (фактическая выручка):")
    lines.append(f"- Количество выкупов: {_to_int(funnel.get('buys'))}")
    lines.append(f"- Выручка (по finance): {_money(finance.get('gross_revenue'))}")
    lines.append("- Часть заказов не выкупается, поэтому оборот по заказам выше фактической выручки.")
    lines.append("")
    lines.append("Разница между заказами и выкупами влияет на:")
    lines.append("- фактическую выручку")
    lines.append("- корректную оценку рекламы")
    lines.append("- реальную прибыль")
    lines.append("")

    lines.append("## 6. Ассортимент (SKU)")
    unprofitable_sku = decision.get("unprofitable_sku") or []
    sku_without_sales = decision.get("sku_without_sales") or []
    if unprofitable_sku:
        lines.append("- SKU со сниженной маржинальностью (top-10):")
        for item in unprofitable_sku[:10]:
            lines.append(
                f"- SKU {item.get('sku')}: прибыль {_money(item.get('profit'))}, маржа {_pct_ratio(item.get('margin'))}"
            )
    else:
        lines.append("- SKU со сниженной маржинальностью не выявлены для текущей диагностики.")
    if sku_without_sales:
        lines.append("- SKU без продаж и с остатками (top-10):")
        for item in sku_without_sales[:10]:
            lines.append(
                f"- SKU {item.get('sku')}: остаток {_to_int(item.get('stock_qty'))} шт, заказы {_to_int(item.get('orders'))}"
            )
    else:
        lines.append("- SKU без продаж и с остатками не выявлены для текущей диагностики.")
    lines.append("")

    lines.append("## 7. Остатки")
    stock_agg_status = str(stock.get("aggregation_status") or "")
    lines.append(f"- Остатки: {_to_int(stock.get('stock_units'))} шт")
    lines.append(f"- SKU/размеры: {_to_int(stock.get('sku_count'))}")
    lines.append(f"- Дни покрытия: {stock.get('days_of_cover', 0)}")
    if stock_agg_status not in {"", "ok"}:
        lines.append(
            f"- Диагностика: частичный статус агрегации по остаткам `{stock_agg_status}` "
            f"(parsed_rows={stock.get('parsed_rows')}, mapped_rows={stock.get('mapped_rows')})."
        )
    dead_stock = decision.get("dead_stock") or []
    if dead_stock:
        lines.append(f"- Мертвые остатки: {len(dead_stock)} SKU/размеров без продаж.")
    else:
        lines.append("- Мертвые остатки не выявлены для текущей диагностики.")
    lines.append("")

    lines.append("## 8. Поисковые запросы")
    search_status = str(search.get("status") or "")
    if search_status == "ok":
        rows_with_orders = len(search.get("profitable") or [])
        rows_without_orders = len(search.get("unprofitable") or [])
        rows_with_potential = len(search.get("potential") or [])

        lines.append(f"- Запросы с заказами: {rows_with_orders}")
        lines.append(f"- Запросы без заказов: {rows_without_orders}")
        lines.append(f"- Запросы с потенциалом: {rows_with_potential}")
        lines.append("")
        lines.append("ТОП-10 запросов по кликам:")
        lines.append("| Запрос | Клики | В корзину | Заказы | Вывод |")
        lines.append("| --- | ---: | ---: | ---: | --- |")
        for row in _search_rows_for_table(search):
            lines.append(
                "| "
                + f"{_sanitize_table_cell(row.get('query'))} | {_to_int(row.get('clicks'))} | "
                + f"{_to_int(row.get('add_to_cart'))} | {_to_int(row.get('orders'))} | {_search_conclusion(row)} |"
            )
    elif search_status == "missing":
        lines.append("- Отчет поисковых запросов не предоставлен.")
    else:
        parse_diag = search.get("parse_diagnostics") or {}
        lines.append(
            f"- Файл search найден, но данные не были разобраны: status={search_status}, "
            f"message={_text(search.get('message'))}."
        )
        lines.append(
            f"- Диагностика parse: sheet={parse_diag.get('sheet')}, header_row={parse_diag.get('header_row')}, "
            f"rows_parsed={parse_diag.get('rows_parsed')}"
        )
    lines.append("")

    lines.append("## 9. Рекомендации")
    if actions:
        for action in actions:
            lines.append(
                f"- [{action.get('priority')}] ({action.get('area')}) {_text(action.get('action'))} "
                f"- {_text(action.get('why'))}. Эффект: {_text(action.get('expected_effect'))}."
            )
    else:
        lines.append("- Рекомендации не сформированы: недостаточно данных.")
    lines.append("")

    missing_required = inputs.get("missing_required") or []
    missing_optional = inputs.get("missing_optional") or []
    lines.append("## Диагностика входа")
    lines.append(f"- Найдено файлов: {len(inputs.get('found_files') or [])}")
    lines.append(f"- Собрано блоков: {_text(', '.join(inputs.get('blocks_collected') or []) or 'нет')}")
    lines.append(f"- Пропущено блоков: {_text(', '.join(inputs.get('blocks_skipped') or []) or 'нет')}")
    if missing_required:
        lines.append(f"- Не хватает обязательных файлов: {_text(', '.join(missing_required))}")
    if missing_optional:
        lines.append(f"- Не хватает опциональных файлов: {_text(', '.join(missing_optional))}")
    if not missing_required and not missing_optional:
        lines.append("- Все ожидаемые файлы присутствуют.")
    lines.append("")

    if sku_profit:
        lines.append("## Приложение: top SKU по прибыли")
        sku_profit_label = "Прибыль без COGS" if finance.get("profit_without_cogs") else "Прибыль"
        for item in sku_profit[:10]:
            lines.append(
                f"- SKU {item.get('sku')}: {sku_profit_label} {_money(item.get('profit'))}, "
                f"выручка {_money(item.get('revenue'))}, остаток {_to_int(item.get('stock_qty'))}"
            )
        lines.append("")

    return "\n".join(lines).strip() + "\n"
