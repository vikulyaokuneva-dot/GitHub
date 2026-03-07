# audit/audit_report.py
from typing import Any, Dict, List


def _money(x: Any) -> str:
    try:
        return f"{float(x or 0):,.2f} ₽".replace(",", " ")
    except Exception:
        return "0.00 ₽"


def _pct(x: Any) -> str:
    try:
        return f"{float(x or 0) * 100:.2f}%"
    except Exception:
        return "0.00%"


def _int(x: Any) -> str:
    try:
        return f"{int(float(x or 0))}"
    except Exception:
        return "0"


def _table(headers: List[str], rows: List[List[str]]) -> str:
    out = []
    out.append("| " + " | ".join(headers) + " |")
    out.append("|" + "|".join(["---"] * len(headers)) + "|")
    for r in rows:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)


def build_audit_markdown(facts: Dict[str, Any]) -> str:
    period = (facts.get("period") or {}).get("label") or "период"
    days = (facts.get("period") or {}).get("days") or ""
    finance = facts.get("financial_summary") or {}
    funnel = facts.get("funnel_summary") or {}
    ads = facts.get("ads_summary") or {}
    stock = facts.get("stock_summary") or {}
    growth = facts.get("growth_engine") or {}
    inputs = facts.get("inputs") or {}

    md: List[str] = []
    md.append(f"# WB аудит за период: {period}")
    if days:
        md.append(f"Период: {period} ({days} дн.)\n")

    md.append("## Источники (файлы)")
    md.append(_table(
        ["Блок", "Файл"],
        [
            ["Финансы", inputs.get("finance_file", "нет") or "нет"],
            ["Воронка", inputs.get("funnel_file", "нет") or "нет"],
            ["Реклама", inputs.get("ads_file", "нет") or "нет"],
            ["Остатки", inputs.get("stocks_file", "нет") or "нет"],
        ]
    ))
    md.append("")

    md.append("## 1) Финансы за период")
    md.append(_table(
        ["Метрика", "Значение"],
        [
            ["Выручка (gross)", _money(finance.get("gross_revenue"))],
            ["Комиссия", _money(finance.get("commission"))],
            ["Логистика", _money(finance.get("logistics"))],
            ["Хранение", _money(finance.get("storage"))],
            ["Штрафы", _money(finance.get("penalties"))],
            ["Себестоимость", _money(finance.get("cogs_total"))],
            ["Налог", _money(finance.get("tax"))],
            ["Прибыль", _money(finance.get("profit"))],
            ["Маржа", _pct(finance.get("margin"))],
            ["Выкупы (шт)", _int(finance.get("sales_qty"))],
            ["Возвраты (шт)", _int(finance.get("returns_qty"))],
            ["К перечислению", _money(finance.get("payout"))],
        ]
    ))
    md.append("")

    md.append("## 2) Воронка продаж (за период)")
    md.append(_table(
        ["Метрика", "Значение"],
        [
            ["Просмотры карточек", _int(funnel.get("views"))],
            ["Добавили в корзину", _int(funnel.get("add_to_cart"))],
            ["Заказы", _int(funnel.get("orders"))],
            ["Выкупы", _int(funnel.get("buys"))],
            ["CR в корзину", _pct(funnel.get("cr_cart"))],
            ["CR в заказ", _pct(funnel.get("cr_order"))],
            ["% выкупа", _pct(funnel.get("buyout_rate"))],
            ["Заказы на сумму", _money(funnel.get("revenue_orders"))],
            ["Выкупы на сумму", _money(funnel.get("revenue_buyouts"))],
        ]
    ))
    md.append("")

    md.append("## 3) Реклама (за период)")
    md.append(_table(
        ["Метрика", "Значение"],
        [
            ["Расход", _money(ads.get("spend"))],
            ["Показы", _int(ads.get("impressions"))],
            ["Клики", _int(ads.get("clicks"))],
            ["CTR", _pct(ads.get("ctr"))],
            ["CPC", _money(ads.get("cpc"))],
            ["CPM", _money(ads.get("cpm"))],
            ["Атриб. выручка (если есть)", _money(ads.get("revenue_attr"))],
            ["ROAS", f"{ads.get('roas', 0)}"],
            ["ДРР", (str(ads.get("drr")) if ads.get("drr") is not None else "нет данных (нет атрибуции)")],
        ]
    ))
    md.append("")

    md.append("## 4) Остатки и риск дефицита")
    md.append(_table(
        ["Метрика", "Значение"],
        [
            ["Остатки (шт)", _int(stock.get("stock_units"))],
            ["SKU/позиций в наличии", _int(stock.get("sku_count"))],
            ["Дни покрытия (оценка)", str(stock.get("days_of_cover", 0))],
            ["Порог (lead+safety)", _int(stock.get("threshold_days"))],
            ["Риск дефицита", "Да" if stock.get("risk_of_oos") else "Нет"],
            ["Примечание", stock.get("note", "") or ""],
        ]
    ))
    md.append("")

    # ---------------------------
    # Growth Engine (правильные поля: numbers.*)
    # ---------------------------
    md.append("## 5) Решения по ассортименту (Growth Engine)")
    top_scale = growth.get("top_scale") or []
    top_opt = growth.get("top_optimize") or []
    top_liq = growth.get("top_liquidate") or []
    top_contrib = growth.get("top_contribution") or []

    def _n(it: Dict[str, Any], key: str, default: Any = 0) -> Any:
        nums = it.get("numbers") or {}
        return nums.get(key, default)

    def sku_rows(items):
        rows = []
        for it in items[:5]:
            rows.append([
                str(it.get("sku", "")),
                _money(_n(it, "revenue", 0.0)),      # может отсутствовать
                _money(_n(it, "profit", 0.0)),
                _pct(_n(it, "margin", 0.0)),
                _int(_n(it, "buyouts", _n(it, "orders", ""))),
            ])
        return rows

    if top_scale:
        md.append("### SCALE (масштабировать)")
        md.append(_table(["SKU", "Выручка", "Прибыль", "Маржа", "Выкупы/заказы"], sku_rows(top_scale)))
        md.append("")
    if top_opt:
        md.append("### OPTIMIZE (оптимизировать)")
        md.append(_table(["SKU", "Выручка", "Прибыль", "Маржа", "Выкупы/заказы"], sku_rows(top_opt)))
        md.append("")
    if top_liq:
        md.append("### LIQUIDATE (ликвидировать)")
        md.append(_table(["SKU", "Выручка", "Прибыль", "Маржа", "Выкупы/заказы"], sku_rows(top_liq)))
        md.append("")

    if top_contrib:
        md.append("### TOP вклад в прибыль")
        rows = []
        for it in top_contrib[:5]:
            rows.append([
                str(it.get("sku", "")),
                _money(_n(it, "profit", 0.0)),
                f"{float(_n(it, 'contribution_share', 0.0) or 0.0) * 100:.2f}%",
            ])
        md.append(_table(["SKU", "Прибыль", "Доля вклада"], rows))
        md.append("")

    # ---------------------------
    # План действий: поддержка текущего формата action_orchestrator.build_actions
    # ---------------------------
    md.append("## 6) План действий (P1/P2/P3)")

    actions = facts.get("actions") or []
    if not actions:
        md.append("- нет действий (оркестратор не сформировал список)\n")
        return "\n".join(md).strip() + "\n"

    pr_map = {"high": "P1", "medium": "P2", "low": "P3"}
    shown = 0
    for a in actions:
        if shown >= 15:
            break
        pr = pr_map.get(str(a.get("priority") or "").lower(), "P2")
        title = (a.get("title") or "").strip()
        rec = (a.get("recommendation") or "").strip()
        sku = ""
        payload = a.get("payload") or {}
        if isinstance(payload, dict):
            sku = str(payload.get("sku") or "")

        line = f"**{pr}**"
        if sku:
            line += f" SKU:{sku}"
        if title:
            line += f" — {title}"
        md.append(line)
        if rec:
            md.append(f"- действие: {rec}")
        shown += 1
        md.append("")

    return "\n".join(md).strip() + "\n"
