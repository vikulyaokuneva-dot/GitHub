#!/usr/bin/env python3
"""File-based audit runner."""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from audit.audit_facts_builder import build_audit_facts
from audit.audit_report import build_audit_markdown
from audit.ozon_facts_builder import build_ozon_audit_facts
from audit.ozon_report import build_ozon_audit_markdown
from audit.lib.pdf_report import markdown_to_simple_pdf

try:
    from src.mailer_yandex import send_email_with_pdf
except Exception:  # pragma: no cover
    send_email_with_pdf = None


DEFAULT_SELLER_ID = "seller_001"


def _build_email_text(facts: dict, actions: list[dict], source: str) -> str:
    decision = facts.get("decision_layer") or {}
    kpi = decision.get("kpi") or {}
    source_norm = str(source or "wb").strip().lower()
    if source_norm == "ozon":
        profit = kpi.get("gross_profit_total_known")
        margin = (facts.get("financial_summary") or {}).get("margin_from_products_with_cogs")
    else:
        profit = kpi.get("profit")
        margin = kpi.get("margin")
    state = decision.get("profit_state") or "unknown"
    missing_required = ((facts.get("inputs") or {}).get("missing_required") or [])

    lines = [
        f"{source_norm.upper()} аудит (file mode)",
        "",
        f"Финрезультат: {state}, profit={profit}, margin={margin}",
        (
            f"Причин в decision_layer: {len(decision.get('reasons_of_loss') or [])}"
            if source_norm == "wb"
            else f"SKU-проблем в decision_layer: {len(decision.get('sku_problems') or [])}"
        ),
    ]
    if missing_required:
        lines.append(f"Внимание: не хватает обязательных файлов: {', '.join(missing_required)}")
    if actions:
        lines.append(f"Приоритетное действие: {actions[0].get('action')}")
    return "\n".join(lines).strip()


def _safe_date_fragment(value: str) -> str:
    text = str(value or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return ""
    return text


def _seller_scoped_paths(seller: str) -> tuple[str, str]:
    seller_norm = str(seller or "").strip() or DEFAULT_SELLER_ID
    base = os.path.join("cabinets", seller_norm)
    return os.path.join(base, "input"), os.path.join(base, "artifacts")


def _resolve_audit_paths(*, input_dir: str | None, out_dir: str | None, seller: str) -> tuple[str, str]:
    default_input, default_out = _seller_scoped_paths(seller)
    input_resolved = str(input_dir or "").strip() or default_input
    out_resolved = str(out_dir or "").strip() or default_out
    return input_resolved, out_resolved


def run_audit_mode(
    *,
    seller: str = DEFAULT_SELLER_ID,
    input_dir: str = "",
    out_dir: str = "",
    source: str = "wb",
    period: str = "",
    send_email: bool = False,
) -> dict:
    input_dir, out_dir = _resolve_audit_paths(
        input_dir=input_dir,
        out_dir=out_dir,
        seller=seller,
    )
    os.makedirs(out_dir, exist_ok=True)
    source_norm = str(source or "wb").strip().lower()
    if source_norm not in {"wb", "ozon"}:
        raise ValueError(f"Unsupported audit source: {source}")

    print(f"[audit] seller={str(seller or '').strip() or DEFAULT_SELLER_ID}")
    print(f"[audit] source={source_norm}")
    print(f"[audit] input_dir={input_dir}")
    print("[audit] scanning files...")

    if source_norm == "ozon":
        facts = build_ozon_audit_facts(input_dir=input_dir, period_label=period)
        md = build_ozon_audit_markdown(facts)
    else:
        facts = build_audit_facts(input_dir=input_dir, period_label=period)
        md = build_audit_markdown(facts)

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

    actions = facts.get("actions") or []
    audit_period = facts.get("audit_period") if isinstance(facts.get("audit_period"), dict) else {}
    period_from = _safe_date_fragment(str(audit_period.get("date_from") or ""))
    period_to = _safe_date_fragment(str(audit_period.get("date_to") or ""))
    period_label_ru = str(audit_period.get("label_ru") or "").strip()

    stamp = datetime.now(ZoneInfo("Europe/Moscow")).strftime("%Y-%m-%d")
    file_date = stamp

    facts_path = os.path.join(out_dir, f"facts_audit_{file_date}.json")
    md_path = os.path.join(out_dir, f"audit_{file_date}.md")
    if source_norm == "wb" and period_from and period_to:
        pdf_path = os.path.join(out_dir, f"audit_wb_{period_from}_{period_to}.pdf")
    else:
        pdf_path = os.path.join(out_dir, f"audit_{file_date}.pdf")
    actions_path = os.path.join(out_dir, f"actions_audit_{file_date}.json")
    search_insights_path = os.path.join(out_dir, "search_insights.json")

    with open(facts_path, "w", encoding="utf-8") as f:
        json.dump(facts, f, ensure_ascii=False, indent=2)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    with open(actions_path, "w", encoding="utf-8") as f:
        json.dump(actions, f, ensure_ascii=False, indent=2)
    with open(search_insights_path, "w", encoding="utf-8") as f:
        json.dump(facts.get("search_insights") or {}, f, ensure_ascii=False, indent=2)

    title_prefix = "WB" if source_norm == "wb" else "Ozon"
    if source_norm == "wb" and period_label_ru:
        pdf_title = f"Аудит кабинета WB за период {period_label_ru}"
    else:
        pdf_title = f"{title_prefix} аудит за {file_date}"
    markdown_to_simple_pdf(
        md,
        pdf_path,
        title=pdf_title,
        page_number_format="Стр. {page} из {total}",
        page_number_align="center",
        skip_first_page_numbering=True,
    )

    if send_email and send_email_with_pdf:
        subject = pdf_title
        body = _build_email_text(facts, actions, source=source_norm)
        send_email_with_pdf(subject, body, pdf_path)

    print(f"[audit] saved facts: {facts_path}")
    print(f"[audit] saved md: {md_path}")
    print(f"[audit] saved pdf: {pdf_path}")
    print(f"[audit] saved actions: {actions_path}")
    print(f"[audit] saved search insights: {search_insights_path}")

    return {
        "facts_path": facts_path,
        "md_path": md_path,
        "pdf_path": pdf_path,
        "actions_path": actions_path,
        "search_insights_path": search_insights_path,
        "seller": str(seller or "").strip() or DEFAULT_SELLER_ID,
        "source": source_norm,
        "missing_required": missing_required,
        "missing_optional": missing_optional,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run offline audit from files.")
    parser.add_argument("--seller", default=DEFAULT_SELLER_ID, help="Seller id for seller-scoped paths")
    parser.add_argument("--source", default="wb", help="Audit source: wb | ozon")
    parser.add_argument("--period", default="", help="Optional period label, e.g. 2026-03-01_2026-03-31")
    parser.add_argument("--input_dir", default="", help="Optional input dir override")
    parser.add_argument("--out_dir", default="", help="Optional output dir override")
    parser.add_argument("--send_email", action="store_true")
    args = parser.parse_args()

    run_audit_mode(
        seller=args.seller,
        input_dir=args.input_dir,
        out_dir=args.out_dir,
        source=args.source,
        period=args.period,
        send_email=bool(args.send_email),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
