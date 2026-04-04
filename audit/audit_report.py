"""Markdown renderer for file-based audit mode."""

from __future__ import annotations

import json
import re
from typing import Any


def _money(x: Any) -> str:
    try:
        return f"{float(x or 0):,.2f} RUB".replace(",", " ")
    except Exception:
        return "0.00 RUB"


def _pct_ratio(x: Any) -> str:
    try:
        return f"{float(x or 0) * 100:.2f}%"
    except Exception:
        return "0.00%"


def _int(x: Any) -> str:
    try:
        return str(int(float(x or 0)))
    except Exception:
        return "0"


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


def _pretty(value: Any) -> str:
    if isinstance(value, (dict, list, tuple)):
        return _repair_text(json.dumps(value, ensure_ascii=False))
    return _repair_text(str(value))


def _kpi_state_text(decision_layer: dict[str, Any], finance: dict[str, Any]) -> str:
    kpi = decision_layer.get("kpi") or {}
    profit = float(kpi.get("profit") or 0)
    margin = float(kpi.get("margin") or 0)
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
    lines.append(f"- ROI/ROAS рекламы: {_pretty(ads.get('roas', '?/?'))}")
    if finance.get("profit_note"):
        lines.append(f"- Примечание: {_pretty(finance.get('profit_note'))}")
    lines.append("")

    lines.append("## 2. Причины потери прибыли")
    reasons = decision.get("reasons_of_loss") or []
    if reasons:
        for reason in reasons:
            lines.append(f"- {_pretty(reason.get('reason'))}: {_pretty(reason.get('numbers'))}")
    else:
        lines.append("- Критичные причины не выявлены: не найдено явных сигналов потери маржинальности.")
    lines.append("")

    lines.append("## 3. Финансы")
    lines.append(f"- Выручка: {_money(finance.get('gross_revenue'))}")
    lines.append(f"- Комиссия WB: {_money(finance.get('commission'))}")
    lines.append(f"- Логистика: {_money(finance.get('logistics'))}")
    lines.append(f"- Хранение: {_money(finance.get('storage'))}")
    lines.append(f"- Себестоимость: {_money(finance.get('cogs_total'))}")
    lines.append(f"- Налог: {_money(finance.get('tax'))}")
    profit_label = _pretty(finance.get("profit_label") or "Прибыль")
    lines.append(f"- {profit_label}: {_money(finance.get('profit'))}")
    lines.append(f"- Маржа: {_pct_ratio(finance.get('margin'))}")
    lines.append("")

    lines.append("## 4. Реклама")
    lines.append(f"- Расход: {_money(ads.get('spend'))}")
    lines.append(f"- Атрибутированная выручка: {_money(ads.get('revenue_attr'))}")
    lines.append(f"- ROAS: {_pretty(ads.get('roas', 0))}")
    leaks = decision.get("ads_leaks") or []
    if leaks:
        lines.append(f"- Утечки бюджета: найдено {len(leaks)} проблемных кампаний.")
    else:
        lines.append("- Утечки бюджета не выявлены: критичных признаков не обнаружено.")
    lines.append("")

    lines.append("## 5. Воронка")
    lines.append(f"- Просмотры: {_int(funnel.get('views'))}")
    lines.append(f"- В корзину: {_int(funnel.get('add_to_cart'))}")
    lines.append(f"- Заказы: {_int(funnel.get('orders'))}")
    lines.append(f"- Выкупы: {_int(funnel.get('buys'))}")
    lines.append(f"- CR в корзину: {_pct_ratio(funnel.get('cr_cart'))}")
    lines.append(f"- CR в заказ: {_pct_ratio(funnel.get('cr_order'))}")
    lines.append(f"- % выкупа: {_pct_ratio(funnel.get('buyout_rate'))}")
    lines.append("")

    lines.append("## 6. Ассортимент (SKU)")
    unprofitable_sku = decision.get("unprofitable_sku") or []
    sku_without_sales = decision.get("sku_without_sales") or []
    if unprofitable_sku:
        lines.append("- Убыточные SKU (top-10):")
        for item in unprofitable_sku[:10]:
            lines.append(
                f"- SKU {item.get('sku')}: прибыль {_money(item.get('profit'))}, маржа {_pct_ratio(item.get('margin'))}"
            )
    else:
        lines.append("- Убыточные SKU не выявлены для текущей диагностики.")
    if sku_without_sales:
        lines.append("- SKU без продаж и с остатками (top-10):")
        for item in sku_without_sales[:10]:
            lines.append(f"- SKU {item.get('sku')}: остаток {_int(item.get('stock_qty'))} шт, выкупы {_int(item.get('buyouts'))}")
    else:
        lines.append("- SKU без продаж и с остатками не выявлены для текущей диагностики.")
    lines.append("")

    lines.append("## 7. Остатки")
    stock_agg_status = str(stock.get("aggregation_status") or "")
    lines.append(f"- Остатки: {_int(stock.get('stock_units'))} шт")
    lines.append(f"- SKU/размеры: {_int(stock.get('sku_count'))}")
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

    lines.append("## 8. Поисковые запросы (если есть)")
    search_status = str(search.get("status") or "")
    if search_status == "ok":
        lines.append(f"- Прибыльные: {len(search.get('profitable') or [])}")
        lines.append(f"- Убыточные: {len(search.get('unprofitable') or [])}")
        lines.append(f"- Потенциал: {len(search.get('potential') or [])}")
    elif search_status == "missing":
        lines.append("- Отчет поисковых запросов не предоставлен.")
    else:
        parse_diag = search.get("parse_diagnostics") or {}
        lines.append(
            f"- Файл search найден, но данные не были разобраны: status={search_status}, "
            f"message={_pretty(search.get('message'))}."
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
                f"- [{action.get('priority')}] ({action.get('area')}) {_pretty(action.get('action'))} "
                f"- {_pretty(action.get('why'))}. Эффект: {_pretty(action.get('expected_effect'))}."
            )
    else:
        lines.append("- Рекомендации не сформированы: недостаточно данных.")
    lines.append("")

    missing_required = inputs.get("missing_required") or []
    missing_optional = inputs.get("missing_optional") or []
    lines.append("## Диагностика входа")
    lines.append(f"- Найдено файлов: {len(inputs.get('found_files') or [])}")
    lines.append(f"- Собрано блоков: {_pretty(', '.join(inputs.get('blocks_collected') or []) or 'нет')}")
    lines.append(f"- Пропущено блоков: {_pretty(', '.join(inputs.get('blocks_skipped') or []) or 'нет')}")
    if missing_required:
        lines.append(f"- Не хватает обязательных файлов: {_pretty(', '.join(missing_required))}")
    if missing_optional:
        lines.append(f"- Не хватает опциональных файлов: {_pretty(', '.join(missing_optional))}")
    if not missing_required and not missing_optional:
        lines.append("- Все ожидаемые файлы присутствуют.")
    lines.append("")

    if sku_profit:
        lines.append("## Приложение: top SKU по прибыли")
        sku_profit_label = "Прибыль без COGS" if finance.get("profit_without_cogs") else "Прибыль"
        for item in sku_profit[:10]:
            lines.append(
                f"- SKU {item.get('sku')}: {sku_profit_label} {_money(item.get('profit'))}, "
                f"выручка {_money(item.get('revenue'))}, остаток {_int(item.get('stock_qty'))}"
            )
        lines.append("")

    return "\n".join(lines).strip() + "\n"
