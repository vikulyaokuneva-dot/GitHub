"""Deterministic renderers that consume `ReportPayload` and perform no business calculation."""

from __future__ import annotations

from html import escape
from typing import Any

from .contracts import ReportPayload


_STATUS_LABELS: dict[str, str] = {
    "missing": "Нет данных",
    "unavailable": "Недоступно",
    "unresolved": "Не определено",
    "conflict": "Конфликт данных",
    "insufficient_data": "Недоступно",
}


def _display(value: object, status: str) -> str:
    if value is not None:
        return str(value)
    return _STATUS_LABELS.get(status, "Недоступно")


def _ordered_rows(payload: ReportPayload) -> tuple[tuple[str, str, str], ...]:
    return tuple((metric.key, _display(metric.value, metric.status), metric.status) for metric in payload.metrics)


def render_email_text(payload: ReportPayload) -> str:
    """Render a stable plain-text projection of already-calculated metric values."""

    lines = [f"WB Autopilot report: {payload.operational_date.isoformat()}"]
    lines.extend(f"{key}: {value}" for key, value, _ in _ordered_rows(payload))
    lines.extend(f"diagnostic: {item}" for item in payload.diagnostics)
    return "\n".join(lines) + "\n"


def render_email_html(payload: ReportPayload) -> str:
    """Render a stable escaped HTML projection without filesystem reads."""

    rows = "".join(
        f"<tr><td>{escape(key)}</td><td>{escape(value)}</td><td>{escape(status)}</td></tr>"
        for key, value, status in _ordered_rows(payload)
    )
    diagnostics = "".join(f"<li>{escape(item)}</li>" for item in payload.diagnostics)
    return (
        "<!doctype html><html><body>"
        f"<h1>WB Autopilot report: {escape(payload.operational_date.isoformat())}</h1>"
        "<table><thead><tr><th>Metric</th><th>Value</th><th>Status</th></tr></thead>"
        f"<tbody>{rows}</tbody></table><ul>{diagnostics}</ul></body></html>"
    )


def render_pdf(payload: ReportPayload) -> bytes:
    """Render a deterministic one-page PDF without business calculations or external assets."""

    from io import BytesIO
    from reportlab.lib.pagesizes import A4  # type: ignore[import-untyped]
    from reportlab.pdfgen.canvas import Canvas  # type: ignore[import-untyped]

    buffer = BytesIO()
    canvas: Any = Canvas(buffer, pagesize=A4, pageCompression=0, invariant=1)
    width, height = A4
    canvas.setTitle("WB Autopilot report")
    canvas.setFont("Helvetica-Bold", 14)
    canvas.drawString(40, height - 40, f"WB Autopilot report: {payload.operational_date.isoformat()}")
    y = height - 70
    canvas.setFont("Helvetica", 9)
    for key, value, status in _ordered_rows(payload):
        if y < 45:
            canvas.showPage()
            canvas.setFont("Helvetica", 9)
            y = height - 40
        line = f"{key}: {value}"
        canvas.drawString(40, y, line[:120])
        y -= 14
    for diagnostic in payload.diagnostics:
        if y < 45:
            canvas.showPage()
            canvas.setFont("Helvetica", 9)
            y = height - 40
        canvas.drawString(40, y, f"diagnostic: {diagnostic}"[:120])
        y -= 14
    canvas.save()
    return buffer.getvalue()
