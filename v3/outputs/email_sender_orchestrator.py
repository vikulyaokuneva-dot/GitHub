from __future__ import annotations

import os
import re
from typing import Any, Callable, Dict, List

from src.mailer_yandex import send_email_with_pdf

from ..pdf_render import normalize_pdf_text
from ..pipeline.job_builder import apply_job_email_result
from .render_policy import format_int_or_unknown, format_pct_or_unknown, is_missing_value


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
    if reject_unsafe_raw and _has_raw_mojibake_signs(raw):
        return ""
    text = normalize_pdf_text(raw)
    text = _translate_technical_values(text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    if _has_raw_mojibake_signs(text):
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

    conversion_text = (
        "недостаточно данных"
        if is_missing_value(conversion)
        else format_pct_or_unknown(conversion, unknown_label="недостаточно данных")
    )

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
            "Доп. конверсии: корзина → заказ "
            + format_pct_or_unknown(cart_to_order, unknown_label="недостаточно данных")
            + ", заказ → выкуп "
            + format_pct_or_unknown(buyout_rate, unknown_label="недостаточно данных")
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

    financial_finality_status = _status_ru(summary.get("financial_finality_status") or "нет данных")

    ai_mode = _status_ru(summary.get("ai_guidance_mode") or "standard")
    raw_reasons = summary.get("ai_guardrail_reasons", []) if isinstance(summary.get("ai_guardrail_reasons"), list) else []
    reasons = [_clean_text(item) for item in raw_reasons if _clean_text(item)]

    orders_text = _summary_text(summary, "orders_count", default="нет данных")
    buyouts_text = _summary_text(summary, "buyouts_count", default="нет данных")
    orders_amount_text = _summary_text(summary, "orders_amount", default="нет данных")
    buyouts_amount_text = _summary_text(summary, "buyouts_amount", default="нет данных")
    avg_check_text = _summary_text(summary, "avg_check", default="нет данных")

    revenue_text = _summary_text(summary, "financial_revenue", default="нет данных")
    net_profit_text = _summary_text(summary, "net_profit", default="нет данных")

    margin_value = summary.get("margin_pct")
    if is_missing_value(margin_value):
        margin_text = "недостаточно данных для расчета"
    else:
        margin_text = _summary_text(summary, "margin_pct", default="недостаточно данных для расчета")

    profitability_text = _summary_text(summary, "profitability_pct", default="недостаточно данных для расчета")

    funnel_lines = _funnel_lines(summary)
    sku_monitor_lines = _sku_monitor_lines(summary)

    insights = _clean_list(summary.get("key_insights", []), limit=3)
    if not insights:
        insights = _fallback_insights(summary)

    recommendations = _clean_list(summary.get("recommendations", []), limit=3)
    if not recommendations:
        recommendations = _fallback_recommendations(summary)

    raw_conclusion = _clean_text(summary.get("ai_day_conclusion", ""), reject_unsafe_raw=True)
    conclusion = raw_conclusion or _fallback_conclusion(summary, operational_day)

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
        "",
        "ФИНАНСОВЫЕ ПОКАЗАТЕЛИ",
        f"- Выручка: {revenue_text}",
        f"- Чистая прибыль: {net_profit_text}",
        f"- Маржа: {margin_text}",
        f"- Рентабельность: {profitability_text}",
        f"- Статус финансового контура: {financial_finality_status}",
        "",
        "РЕЖИМ РЕКОМЕНДАЦИЙ ИИ",
        f"- Режим: {ai_mode}",
        ("- Основания: " + "; ".join(reasons)) if reasons else "- Основания: нет данных",
        "",
        "ВОРОНКА ПРОДАЖ",
    ]

    if funnel_lines:
        lines.extend(f"- {line}" for line in funnel_lines[:4])
    else:
        lines.append("- Конверсия просмотр → заказ: недостаточно данных")

    lines.extend(["", "МОНИТОРИНГ ТОВАРОВ"])
    if sku_monitor_lines:
        lines.extend(f"- {line}" for line in sku_monitor_lines[:5])
    else:
        lines.append("- Нет критичных изменений по SKU.")

    lines.extend(["", "КЛЮЧЕВЫЕ ВЫВОДЫ"])
    lines.extend(f"- {line}" for line in insights[:3])

    lines.extend(["", "РЕКОМЕНДАЦИИ"])
    lines.extend(f"- {line}" for line in recommendations[:3])

    lines.extend(["", "ВЫВОД ИИ ЗА ДЕНЬ", conclusion])

    final_lines: List[str] = []
    for line in lines:
        cleaned = _clean_text(line, reject_unsafe_raw=False)
        if not cleaned and str(line).strip():
            continue
        final_lines.append(cleaned if cleaned else "")

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


