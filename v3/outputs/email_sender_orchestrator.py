from __future__ import annotations

import os
import re
from typing import Any, Callable, Dict, List

from src.mailer_yandex import send_email_with_pdf

from ..pipeline.job_builder import apply_job_email_result


def _mask_email_address(value: str) -> str:
    clean = str(value or "").strip()
    if not clean:
        return ""
    local, sep, domain = clean.partition("@")
    if sep != "@":
        return clean
    if not local:
        return f"***@{domain}"
    if len(local) == 1:
        return f"{local}***@{domain}"
    if len(local) == 2:
        return f"{local[0]}***@{domain}"
    return f"{local[:2]}***@{domain}"


def mask_email_targets(raw_value: str) -> str:
    parts = [item.strip() for item in re.split(r"[;,]", str(raw_value or "")) if item.strip()]
    if not parts:
        return ""
    return ", ".join(_mask_email_address(item) for item in parts)


def send_daily_report_email(
    *,
    seller_id: str,
    run_date: str,
    report_pdf_path: str,
    email_summary: Dict[str, Any] | None,
    build_body: Callable[[str, str, Dict[str, Any] | None], str],
) -> str:
    email_to_raw = str(os.getenv("EMAIL_TO", "")).strip()
    email_to_masked = mask_email_targets(email_to_raw)
    smtp_user = str(os.getenv("YANDEX_SMTP_USER", "")).strip()
    smtp_pass = str(os.getenv("YANDEX_SMTP_APP_PASS", "")).strip()
    attachment_exists = os.path.isfile(report_pdf_path)

    print(f"[mail] email_to={email_to_masked or '<empty>'}")
    print(f"[mail] smtp_user_exists={str(bool(smtp_user)).lower()}")
    print(f"[mail] attachment_exists={str(attachment_exists).lower()}")
    print("[mail] send_started")

    missing_env: List[str] = []
    if not smtp_user:
        missing_env.append("YANDEX_SMTP_USER")
    if not smtp_pass:
        missing_env.append("YANDEX_SMTP_APP_PASS")
    if not email_to_raw:
        missing_env.append("EMAIL_TO")
    if missing_env:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing_env)}")
    if not attachment_exists:
        raise FileNotFoundError(f"Attachment not found: {report_pdf_path}")

    subject = f"WB AI Agent v3 — управленческое резюме: {seller_id} ({run_date})"
    body = build_body(
        seller_id,
        run_date,
        email_summary if isinstance(email_summary, dict) else {},
    )
    send_email_with_pdf(subject=subject, body=body, pdf_path=report_pdf_path)
    print("[mail] send_success")
    return email_to_masked


def orchestrate_daily_email_send(
    *,
    job: Dict[str, Any],
    seller_id: str,
    run_date: str,
    report_pdf_path: str,
    email_summary: Dict[str, Any] | None,
    build_body: Callable[[str, str, Dict[str, Any] | None], str],
) -> Dict[str, Any]:
    email_to_masked = mask_email_targets(str(os.getenv("EMAIL_TO", "")).strip())
    try:
        email_to_masked = send_daily_report_email(
            seller_id=seller_id,
            run_date=run_date,
            report_pdf_path=report_pdf_path,
            email_summary=email_summary if isinstance(email_summary, dict) else {},
            build_body=build_body,
        )
        return apply_job_email_result(
            job=job,
            attempted=True,
            sent=True,
            email_to=email_to_masked,
            error=None,
        )
    except Exception as exc:
        print(f"[mail] send_failed: {exc}")
        return apply_job_email_result(
            job=job,
            attempted=True,
            sent=False,
            email_to=email_to_masked,
            error=str(exc),
        )
