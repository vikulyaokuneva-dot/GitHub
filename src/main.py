import json
import re
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from src.report_prompt import REPORT_PROMPT_TEMPLATE
from src.gigachat_client import generate_report_from_facts
from src.pdf_report import markdown_to_simple_pdf
from src.mailer_yandex import send_email_with_pdf
from src.cogs import calc_cogs_for_rows
from src.facts_builder import build_facts_json
from src.report_metrics import compute_report_metrics
from src.trends import save_snapshot, compute_trends_7d


def _canonical_key(name) -> str:
    try:
        text = str(name or "")
    except Exception:
        text = ""
    text = text.strip().lower().replace("ё", "е").replace("-", "_")
    text = re.sub(r"\s+", "_", text)
    return text


def _normalize_text(value) -> str:
    try:
        text = str(value or "")
    except Exception:
        text = ""
    text = text.strip().lower().replace("ё", "е")
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .,:;")


def _to_non_negative_float(value):
    try:
        if value is None or value == "":
            return None
        if isinstance(value, str):
            value = value.strip().replace(" ", "").replace(",", ".")
        parsed = float(value)
    except Exception:
        return None
    if parsed < 0:
        return None
    return parsed


def _to_non_negative_int(value):
    parsed = _to_non_negative_float(value)
    if parsed is None:
        return None
    return int(round(parsed))


def _lookup_row_value(row: dict, aliases: tuple[str, ...]):
    if not isinstance(row, dict):
        return None
    normalized = {_canonical_key(k): v for k, v in row.items()}
    for alias in aliases:
        alias_key = _canonical_key(alias)
        if alias_key in normalized:
            return normalized.get(alias_key)
    return None


def _iter_nested_dict_rows(payload, max_nodes: int = 30000):
    stack = [payload]
    seen = set()
    nodes = 0
    while stack and nodes < max_nodes:
        current = stack.pop()
        nodes += 1

        if isinstance(current, dict):
            obj_id = id(current)
            if obj_id in seen:
                continue
            seen.add(obj_id)
            yield current

            preferred = (
                "rows",
                "items",
                "data",
                "result",
                "list",
                "records",
                "realization_raw",
                "financial_rows",
                "realization_rows",
                "daily_report_rows",
                "daily_detailed_report_rows",
            )
            for key in preferred:
                nested = current.get(key)
                if isinstance(nested, (list, dict)):
                    stack.append(nested)
            for nested in current.values():
                if isinstance(nested, (list, dict)):
                    stack.append(nested)

        elif isinstance(current, list):
            for item in current:
                if isinstance(item, (list, dict)):
                    stack.append(item)


def _extract_buyouts_from_daily_detailed_payload(payload) -> tuple[int | None, int]:
    doc_aliases = (
        "Тип документа",
        "тип_документа",
        "document_type",
        "doc_type_name",
        "doc_type",
        "doctype",
    )
    reason_aliases = (
        "Обоснование для оплаты",
        "обоснование_для_оплаты",
        "Основание оплаты",
        "payment_reason",
        "supplier_oper_name",
        "operationTypeName",
        "operation basis",
        "reason",
    )
    qty_aliases = (
        "Кол-во",
        "кол_во",
        "Количество",
        "количество",
        "quantity",
        "qty",
        "count",
    )

    total_qty = 0.0
    matched_rows = 0
    for row in _iter_nested_dict_rows(payload):
        doc_type = _normalize_text(_lookup_row_value(row, doc_aliases))
        payment_reason = _normalize_text(_lookup_row_value(row, reason_aliases))
        is_sale = doc_type in {"продажа", "sale"} or payment_reason in {"продажа", "sale"}
        if not is_sale:
            continue

        qty = _to_non_negative_float(_lookup_row_value(row, qty_aliases))
        if qty is None or qty <= 0:
            continue
        total_qty += qty
        matched_rows += 1

    if matched_rows == 0:
        return None, 0
    return int(round(total_qty)), matched_rows


def _extract_buyouts_from_daily_detailed_facts(facts: dict) -> tuple[int | None, str | None]:
    financial_summary = facts.get("financial_summary") or {}
    candidates = [
        ("facts.realization_raw", facts.get("realization_raw")),
        ("facts.daily_detailed_report_rows", facts.get("daily_detailed_report_rows")),
        ("facts.daily_report_rows", facts.get("daily_report_rows")),
        ("facts.financial_rows", facts.get("financial_rows")),
        ("facts.raw", facts.get("raw")),
        ("facts.job", facts.get("job")),
        ("facts.file_reports", facts.get("file_reports")),
        ("facts.uploaded_reports", facts.get("uploaded_reports")),
        ("financial_summary.rows", financial_summary.get("rows")),
        ("financial_summary.raw_rows", financial_summary.get("raw_rows")),
        ("financial_summary.items", financial_summary.get("items")),
        ("financial_summary.realization_rows", financial_summary.get("realization_rows")),
    ]
    for source_name, payload in candidates:
        if payload is None:
            continue
        buyouts, matched_rows = _extract_buyouts_from_daily_detailed_payload(payload)
        if buyouts is not None and matched_rows > 0:
            return buyouts, source_name
    return None, None



