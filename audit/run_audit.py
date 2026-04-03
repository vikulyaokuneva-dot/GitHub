#!/usr/bin/env python3
"""File-based audit runner."""

from __future__ import annotations

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
except Exception:  # pragma: no cover
    send_email_with_pdf = None


def _build_email_text(facts: dict, actions: list[dict]) -> str:
    decision = facts.get("decision_layer") or {}
    kpi = decision.get("kpi") or {}
    profit = kpi.get("profit")
    margin = kpi.get("margin")
    state = decision.get("profit_state")
    missing_required = ((facts.get("inputs") or {}).get("missing_required") or [])

    lines = [
        "WB аудит (file mode)",
        "",
        f"Финрезультат: {state}, profit={profit}, margin={margin}",
        f"Причин в decision_layer: {len(decision.get('reasons_of_loss') or [])}",
    ]
    if missing_required:
        lines.append(f"Внимание: не хватает обязательных файлов: {', '.join(missing_required)}")
    if actions:
        lines.append(f"Приоритетное действие: {actions[0].get('action')}")
    return "\n".join(lines).strip()


def run_audit_mode(
    *,
    input_dir: str = "audit/input",
    out_dir: str = "audit/output",
    period: str = "",
    send_email: bool = False,
) -> dict:
    os.makedirs(out_dir, exist_ok=True)

    print(f"[audit] input_dir={input_dir}")
    print("[audit] scanning files...")

    facts = build_audit_facts(input_dir=input_dir, period_label=period)
    inputs = facts.get("inputs") or {}

    found_files = inputs.get("found_files") or []
    selected_files = inputs.get("selected_files") or {}
    missing_required = inputs.get("missing_required") or []
    missing_optional = inputs.get("missing_optional") or []
    blocks_collected = inputs.get("blocks_collected") or []
    blocks_skipped = inputs.get("blocks_skipped") or []

    print(f"[audit] found files: {len(found_files)}")
    for item in found_files:
        print(
            f"[audit] file: {item.get('path')} | type={item.get('type')} "
            f"| score={item.get('score')} | by={item.get('detected_by')}"
        )
    print(f"[audit] selected: {selected_files}")
    print(f"[audit] blocks collected: {blocks_collected}")
    print(f"[audit] blocks skipped: {blocks_skipped}")
    print(f"[audit] missing required: {missing_required}")
    print(f"[audit] missing optional: {missing_optional}")

    md = build_audit_markdown(facts)
    actions = facts.get("actions") or []

    stamp = datetime.now(ZoneInfo("Europe/Moscow")).strftime("%Y-%m-%d")
    file_date = stamp

    facts_path = os.path.join(out_dir, f"facts_audit_{file_date}.json")
    md_path = os.path.join(out_dir, f"audit_{file_date}.md")
    pdf_path = os.path.join(out_dir, f"audit_{file_date}.pdf")
    actions_path = os.path.join(out_dir, f"actions_audit_{file_date}.json")

    with open(facts_path, "w", encoding="utf-8") as f:
        json.dump(facts, f, ensure_ascii=False, indent=2)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    with open(actions_path, "w", encoding="utf-8") as f:
        json.dump(actions, f, ensure_ascii=False, indent=2)

    markdown_to_simple_pdf(md, pdf_path, title=f"WB аудит за {file_date}")

    if send_email and send_email_with_pdf:
        subject = f"WB аудит за {file_date}"
        body = _build_email_text(facts, actions)
        send_email_with_pdf(subject, body, pdf_path)

    print(f"[audit] saved facts: {facts_path}")
    print(f"[audit] saved md: {md_path}")
    print(f"[audit] saved pdf: {pdf_path}")
    print(f"[audit] saved actions: {actions_path}")

    return {
        "facts_path": facts_path,
        "md_path": md_path,
        "pdf_path": pdf_path,
        "actions_path": actions_path,
        "missing_required": missing_required,
        "missing_optional": missing_optional,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run WB offline audit from audit/input files.")
    parser.add_argument("--period", default="", help="Optional period label, e.g. 2026-03-01_2026-03-31")
    parser.add_argument("--input_dir", default="audit/input")
    parser.add_argument("--out_dir", default="audit/output")
    parser.add_argument("--send_email", action="store_true")
    args = parser.parse_args()

    run_audit_mode(
        input_dir=args.input_dir,
        out_dir=args.out_dir,
        period=args.period,
        send_email=bool(args.send_email),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

