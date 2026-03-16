from __future__ import annotations

import os
import re
from typing import Any, Callable, Dict, List

from src.mailer_yandex import EmailDeliveryError, normalize_email_failure_reason, send_email_with_pdf

from ..pdf_render import normalize_pdf_text
from ..pipeline.job_builder import apply_job_email_result
from .render_policy import format_int_or_unknown, format_pct_or_unknown, is_missing_value


def _format_rate_for_email(value: Any, *, lag_sensitive: bool = False) -> str:
    unknown = "недостаточно данных"
    lag_unknown = (
        "недостаточно данных "
        "(возможен лаг подтверждения выкупа)"
    )
    if is_missing_value(value):
        return unknown
    try:
        rate = float(value)
    except (TypeError, ValueError):
        return unknown
    if rate < 0:
        return unknown
    if rate > 100.0:
        return lag_unknown if lag_sensitive else unknown
    return format_pct_or_unknown(rate, unknown_label=unknown)


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
    return f"WB ИИ-агент v3 — управленческое резюме: {seller_id} ({run_date})"


def _has_raw_mojibake_signs(text: str) -> bool:
    sample = str(text or "")
    if not sample:
        return False
    if "в†" in sample or "вЂ" in sample:
        return True
    if re.search(r"[РС][^А-Яа-яЁё0-9\s\.,:;!?()\"'«»—–/+%=-]", sample):
        return True
    return False


def _translate_technical_values(text: str) -> str:
    out = str(text or "")
    replacements = [
        (r"(?i)\bfinancial contour is not final\b", "финансовый контур не финализирован"),
        (r"(?i)\bfinancial completeness is low\b", "низкая полнота финансовых данных"),
        (r"(?i)\bterritorial analysis is preview-only\b", "территориальный анализ в режиме предпросмотра"),
        (r"(?i)\bads data is missing\b", "недостаточно данных по рекламе"),
        (r"(?i)\bkeep monitoring\b", "продолжить мониторинг"),
        (r"(?i)\bre-check\b", "перепроверить"),
        (r"(?i)\brecheck\b", "перепроверить"),
        (r"(?i)\bnot[ _-]?confirmed\b", "данные не подтверждены"),
        (r"(?i)\bне подтверждено\b", "данные не подтверждены"),
        (r"(?i)\bunknown\b", "нет данных"),
        (r"(?i)\bpartial\b", "частичный"),
        (r"(?i)\bprovisional\b", "предварительный"),
        (r"(?i)\bhypothesis\b", "гипотеза"),
        (r"(?i)\bstandard\b", "стандартный"),
        (r"(?i)\bpreliminary\b", "предварительный"),
        (r"(?i)\bactionable\b", "доступен"),
        (r"(?i)\bpreview-only\b", "предпросмотр"),
    ]
    for pattern, target in replacements:
        out = re.sub(pattern, target, out)
    out = out.replace("->", "→")
    return out