def _enforce_kpi_totals(pdf_markdown: str, facts: dict) -> str:
    """Hard-fix ключевых KPI в тексте отчёта по фактам, чтобы LLM не 'придумывал' цифры."""
    try:
        acc = facts.get("account_summary") or {}
        funnel = facts.get("funnel_summary") or {}
        financial = facts.get("financial_summary") or {}
        orders = acc.get("orders")
        buyouts = None
        sku_fin = financial.get("sku_financials")
        if isinstance(sku_fin, dict):
            fin_buyouts_total = 0.0
            fin_buyouts_found = False
            for row in sku_fin.values():
                if not isinstance(row, dict):
                    continue
                try:
                    qty_raw = row.get("sales_qty")
                    if qty_raw is None or qty_raw == "":
                        continue
                    qty = float(qty_raw)
                    if qty < 0:
                        continue
                    fin_buyouts_total += qty
                    fin_buyouts_found = True
                except Exception:
                    continue
            if fin_buyouts_found:
                buyouts = int(round(fin_buyouts_total))
        finance_status = str(facts.get("finance_status") or "").strip().lower()
        raw_rows_count = facts.get("financial_rows_count")
        if raw_rows_count in (None, ""):
            raw_rows_count = financial.get("rows_count")
        rows_count = _to_non_negative_int(raw_rows_count)
        use_detailed_buyouts_fallback = (rows_count == 0) or (finance_status == "delayed")
        if buyouts is None and use_detailed_buyouts_fallback:
            detailed_buyouts, _ = _extract_buyouts_from_daily_detailed_facts(facts)
            if detailed_buyouts is not None:
                buyouts = detailed_buyouts
        if buyouts is None:
            try:
                candidate = acc.get("buyouts")
                if candidate is not None and candidate != "":
                    parsed = float(candidate)
                    if parsed >= 0:
                        buyouts = int(round(parsed))
            except Exception:
                buyouts = None
        if buyouts is None:
            try:
                candidate = funnel.get("buys")
                if candidate is not None and candidate != "":
                    parsed = float(candidate)
                    if parsed >= 0:
                        buyouts = int(round(parsed))
            except Exception:
                buyouts = None
        returns_ = acc.get("returns")
        views = funnel.get("views")
        add_to_cart = funnel.get("add_to_cart")
    except Exception:
        return pdf_markdown

    def repl_int(label_patterns, value):
        nonlocal pdf_markdown
        if value is None:
            return
        for pat in label_patterns:
            pdf_markdown = re.sub(pat, lambda m: f"{m.group(1)}{int(value)}{m.group(3)}", pdf_markdown)

    # KPI blocks commonly appear like:
    # "Заказы: 5 шт." / "Заказа: 5" / "Заказов: 5"
    repl_int([r"(\bЗаказ(?:ы|а|ов)\s*:\s*)(\d+)(\s*(?:шт\.)?)"], orders)
    repl_int([r"(\bВыкуп(?:ы|ов)\s*:\s*)(\d+)(\s*(?:шт\.)?)"], buyouts)
    repl_int([r"(\bВозврат(?:ы|ов)\s*:\s*)(\d+)(\s*(?:шт\.)?)"], returns_)
    repl_int([r"(\bПросмотров\s*:\s*)(\d+)(\b)"], views)
    repl_int([r"(\bДобавлен(?:ий|ия)\s+в\s+корзин(?:у|у)\s*:\s*)(\d+)(\b)"], add_to_cart)

    return pdf_markdown


