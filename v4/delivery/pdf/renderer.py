"""Minimal deterministic PDF renderer for delivery layer.

Input: PdfPayload produced by outputs layer.
Output: rendered PDF file path.
Does not read metrics/facts/decisions directly and does not recompute KPI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from v3.pdf_render import write_text_pdf

from ...outputs.artifacts.writer import AUDIT_DISCLAIMER
from ...outputs.pdf.contracts import PdfPayload


def _normalize_mode(mode: object) -> str:
    return "audit" if str(mode).strip().lower() == "audit" else "daily"


def _status_text(status: object) -> str:
    text = str(status if status is not None else "").strip().lower()
    if text == "partial":
        return "partial"
    if text == "unavailable":
        return "unavailable"
    if text == "confirmed":
        return "confirmed"
    return text or "unknown"


def _display_value_by_status(row: dict[str, Any]) -> str:
    status = _status_text(row.get("status"))
    value = row.get("value")
    if isinstance(value, str):
        text = value.strip()
        if text and status in {"partial", "unavailable"}:
            return text
    if status == "unavailable":
        return "нет данных"
    if status == "partial":
        return "частично"

    if value is None:
        return "нет данных"
    text = str(value).strip()
    return text or "нет данных"


def _display_label(row: dict[str, Any]) -> str:
    label = row.get("label")
    if label is None:
        label = row.get("key")
    text = str(label if label is not None else "").strip()
    return text or "—"


def _status_ru(status: object) -> str:
    text = _status_text(status)
    if text == "confirmed":
        return "подтверждено"
    if text == "partial":
        return "частично"
    if text == "unavailable":
        return "нет данных"
    return text or "unknown"


def _sorted_items_text(payload: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for key in sorted(str(k) for k in payload.keys()):
        value = payload.get(key)
        if isinstance(value, dict):
            compact = ", ".join(f"{k}={value[k]}" for k in sorted(value.keys(), key=str))
            lines.append(f"{key}: {compact}")
        else:
            lines.append(f"{key}: {value}")
    return lines


def _mode_notes(pdf_payload: PdfPayload) -> list[str]:
    mode = _normalize_mode(pdf_payload.mode)
    lines = [f"mode: {mode}"]
    if mode == "audit":
        lines.append("mode_policy: limited")
        lines.append(AUDIT_DISCLAIMER)
    return lines


def _to_render_lines(pdf_payload: PdfPayload) -> list[str]:
    lines: list[str] = ["# WB v4 Delivery PDF"]
    lines.extend(_mode_notes(pdf_payload))

    if pdf_payload.warnings:
        lines.append("")
        lines.append("## Warnings")
        for warning in pdf_payload.warnings:
            lines.append(f"- {warning}")

    if pdf_payload.diagnostics:
        lines.append("")
        lines.append("## Diagnostics")
        lines.extend(_sorted_items_text(dict(pdf_payload.diagnostics)))

    rendered_pages = 0
    for page in pdf_payload.pages:
        page_has_rows = any(bool(block.rows) for block in page.blocks)
        if not page_has_rows:
            continue
        rendered_pages += 1

        lines.append("\f")
        lines.append(f"# {rendered_pages}. {str(page.title or 'Page')}")

        for block in page.blocks:
            if not block.rows:
                continue
            lines.append(f"## {block.title or 'Block'}")
            lines.append(f"Status: {_status_ru(block.status)}")
            lines.append("| Показатель | Значение | Статус |")
            lines.append("| --- | --- | --- |")
            for row in block.rows:
                lines.append(
                    "| "
                    + f"{_display_label(row)} | {_display_value_by_status(row)} | {_status_ru(row.get('status'))}"
                    + " |"
                )
            if block.diagnostics:
                lines.append("Diagnostics:")
                for diag in _sorted_items_text(dict(block.diagnostics)):
                    lines.append(f"- {diag}")

    if rendered_pages == 0:
        lines.append("")
        lines.append("Нет данных для рендеринга PDF.")

    return lines


def render_pdf(pdf_payload: PdfPayload, output_path: str | Path) -> str:
    if not isinstance(pdf_payload, PdfPayload):
        raise TypeError("render_pdf expects PdfPayload")

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    lines = _to_render_lines(pdf_payload)
    write_text_pdf(str(target), lines)
    return str(target.resolve())


__all__ = ["render_pdf", "_display_value_by_status", "_mode_notes", "_to_render_lines"]
