"""Report builder for Ozon express audit MVP."""

from __future__ import annotations

from typing import Any


def _fmt_int(value: Any) -> str:
    try:
        return str(int(float(value or 0)))
    except Exception:
        return "0"


def _fmt_money(value: Any) -> str:
    if value is None:
        return "недостаточно данных"
    try:
        return f"{float(value):,.2f} RUB".replace(",", " ")
    except Exception:
        return "недостаточно данных"


def _build_actions(facts: dict[str, Any]) -> list[dict[str, str]]:
    top_sku = facts.get("top_sku") or []
    problem_sku = facts.get("problem_sku") or []

    actions: list[dict[str, str]] = []
    if problem_sku:
        skus = ", ".join(str(x.get("sku")) for x in problem_sku[:5] if x.get("sku"))
        if skus:
            actions.append(
                {
                    "priority": "P0",
                    "action": f"Проверить и сократить неликвид по SKU: {skus}",
                    "why": "Есть товары без продаж или с низкой оборачиваемостью.",
                }
            )

    if top_sku:
        skus = ", ".join(str(x.get("sku")) for x in top_sku[:5] if x.get("sku"))
        if skus:
            actions.append(
                {
                    "priority": "P1",
                    "action": f"Усилить карточки и продвижение топ SKU: {skus}",
                    "why": "Эти позиции формируют основную отдачу в текущем файле.",
                }
            )

    if not actions:
        actions.append(
            {
                "priority": "P1",
                "action": "Собрать расширенный набор данных (финансы, реклама, остатки по складам).",
                "why": "По одному файлу рекомендации ограничены.",
            }
        )
    return actions


def build_ozon_report(facts: dict[str, Any]) -> dict[str, Any]:
    summary = facts.get("summary") or {}
    top_sku = facts.get("top_sku") or []
    problem_sku = facts.get("problem_sku") or []
    detected = facts.get("detected_columns") or {}
    quality = facts.get("data_quality") or {}

    actions = _build_actions(facts)

    lines: list[str] = []
    lines.append("# Экспресс-аудит Ozon")
    lines.append("")

    lines.append("## Ограничение данных")
    lines.append("- Анализ выполнен на основе одного файла.")
    lines.append("- Выводы предварительные и подходят для экспресс-оценки.")
    lines.append("")

    lines.append("## Основные показатели")
    lines.append(f"- Заказы: {_fmt_int(summary.get('total_orders'))}")
    lines.append(f"- Выручка: {_fmt_money(summary.get('total_revenue'))}")
    lines.append(f"- SKU: {_fmt_int(summary.get('sku_count'))}")
    lines.append("")

    lines.append("## Ключевые наблюдения")
    if top_sku:
        top_preview = ", ".join(str(x.get("sku")) for x in top_sku[:5] if x.get("sku"))
        lines.append(f"- Топ SKU по текущему файлу: {top_preview or 'недостаточно данных'}.")
    else:
        lines.append("- Топ SKU: недостаточно данных.")

    no_sales_count = len([x for x in problem_sku if str(x.get("reason")) in {"без продаж", "остаток есть, продаж нет"}])
    lines.append(f"- SKU без продаж: {_fmt_int(no_sales_count)}.")

    if summary.get("sku_count") and summary.get("sku_count") > 0 and top_sku:
        top_orders = float(sum((x.get("orders") or 0) for x in top_sku[:3]))
        total_orders = float(summary.get("total_orders") or 0)
        if total_orders > 0 and (top_orders / total_orders) >= 0.5:
            lines.append("- Есть перекос ассортимента: заметная доля заказов сосредоточена в ограниченном числе SKU.")
        else:
            lines.append("- Перекос ассортимента по текущим данным не выражен.")
    else:
        lines.append("- Перекос ассортимента: недостаточно данных.")
    lines.append("")

    lines.append("## Проблемы")
    if problem_sku:
        for item in problem_sku[:10]:
            sku = item.get("sku") or "unknown"
            reason = item.get("reason") or "требует проверки"
            orders = item.get("orders")
            stock = item.get("stock")
            parts = [f"SKU {sku}: {reason}"]
            if orders is not None:
                parts.append(f"заказы={_fmt_int(orders)}")
            if stock is not None:
                parts.append(f"остаток={_fmt_int(stock)}")
            lines.append(f"- {', '.join(parts)}")
    else:
        lines.append("- Явных проблемных SKU не выявлено или недостаточно данных.")
    lines.append("")

    lines.append("## Рекомендации")
    for action in actions:
        lines.append(f"- [{action.get('priority')}] {action.get('action')} ({action.get('why')})")
    lines.append("")

    lines.append("## Диагностика распознавания колонок")
    lines.append(f"- SKU: {detected.get('sku') or 'недостаточно данных'}")
    lines.append(f"- Заказы: {detected.get('orders') or 'недостаточно данных'}")
    lines.append(f"- Выручка: {detected.get('revenue') or 'недостаточно данных'}")
    lines.append(f"- Остатки: {detected.get('stock') or 'недостаточно данных'}")
    lines.append(f"- Строк в файле: {_fmt_int(quality.get('row_count'))}")
    lines.append("")

    return {
        "pdf_markdown": "\n".join(lines).strip() + "\n",
        "actions": actions,
    }