def _env_flag(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _fmt_money(value) -> str:
    try:
        amount = float(value)
    except Exception:
        return "н/д"
    if abs(amount - round(amount)) < 1e-9:
        return f"{int(round(amount))} RUB"
    return f"{amount:.2f} RUB"


def _fmt_pct(value) -> str:
    try:
        pct = float(value)
    except Exception:
        return "н/д"
    return f"{pct:.2f}".rstrip("0").rstrip(".").replace(".", ",") + "%"


def build_local_report_from_facts(report_date: str, facts: dict) -> dict:
    account_summary = facts.get("account_summary") or {}
    funnel_summary = facts.get("funnel_summary") or {}
    financial_summary = facts.get("financial_summary") or {}

    metrics = compute_report_metrics(facts)

    orders = account_summary.get("orders")
    if orders is None:
        orders = funnel_summary.get("orders")

    buyouts = account_summary.get("buyouts")
    if buyouts is None:
        buyouts = funnel_summary.get("buys")

    views = metrics.get("views")
    add_to_cart = metrics.get("add_to_cart")
    cr_cart = metrics.get("cr_cart")
    cr_order = metrics.get("cr_order")

    revenue_orders = funnel_summary.get("revenue_orders")
    if revenue_orders is None:
        revenue_orders = account_summary.get("revenue_orders")

    # Buyouts amount must come from realization-based finance first.
    # Funnel buyout sum is used only as fallback when finance is unavailable.
    revenue_buyouts = None
    finance_rows_count = 0
    try:
        raw_rows = financial_summary.get("rows_count")
        if raw_rows is not None and raw_rows != "":
            finance_rows_count = int(float(raw_rows))
    except Exception:
        finance_rows_count = 0

    if finance_rows_count > 0:
        revenue_buyouts = financial_summary.get("gross_revenue")
    if revenue_buyouts is None:
        revenue_buyouts = funnel_summary.get("revenue_buyouts")
    if revenue_buyouts is None:
        revenue_buyouts = account_summary.get("revenue_buyouts")
    print("DEBUG BUYOUTS financial_summary:", json.dumps(financial_summary, ensure_ascii=False, sort_keys=True))
    print("DEBUG BUYOUTS rows_count:", financial_summary.get("rows_count"))
    print("DEBUG BUYOUTS gross_revenue:", financial_summary.get("gross_revenue"))
    print("DEBUG BUYOUTS selected_revenue_buyouts:", revenue_buyouts)

    ad_spend = metrics.get("ad_spend")
    ad_attributed_revenue = metrics.get("ad_attributed_revenue")
    roas = metrics.get("roas")
    stock_units = metrics.get("stock_units")
    sku_count = metrics.get("sku_count")
    rows_count = metrics.get("financial_rows_count")
    finance_available = bool(metrics.get("finance_available"))
    finance_status = str(metrics.get("finance_status") or facts.get("finance_status") or "missing")
    finance_message = str(metrics.get("finance_message") or facts.get("finance_message") or "")
    report_date_effective = str(facts.get("report_date") or report_date)
    ads_efficiency_limited = bool(metrics.get("ads_efficiency_limited"))
    no_sales_top5 = metrics.get("no_sales_with_stock_top5") or []
    raw_values = metrics.get("raw_values") or {}

    ad_attr_candidates = [
        raw_values.get("ad_summary.ad_attributed_revenue"),
        raw_values.get("ad_summary.revenue_attr"),
        raw_values.get("ad_summary.revenue"),
        raw_values.get("ads_summary.ad_attributed_revenue"),
        raw_values.get("ads_summary.revenue_attr"),
        raw_values.get("ads_summary.revenue"),
    ]
    ad_attribution_available = any(v is not None for v in ad_attr_candidates)
    roas_text = _fmt_pct(roas) if (ad_attribution_available and roas is not None) else "н/д"

    def _to_safe_int(value):
        try:
            if value is None or value == "":
                return None
            return int(value)
        except Exception:
            return None

    def _to_safe_float(value):
        try:
            if value is None or value == "":
                return None
            return float(value)
        except Exception:
            return None

    def _to_safe_qty(value):
        try:
            if value is None or value == "":
                return None
            qty = float(value)
            if qty < 0:
                return None
            return qty
        except Exception:
            return None

    def _to_safe_buyouts_int(value):
        qty = _to_safe_qty(value)
        if qty is None:
            return None
        return int(round(qty))

    def _extract_buyouts_from_financial_summary() -> tuple[dict[int, float], bool]:
        qty = {}
        sku_fin = financial_summary.get("sku_financials")
        if not isinstance(sku_fin, dict):
            return qty, False
        for sku_raw, row in sku_fin.items():
            if not isinstance(row, dict):
                continue
            sku_i = _to_safe_int(sku_raw)
            qty_i = _to_safe_qty(row.get("sales_qty"))
            if sku_i is None or qty_i is None or qty_i <= 0:
                continue
            qty[sku_i] = qty.get(sku_i, 0.0) + qty_i
        return qty, True

    def _sum_buyouts_from_financial_summary() -> tuple[int | None, bool]:
        sku_fin = financial_summary.get("sku_financials")
        if not isinstance(sku_fin, dict):
            return None, False

        total = 0.0
        has_values = False
        for row in sku_fin.values():
            if not isinstance(row, dict):
                continue
            qty_i = _to_safe_qty(row.get("sales_qty"))
            if qty_i is None:
                continue
            total += qty_i
            has_values = True

        if not has_values:
            return None, True
        return int(round(total)), True

    def _extract_buyouts_from_sku_rows() -> tuple[dict[int, float], bool]:
        qty = {}
        rows = (facts.get("sku_performance") or {}).get("rows")
        if not isinstance(rows, list):
            return qty, False

        has_buyout_fields = False
        for row in rows:
            if not isinstance(row, dict):
                continue
            sku_i = _to_safe_int(row.get("sku") or row.get("nmId") or row.get("nm_id"))
            if sku_i is None:
                continue

            qty_i = None
            for field in ("buyouts", "buys"):
                if field in row and row.get(field) not in (None, ""):
                    has_buyout_fields = True
                qty_i = _to_safe_qty(row.get(field))
                if qty_i is not None:
                    break

            if qty_i is None or qty_i <= 0:
                continue
            qty[sku_i] = qty.get(sku_i, 0.0) + qty_i

        return qty, has_buyout_fields

    qty_source = None
    qty_by_sku, fin_qty_source_found = _extract_buyouts_from_financial_summary()
    if qty_by_sku:
        qty_source = "financial_summary.sku_financials.sales_qty"

    sku_qty_source_found = False
    if not qty_by_sku:
        sku_qty_by_sku, sku_qty_source_found = _extract_buyouts_from_sku_rows()
        if sku_qty_by_sku:
            qty_by_sku = sku_qty_by_sku
            qty_source = "sku_performance.rows.buyouts/buys"

    qty_source_found = fin_qty_source_found or sku_qty_source_found

    buyouts_source = None
    financial_buyouts, _ = _sum_buyouts_from_financial_summary()
    use_detailed_buyouts_fallback = int(rows_count or 0) == 0 or str(finance_status).strip().lower() == "delayed"
    detailed_buyouts = None
    detailed_buyouts_source = None
    if use_detailed_buyouts_fallback:
        detailed_buyouts, detailed_buyouts_source = _extract_buyouts_from_daily_detailed_facts(facts)

    if financial_buyouts is not None:
        buyouts = financial_buyouts
        buyouts_source = "financial_summary.sku_financials.sales_qty"
    elif detailed_buyouts is not None:
        buyouts = detailed_buyouts
        buyouts_source = f"{detailed_buyouts_source}.sale_qty" if detailed_buyouts_source else "daily_detailed.sale_qty"
    else:
        buyouts_account = _to_safe_buyouts_int(account_summary.get("buyouts"))
        if buyouts_account is not None:
            buyouts = buyouts_account
            buyouts_source = "account_summary.buyouts"
        else:
            buyouts_funnel = _to_safe_buyouts_int(funnel_summary.get("buys"))
            if buyouts_funnel is not None:
                buyouts = buyouts_funnel
                buyouts_source = "funnel_summary.buys"
            else:
                buyouts = None
                buyouts_source = "unavailable"
    print("DEBUG BUYOUTS selected_buyouts:", buyouts, "source:", buyouts_source)

    buyouts_num = _to_safe_float(buyouts)
    revenue_buyouts_num = _to_safe_float(revenue_buyouts)
    ad_spend_num = _to_safe_float(ad_spend)

    cogs_unavailable_reason = None
    cogs_total = None
    cogs_by_sku = {}
    missing_cogs_sku = {}

    if buyouts_num == 0:
        cogs_total = 0.0
    else:
        qty_for_cogs = {}
        for sku_i, qty_val in qty_by_sku.items():
            q = int(float(qty_val))
            if q > 0:
                qty_for_cogs[int(sku_i)] = q

        if qty_for_cogs:
            cogs_total_raw, cogs_by_sku, missing_cogs_sku = calc_cogs_for_rows(qty_for_cogs)
            cogs_total = cogs_total_raw
            if cogs_total_raw == 0 and missing_cogs_sku:
                cogs_total = None
        else:
            cogs_unavailable_reason = "buyout_qty_by_sku missing or empty"

    if not finance_available:
        wb_commission = None
        logistics = None
        storage = None
    else:
        wb_commission = _to_safe_float(
            financial_summary.get("commission")
            if financial_summary.get("commission") is not None
            else financial_summary.get("wb_commission")
        )
        logistics = _to_safe_float(
            financial_summary.get("logistics")
            if financial_summary.get("logistics") is not None
            else financial_summary.get("logistics_cost")
        )
        storage = _to_safe_float(
            financial_summary.get("storage")
            if financial_summary.get("storage") is not None
            else financial_summary.get("storage_fee")
        )

    tax = None if revenue_buyouts_num is None else round(revenue_buyouts_num * 0.06, 2)

    total_costs = None
    profit = None
    margin = None
    roi = None
    if (
        revenue_buyouts_num is not None
        and cogs_total is not None
        and wb_commission is not None
        and logistics is not None
        and storage is not None
        and tax is not None
        and ad_spend_num is not None
    ):
        total_costs = round(cogs_total + wb_commission + logistics + storage + tax + ad_spend_num, 2)
        profit = round(revenue_buyouts_num - total_costs, 2)
        if revenue_buyouts_num > 0:
            margin = (profit / revenue_buyouts_num) * 100
        if total_costs > 0:
            roi = (profit / total_costs) * 100

    print("COGS QTY SOURCE:", qty_source or "unavailable")
    print("COGS QTY BY SKU:", json.dumps(qty_by_sku, ensure_ascii=False, sort_keys=True))
    if not qty_source_found:
        print("COGS DIAGNOSTIC: buyout_qty_by_sku source not found in facts")
    if cogs_unavailable_reason:
        print("COGS DIAGNOSTIC:", cogs_unavailable_reason)
    if missing_cogs_sku:
        print("COGS MISSING SKU:", json.dumps(missing_cogs_sku, ensure_ascii=False, sort_keys=True))

    print("REPORT METRICS RAW:", json.dumps(metrics.get("raw_values", {}), ensure_ascii=False, sort_keys=True))
    print("REPORT METRICS SOURCES:", json.dumps(metrics.get("sources", {}), ensure_ascii=False, sort_keys=True))
    print(
        "REPORT METRICS COMPUTED:",
        json.dumps(
            {
                "orders": orders,
                "buyouts": buyouts,
                "buyouts_source": buyouts_source,
                "views": views,
                "add_to_cart": add_to_cart,
                "cr_cart": cr_cart,
                "cr_order": cr_order,
                "revenue_orders": revenue_orders,
                "revenue_buyouts": revenue_buyouts,
                "ad_spend": ad_spend,
                "ad_attributed_revenue": ad_attributed_revenue,
                "roas": roas,
                "stock_units": stock_units,
                "sku_count": sku_count,
                "financial_rows_count": rows_count,
                "finance_available": finance_available,
                "finance_status": finance_status,
                "finance_message": finance_message,
                "ads_efficiency_limited": ads_efficiency_limited,
                "cogs_total": cogs_total,
                "wb_commission": wb_commission,
                "logistics": logistics,
                "storage": storage,
                "tax": tax,
                "profit": profit,
                "margin": margin,
                "roi": roi,
                "cogs_qty_source": qty_source,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
    )

    actions = []
    existing_actions = facts.get("actions")
    if isinstance(existing_actions, list):
        actions.extend(existing_actions)

    if not finance_available:
        finance_why = (
            finance_message
            if finance_message
            else "financial_summary.rows_count = 0, финансовый отчёт за дату не получен"
        )
        actions.append(
            {
                "priority": "P0",
                "area": "finance",
                "sku": "",
                "campaign_id": "",
                "action": "Check WB financial report export for the report date",
                "why": finance_why,
                "expected_effect": "Financial conclusions become available after WB returns financial rows",
                "numbers": {
                    "financial_summary_rows_count": int(rows_count or 0),
                    "finance_status": finance_status,
                },
            }
        )

    if no_sales_top5 and finance_status != "delayed":
        actions.append(
            {
                "priority": "P2",
                "area": "stock",
                "sku": "",
                "campaign_id": "",
                "action": "Review SKU with stock but no sales",
                "why": f"SKU without sales but with stock: {len(no_sales_top5)} (top-5 in report)",
                "expected_effect": "Lower frozen stock and improve turnover",
                "numbers": {"sku_no_sales_with_stock_top5": len(no_sales_top5)},
            }
        )

    def _fmt_int(value) -> str:
        try:
            return str(int(value))
        except Exception:
            return "н/д"

    markdown_lines = [
        f"# WB отчёт за {report_date}",
        "",
        "## Продажи",
        f"- Заказы: {_fmt_int(orders)}",
        f"- Выкупы: {_fmt_int(buyouts)}",
        f"- Сумма заказов: {_fmt_money(revenue_orders)}",
        f"- Сумма выкупов: {_fmt_money(revenue_buyouts)}",
        "",
        "## Затраты",
        f"- Себестоимость: {_fmt_money(cogs_total) if cogs_total is not None else 'н/д'}",
        f"- Вознаграждение WB: {_fmt_money(wb_commission) if wb_commission is not None else 'н/д'}",
        f"- Логистика: {_fmt_money(logistics) if logistics is not None else 'н/д'}",
        f"- Хранение: {_fmt_money(storage) if storage is not None else 'н/д'}",
        f"- Налог: {_fmt_money(tax) if tax is not None else 'н/д'}",
        f"- Реклама: {_fmt_money(ad_spend_num) if ad_spend_num is not None else 'н/д'}",
        "",
        "## Финальный результат",
        f"- Чистая прибыль: {_fmt_money(profit) if profit is not None else 'н/д'}",
        f"- Маржинальность: {_fmt_pct(margin) if margin is not None else 'н/д'}",
        f"- ROI: {_fmt_pct(roi) if roi is not None else 'н/д'}",
        "",
        "## Сводка Воронки",
        f"- Просмотры: {_fmt_int(views)}",
        f"- Добавления в корзину: {_fmt_int(add_to_cart)}",
        f"- CR корзины: {_fmt_pct(cr_cart)}",
        f"- CR заказа: {_fmt_pct(cr_order)}",
        "",
        "## Сводка Остатков",
        f"- Остатки (шт): {_fmt_int(stock_units)}",
        f"- Количество SKU: {_fmt_int(sku_count)}",
        "",
        "## Сводка Рекламы",
        f"- Атрибутированная выручка рекламы: {_fmt_money(ad_attributed_revenue)}",
        f"- ROAS: {roas_text}",
    ]

    if finance_status == "delayed":
        markdown_lines.append(
            "- Заказы уже есть, но WB ещё не отдал финансовые строки/выкупы за эту дату. "
            "Данные по выкупам, логистике и прибыли могут обновиться позже."
        )
        markdown_lines.append("- Статус финансов: delayed (предварительные данные, прибыль не окончательная).")
    elif not finance_available:
        markdown_lines.append(f"- {finance_message or 'Финансовые данные за дату недоступны.'}")
    else:
        markdown_lines.append(f"- Количество финансовых строк: {_fmt_int(rows_count)}")

    if ads_efficiency_limited:
        markdown_lines.append("- Оценка эффективности рекламы ограничена: есть расход, но нет атрибутированной выручки.")

    markdown_lines.extend(["", "## Сводка SKU"])
    if no_sales_top5 and finance_status != "delayed":
        markdown_lines.append("- SKU без продаж, но с остатками (top-5):")
        for item in no_sales_top5:
            if isinstance(item, dict):
                sku_id = item.get("sku", "н/д")
                qty = item.get("stock_qty")
                try:
                    qty_text = f"{float(qty):.2f}".rstrip("0").rstrip(".")
                except Exception:
                    qty_text = "н/д"
                markdown_lines.append(f"- SKU {sku_id}: остаток {qty_text} шт")
            else:
                markdown_lines.append(f"- {item}")
    else:
        if finance_status == "delayed":
            markdown_lines.append("- SKU без продаж, но с остатками: оценка отложена до прихода финансовых строк.")
        else:
            markdown_lines.append("- SKU без продаж, но с остатками: нет")

    email_lines = [
        f"WB отчёт за {report_date}",
        "",
        "Продажи:",
        f"Заказы: {_fmt_int(orders)}",
        f"Выкупы: {_fmt_int(buyouts)}",
        f"Сумма заказов: {_fmt_money(revenue_orders)}",
        f"Сумма выкупов: {_fmt_money(revenue_buyouts)}",
        "",
        "Затраты:",
        f"Себестоимость: {_fmt_money(cogs_total) if cogs_total is not None else 'н/д'}",
        f"Вознаграждение WB: {_fmt_money(wb_commission) if wb_commission is not None else 'н/д'}",
        f"Логистика: {_fmt_money(logistics) if logistics is not None else 'н/д'}",
        f"Хранение: {_fmt_money(storage) if storage is not None else 'н/д'}",
        f"Налог: {_fmt_money(tax) if tax is not None else 'н/д'}",
        f"Реклама: {_fmt_money(ad_spend_num) if ad_spend_num is not None else 'н/д'}",
        "",
        "Финальный результат:",
        f"Чистая прибыль: {_fmt_money(profit) if profit is not None else 'н/д'}",
        f"Маржинальность: {_fmt_pct(margin) if margin is not None else 'н/д'}",
        f"ROI: {_fmt_pct(roi) if roi is not None else 'н/д'}",
        "",
        f"Просмотры: {_fmt_int(views)}",
        f"Добавления в корзину: {_fmt_int(add_to_cart)}",
        f"CR корзины: {_fmt_pct(cr_cart)}",
        f"CR заказа: {_fmt_pct(cr_order)}",
        f"Остатки (шт): {_fmt_int(stock_units)}",
        f"Атрибутированная выручка рекламы: {_fmt_money(ad_attributed_revenue)}",
        f"ROAS: {roas_text}",
    ]
    if finance_status == "delayed":
        email_lines.append(
            "Заказы уже есть, но WB ещё не отдал финансовые строки/выкупы за эту дату. "
            "Данные по выкупам, логистике и прибыли могут обновиться позже."
        )
        email_lines.append("Статус финансов: delayed (предварительные данные, прибыль не окончательная).")
    elif not finance_available:
        email_lines.append(finance_message or "Финансовые данные за дату недоступны.")
    else:
        email_lines.append(f"Количество финансовых строк: {_fmt_int(rows_count)}")

    if ads_efficiency_limited:
        email_lines.append("Оценка эффективности рекламы ограничена: есть расход, но нет атрибутированной выручки.")

    return {
        "report_date": report_date_effective,
        "finance_status": finance_status,
        "finance_message": finance_message,
        "financial_rows_count": int(rows_count or 0),
        "email_text": "\n".join(email_lines),
        "pdf_markdown": "\n".join(markdown_lines),
        "actions": actions,
    }

def build_fallback_json(report_date: str, facts_json: str) -> dict:
    return {
        "email_text": f"WB отчёт за {report_date}\n\nМодель вернула некорректный ответ. См. PDF (fallback) и артефакты.",
        "pdf_markdown": (
            f"# WB отчёт за {report_date}\n\n"
            "## Статус\n"
            "LLM не вернул корректный JSON-ответ. Ниже — сохранённые факты (обрезано).\n\n"
            "## Facts JSON (sample)\n"
            "```json\n"
            + facts_json[:4000]
            + "\n```\n"
        ),
        "actions": [
            {
                "priority": "P1",
                "area": "LLM",
                "sku": "",
                "campaign_id": "",
                "action": "Проверить, что LLM возвращает валидный JSON без лишнего текста",
                "why": "Ответ модели не удалось распарсить как JSON",
                "expected_effect": "Восстановится полноценный отчёт без fallback",
                "numbers": {}
            }
        ]
    }


def parse_llm_json(llm_text: str) -> dict:
    raw = (llm_text or "").strip()

    def strip_code_fences(s: str) -> str:
        s = s.strip()
        if s.startswith("```"):
            s2 = s[3:]
            s2 = s2.lstrip()
            if s2.lower().startswith("json"):
                s2 = s2[4:].lstrip()
            if "```" in s2:
                s2 = s2.split("```", 1)[0]
            return s2.strip()
        return s

    def extract_first_json_object(s: str) -> str | None:
        start = s.find("{")
        if start == -1:
            return None

        in_string = False
        escape = False
        depth = 0
        for i in range(start, len(s)):
            ch = s[i]

            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            else:
                if ch == '"':
                    in_string = True
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return s[start : i + 1]
        return None

    def sanitize_json_text(s: str) -> str:
        out = []
        in_string = False
        escape = False

        for ch in s:
            code = ord(ch)

            if in_string:
                if escape:
                    out.append(ch)
                    escape = False
                    continue

                if ch == "\\":
                    out.append(ch)
                    escape = True
                    continue

                if ch == '"':
                    out.append(ch)
                    in_string = False
                    continue

                if ch == "\n":
                    out.append("\\n")
                    continue
                if ch == "\r":
                    out.append("\\r")
                    continue
                if ch == "\t":
                    out.append("\\t")
                    continue
                if code < 32:
                    continue

                out.append(ch)
                continue

            if ch == '"':
                out.append(ch)
                in_string = True
                continue

            if code < 32 and ch not in ("\n", "\r", "\t"):
                continue

            out.append(ch)

        return "".join(out).strip()

    raw2 = strip_code_fences(raw)

    cand = sanitize_json_text(raw2)
    try:
        return json.loads(cand)
    except Exception:
        pass

    obj = extract_first_json_object(raw2)
    if obj:
        obj = sanitize_json_text(obj)
        return json.loads(obj)

    obj2 = extract_first_json_object(raw)
    if obj2:
        obj2 = sanitize_json_text(obj2)
        return json.loads(obj2)

    raise ValueError("Cannot parse LLM response as JSON")


def validate_llm_json(data: dict):
    if not isinstance(data, dict):
        raise ValueError("LLM JSON is not an object")
    for k in ("email_text", "pdf_markdown", "actions"):
        if k not in data:
            raise ValueError(f"Missing key in LLM JSON: {k}")
    if not str(data.get("pdf_markdown", "")).strip():
        raise ValueError("pdf_markdown is empty")


def main():
    print("DEBUG ENTRY FILE:", __file__)
    os.makedirs("out", exist_ok=True)

    # 1) Получаем факты за день
    facts = build_facts_json()

    # 2) Snapshot
    snapshots_dir = os.path.join("out", "snapshots")
    os.makedirs(snapshots_dir, exist_ok=True)
    save_snapshot(facts, snapshots_dir)

    # 3) Тренды
    facts["trends_7d"] = compute_trends_7d(snapshots_dir, end_date=facts.get("date"))

    # --- COMPACT FACTS для LLM ---
    facts_for_llm = dict(facts)

    # 3.1) Жёстко выкидываем потенциально тяжёлые/сырьевые блоки (они LLM не нужны)
    for heavy_key in (
        "sku_performance",
        "stocks_raw",
        "ads_raw",
        "realization_raw",
        "orders_raw",
        "funnel_raw",
        "cards_raw",
        "raw",
    ):
        facts_for_llm.pop(heavy_key, None)

    # 3.2) Сжимаем financial_summary
    if "financial_summary" in facts_for_llm and isinstance(facts_for_llm["financial_summary"], dict):
        fs = dict(facts_for_llm["financial_summary"])
        fs.pop("sku_financials", None)
        fs.pop("cogs_by_sku", None)
        # витрины оставляем как есть (обычно короткие)
        facts_for_llm["financial_summary"] = fs

    # 3.3) Сжимаем sku_summary (если есть)
    if "sku_summary" in facts_for_llm and isinstance(facts_for_llm["sku_summary"], dict):
        ss = dict(facts_for_llm["sku_summary"])
        for k, v in list(ss.items()):
            if isinstance(v, list):
                ss[k] = v[:10]
        facts_for_llm["sku_summary"] = ss

    # 3.4) Сжимаем trends_7d (на всякий случай)
    if "trends_7d" in facts_for_llm and isinstance(facts_for_llm["trends_7d"], dict):
        t = dict(facts_for_llm["trends_7d"])
        # оставляем только summary (если есть) + ключевые метрики
        keep = {}
        for k in ("summary", "delta_revenue_pct", "delta_profit_pct", "delta_orders_pct", "delta_buyouts_pct"):
            if k in t:
                keep[k] = t[k]
        facts_for_llm["trends_7d"] = keep or t

    report_date = facts.get("date") or datetime.now(ZoneInfo("Europe/Berlin")).date().isoformat()
    use_gigachat = _env_flag("USE_GIGACHAT", default=False)
    if use_gigachat:
        print("USE_GIGACHAT=true requested, but deterministic mode is enforced.")
        use_gigachat = False
    print("USE_GIGACHAT:", use_gigachat)

    # ВАЖНО: без indent, чтобы не раздувать prompt
    facts_json = json.dumps(facts_for_llm, ensure_ascii=False)
    print("FACTS SIZE (chars):", len(facts_json))

    if not use_gigachat:
        data = build_local_report_from_facts(report_date, facts)

        email_text = str(data.get("email_text", "")).strip()
        pdf_markdown = str(data.get("pdf_markdown", "")).strip()

        pdf_markdown = pdf_markdown.replace("\\n", "\n")
        pdf_markdown = re.sub(r"\n-", "\n\n-", pdf_markdown)
        pdf_markdown = re.sub(r"\n\s*,\s*\n", "\n", pdf_markdown)
        pdf_markdown = re.sub(r"\n\s*comma\s*\n", "\n", pdf_markdown, flags=re.IGNORECASE)
        pdf_markdown = re.sub(r"(?im)^\s*comma\s*$", "", pdf_markdown)
        pdf_markdown = re.sub(r"\n{3,}", "\n\n", pdf_markdown).strip()
        pdf_markdown = pdf_markdown.replace("$", "₽").replace("USD", "RUB")
        pdf_markdown = _enforce_kpi_totals(pdf_markdown, facts)

        actions = data.get("actions", [])

        pdf_path = f"out/wb_report_{report_date}.pdf"
        md_path = f"out/wb_report_{report_date}.md"
        json_path = f"out/facts_{report_date}.json"
        actions_path = f"out/actions_{report_date}.json"

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(pdf_markdown + "\n")
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(facts_json)
        with open(actions_path, "w", encoding="utf-8") as f:
            json.dump(actions, f, ensure_ascii=False, indent=2)

        markdown_to_simple_pdf(pdf_markdown, pdf_path, title=f"WB отчёт за {report_date}")

        subject = f"WB отчёт за {report_date}"
        if not email_text:
            email_text = f"WB отчёт за {report_date}\n\nСм. PDF."
        body = email_text + "\n\n(Артефакты сохранены в GitHub Actions.)"

        send_email_with_pdf(subject, body, pdf_path)
        return

    # 4) Prompt → LLM
    prompt = REPORT_PROMPT_TEMPLATE.replace("__FACTS_JSON__", facts_json)
    llm_text = generate_report_from_facts(prompt)

    # 5) Сохраняем сырой ответ LLM
    debug_file = f"out/llm_raw_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(debug_file, "w", encoding="utf-8") as f:
        f.write(str(llm_text))
    print("LLM RAW RESPONSE SAVED:", debug_file)

    # 5.1) Защита от слишком длинного ответа (часто это признак мусора/повтора)
    if len(str(llm_text)) > 120_000:
        print("LLM response too large, forcing fallback")
        data = build_fallback_json(report_date, facts_json)
    else:
        # 6) Парсим JSON (с repair retry)
        data = None
        try:
            data = parse_llm_json(str(llm_text))
            validate_llm_json(data)
        except Exception as e:
            print("LLM JSON parse/validation failed:", repr(e))

            repair_prompt = (
                "Верни ТОЛЬКО валидный JSON объекта с ключами "
                "email_text, pdf_markdown, actions. Без ``` и без текста.\n\n"
                "Вот исходный ответ модели:\n"
                + str(llm_text)
            )
            llm_text2 = generate_report_from_facts(repair_prompt)

            repair_file = f"out/llm_raw_repair_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(repair_file, "w", encoding="utf-8") as f:
                f.write(str(llm_text2))
            print("LLM REPAIR RAW SAVED:", repair_file)

            try:
                data = parse_llm_json(str(llm_text2))
                validate_llm_json(data)
            except Exception as e2:
                print("LLM repair also failed:", repr(e2))
                data = build_fallback_json(report_date, facts_json)

    email_text = str(data.get("email_text", "")).strip()
    pdf_markdown = str(data.get("pdf_markdown", "")).strip()
    
    # FIX переносов строк от LLM
    pdf_markdown = pdf_markdown.replace("\\n", "\n")
    
    # делаем списки читаемыми
    pdf_markdown = re.sub(r"\n-", "\n\n-", pdf_markdown)
    
    # --- cleanup мусора от LLM ---
    pdf_markdown = re.sub(r"\n\s*,\s*\n", "\n", pdf_markdown)
    pdf_markdown = re.sub(r"\n\s*comma\s*\n", "\n", pdf_markdown, flags=re.IGNORECASE)
    pdf_markdown = re.sub(r"(?im)^\s*comma\s*$", "", pdf_markdown)
    pdf_markdown = re.sub(r"\n{3,}", "\n\n", pdf_markdown).strip()
    # Currency hard-fix: enforce RUB symbol in generated text
    pdf_markdown = pdf_markdown.replace("$", "₽").replace("USD", "RUB")

    # Hard-fix KPI totals from facts (LLM иногда путает заказы/выкупы)
    pdf_markdown = _enforce_kpi_totals(pdf_markdown, facts)


    actions = data.get("actions", [])

    # 7) Пути файлов
    pdf_path = f"out/wb_report_{report_date}.pdf"
    md_path = f"out/wb_report_{report_date}.md"
    json_path = f"out/facts_{report_date}.json"
    actions_path = f"out/actions_{report_date}.json"

    # 8) Сохраняем артефакты
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(pdf_markdown + "\n")
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(facts_json)
    with open(actions_path, "w", encoding="utf-8") as f:
        json.dump(actions, f, ensure_ascii=False, indent=2)

    # 9) PDF
    markdown_to_simple_pdf(pdf_markdown, pdf_path, title=f"WB отчёт за {report_date}")

    # 10) Email
    subject = f"WB отчёт за {report_date}"
    if not email_text:
        email_text = f"WB отчёт за {report_date}\n\nСм. PDF."
    body = email_text + "\n\n(Артефакты сохранены в GitHub Actions.)"

    send_email_with_pdf(subject, body, pdf_path)


if __name__ == "__main__":
    main()
