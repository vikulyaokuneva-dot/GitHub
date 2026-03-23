#!/usr/bin/env python3
# audit/run_audit.py
"""
Offline Audit mode (no WB API required, no LLM required).

Inputs (by default):
  audit/input/ads/*           - рекламная статистика (xlsx), лист "Статистика"
  audit/input/stocks/*        - остатки (xlsx)
  audit/input/finance/*       - финансовый детализированный отчет (xlsx)
  audit/input/funnel/*        - воронка продаж по товарам (xlsx), лист "Товары"

Outputs:
  audit/artifacts/audit_<period>.pdf
  audit/artifacts/facts_audit_<period>.json
  audit/artifacts/audit_<period>.md
  audit/artifacts/actions_audit_<period>.json
"""
import argparse
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from audit.audit_facts_builder import build_audit_facts
from audit.audit_report import build_audit_markdown
from src.pdf_report import markdown_to_simple_pdf

# Optional: email sending (disabled by default)
try:
    from src.mailer_yandex import send_email_with_pdf
except Exception:
    send_email_with_pdf = None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", default="", help="Label for the audit period, e.g. 2026-02-23_2026-03-01")
    ap.add_argument("--input_dir", default="audit/input", help="Input directory root")
    ap.add_argument("--out_dir", default="audit/artifacts", help="Output directory")
    ap.add_argument("--send_email", action="store_true", help="Send email (requires env SMTP vars like daily)")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    facts = build_audit_facts(input_dir=args.input_dir, period_label=args.period)

    # LLM report generation
    from src.report_prompt import REPORT_PROMPT_TEMPLATE
    from src.gigachat_client import generate_report_from_facts

    facts_for_llm = dict(facts)

    prompt = REPORT_PROMPT_TEMPLATE.replace(
        "__FACTS_JSON__",
        json.dumps(facts_for_llm, ensure_ascii=False)
    )

    response_text = generate_report_from_facts(prompt)

    try:
        resp = json.loads(response_text)
    except Exception:
        resp = {
            "status": "invalid_json",
            "raw": response_text
        }

    md = resp.get("pdf_markdown", "")
    actions = resp.get("actions", [])

    tz = ZoneInfo("Europe/Moscow")
    stamp = datetime.now(tz).strftime("%Y-%m-%d")
    period = facts.get("period", {}).get("label") or args.period or stamp

    md_path = os.path.join(args.out_dir, f"audit_{period}.md")
    json_path = os.path.join(args.out_dir, f"facts_audit_{period}.json")
    actions_path = os.path.join(args.out_dir, f"actions_audit_{period}.json")
    pdf_path = os.path.join(args.out_dir, f"audit_{period}.pdf")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md.strip() + "\n")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(facts, f, ensure_ascii=False, indent=2)
    with open(actions_path, "w", encoding="utf-8") as f:
        json.dump(facts.get("actions", []), f, ensure_ascii=False, indent=2)

    markdown_to_simple_pdf(md, pdf_path, title=f"WB аудит: {period}")

    if args.send_email and send_email_with_pdf:
        subject = f"WB аудит: {period}"
        body = f"WB аудит за период {period}\n\nСм. PDF во вложении.\n\n(Артефакты сохранены в GitHub Actions.)"
        send_email_with_pdf(subject, body, pdf_path)

    print("OK:", pdf_path)


if __name__ == "__main__":
    main()
