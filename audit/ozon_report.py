"""Markdown report builder for Ozon MVP audit."""

from __future__ import annotations

from typing import Any


def _money(value: Any) -> str:
    if value is None:
        return "н/д"
    try:
        return f"{float(value):,.2f} RUB".replace(",", " ")
    except Exception:
        return "н/д"


def _int(value: Any) -> str:
    if value is None:
        return "н/д"
    try:
        return str(int(float(value)))
    except Exception:
        return "н/д"


def _pct_ratio(value: Any) -> str:
    try:
        return f"{float(value or 0) * 100:.2f}%"
    except Exception:
        return "0.00%"


def build_ozon_audit_markdown(facts: dict[str, Any]) -> str:
    products_summary = facts.get("ozon_products_summary") or {}
    sku_profit = (facts.get("sku_profit") or {}).get("items") or []
    sku_summary = (facts.get("sku_profit") or {}).get("summary") or {}
    abc = facts.get("abc_analysis") or {}
    decision = facts.get("decision_layer") or {}
    inputs = facts.get("inputs") or {}
    top_by_revenue = facts.get("top_sku_by_revenue") or []
    top_by_orders = facts.get("top_sku_by_orders") or []
    sku_without_orders = facts.get("sku_without_orders") or []
    sku_with_stock = facts.get("sku_with_stock") or []

    total_revenue = products_summary.get("total_revenue")
    total_orders = products_summary.get("total_orders")
    known_profit = (decision.get("kpi") or {}).get("gross_profit_total_known")
    abc_summary = abc.get("summary") or {}
    products_diag = products_summary.get("diagnostics") or {}

    lines: list[str] = []
    lines.append("# АУДИТ Ozon КАБИНЕТА (MVP)")
    lines.append("")

    lines.append("## 1. Итог")
    lines.append(f"- Проанализировано SKU: {_int(products_summary.get('rows_count'))}")
    lines.append(f"- Выручка по отчету товаров: {_money(total_revenue)}")
    lines.append(f"- Заказы по отчету товаров: {_int(total_orders)}")
    if known_profit is not None:
        lines.append(f"- Валовая прибыль (только SKU с cogs): {_money(known_profit)}")
    else:
        lines.append("- Валовая прибыль не рассчитана: нет достаточных данных по себестоимости/заказам.")
    for warning in (products_summary.get("metrics_warnings") or []):
        lines.append(f"- [diag] {warning}")
    lines.append("")

    lines.append("## 2. Что удалось проанализировать")
    lines.append("- SKU-уровень по отчету Ozon по товарам.")
    if abc_summary.get("basis") == "revenue":
        lines.append("- ABC-анализ по выручке (fallback, т.к. нет COGS).")
    else:
        lines.append("- ABC-анализ по валовой прибыли.")
    lines.append("- Проблемные SKU и точки роста на текущем наборе данных.")
    lines.append("")

    lines.append("## 3. Топ SKU")
    top_profit = [x for x in sku_profit if x.get("gross_profit") is not None]
    top_profit = sorted(top_profit, key=lambda x: float(x.get("gross_profit") or 0.0), reverse=True)[:10]
    if top_profit:
        lines.append("### 3.1 По валовой прибыли")
        for item in top_profit:
            sku_label = item.get("sku") or item.get("offer_id") or item.get("name") or "unknown"
            lines.append(
                f"- SKU {sku_label}: выручка {_money(item.get('revenue_total'))}, "
                f"валовая прибыль {_money(item.get('gross_profit'))}, заказы {_int(item.get('orders'))}"
            )
    else:
        lines.append("- Нет SKU с рассчитанной валовой прибылью.")

    if top_by_revenue:
        lines.append("### 3.2 По выручке")
        for item in top_by_revenue[:10]:
            sku_label = item.get("sku") or item.get("offer_id") or item.get("name") or "unknown"
            lines.append(
                f"- SKU {sku_label}: выручка {_money(item.get('revenue_total'))}, "
                f"заказы {_int(item.get('orders'))}"
            )

    if top_by_orders:
        lines.append("### 3.3 По заказам")
        for item in top_by_orders[:10]:
            sku_label = item.get("sku") or item.get("offer_id") or item.get("name") or "unknown"
            lines.append(
                f"- SKU {sku_label}: заказы {_int(item.get('orders'))}, "
                f"выручка {_money(item.get('revenue_total'))}"
            )
    lines.append("")

    lines.append("## 4. Слабые SKU / Риски")
    sku_problems = decision.get("sku_problems") or []
    if sku_problems:
        for item in sku_problems[:15]:
            sku_label = item.get("sku") or item.get("offer_id") or item.get("name") or "unknown"
            reason = item.get("reason") or item.get("type")
            lines.append(f"- SKU {sku_label}: {reason}")
    else:
        lines.append("- Критичные SKU-проблемы не выявлены на доступных данных.")

    if sku_without_orders:
        lines.append("### 4.1 SKU без заказов")
        for item in sku_without_orders[:10]:
            sku_label = item.get("sku") or item.get("offer_id") or item.get("name") or "unknown"
            lines.append(f"- SKU {sku_label}: заказов {_int(item.get('orders'))}, выручка {_money(item.get('revenue_total'))}")

    if sku_with_stock:
        lines.append("### 4.2 SKU с остатками")
        for item in sku_with_stock[:10]:
            sku_label = item.get("sku") or item.get("offer_id") or item.get("name") or "unknown"
            lines.append(f"- SKU {sku_label}: остаток {_int(item.get('stock'))}, заказы {_int(item.get('orders'))}")
    lines.append("")

    lines.append("## 5. ABC-анализ")
    lines.append(f"- A: {_int(abc_summary.get('a_count'))} SKU")
    lines.append(f"- B: {_int(abc_summary.get('b_count'))} SKU")
    lines.append(f"- C: {_int(abc_summary.get('c_count'))} SKU")
    lines.append(f"- Покрыто SKU: {_int(abc_summary.get('total_items'))}")
    if abc_summary.get("basis_note"):
        lines.append(f"- {abc_summary.get('basis_note')}")
    lines.append("")

    lines.append("## 6. Пробелы в данных")
    lines.append("- Чистая прибыль кабинета пока не рассчитана, так как нет фин. отчета Ozon.")
    lines.append("- Реклама не проанализирована, так как нет рекламного отчета Ozon.")
    lines.append("- Остатки не проанализированы полностью, так как нет отдельного отчета остатков Ozon.")
    gaps = decision.get("data_gaps") or []
    for gap in gaps[:15]:
        lines.append(f"- {gap.get('type')}: {gap.get('details')}")
    lines.append("")

    lines.append("## 7. Что запросить у клиента дальше")
    lines.append("- Финансовый отчет Ozon за тот же период.")
    lines.append("- Рекламный отчет Ozon за тот же период.")
    lines.append("- Отчет по остаткам Ozon.")
    lines.append("")

    lines.append("## 8. Что делать сейчас")
    actions = facts.get("actions") or []
    if actions:
        for action in actions:
            lines.append(
                f"- [{action.get('priority')}] ({action.get('area')}) {action.get('action')} "
                f"- {action.get('why')}. Эффект: {action.get('expected_effect')}."
            )
    else:
        lines.append("- Действия не сформированы: недостаточно данных.")
    lines.append("")

    lines.append("## Диагностика загрузки")
    lines.append(f"- Найдено файлов: {_int(len(inputs.get('found_files') or []))}")
    lines.append(f"- Собраны блоки: {', '.join(inputs.get('blocks_collected') or []) or 'нет'}")
    lines.append(f"- Пропущены блоки: {', '.join(inputs.get('blocks_skipped') or []) or 'нет'}")
    lines.append(f"- Не хватает обязательных: {', '.join(inputs.get('missing_required') or []) or 'нет'}")
    lines.append(f"- Не хватает опциональных: {', '.join(inputs.get('missing_optional') or []) or 'нет'}")
    lines.append(f"- source_columns: {products_diag.get('source_columns') or []}")
    lines.append(f"- resolved_columns: {products_diag.get('resolved_columns') or {}}")
    lines.append(f"- unresolved_columns: {products_diag.get('unresolved_columns') or []}")
    lines.append("")

    lines.append("## Быстрые метрики покрытия")
    lines.append(f"- SKU с рассчитанной прибылью: {_int(sku_summary.get('ok_items'))}")
    lines.append(f"- SKU без cogs: {_int(sku_summary.get('no_cogs_items'))}")
    lines.append(f"- SKU без orders: {_int(sku_summary.get('sku_without_orders_count'))}")
    lines.append(f"- SKU с остатками: {_int(sku_summary.get('sku_with_stock_count'))}")
    lines.append("")

    margin_known = (facts.get("financial_summary") or {}).get("margin_from_products_with_cogs")
    if margin_known is not None:
        lines.append(f"- Валовая маржа по SKU с cogs: {_pct_ratio(margin_known)}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"
