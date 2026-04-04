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
    if value is None:
        return ""
    return _repair_text(str(value)).strip()


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
    local_orders_insights = facts.get("local_orders_insights") or {}
    decision = facts.get("decision_layer") or {}
    inputs = facts.get("inputs") or {}
    sku_profit = facts.get("sku_profit") or []
    actions = facts.get("actions") or []

    source_label = _text(facts.get("source") or "wb").upper()
    period_label = _period_text(facts.get("period") or facts.get("date") or "н/д")
    report_date = _text(facts.get("date") or period_label)
    selected_files = inputs.get("selected_files") if isinstance(inputs.get("selected_files"), dict) else {}

    lines: list[str] = []
    lines.append(f"# {source_label} аудит за период: {period_label}")
    lines.append(f"Период отчета: {period_label}")
    lines.append(f"Дата формирования: {report_date}")
    lines.append(f"Источник: {source_label} (file-based audit)")
    lines.append("")

    lines.append("## Источники (файлы)")
    source_rows = [
        ["Финансы", _source_file_cell(selected_files.get("finance"))],
        ["Воронка", _source_file_cell(selected_files.get("funnel"))],
        ["Реклама", _source_file_cell(selected_files.get("ads"))],
        ["Остатки", _source_file_cell(selected_files.get("stocks"))],
        ["Поиск", _source_file_cell(selected_files.get("search"))],
        ["COGS", _source_file_cell(selected_files.get("cogs"))],
    ]
    _append_markdown_table(lines, ["Блок", "Файл"], source_rows)

    lines.append("## 1. KPI и инсайты")
    insights: list[str] = [
        _kpi_state_text(decision, finance),
        f"Выручка за период: {_money(finance.get('gross_revenue'))}.",
        f"ROAS рекламы: {_sanitize_table_cell(ads.get('roas', 'н/д'))}.",
    ]
    for reason in _loss_reasons_human(decision, finance)[:2]:
        insights.append(reason)
    for insight in insights[:5]:
        lines.append(f"- {insight}")
    lines.append("")

    lines.append("## 2. Финансы за период")
    profit_label = _text(finance.get("profit_label") or "Прибыль")
    roi_main, roi_extra = _roi_line(finance, ads)
    finance_rows = [
        ["Выручка", _money(finance.get("gross_revenue"))],
        ["Продажи (сумма заказов)", _money(funnel.get("revenue_orders"))],
        ["Выкупы (сумма)", _money(finance.get("gross_revenue"))],
        ["Выкупы (шт)", _to_int(funnel.get("buys"))],
        ["Комиссия WB", _money(finance.get("commission"))],
        ["Логистика", _money(finance.get("logistics"))],
        ["Хранение", _money(finance.get("storage"))],
        ["Себестоимость", _money(finance.get("cogs_total"))],
        ["Налог", _money(finance.get("tax"))],
        [profit_label, _money(finance.get("profit"))],
        ["Маржа", _pct_ratio(finance.get("margin"))],
        ["ROI", _text(roi_main.replace("ROI: ", ""))],
        ["К перечислению", _money(finance.get("payout"))],
    ]
    _append_markdown_table(lines, ["Метрика", "Значение"], finance_rows, align_right={1})
    for extra in roi_extra:
        lines.append(f"- {extra}")
    if finance.get("profit_note"):
        lines.append(f"- {_text(finance.get('profit_note'))}")
    lines.append("")

    _page_break(lines)

    lines.append("## 3. Воронка продаж")
    impressions = _extract_funnel_impressions(facts, funnel)
    funnel_rows: list[list[Any]] = []
    if impressions is not None:
        funnel_rows.append(["Показы", _to_int(impressions)])
    funnel_rows.extend(
        [
            ["Переходы в карточку", _to_int(funnel.get("views"))],
            ["В корзину", _to_int(funnel.get("add_to_cart"))],
            ["Заказы", _to_int(funnel.get("orders"))],
            ["Выкупы", _to_int(funnel.get("buys"))],
            ["CR в корзину", _pct_ratio(funnel.get("cr_cart"))],
            ["CR в заказ", _pct_ratio(funnel.get("cr_order"))],
            ["% выкупа", _pct_ratio(funnel.get("buyout_rate"))],
            ["Заказы на сумму", _money(funnel.get("revenue_orders"))],
            ["Выкупы на сумму", _money(finance.get("gross_revenue"))],
        ]
    )
    _append_markdown_table(lines, ["Показатель", "Значение"], funnel_rows, align_right={1})
    lines.append(
        "- Часть заказов не выкупается, поэтому оборот по заказам обычно выше фактической выручки из finance."
    )
    lines.append("")

    lines.append("## 4. Реклама")
    drr_value = _to_float(ads.get("drr"))
    drr_text = _pct_ratio(drr_value) if drr_value is not None else "н/д"
    ads_rows = [
        ["Расход", _money(ads.get("spend"))],
        ["Показы", _to_int(ads.get("impressions"))],
        ["Клики", _to_int(ads.get("clicks"))],
        ["CTR", _pct_ratio(ads.get("ctr"))],
        ["CPC", _money(ads.get("cpc"))],
        ["CPM", _money(ads.get("cpm"))],
        ["Атрибутированная выручка", _money(ads.get("revenue_attr"))],
        ["ROAS", _sanitize_table_cell(ads.get("roas", "н/д"))],
        ["ДРР", drr_text],
    ]
    _append_markdown_table(lines, ["Метрика", "Значение"], ads_rows, align_right={1})

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
    lines.append(f"- Найдено {len(leaks)} рекламных связок/запросов без заказов." if leaks else "- Связки без заказов не обнаружены.")
    lines.append("")

    lines.append("## 5. Остатки и риск дефицита")
    stock_rows = [
        ["Остатки, шт", _to_int(stock.get("stock_units"))],
        ["SKU/позиций", _to_int(stock.get("sku_count"))],
        ["Дни покрытия", _sanitize_table_cell(stock.get("days_of_cover"))],
        ["Порог, дней", _sanitize_table_cell(stock.get("threshold_days"))],
        ["Риск дефицита", "да" if bool(stock.get("risk_of_oos")) else "нет"],
    ]
    _append_markdown_table(lines, ["Показатель", "Значение"], stock_rows, align_right={1})

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

    lines.append("### SKU с остатками и слабым движением")
    sku_without_sales = decision.get("sku_without_sales") or []
    if sku_without_sales:
        rows_without_sales = [
            [
                item.get("sku"),
                _to_int(item.get("stock_qty")),
                _to_int(item.get("orders")),
                _money(item.get("revenue")),
            ]
            for item in sku_without_sales[:10]
        ]
        _append_markdown_table(
            lines,
            ["SKU", "Остаток, шт", "Заказы", "Выручка"],
            rows_without_sales,
            align_right={1, 2, 3},
        )
    else:
        lines.append("- SKU с остатками и слабым движением не выявлены.")
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

    lines.extend(_local_orders_section_lines(local_orders_insights))

    _page_break(lines)

    lines.append("## 8. Поисковые запросы")
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

    lines.append("## 9. План действий / рекомендации")
    if actions:
        action_rows = [
            [
                _text(action.get("priority") or ""),
                _text(action.get("area") or ""),
                _text(action.get("action") or ""),
                _text(action.get("expected_effect") or ""),
            ]
            for action in actions
        ]
        _append_markdown_table(
            lines,
            ["Приоритет", "Блок", "Действие", "Ожидаемый эффект"],
            action_rows,
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
