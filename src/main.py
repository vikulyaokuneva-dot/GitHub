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



def _enforce_kpi_totals(pdf_markdown: str, facts: dict) -> str:
    """Hard-fix ключевых KPI в тексте отчёта по фактам, чтобы LLM не 'придумывал' цифры."""
    try:
        acc = facts.get("account_summary") or {}
        orders = acc.get("orders")
        buyouts = acc.get("buyouts")
        returns_ = acc.get("returns")
        views = (facts.get("funnel_summary") or {}).get("views")
        add_to_cart = (facts.get("funnel_summary") or {}).get("add_to_cart")
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

    metrics = compute_report_metrics(facts)

    orders = metrics.get("orders")
    buyouts = account_summary.get("buyouts")
    if buyouts is None:
        buyouts = funnel_summary.get("buys")
    views = metrics.get("views")
    add_to_cart = metrics.get("add_to_cart")
    cr_cart = metrics.get("cr_cart")
    cr_order = metrics.get("cr_order")
    revenue_orders = metrics.get("revenue_orders")
    revenue_buyouts = funnel_summary.get("revenue_buyouts")
    if revenue_buyouts is None:
        revenue_buyouts = account_summary.get("revenue_buyouts")
    ad_spend = metrics.get("ad_spend")
    ad_attributed_revenue = metrics.get("ad_attributed_revenue")
    roas = metrics.get("roas")
    stock_units = metrics.get("stock_units")
    sku_count = metrics.get("sku_count")
    rows_count = metrics.get("financial_rows_count")
    finance_available = bool(metrics.get("finance_available"))
    ads_efficiency_limited = bool(metrics.get("ads_efficiency_limited"))
    no_sales_top5 = metrics.get("no_sales_with_stock_top5") or []

    def _to_safe_int(value):
        try:
            if value is None or value == "":
                return None
            return int(value)
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

    def _extract_buyouts_from_financial_summary() -> dict[int, float]:
        qty = {}
        sku_fin = (facts.get("financial_summary") or {}).get("sku_financials")
        if not isinstance(sku_fin, dict):
            return qty
        for sku_raw, row in sku_fin.items():
            if not isinstance(row, dict):
                continue
            sku_i = _to_safe_int(sku_raw)
            qty_i = _to_safe_qty(row.get("sales_qty"))
            if sku_i is None or qty_i is None or qty_i <= 0:
                continue
            qty[sku_i] = qty.get(sku_i, 0.0) + qty_i
        return qty

    def _extract_from_sku_rows(field_names: tuple[str, ...]) -> dict[int, float]:
        qty = {}
        rows = (facts.get("sku_performance") or {}).get("rows")
        if not isinstance(rows, list):
            return qty
        for row in rows:
            if not isinstance(row, dict):
                continue
            sku_i = _to_safe_int(row.get("sku") or row.get("nmId") or row.get("nm_id"))
            if sku_i is None:
                continue
            qty_i = None
            for field in field_names:
                qty_i = _to_safe_qty(row.get(field))
                if qty_i is not None:
                    break
            if qty_i is None or qty_i <= 0:
                continue
            qty[sku_i] = qty.get(sku_i, 0.0) + qty_i
        return qty

    qty_by_sku = _extract_buyouts_from_financial_summary()
    qty_source = "financial_summary.sku_financials.sales_qty" if qty_by_sku else None

    if not qty_by_sku:
        qty_by_sku = _extract_from_sku_rows(("buyouts", "buys"))
        if qty_by_sku:
            qty_source = "sku_performance.rows.buyouts"

    if not qty_by_sku:
        qty_by_sku = _extract_from_sku_rows(("sales_qty", "orders"))
        if qty_by_sku:
            qty_source = "sku_performance.rows.sales_qty/orders"

    cogs_total = None
    cogs_by_sku = {}
    missing_cogs_sku = {}
    if qty_by_sku:
        qty_for_cogs = {}
        for sku_i, qty_val in qty_by_sku.items():
            q = int(qty_val)
            if q > 0:
                qty_for_cogs[int(sku_i)] = q
        if qty_for_cogs:
            cogs_total_raw, cogs_by_sku, missing_cogs_sku = calc_cogs_for_rows(qty_for_cogs)
            cogs_total = cogs_total_raw
            if cogs_total_raw == 0 and missing_cogs_sku:
                cogs_total = None

    print("COGS QTY SOURCE:", qty_source or "unavailable")
    print("COGS QTY BY SKU:", json.dumps(qty_by_sku, ensure_ascii=False, sort_keys=True))
    if missing_cogs_sku:
        print("COGS MISSING SKU:", json.dumps(missing_cogs_sku, ensure_ascii=False, sort_keys=True))

    print("REPORT METRICS RAW:", json.dumps(metrics.get("raw_values", {}), ensure_ascii=False, sort_keys=True))
    print("REPORT METRICS SOURCES:", json.dumps(metrics.get("sources", {}), ensure_ascii=False, sort_keys=True))
    print(
        "REPORT METRICS COMPUTED:",
        json.dumps(
            {
                "orders": orders,
                "views": views,
                "add_to_cart": add_to_cart,
                "cr_cart": cr_cart,
                "cr_order": cr_order,
                "revenue_orders": revenue_orders,
                "ad_spend": ad_spend,
                "ad_attributed_revenue": ad_attributed_revenue,
                "roas": roas,
                "stock_units": stock_units,
                "sku_count": sku_count,
                "financial_rows_count": rows_count,
                "finance_available": finance_available,
                "ads_efficiency_limited": ads_efficiency_limited,
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
        actions.append(
            {
                "priority": "P0",
                "area": "finance",
                "sku": "",
                "campaign_id": "",
                "action": "Check WB financial report export for the report date",
                "why": 'financial_summary.rows_count = 0, финансовый отчёт за дату не получен',
                "expected_effect": "Financial conclusions become available after WB returns financial rows",
                "numbers": {"financial_summary_rows_count": 0},
            }
        )

    if no_sales_top5:
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
        "## Сводка Воронки",
        f"- Заказы: {_fmt_int(orders)}",
        f"- Выкупы: {_fmt_int(buyouts)}",
        f"- Сумма заказов: {_fmt_money(revenue_orders)}",
        f"- Сумма выкупов: {_fmt_money(revenue_buyouts)}",
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
        f"- Расход на рекламу: {_fmt_money(ad_spend)}",
        f"- Атрибутированная выручка рекламы: {_fmt_money(ad_attributed_revenue)}",
        f"- ROAS: {_fmt_pct(roas) if roas is not None else 'н/д'}",
        "",
        "## Финансовая Сводка",
        f"- Себестоимость: {_fmt_money(cogs_total) if cogs_total is not None else 'н/д'}",
    ]

    if not finance_available:
        markdown_lines.append("- Финансовые данные за дату недоступны: WB не вернул реализацию / финансовые строки за этот день.")
    else:
        markdown_lines.append(f"- Количество финансовых строк: {_fmt_int(rows_count)}")

    if ads_efficiency_limited:
        markdown_lines.append("- Оценка эффективности рекламы ограничена: есть расход, но нет атрибутированной выручки.")

    markdown_lines.extend(["", "## Сводка SKU"])
    if no_sales_top5:
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
        markdown_lines.append("- SKU без продаж, но с остатками: нет")

    email_lines = [
        f"WB отчёт за {report_date}",
        f"Заказы: {_fmt_int(orders)}",
        f"Выкупы: {_fmt_int(buyouts)}",
        f"Сумма заказов: {_fmt_money(revenue_orders)}",
        f"Сумма выкупов: {_fmt_money(revenue_buyouts)}",
        f"Остатки (шт): {_fmt_int(stock_units)}",
        f"Расход на рекламу: {_fmt_money(ad_spend)}",
        f"Атрибутированная выручка рекламы: {_fmt_money(ad_attributed_revenue)}",
        f"ROAS: {_fmt_pct(roas) if roas is not None else 'н/д'}",
        f"Себестоимость: {_fmt_money(cogs_total) if cogs_total is not None else 'н/д'}",
    ]
    if not finance_available:
        email_lines.append("Финансовые данные за дату недоступны: WB не вернул реализацию / финансовые строки за этот день.")
    else:
        email_lines.append(f"Количество финансовых строк: {_fmt_int(rows_count)}")

    if ads_efficiency_limited:
        email_lines.append("Оценка эффективности рекламы ограничена: есть расход, но нет атрибутированной выручки.")

    return {
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
