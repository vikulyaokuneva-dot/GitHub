from __future__ import annotations

import os
import re
from typing import Any, Callable, Dict, List

from src.mailer_yandex import send_email_with_pdf

from ..pdf_render import repair_mojibake
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


def build_daily_email_subject(*, seller_id: str, run_date: str) -> str:
    subject = (
        f"WB AI Agent v3 — "
        f"\u0443\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0447\u0435\u0441\u043a\u043e\u0435 "
        f"\u0440\u0435\u0437\u044e\u043c\u0435: {seller_id} ({run_date})"
    )
    return repair_mojibake(subject)


def _summary_text(summary: Dict[str, Any], key: str, default: str = "not confirmed") -> str:
    display = summary.get("display", {}) if isinstance(summary.get("display"), dict) else {}
    value = display.get(key)
    if value is None:
        value = summary.get(key)
    text = str(value or "").strip()
    return repair_mojibake(text) if text else default


def build_daily_email_body(
    *,
    seller_id: str,
    run_date: str,
    email_summary: Dict[str, Any] | None,
    build_body: Callable[[str, str, Dict[str, Any] | None], str],
) -> str:
    _ = build_body
    summary = email_summary if isinstance(email_summary, dict) else {}
    event_date_model = summary.get("event_date_model", {}) if isinstance(summary.get("event_date_model"), dict) else {}
    operational_day = str(event_date_model.get("operational_date") or run_date)
    financial_finality_status = str(summary.get("financial_finality_status") or "unavailable")
    financial_interpretation = "provisional" if financial_finality_status != "final" else "final"
    ai_mode = str(summary.get("ai_guidance_mode") or "standard")
    ai_reasons = summary.get("ai_guardrail_reasons", []) if isinstance(summary.get("ai_guardrail_reasons"), list) else []

    lines: List[str] = [
        f"\u0423\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0447\u0435\u0441\u043a\u043e\u0435 \u0440\u0435\u0437\u044e\u043c\u0435 WB AI Agent v3 - cabinet {seller_id}",
        f"Report date: {run_date}",
        f"Operational day: {operational_day}",
        "",
        "COMMERCE KPI",
        f"- Orders: {_summary_text(summary, 'orders_count')}",
        f"- Buyouts: {_summary_text(summary, 'buyouts_count')}",
        f"- Buyouts amount: {_summary_text(summary, 'buyouts_amount')}",
        f"- Orders amount: {_summary_text(summary, 'orders_amount')}",
        "",
        "FINANCIAL KPI",
        f"- Revenue: {_summary_text(summary, 'financial_revenue')}",
        f"- Net profit: {_summary_text(summary, 'net_profit')}",
        f"- Margin: {_summary_text(summary, 'margin_pct')}",
        f"- Profitability: {_summary_text(summary, 'profitability_pct')}",
        f"- Financial contour status: {financial_finality_status}",
        f"- Financial KPI interpretation: {financial_interpretation}",
    ]

    if ai_mode == "preliminary":
        reasons_text = "; ".join(str(item).strip() for item in ai_reasons if str(item).strip())
        lines.extend(
            [
                "",
                "AI Guidance Mode",
                "- PRELIMINARY / HYPOTHESIS ONLY",
                "- High-impact actions require confirmation on complete data.",
                ("- Reasons: " + reasons_text) if reasons_text else "- Reasons: limited data quality",
            ]
        )

    insights = summary.get("key_insights", []) if isinstance(summary.get("key_insights"), list) else []
    recommendations = summary.get("recommendations", []) if isinstance(summary.get("recommendations"), list) else []

    lines.extend(["", "Key Insights"])
    if insights:
        lines.extend(f"- {repair_mojibake(str(item))}" for item in insights[:3] if str(item).strip())
    else:
        lines.append("- No major deviations detected.")

    lines.extend(["", "Recommendations"])
    if recommendations:
        lines.extend(f"- {repair_mojibake(str(item))}" for item in recommendations[:3] if str(item).strip())
    else:
        lines.append("- Keep current operating strategy and monitor KPI dynamics.")

    conclusion = str(summary.get("ai_day_conclusion") or "").strip()
    if conclusion:
        lines.extend(["", "AI Conclusion", repair_mojibake(conclusion)])

    return "\n".join(lines)


def send_daily_report_email(
    *,
    seller_id: str,
    run_date: str,
    report_pdf_path: str,
    email_summary: Dict[str, Any] | None,
    build_body: Callable[[str, str, Dict[str, Any] | None], str],
) -> Dict[str, str]:
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

    subject = build_daily_email_subject(seller_id=seller_id, run_date=run_date)
    body = build_daily_email_body(
        seller_id=seller_id,
        run_date=run_date,
        email_summary=email_summary if isinstance(email_summary, dict) else {},
        build_body=build_body,
    )
    send_email_with_pdf(subject=subject, body=body, pdf_path=report_pdf_path)
    print("[mail] send_success")
    return {
        "email_to_masked": email_to_masked,
        "subject": subject,
        "body": body,
    }


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
    email_subject = ""
    email_body_text = ""
    try:
        send_result = send_daily_report_email(
            seller_id=seller_id,
            run_date=run_date,
            report_pdf_path=report_pdf_path,
            email_summary=email_summary if isinstance(email_summary, dict) else {},
            build_body=build_body,
        )
        if isinstance(send_result, dict):
            email_to_masked = str(send_result.get("email_to_masked") or email_to_masked)
            email_subject = str(send_result.get("subject") or "")
            email_body_text = str(send_result.get("body") or "")
        out = apply_job_email_result(
            job=job,
            attempted=True,
            sent=True,
            email_to=email_to_masked,
            error=None,
        )
        out["email_subject"] = email_subject
        out["email_body_text"] = email_body_text
        return out
    except Exception as exc:
        print(f"[mail] send_failed: {exc}")
        out = apply_job_email_result(
            job=job,
            attempted=True,
            sent=False,
            email_to=email_to_masked,
            error=str(exc),
        )
        if email_subject:
            out["email_subject"] = email_subject
        if email_body_text:
            out["email_body_text"] = email_body_text
        return out
