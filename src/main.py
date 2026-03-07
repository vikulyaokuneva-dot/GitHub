import json
import re
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from src.report_prompt import REPORT_PROMPT_TEMPLATE
from src.gigachat_client import generate_report_from_facts
from src.pdf_report import markdown_to_simple_pdf
from src.mailer_yandex import send_email_with_pdf
from src.facts_builder import build_facts_json
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

    # ВАЖНО: без indent, чтобы не раздувать prompt
    facts_json = json.dumps(facts_for_llm, ensure_ascii=False)
    print("FACTS SIZE (chars):", len(facts_json))

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
