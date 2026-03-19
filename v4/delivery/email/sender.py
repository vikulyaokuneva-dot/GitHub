"""Email sender/preview adapters for delivery layer.

Input: EmailPayload (+ optional attachment paths).
Output: message draft dict and preview artifact.
Does not send SMTP by default.
"""

from __future__ import annotations

import json
from pathlib import Path

from ...outputs.email.contracts import EmailPayload
from .formatter import format_email_body


def _normalize_mode(mode: object) -> str:
    return "audit" if str(mode).strip().lower() == "audit" else "daily"


def _dedupe_attachments(attachments: list[str] | None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in attachments or []:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def build_email_message(email_payload: EmailPayload, attachments: list[str] | None = None) -> dict:
    if not isinstance(email_payload, EmailPayload):
        raise TypeError("build_email_message expects EmailPayload")

    safe_attachments = _dedupe_attachments(attachments)
    body = format_email_body(email_payload)
    mode = _normalize_mode(email_payload.mode)

    return {
        "subject": email_payload.subject,
        "preheader": email_payload.preheader,
        "mode": mode,
        "body": body,
        "attachments": safe_attachments,
        "diagnostics": {
            "sections_count": len(email_payload.sections),
            "summary_lines_count": len(email_payload.summary_lines),
            "warnings_count": len(email_payload.warnings),
            "attachments_count": len(safe_attachments),
        },
    }


def save_email_preview(
    email_payload: EmailPayload,
    output_dir: str | Path,
    attachments: list[str] | None = None,
) -> str:
    target_dir = Path(output_dir) if output_dir is not None else None
    if target_dir is None or not str(target_dir).strip():
        raise ValueError("output_dir is required for save_email_preview")

    target_dir.mkdir(parents=True, exist_ok=True)
    message = build_email_message(email_payload, attachments=attachments)

    preview_path = target_dir / "email_preview.json"
    preview_path.write_text(
        json.dumps(message, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(preview_path.resolve())


__all__ = ["build_email_message", "save_email_preview"]
