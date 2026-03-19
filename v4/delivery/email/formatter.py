"""Plain-text email formatter for delivery layer.

Input: EmailPayload from outputs layer.
Output: deterministic plain-text body.
Does not generate new business meaning.
"""

from __future__ import annotations

from ...outputs.email.builder import AUDIT_DISCLAIMER
from ...outputs.email.contracts import EmailPayload


def _normalize_mode(mode: object) -> str:
    return "audit" if str(mode).strip().lower() == "audit" else "daily"


def _status_text(status: object) -> str:
    text = str(status if status is not None else "").strip().lower()
    return text or "unknown"


def format_email_body(email_payload: EmailPayload) -> str:
    if not isinstance(email_payload, EmailPayload):
        raise TypeError("format_email_body expects EmailPayload")

    mode = _normalize_mode(email_payload.mode)
    lines: list[str] = [
        f"Subject: {email_payload.subject}",
        f"Preheader: {email_payload.preheader}",
        f"Mode: {mode}",
        "",
    ]

    lines.append("Summary:")
    if email_payload.summary_lines:
        for line in email_payload.summary_lines:
            lines.append(f"- {line}")
    else:
        lines.append("- нет данных")

    for section in email_payload.sections:
        lines.append("")
        lines.append(f"[{_status_text(section.status)}] {section.title}")
        if section.lines:
            for line in section.lines:
                lines.append(f"- {line}")
        else:
            lines.append("- нет данных")

    lines.append("")
    lines.append("Warnings:")
    if email_payload.warnings:
        for warning in email_payload.warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- none")

    if mode == "audit" and not any(AUDIT_DISCLAIMER in line for line in lines):
        lines.append("")
        lines.append(AUDIT_DISCLAIMER)

    return "\n".join(lines).rstrip() + "\n"


__all__ = ["format_email_body"]