def _clean_text(value: Any, *, reject_unsafe_raw: bool = True) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if re.fullmatch(r"[?\s\.,:;!/\-]{4,}", raw):
        return ""
    if raw.count("?") >= 6 and not re.search(r"[А-Яа-яЁёA-Za-z0-9]", raw):
        return ""
    if reject_unsafe_raw and _has_raw_mojibake_signs(raw):
        return ""
    text = normalize_pdf_text(raw)
    text = _translate_technical_values(text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    if _has_raw_mojibake_signs(text):
        return ""
    if re.search(r"\?{4,}", text):
        return ""
    if reject_unsafe_raw and re.search(r"\b[A-Za-z]{4,}\b", text):
        return ""
    return text


def _status_ru(value: Any) -> str:
    token = str(value or "").strip().lower().replace("_", " ").replace("-", " ")
    mapping = {
        "ok": "норма",
        "good": "норма",
        "confirmed": "подтверждено",
        "final": "подтверждено",
        "partial": "частичный",
        "provisional": "предварительный",
        "unknown": "нет данных",
        "not confirmed": "данные не подтверждены",
        "notconfirmed": "данные не подтверждены",
        "warning": "внимание",
        "critical": "критично",
        "hypothesis": "гипотеза",
        "standard": "стандартный",
        "preliminary": "предварительный",
    }
    if token in mapping:
        return mapping[token]
    cleaned = _clean_text(token, reject_unsafe_raw=False)
    return cleaned or "нет данных"


def _summary_text(summary: Dict[str, Any], key: str, default: str = "нет данных") -> str:
    display = summary.get("display", {}) if isinstance(summary.get("display"), dict) else {}
    value = display.get(key)
    if value is None:
        value = summary.get(key)
    text = _clean_text(value)
    if text:
        return text
    return default


def _clean_list(items: Any, *, limit: int = 3) -> List[str]:
    if not isinstance(items, list):
        return []
    out: List[str] = []
    for item in items:
        line = _clean_text(item)
        if not line:
            continue
        if re.search(r"\b(?:COMMERCE|FINANCIAL|GUIDANCE|INSIGHTS|RECOMMENDATIONS|CONCLUSION|status|preview-only)\b", line, re.IGNORECASE):
            continue
        if re.search(r"\b[A-Za-z]{4,}\b", line):
            continue
        out.append(line)
        if len(out) >= limit:
            break
    return out


def _funnel_lines(summary: Dict[str, Any]) -> List[str]:
    snapshot = summary.get("funnel_snapshot", {}) if isinstance(summary.get("funnel_snapshot"), dict) else {}
    funnel = snapshot.get("funnel", {}) if isinstance(snapshot.get("funnel"), dict) else {}
    status = snapshot.get("status", {}) if isinstance(snapshot.get("status"), dict) else {}

    views = funnel.get("views", funnel.get("impressions"))
    add_to_cart = funnel.get("add_to_cart", funnel.get("cart_count"))
    orders = funnel.get("orders")
    buyouts = funnel.get("buyouts")
    conversion = funnel.get("view_to_order_conversion", funnel.get("click_to_order_conversion_pct"))
    cart_to_order = funnel.get("cart_to_order", funnel.get("cart_conversion_pct"))
    buyout_rate = funnel.get("buyout_rate", funnel.get("order_to_buyout_conversion_pct"))

    conversion_text = _format_rate_for_email(conversion)
    cart_to_order_text = _format_rate_for_email(cart_to_order)
    buyout_rate_text = _format_rate_for_email(buyout_rate, lag_sensitive=True)

    lines = [
        (
            "Просмотры: "
            + format_int_or_unknown(views, unknown_label="нет данных")
            + ", в корзину: "
            + format_int_or_unknown(add_to_cart, unknown_label="нет данных")
            + ", заказы: "
            + format_int_or_unknown(orders, unknown_label="нет данных")
            + ", выкупы: "
            + format_int_or_unknown(buyouts, unknown_label="нет данных")
        ),
        "Конверсия просмотр → заказ: " + conversion_text,
        (
            "\u0414\u043e\u043f. \u043a\u043e\u043d\u0432\u0435\u0440\u0441\u0438\u0438: \u043a\u043e\u0440\u0437\u0438\u043d\u0430 \u2192 \u0437\u0430\u043a\u0430\u0437 "
            + cart_to_order_text
            + ", \u0437\u0430\u043a\u0430\u0437 \u2192 \u0432\u044b\u043a\u0443\u043f "
            + buyout_rate_text
        ),
        (
            "Статусы: трафик — "
            + _status_ru(status.get("traffic"))
            + ", конверсия — "
            + _status_ru(status.get("conversion"))
            + ", выкуп — "
            + _status_ru(status.get("buyout_stage"))
        ),
    ]
    return [_clean_text(line, reject_unsafe_raw=False) for line in lines if _clean_text(line, reject_unsafe_raw=False)]


def _sku_monitor_lines(summary: Dict[str, Any]) -> List[str]:
    watchlists = summary.get("sku_watchlists", {}) if isinstance(summary.get("sku_watchlists"), dict) else {}
    groups = [
        ("top_growth", "Рост"),
        ("top_risk", "Риск"),
        ("dead_stock", "Неликвид"),
        ("ad_inefficiency", "Реклама"),
        ("conversion_drop", "Конверсия"),
    ]

    watch_data = watchlists.get("watchlists", {}) if isinstance(watchlists.get("watchlists"), dict) else {}
    lines: List[str] = []
    for key, label in groups:
        rows = watch_data.get(key, []) if isinstance(watch_data, dict) else []
        if not isinstance(rows, list):
            continue
        compact: List[str] = []
        for row in rows[:5]:
            if not isinstance(row, dict):
                continue
            sku = _clean_text(row.get("sku"))
            if not sku:
                continue
            score = int(float(row.get("attention_score", 0) or 0))
            compact.append(f"{sku}({score})")
        if compact:
            lines.append(f"{label}: " + ", ".join(compact))
    return lines


def _fallback_insights(summary: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    if not bool(summary.get("orders_count_confirmed", False)):
        lines.append("Данные по заказам пока не подтверждены.")

    margin_value = summary.get("margin_pct")
    if is_missing_value(margin_value):
        lines.append("Маржа: недостаточно данных для расчета.")
    else:
        lines.append("Маржа: " + format_pct_or_unknown(margin_value, unknown_label="недостаточно данных для расчета") + ".")

    if str(summary.get("financial_finality_status") or "").strip().lower() != "final":
        lines.append("Финансовые показатели за день предварительные.")
    return lines[:3]


def _fallback_recommendations(summary: Dict[str, Any]) -> List[str]:
    if not bool(summary.get("orders_count_confirmed", False)):
        return [
            "Дождаться подтверждения заказов и выкупов перед изменением стратегии.",
            "После подтверждения данных повторно оценить маржу и воронку продаж.",
        ]
    return [
        "Сохранить текущую стратегию и контролировать динамику KPI.",
        "Перепроверить показатели маржи и конверсии на следующем цикле.",
    ]


def _fallback_conclusion(summary: Dict[str, Any], run_date: str) -> str:
    parts: List[str] = [f"Операционный день: {run_date}."]
    if not bool(summary.get("orders_count_confirmed", False)):
        parts.append("Данные по заказам пока не подтверждены.")
    margin_value = summary.get("margin_pct")
    if is_missing_value(margin_value):
        parts.append("Маржа: недостаточно данных для расчета.")
    else:
        parts.append("Маржа: " + format_pct_or_unknown(margin_value, unknown_label="недостаточно данных для расчета") + ".")

    snapshot = summary.get("funnel_snapshot", {}) if isinstance(summary.get("funnel_snapshot"), dict) else {}
    funnel = snapshot.get("funnel", {}) if isinstance(snapshot.get("funnel"), dict) else {}
    conversion = funnel.get("view_to_order_conversion", funnel.get("click_to_order_conversion_pct"))
    if is_missing_value(conversion):
        parts.append("Конверсия просмотр → заказ: недостаточно данных.")
    else:
        parts.append("Конверсия просмотр → заказ: " + format_pct_or_unknown(conversion, unknown_label="недостаточно данных") + ".")

    return " ".join(parts)


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

    orders_text = _summary_text(summary, "orders_count", default="недостаточно данных")
    buyouts_text = _summary_text(summary, "buyouts_count", default="недостаточно данных")
    orders_amount_text = _summary_text(summary, "orders_amount", default="недостаточно данных")
    buyouts_amount_text = _summary_text(summary, "buyouts_amount", default="недостаточно данных")
    avg_check_text = _summary_text(summary, "avg_check", default="недостаточно данных")

    revenue_text = _summary_text(summary, "financial_revenue", default="недостаточно данных")
    net_profit_text = _summary_text(summary, "net_profit", default="недостаточно данных")

    margin_value = summary.get("margin_pct")
    if is_missing_value(margin_value):
        margin_text = "недостаточно данных для расчета"
    else:
        margin_text = _summary_text(summary, "margin_pct", default="недостаточно данных для расчета")

    profitability_text = _summary_text(summary, "profitability_pct", default="недостаточно данных для расчета")

    snapshot = summary.get("funnel_snapshot", {}) if isinstance(summary.get("funnel_snapshot"), dict) else {}
    funnel = snapshot.get("funnel", {}) if isinstance(snapshot.get("funnel"), dict) else {}
    view_to_order = funnel.get("view_to_order_conversion", funnel.get("click_to_order_conversion_pct"))
    order_to_buyout = funnel.get("buyout_rate", funnel.get("order_to_buyout_conversion_pct"))
    view_to_order_text = _format_rate_for_email(view_to_order)
    order_to_buyout_text = _format_rate_for_email(order_to_buyout, lag_sensitive=True)

    insights = _clean_list(summary.get("key_insights", []), limit=3)
    if not insights:
        insights = _fallback_insights(summary)

    recommendations = _clean_list(summary.get("recommendations", []), limit=3)
    if not recommendations:
        recommendations = _fallback_recommendations(summary)

    raw_conclusion = _clean_text(summary.get("ai_day_conclusion", ""), reject_unsafe_raw=True)
    conclusion = raw_conclusion or _fallback_conclusion(summary, operational_day)
    if "\n" in conclusion:
        conclusion = next((line.strip() for line in conclusion.splitlines() if line.strip()), conclusion)
    if len(conclusion) > 420:
        conclusion = conclusion[:417].rstrip() + "..."

    lines: List[str] = [
        "Управленческое резюме WB ИИ-агент v3",
        f"Кабинет: {seller_id}",
        f"Дата отчета: {run_date}",
        f"Операционный день: {operational_day}",
        "",
        "КЛЮЧЕВЫЕ ПОКАЗАТЕЛИ",
        f"- Заказы: {orders_text}",
        f"- Выкупы: {buyouts_text}",
        f"- Заказы, сумма: {orders_amount_text}",
        f"- Выкупы, сумма: {buyouts_amount_text}",
        f"- Средний чек: {avg_check_text}",
        f"- Конверсия просмотр → заказ: {view_to_order_text}",
        f"- Конверсия заказ → выкуп: {order_to_buyout_text}",
        "",
        "ФИНАНСОВЫЕ ПОКАЗАТЕЛИ",
        f"- К перечислению продавцу: {revenue_text}",
        f"- Чистая прибыль: {net_profit_text}",
        f"- Маржа: {margin_text}",
        f"- Рентабельность: {profitability_text}",
        "",
        "ГЛАВНЫЕ ВЫВОДЫ",
    ]

    lines.extend(f"- {line}" for line in insights[:3])
    lines.extend(["", "РЕКОМЕНДАЦИИ"])
    lines.extend(f"- {line}" for line in recommendations[:3])
    lines.extend(["", "ВЫВОД ДНЯ", conclusion, "", "Детали в PDF."])

    final_lines: List[str] = []
    seen: set[str] = set()
    for line in lines:
        cleaned = _clean_text(line, reject_unsafe_raw=False)
        if not cleaned and str(line).strip():
            continue
        normalized = cleaned if cleaned else ""
        dedup_key = normalized.strip().lower()
        if dedup_key and dedup_key in seen:
            continue
        if dedup_key:
            seen.add(dedup_key)
        final_lines.append(normalized)

    return "\n".join(final_lines)

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
    transport = send_email_with_pdf(subject=subject, body=body, pdf_path=report_pdf_path)
    print("[mail] send_success")
    return {
        "email_to_masked": email_to_masked,
        "subject": subject,
        "body": body,
        "email_stage": str(transport.get("email_stage") or "send") if isinstance(transport, dict) else "send",
        "email_transport_status": str(transport.get("email_transport_status") or "success") if isinstance(transport, dict) else "success",
        "email_failure_reason_normalized": str(transport.get("email_failure_reason_normalized") or "") if isinstance(transport, dict) else "",
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
    email_stage = "unknown"
    email_transport_status = "skipped"
    email_failure_reason_normalized = ""
    attempted = False
    sent = False
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
            email_stage = str(send_result.get("email_stage") or "send")
            email_transport_status = str(send_result.get("email_transport_status") or "success")
            email_failure_reason_normalized = str(send_result.get("email_failure_reason_normalized") or "")
        attempted = True
        sent = True
        out = apply_job_email_result(
            job=job,
            attempted=attempted,
            sent=sent,
            email_to=email_to_masked,
            error=None,
            email_stage=email_stage,
            email_transport_status=email_transport_status,
            email_failure_reason_normalized=email_failure_reason_normalized,
        )
        out["email_subject"] = email_subject
        out["email_body_text"] = email_body_text
        return out
    except Exception as exc:
        reason = str(exc)
        raw_reason = reason
        if isinstance(exc, EmailDeliveryError):
            email_stage = str(getattr(exc, "email_stage", "unknown") or "unknown")
            email_failure_reason_normalized = str(
                getattr(exc, "failure_reason_normalized", "") or normalize_email_failure_reason(exc)
            )
            raw_reason = str(getattr(exc, "raw_reason", "") or reason)
            attempted = email_stage in {"connect", "login", "send"}
            email_transport_status = "failed"
        elif reason.startswith("Missing required env vars:"):
            email_stage = "unknown"
            email_failure_reason_normalized = "Email configuration missing required environment variables"
            attempted = False
            email_transport_status = "skipped"
        elif reason.startswith("Attachment not found:"):
            email_stage = "unknown"
            email_failure_reason_normalized = "Email attachment is missing"
            attempted = False
            email_transport_status = "skipped"
        else:
            email_stage = "unknown"
            email_failure_reason_normalized = normalize_email_failure_reason(exc)
            attempted = False
            email_transport_status = "failed"

        sent = False
        failure_message = (
            f"EMAIL DELIVERY FAILED [{email_stage}]: {email_failure_reason_normalized} ({raw_reason})"
            if raw_reason
            else f"EMAIL DELIVERY FAILED [{email_stage}]: {email_failure_reason_normalized}"
        )
        print(f"[mail] {failure_message}")
        out = apply_job_email_result(
            job=job,
            attempted=attempted,
            sent=sent,
            email_to=email_to_masked,
            error=failure_message,
            email_stage=email_stage,
            email_transport_status=email_transport_status,
            email_failure_reason_normalized=email_failure_reason_normalized,
        )
        if email_subject:
            out["email_subject"] = email_subject
        if email_body_text:
            out["email_body_text"] = email_body_text
        return out
