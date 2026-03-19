"""Email sender/preview adapters for delivery layer.

Input: EmailPayload (+ optional attachment paths).
Output: message draft dict, preview artifact, optional SMTP send result.
"""

from __future__ import annotations

import json
import mimetypes
import os
import smtplib
from email.header import Header
from email.message import EmailMessage
from pathlib import Path
from typing import Any

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


def _mask_email_targets(raw_value: str) -> str:
    parts = [item.strip() for item in str(raw_value or "").replace(";", ",").split(",") if item.strip()]
    masked: list[str] = []
    for part in parts:
        local, sep, domain = part.partition("@")
        if sep != "@":
            masked.append(part)
            continue
        if len(local) <= 2:
            masked_local = (local[:1] + "***") if local else "***"
        else:
            masked_local = local[:2] + "***"
        masked.append(f"{masked_local}@{domain}")
    return ", ".join(masked)


def _resolve_email_config() -> dict[str, Any]:
    username = str(os.getenv("EMAIL_USERNAME") or os.getenv("YANDEX_SMTP_USER") or "").strip()
    password = str(os.getenv("EMAIL_PASSWORD") or os.getenv("YANDEX_SMTP_APP_PASS") or "").strip()
    email_to = str(os.getenv("EMAIL_TO") or "").strip()

    missing: list[str] = []
    if not username:
        missing.append("EMAIL_USERNAME")
    if not password:
        missing.append("EMAIL_PASSWORD")
    if not email_to:
        missing.append("EMAIL_TO")
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

    smtp_host = str(os.getenv("SMTP_HOST") or os.getenv("YANDEX_SMTP_HOST") or "smtp.gmail.com").strip()
    smtp_port_text = str(os.getenv("SMTP_PORT") or os.getenv("YANDEX_SMTP_PORT") or "465").strip()
    try:
        smtp_port = int(smtp_port_text)
    except ValueError as exc:
        raise RuntimeError(f"Invalid SMTP_PORT value: {smtp_port_text}") from exc

    use_ssl_text = str(os.getenv("SMTP_SSL", "true")).strip().lower()
    use_ssl = use_ssl_text not in {"0", "false", "no", "off"}
    timeout_text = str(os.getenv("SMTP_TIMEOUT_SECONDS", "30")).strip()
    try:
        timeout_seconds = float(timeout_text)
    except ValueError as exc:
        raise RuntimeError(f"Invalid SMTP_TIMEOUT_SECONDS value: {timeout_text}") from exc

    return {
        "username": username,
        "password": password,
        "email_to": email_to,
        "smtp_host": smtp_host,
        "smtp_port": smtp_port,
        "use_ssl": use_ssl,
        "timeout_seconds": timeout_seconds,
    }


def _build_smtp_message(
    *,
    subject: str,
    body: str,
    from_addr: str,
    to_addr: str,
    attachments: list[Path],
) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = str(Header(str(subject or ""), "utf-8"))
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(body, subtype="plain", charset="utf-8")

    for path in attachments:
        guessed_type, _ = mimetypes.guess_type(str(path))
        if guessed_type:
            maintype, subtype = guessed_type.split("/", 1)
        else:
            maintype, subtype = "application", "octet-stream"
        payload = path.read_bytes()
        msg.add_attachment(payload, maintype=maintype, subtype=subtype, filename=path.name)
    return msg


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


def send_email_via_smtp(
    email_payload: EmailPayload,
    *,
    attachments: list[str] | None = None,
) -> dict:
    if not isinstance(email_payload, EmailPayload):
        raise TypeError("send_email_via_smtp expects EmailPayload")

    body = format_email_body(email_payload)
    if not str(body).strip():
        raise RuntimeError("Email body is empty")

    cfg = _resolve_email_config()
    attachment_paths: list[Path] = []
    for value in _dedupe_attachments(attachments):
        path = Path(value).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Attachment not found: {path}")
        attachment_paths.append(path)

    if not attachment_paths:
        raise RuntimeError("At least one attachment is required for SMTP send")

    message = _build_smtp_message(
        subject=email_payload.subject,
        body=body,
        from_addr=str(cfg["username"]),
        to_addr=str(cfg["email_to"]),
        attachments=attachment_paths,
    )

    client: smtplib.SMTP | smtplib.SMTP_SSL | None = None
    try:
        if bool(cfg["use_ssl"]):
            client = smtplib.SMTP_SSL(
                str(cfg["smtp_host"]),
                int(cfg["smtp_port"]),
                timeout=float(cfg["timeout_seconds"]),
            )
        else:
            client = smtplib.SMTP(
                str(cfg["smtp_host"]),
                int(cfg["smtp_port"]),
                timeout=float(cfg["timeout_seconds"]),
            )
            client.ehlo()
            client.starttls()
            client.ehlo()

        client.login(str(cfg["username"]), str(cfg["password"]))
        client.send_message(message)
    finally:
        if client is not None:
            try:
                client.quit()
            except Exception:
                pass

    return {
        "email_to_masked": _mask_email_targets(str(cfg["email_to"])),
        "subject": email_payload.subject,
        "email_stage": "send",
        "email_transport_status": "success",
        "email_failure_reason_normalized": "",
        "attachments_count": len(attachment_paths),
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


__all__ = ["build_email_message", "save_email_preview", "send_email_via_smtp"]

