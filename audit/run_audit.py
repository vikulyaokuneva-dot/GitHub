#!/usr/bin/env python3
# audit/run_audit.py

import argparse
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from audit.audit_facts_builder import build_audit_facts
from audit.audit_report import build_audit_markdown
from src.pdf_report import markdown_to_simple_pdf

try:
    from src.mailer_yandex import send_email_with_pdf
except Exception:
    send_email_with_pdf = None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", default="")
    ap.add_argument("--input_dir", default="audit/input")
    ap.add_argument("--out_dir", default="audit/artifacts")
    ap.add_argument("--send_email", action="store_true")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    # --- 1. Собираем факты ---
    facts = build_audit_facts(input_dir=args.input_dir, period_label=args.period)

    # --- 2. Пытаемся получить отчёт (через GigaChat / fallback) ---
    from src.report_prompt import REPORT_PROMPT_TEMPLATE
    from src.gigachat_client import generate_report_from_facts

    prompt = REPORT_PROMPT_TEMPLATE.replace(
        "__FACTS_JSON__",
        json.dumps(facts, ensure_ascii=False)
    )

    response_text = generate_report_from_facts(prompt)

    # --- 3. Парсим ответ безопасно ---
    try:
        resp = json.loads(response_text)
    except Exception:
        resp = {}

    md = resp.get("pdf_markdown", "")
    actions = resp.get("actions", [])

    # --- 4. 🔥 КЛЮЧЕВОЙ ФИКС: если md пустой ---
    if not md or not md.strip():
        print("⚠️ GigaChat не дал отчёт — используем локальную генерацию")

        md = build_audit_markdown(facts)

        # если actions не пришли — берём из facts
        if not actions:
            actions = facts.get("actions", [])

    # --- 5. Подготовка путей ---
    tz = ZoneInfo("Europe/Moscow")
    stamp = datetime.now(tz).strftime("%Y-%m-%d")
    period = facts.get("period", {}).get("label") or args.period or stamp

    md_path = os.path.join(args.out_dir, f"audit_{period}.md")
    json_path = os.path.join(args.out_dir, f"facts_audit_{period}.json")
    actions_path = os.path.join(args.out_dir, f"actions_audit_{period}.json")
    pdf_path = os.path.join(args.out_dir, f"audit_{period}.pdf")

    # --- 6. Сохраняем ---
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md.strip() + "\n")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(facts, f, ensure_ascii=False, indent=2)

    with open(actions_path, "w", encoding="utf-8") as f:
        json.dump(actions, f, ensure_ascii=False, indent=2)

    # --- 7. Генерация PDF ---
    markdown_to_simple_pdf(md, pdf_path, title=f"WB аудит: {period}")

    # --- 8. Email (опционально) ---
    if args.send_email and send_email_with_pdf:
        subject = f"WB аудит: {period}"
        body = f"WB аудит за период {period}\n\nСм. PDF во вложении."
        send_email_with_pdf(subject, body, pdf_path)

    print("OK:", pdf_path)


if __name__ == "__main__":
    main()