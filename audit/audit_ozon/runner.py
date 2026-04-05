"""Runner for isolated Ozon express audit mode."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from src.pdf_report import markdown_to_simple_pdf

from .facts_builder import build_ozon_facts
from .loader import load_ozon_excel
from .report import build_ozon_report


def _period_suffix(facts: dict[str, Any]) -> str:
    period = facts.get("period") if isinstance(facts.get("period"), dict) else {}
    date_from = str(period.get("date_from") or "").strip()
    date_to = str(period.get("date_to") or "").strip()
    if len(date_from) == 10 and len(date_to) == 10:
        return f"_{date_from}_{date_to}"
    return ""


def _pdf_title(facts: dict[str, Any]) -> str:
    period = facts.get("period") if isinstance(facts.get("period"), dict) else {}
    label = str(period.get("label_ru") or "").strip()
    if label:
        return f"Экспресс-аудит Ozon за период {label}"
    return "Экспресс-аудит Ozon"


def run_ozon_audit(input_path: str, output_dir: str) -> dict[str, Any]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    default_md_path = out_dir / "ozon_report.md"
    default_pdf_path = out_dir / "ozon_report.pdf"
    facts_path = out_dir / "ozon_facts.json"
    actions_path = out_dir / "ozon_actions.json"

    data = load_ozon_excel(input_path)
    if data.get("error"):
        markdown = (
            "# Экспресс-аудит Ozon\n\n"
            "## Ошибка загрузки\n"
            f"- Не удалось прочитать файл: {data.get('error')}\n"
        )
        default_md_path.write_text(markdown, encoding="utf-8")
        markdown_to_simple_pdf(markdown, str(default_pdf_path), title="Экспресс-аудит Ozon")
        facts_path.write_text(json.dumps({"error": data.get("error")}, ensure_ascii=False, indent=2), encoding="utf-8")
        actions_path.write_text(json.dumps([], ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "ok": False,
            "error": data.get("error"),
            "md_path": str(default_md_path),
            "pdf_path": str(default_pdf_path),
            "facts_path": str(facts_path),
            "actions_path": str(actions_path),
        }

    facts = build_ozon_facts(data)
    report = build_ozon_report(facts)
    markdown = str(report.get("pdf_markdown") or "").strip() + "\n"
    actions = report.get("actions") or []

    suffix = _period_suffix(facts)
    report_stem = f"ozon_report{suffix}" if suffix else "ozon_report"
    md_path = out_dir / f"{report_stem}.md"
    pdf_path = out_dir / f"{report_stem}.pdf"

    md_path.write_text(markdown, encoding="utf-8")
    markdown_to_simple_pdf(markdown, str(pdf_path), title=_pdf_title(facts))

    # Compatibility aliases for older integrations.
    if md_path != default_md_path:
        shutil.copyfile(md_path, default_md_path)
    if pdf_path != default_pdf_path:
        shutil.copyfile(pdf_path, default_pdf_path)

    facts_path.write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")
    actions_path.write_text(json.dumps(actions, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "ok": True,
        "md_path": str(md_path),
        "pdf_path": str(pdf_path),
        "facts_path": str(facts_path),
        "actions_path": str(actions_path),
        "md_alias": str(default_md_path),
        "pdf_alias": str(default_pdf_path),
    }
