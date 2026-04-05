"""Runner for isolated Ozon express audit mode."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.pdf_report import markdown_to_simple_pdf

from .facts_builder import build_ozon_facts
from .loader import load_ozon_excel
from .report import build_ozon_report


def run_ozon_audit(input_path: str, output_dir: str) -> dict[str, Any]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    md_path = out_dir / "ozon_report.md"
    pdf_path = out_dir / "ozon_report.pdf"
    facts_path = out_dir / "ozon_facts.json"
    actions_path = out_dir / "ozon_actions.json"

    data = load_ozon_excel(input_path)
    if data.get("error"):
        message = (
            "# Экспресс-аудит Ozon\n\n"
            "## Ошибка загрузки\n"
            f"- Не удалось прочитать файл: {data.get('error')}\n"
        )
        md_path.write_text(message, encoding="utf-8")
        markdown_to_simple_pdf(message, str(pdf_path), title="Экспресс-аудит Ozon")
        facts_path.write_text(json.dumps({"error": data.get("error")}, ensure_ascii=False, indent=2), encoding="utf-8")
        actions_path.write_text(json.dumps([], ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "ok": False,
            "error": data.get("error"),
            "md_path": str(md_path),
            "pdf_path": str(pdf_path),
            "facts_path": str(facts_path),
            "actions_path": str(actions_path),
        }

    facts = build_ozon_facts(data)
    report = build_ozon_report(facts)
    markdown = str(report.get("pdf_markdown") or "").strip() + "\n"
    actions = report.get("actions") or []

    md_path.write_text(markdown, encoding="utf-8")
    markdown_to_simple_pdf(markdown, str(pdf_path), title="Экспресс-аудит Ozon")
    facts_path.write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")
    actions_path.write_text(json.dumps(actions, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "ok": True,
        "md_path": str(md_path),
        "pdf_path": str(pdf_path),
        "facts_path": str(facts_path),
        "actions_path": str(actions_path),
    }

