"""Report builder for Ozon express audit."""

from __future__ import annotations

from typing import Any


def _fmt_int(value: Any) -> str:
    if value is None:
        return "н/д"
    try:
        return str(int(round(float(value))))
    except Exception:
        return "н/д"


def _fmt_money(value: Any) -> str:
    if value is None:
        return "н/д"
    try:
        return f"{float(value):,.2f} RUB".replace(",", " ")
    except Exception:
        return "н/д"


def _fmt_pct(value: Any, digits: int = 2) -> str:
    if value is None:
        return "н/д"
    try:
        return f"{float(value):.{digits}f}%"
    except Exception:
        return "н/д"


def _fmt_ratio_pct(value: Any, digits: int = 2) -> str:
    if value is None:
        return "н/д"
    try:
        return f"{float(value) * 100.0:.{digits}f}%"
    except Exception:
        return "н/д"


def _safe_text(value: Any) -> str:
    return str(value or "").strip().replace("|", "/")


def _split_problem_types(problem_rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {
        "no_orders_with_stock": [],
        "high_drr": [],
        "high_cancellation_share": [],
        "low_buyout_rate": [],
        "bad_price_index_on_selling": [],
        "suspicious_revenue_without_orders": [],
    }
    for row in problem_rows:
        if not isinstance(row, dict):
            continue
        kind = str(row.get("type") or "")
        if kind in output:
            output[kind].append(row)
    return output


def _labels(rows: list[dict[str, Any]], limit: int = 5) -> str:
    values = [_safe_text(x.get("label") or x.get("sku")) for x in rows]
    values = [x for x in values if x]
    return ", ".join(values[:limit])


def _build_actions(facts: dict[str, Any]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []

    summary = facts.get("summary") or {}
    abc = facts.get("abc_analysis") or {}
    abc_summary = abc.get("summary") if isinstance(abc.get("summary"), dict) else {}
    promotion = facts.get("promotion_summary") or {}
    price_index = facts.get("price_index_summary") or {}
    consistency = facts.get("consistency_checks") or {}
    suspicious = consistency.get("suspicious_revenue_without_orders") or []
    problems = _split_problem_types(facts.get("problem_sku") or [])

    a_count = (abc_summary.get("counts") or {}).get("A")
    a_share = abc_summary.get("a_revenue_share_pct")
    if a_count is not None and a_share is not None and int(a_count) > 0:
        actions.append(
            {
                "priority": "P0",
                "area": "assortment",
                "action": "Сконцентрировать закупки и продвижение на группе A",
                "why": f"{int(a_count)} SKU формируют {float(a_share):.1f}% выручки",
                "expected_effect": "Рост оборота без расширения слабого хвоста ассортимента",
            }
        )

    no_orders_with_stock = problems.get("no_orders_with_stock") or []
    if no_orders_with_stock:
        actions.append(
            {
                "priority": "P0",
                "area": "stock",
                "action": f"Сократить неликвидные остатки по SKU: {_labels(no_orders_with_stock)}",
                "why": f"{len(no_orders_with_stock)} SKU имеют остаток при нулевых заказах",
                "expected_effect": "Разморозка денег в запасах и снижение складской нагрузки",
            }
        )

    critical_drr = [x for x in (problems.get("high_drr") or []) if str(x.get("severity") or "") == "critical"]
    high_drr = problems.get("high_drr") or []
    if critical_drr:
        actions.append(
            {
                "priority": "P0",
                "area": "promotion",
                "action": f"Снизить ставки/отключить рекламу по SKU с ДРР > 30%: {_labels(critical_drr)}",
                "why": f"{len(critical_drr)} SKU тратят на рекламу более 30% выручки",
                "expected_effect": "Снижение риска убыточного трафика и стабилизация маржи",
            }
        )
    elif high_drr:
        actions.append(
            {
                "priority": "P1",
                "area": "promotion",
                "action": f"Пересчитать кампании по SKU с ДРР > 25%: {_labels(high_drr)}",
                "why": f"{len(high_drr)} SKU имеют высокий ДРР при активной рекламе",
                "expected_effect": "Снижение рекламной нагрузки без потери ключевых продаж",
            }
        )

    low_buyout = problems.get("low_buyout_rate") or []
    if low_buyout:
        actions.append(
            {
                "priority": "P1",
                "area": "card_quality",
                "action": f"Проверить карточки и причины отказов по SKU: {_labels(low_buyout)}",
                "why": f"{len(low_buyout)} SKU имеют низкий выкуп",
                "expected_effect": "Рост выкупа и снижение потерь на отменах/возвратах",
            }
        )

    high_cancel = problems.get("high_cancellation_share") or []
    if high_cancel:
        actions.append(
            {
                "priority": "P1",
                "area": "orders_quality",
                "action": f"Снизить причины отмен по SKU: {_labels(high_cancel)}",
                "why": f"{len(high_cancel)} SKU имеют высокую долю отмен",
                "expected_effect": "Повышение конверсии в выкуп и более стабильный оборот",
            }
        )

    unprofitable_count = int(price_index.get("unprofitable") or 0)
    if unprofitable_count > 0:
        actions.append(
            {
                "priority": "P1",
                "area": "pricing",
                "action": "Пересмотреть цены и unit-экономику по SKU с невыгодным индексом",
                "why": f"{unprofitable_count} SKU помечены как невыгодные по индексу цены",
                "expected_effect": "Снижение давления на маржу и рост вклада продающих SKU",
            }
        )

    if suspicious:
        actions.append(
            {
                "priority": "P0",
                "area": "data_quality",
                "action": "Проверить выгрузку: устранить случаи выручки без заказов",
                "why": f"{len(suspicious)} SKU имеют revenue > 0 при orders = 0",
                "expected_effect": "Устранение противоречий и повышение точности управленческих решений",
            }
        )

    sku_without_orders = summary.get("sku_without_orders_count")
    sku_total = summary.get("sku_count")
    if sku_without_orders is not None and sku_total is not None and int(sku_total) > 0:
        share = float(sku_without_orders) / float(sku_total)
        if share >= 0.5:
            actions.append(
                {
                    "priority": "P1",
                    "area": "assortment",
                    "action": "Провести ревизию хвоста ассортимента и убрать позиции без спроса",
                    "why": f"{int(sku_without_orders)} из {int(sku_total)} SKU без заказов",
                    "expected_effect": "Снижение операционной сложности и ускорение оборачиваемости",
                }
            )

    if not actions:
        actions.append(
            {
                "priority": "P2",
                "area": "growth",
                "action": "Масштабировать текущие рабочие SKU без резкого расширения ассортимента",
                "why": "Критичных отклонений по текущей выгрузке не выявлено",
                "expected_effect": "Контролируемый рост оборота при сохранении маржинальности",
            }
        )

    return actions


def _append_problem_block(lines: list[str], title: str, rows: list[dict[str, Any]], formatter) -> None:
    if not rows:
        return
    lines.append(f"### {title}")
    for row in rows[:10]:
        lines.append(formatter(row))
    lines.append("")


def build_ozon_report(facts: dict[str, Any]) -> dict[str, Any]:
    summary = facts.get("summary") or {}
    top_sku = facts.get("top_sku") or []
    problem_rows = facts.get("problem_sku") or []
    assortment = facts.get("assortment_summary") or {}
    abc = facts.get("abc_analysis") or {}
    abc_summary = abc.get("summary") if isinstance(abc.get("summary"), dict) else {}
    counts = abc_summary.get("counts") if isinstance(abc_summary.get("counts"), dict) else {}
    promotion = facts.get("promotion_summary") or {}
    period = facts.get("period") or {}
    quality = facts.get("data_quality") or {}
    key_findings = facts.get("key_findings") or []
    consistency = facts.get("consistency_checks") or {}
    suspicious = consistency.get("suspicious_revenue_without_orders") or []
    problems = _split_problem_types(problem_rows)
    actions = _build_actions(facts)

    period_label = _safe_text(period.get("label_ru") or "период не распознан автоматически")
    period_message = _safe_text(period.get("message") or "")

    lines: list[str] = []
    lines.append("# Экспресс-аудит Ozon")
    lines.append("")
    lines.append("## Период")
    lines.append(f"- {period_label}")
    if period_message:
        lines.append(f"- {period_message}")
    lines.append("")

    lines.append("## Ограничение данных")
    lines.append("- Анализ выполнен на основе одного файла Ozon.")
    lines.append("- Выводы предварительные; для полного аудита нужны финансы, реклама и unit-экономика кабинета.")
    lines.append("")

    lines.append("## Главные показатели")
    lines.append(f"- SKU: {_fmt_int(summary.get('sku_count'))}")
    lines.append(f"- SKU с заказами: {_fmt_int(summary.get('sku_with_orders_count'))}")
    lines.append(f"- SKU без заказов: {_fmt_int(summary.get('sku_without_orders_count'))}")
    lines.append(f"- Заказы: {_fmt_int(summary.get('total_orders'))}")
    lines.append(f"- Выручка: {_fmt_money(summary.get('total_revenue'))}")
    lines.append(f"- Выкуп: {_fmt_int(summary.get('total_buyouts'))}")
    lines.append(f"- Отмены: {_fmt_int(summary.get('total_cancellations'))}")
    lines.append(f"- Остаток: {_fmt_int(summary.get('total_stock'))}")
    lines.append("")

    lines.append("## Ключевые выводы")
    if key_findings:
        for finding in key_findings[:7]:
            lines.append(f"- {finding}")
    else:
        lines.append("- Недостаточно данных для сильных выводов: проверьте корректность выгрузки.")
    lines.append("")
    lines.append("---PAGEBREAK---")
    lines.append("")

    lines.append("## Топ SKU")
    if top_sku:
        lines.append("| SKU | Заказы | Выручка | Остаток | ДРР |")
        lines.append("| --- | ---: | ---: | ---: | ---: |")
        for row in top_sku[:10]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _safe_text(row.get("label") or row.get("sku")),
                        _fmt_int(row.get("orders")),
                        _fmt_money(row.get("revenue")),
                        _fmt_int(row.get("stock")),
                        _fmt_ratio_pct(row.get("drr")),
                    ]
                )
                + " |"
            )
    else:
        lines.append("- Топ SKU не сформирован: нет валидных продающих SKU с orders > 0.")
    lines.append("")

    lines.append("## Структура ассортимента (ABC)")
    lines.append(f"- Доля выручки группы A: {_fmt_pct(abc_summary.get('a_revenue_share_pct'), 1)}")
    lines.append(
        f"- SKU в группах A/B/C: {_fmt_int(counts.get('A'))} / {_fmt_int(counts.get('B'))} / {_fmt_int(counts.get('C'))}"
    )
    lines.append(f"- Top-5 доля выручки: {_fmt_pct(assortment.get('top_5_revenue_share_pct'), 1)}")
    lines.append(f"- Top-10 доля выручки: {_fmt_pct(assortment.get('top_10_revenue_share_pct'), 1)}")
    lines.append(f"- {assortment.get('sales_concentration_comment') or abc_summary.get('concentration_comment') or 'н/д'}")
    lines.append("")
    lines.append("---PAGEBREAK---")
    lines.append("")

    lines.append("## Проблемные SKU")
    _append_problem_block(
        lines,
        "1) Без заказов + остаток (замороженные деньги)",
        problems.get("no_orders_with_stock") or [],
        lambda row: (
            f"- {_safe_text(row.get('label'))}: заказов {_fmt_int(row.get('orders'))}, "
            f"остаток {_fmt_int(row.get('stock'))} -> деньги заморожены в неликвиде."
        ),
    )
    _append_problem_block(
        lines,
        "2) Высокий ДРР (сливается бюджет)",
        problems.get("high_drr") or [],
        lambda row: (
            f"- {_safe_text(row.get('label'))}: ДРР {_fmt_pct(row.get('drr_pct'))}, "
            f"расход {_fmt_money(row.get('ad_spend'))}, выручка {_fmt_money(row.get('revenue'))} -> риск убыточности."
        ),
    )
    _append_problem_block(
        lines,
        "3) Низкий выкуп",
        problems.get("low_buyout_rate") or [],
        lambda row: (
            f"- {_safe_text(row.get('label'))}: выкуп {_fmt_pct(row.get('buyout_rate_pct'))} "
            f"при {_fmt_int(row.get('orders'))} заказах -> потери оборота."
        ),
    )
    _append_problem_block(
        lines,
        "4) Высокая доля отмен",
        problems.get("high_cancellation_share") or [],
        lambda row: (
            f"- {_safe_text(row.get('label'))}: отмены {_fmt_int(row.get('cancellations'))}, "
            f"доля {_fmt_pct(row.get('cancel_share_pct'))} -> просадка выкупа."
        ),
    )
    _append_problem_block(
        lines,
        "5) Подозрительная консистентность (выручка без заказов)",
        problems.get("suspicious_revenue_without_orders") or [],
        lambda row: (
            f"- {_safe_text(row.get('label'))}: выручка {_fmt_money(row.get('revenue'))} "
            f"при {_fmt_int(row.get('orders'))} заказах -> нужна проверка выгрузки."
        ),
    )

    if not any(problems.values()):
        lines.append("- Критичные проблемные SKU по текущим правилам не выявлены.")
        lines.append("")

    lines.append("## Продвижение и ДРР")
    lines.append(
        f"- SKU с рекламой: {_fmt_int(promotion.get('sku_with_ads_count'))} "
        f"({_fmt_pct(promotion.get('ads_sku_share_pct'), 1)} ассортимента)."
    )
    lines.append(f"- Доля выручки SKU с рекламой: {_fmt_pct(promotion.get('revenue_with_ads_share_pct'), 1)}.")
    lines.append(f"- Средний ДРР по SKU с расходом: {_fmt_ratio_pct(promotion.get('avg_drr_active'))}.")
    lines.append(f"- SKU с ДРР > 25%: {_fmt_int(promotion.get('high_drr_count'))}.")
    lines.append(f"- SKU с ДРР > 30%: {_fmt_int(promotion.get('critical_drr_count'))}.")
    if not quality.get("has_spend"):
        lines.append("- Рекламный расход в файле не найден: ДРР трактуется ограниченно.")
    lines.append("")
    lines.append("---PAGEBREAK---")
    lines.append("")

    lines.append("## Рекомендации (Action-Level)")
    lines.append("| Priority | Area | Action | Why | Expected Effect |")
    lines.append("| --- | --- | --- | --- | --- |")
    for action in actions:
        lines.append(
            "| "
            + " | ".join(
                [
                    _safe_text(action.get("priority")),
                    _safe_text(action.get("area")),
                    _safe_text(action.get("action")),
                    _safe_text(action.get("why")),
                    _safe_text(action.get("expected_effect")),
                ]
            )
            + " |"
        )
    lines.append("")

    lines.append("## Диагностика источника")
    lines.append(f"- Выбран лист: {_safe_text(facts.get('chosen_sheet') or 'н/д')}")
    lines.append(f"- Выбран header_row: {_fmt_int(facts.get('chosen_header_row'))}")
    lines.append(f"- Обработано строк: {_fmt_int(facts.get('row_count'))}")
    lines.append(f"- Консистентность данных: {'ok' if quality.get('consistency_ok') else 'needs_check'}")
    if suspicious:
        lines.append(f"- Подозрительных SKU (выручка без заказов): {_fmt_int(len(suspicious))}")
    lines.append("")

    return {
        "pdf_markdown": "\n".join(lines).strip() + "\n",
        "actions": actions,
    }
