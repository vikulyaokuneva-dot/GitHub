"""Markdown renderer for file-based audit mode."""

from __future__ import annotations

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


def _kpi_state_text(decision_layer: dict[str, Any]) -> str:
    kpi = decision_layer.get("kpi") or {}
    profit = float(kpi.get("profit") or 0)
    margin = float(kpi.get("margin") or 0)
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

    lines.append("## 1. Итог")
    lines.append(f"- {_kpi_state_text(decision)}")
    lines.append(f"- Выручка: {_money(finance.get('gross_revenue'))}")
    lines.append(f"- ROI/ROAS рекламы: {ads.get('roas', 'н/д')}")
    lines.append("")

    lines.append("## 2. Почему результат такой")
    reasons = decision.get("reasons_of_loss") or []
    if reasons:
        for reason in reasons:
            lines.append(f"- {reason.get('reason')}: {reason.get('numbers')}")
    else:
        lines.append("- Причины не определены: не хватает данных для причинно-следственного вывода.")
    lines.append("")

    lines.append("## 3. Финансы")
    lines.append(f"- Выручка: {_money(finance.get('gross_revenue'))}")
    lines.append(f"- Комиссия WB: {_money(finance.get('commission'))}")
    lines.append(f"- Логистика: {_money(finance.get('logistics'))}")
    lines.append(f"- Хранение: {_money(finance.get('storage'))}")
    lines.append(f"- Себестоимость: {_money(finance.get('cogs_total'))}")
    lines.append(f"- Налог: {_money(finance.get('tax'))}")
    lines.append(f"- Прибыль: {_money(finance.get('profit'))}")
    lines.append(f"- Маржа: {_pct_ratio(finance.get('margin'))}")
    lines.append("")

    lines.append("## 4. Реклама")
    lines.append(f"- Расход: {_money(ads.get('spend'))}")
    lines.append(f"- Атрибутированная выручка: {_money(ads.get('revenue_attr'))}")
    lines.append(f"- ROAS: {ads.get('roas', 0)}")
    leaks = decision.get("ads_leaks") or []
    if leaks:
        lines.append(f"- Слив бюджета: найдено {len(leaks)} проблемных сегментов.")
    else:
        lines.append("- Слив бюджета по доступным данным не подтвержден.")
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
        lines.append("- Убыточные SKU не выявлены или данных недостаточно.")
    if sku_without_sales:
        lines.append("- SKU без продаж с остатком (top-10):")
        for item in sku_without_sales[:10]:
            lines.append(f"- SKU {item.get('sku')}: остаток {_int(item.get('stock_qty'))} шт, выкупы {_int(item.get('buyouts'))}")
    else:
        lines.append("- SKU без продаж с остатком не выявлены или данных недостаточно.")
    lines.append("")

    lines.append("## 7. Остатки")
    lines.append(f"- Остаток: {_int(stock.get('stock_units'))} шт")
    lines.append(f"- SKU/позиций: {_int(stock.get('sku_count'))}")
    lines.append(f"- Дни покрытия: {stock.get('days_of_cover', 0)}")
    dead_stock = decision.get("dead_stock") or []
    if dead_stock:
        lines.append(f"- Мертвые остатки: {len(dead_stock)} SKU/позиций без продаж.")
    else:
        lines.append("- Мертвые остатки по доступным данным не зафиксированы.")
    lines.append("")

    lines.append("## 8. Поисковые запросы (если есть)")
    if (search.get("status") or "") == "ok":
        lines.append(f"- Прибыльные: {len(search.get('profitable') or [])}")
        lines.append(f"- Убыточные: {len(search.get('unprofitable') or [])}")
        lines.append(f"- Потенциал: {len(search.get('potential') or [])}")
    else:
        lines.append("- Данные по поисковым запросам отсутствуют.")
    lines.append("")

    lines.append("## 9. Рекомендации")
    if actions:
        for action in actions:
            lines.append(
                f"- [{action.get('priority')}] ({action.get('area')}) {action.get('action')} "
                f"— {action.get('why')}. Эффект: {action.get('expected_effect')}."
            )
    else:
        lines.append("- Действия не сформированы: недостаточно данных.")
    lines.append("")

    missing_required = inputs.get("missing_required") or []
    missing_optional = inputs.get("missing_optional") or []
    lines.append("## Доступность данных")
    lines.append(f"- Найдено файлов: {len(inputs.get('found_files') or [])}")
    lines.append(f"- Собраны блоки: {', '.join(inputs.get('blocks_collected') or []) or 'нет'}")
    lines.append(f"- Пропущены блоки: {', '.join(inputs.get('blocks_skipped') or []) or 'нет'}")
    if missing_required:
        lines.append(f"- Не хватает обязательных файлов: {', '.join(missing_required)}")
    if missing_optional:
        lines.append(f"- Не хватает опциональных файлов: {', '.join(missing_optional)}")
    if not missing_required and not missing_optional:
        lines.append("- Все ожидаемые файлы присутствуют.")
    lines.append("")

    # Keep compact SKU profit appendix.
    if sku_profit:
        lines.append("## Приложение: top SKU по прибыли")
        for item in sku_profit[:10]:
            lines.append(
                f"- SKU {item.get('sku')}: прибыль {_money(item.get('profit'))}, "
                f"выручка {_money(item.get('revenue'))}, остаток {_int(item.get('stock_qty'))}"
            )
        lines.append("")

    return "\n".join(lines).strip() + "\n"

