from __future__ import annotations

import re
from typing import Any, Dict, List

from ..pdf_render import normalize_pdf_text
from ..pipeline.daily_stage_support import sync_from_entry
from .email_summary_builder import build_email_summary
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


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_mojibake_text(text: str) -> bool:
    sample = str(text or "")
    if not sample:
        return False
    if "в†" in sample or "вЂ" in sample:
        return True
    if re.search(r"[РС][^А-Яа-яЁё0-9\s\.,:;!?()\"'«»—–/+%=-]", sample):
        return True
    return False


def _translate_technical_words(text: str) -> str:
    normalized = str(text or "")
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
    ]
    for pattern, target in replacements:
        normalized = re.sub(pattern, target, normalized)
    normalized = normalized.replace("->", "→")
    return normalized


def _clean_text(value: Any, *, reject_unsafe_raw: bool = True) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if re.fullmatch(r"[?\s\.,:;!/\-]{4,}", raw):
        return ""
    if raw.count("?") >= 6 and not re.search(r"[А-Яа-яЁёA-Za-z0-9]", raw):
        return ""
    if reject_unsafe_raw and _is_mojibake_text(raw):
        return ""
    text = normalize_pdf_text(raw)
    text = _translate_technical_words(text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    if _is_mojibake_text(text):
        return ""
    if re.search(r"\?{4,}", text):
        return ""
    if reject_unsafe_raw and re.search(r"\b[A-Za-z]{4,}\b", text):
        return ""
    return text


def _clean_lines(items: Any, *, limit: int = 6) -> List[str]:
    if not isinstance(items, list):
        return []
    out: List[str] = []
    for item in items:
        line = _clean_text(item)
        if not line:
            continue
        if re.search(r"\b(?:COMMERCE|FINANCIAL|INSIGHTS|RECOMMENDATIONS|CONCLUSION|statuses|preview-only)\b", line, re.IGNORECASE):
            continue
        if re.search(r"\?{4,}", line):
            continue
        if re.search(r"\b[A-Za-z]{4,}\b", line):
            continue
        out.append(line)
        if len(out) >= limit:
            break
    return out


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
    }
    if token in mapping:
        return mapping[token]
    cleaned = _clean_text(token)
    return cleaned or "нет данных"


def _top_watchlist_rows(sku_watchlists: Dict[str, Any], group: str, limit: int = 5) -> List[Dict[str, Any]]:
    watchlists = sku_watchlists.get("watchlists", {}) if isinstance(sku_watchlists, dict) else {}
    rows = watchlists.get(group, []) if isinstance(watchlists, dict) else []
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)][: max(0, int(limit))]


def _build_funnel_email_brief(cabinet_funnel: Dict[str, Any], funnel_alerts: Dict[str, Any]) -> List[str]:
    funnel = cabinet_funnel.get("funnel", {}) if isinstance(cabinet_funnel, dict) else {}
    status = cabinet_funnel.get("status", {}) if isinstance(cabinet_funnel, dict) else {}
    if not isinstance(funnel, dict):
        funnel = {}
    if not isinstance(status, dict):
        status = {}

    views = funnel.get("views", funnel.get("impressions"))
    add_to_cart = funnel.get("add_to_cart", funnel.get("cart_count"))
    orders = funnel.get("orders")
    buyouts = funnel.get("buyouts")
    view_to_order = funnel.get("view_to_order_conversion", funnel.get("click_to_order_conversion_pct"))
    cart_to_order = funnel.get("cart_to_order", funnel.get("cart_conversion_pct"))
    buyout_rate = funnel.get("buyout_rate", funnel.get("order_to_buyout_conversion_pct"))
    cpo = funnel.get("cpo", funnel.get("CPO"))

    cpo_value = _safe_float(cpo)
    cpo_text = f"{cpo_value:.2f}" if cpo_value is not None else "недостаточно данных"

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
        (
            "\u041a\u043e\u043d\u0432\u0435\u0440\u0441\u0438\u044f \u043f\u0440\u043e\u0441\u043c\u043e\u0442\u0440 \u2192 \u0437\u0430\u043a\u0430\u0437: "
            + _format_rate_for_email(view_to_order)
            + ", \u043a\u043e\u0440\u0437\u0438\u043d\u0430 \u2192 \u0437\u0430\u043a\u0430\u0437: "
            + _format_rate_for_email(cart_to_order)
            + ", \u0437\u0430\u043a\u0430\u0437 \u2192 \u0432\u044b\u043a\u0443\u043f: "
            + _format_rate_for_email(buyout_rate, lag_sensitive=True)
            + ", CPO: "
            + cpo_text
        ),
        (
            "Статусы воронки: трафик — "
            + _status_ru(status.get("traffic"))
            + ", конверсия — "
            + _status_ru(status.get("conversion"))
            + ", выкуп — "
            + _status_ru(status.get("buyout_stage"))
        ),
    ]

    if isinstance(funnel_alerts, dict) and isinstance(funnel_alerts.get("summary"), dict):
        summary = funnel_alerts.get("summary", {})
        lines.append(
            "Сигналы: предупреждений="
            + str(int(summary.get("warning_count", 0) or 0))
            + ", критических="
            + str(int(summary.get("critical_count", 0) or 0))
        )

    return [_clean_text(line, reject_unsafe_raw=False) for line in lines if _clean_text(line, reject_unsafe_raw=False)]


def _build_sku_monitor_email_brief(sku_watchlists: Dict[str, Any]) -> List[str]:
    groups = [
        ("top_growth", "Рост"),
        ("top_risk", "Риск"),
        ("dead_stock", "Неликвид"),
        ("ad_inefficiency", "Реклама"),
        ("conversion_drop", "Конверсия"),
    ]
    lines: List[str] = []
    for key, label in groups:
        rows = _top_watchlist_rows(sku_watchlists, key, limit=5)
        if not rows:
            continue
        compact: List[str] = []
        for row in rows:
            sku = _clean_text(row.get("sku"), reject_unsafe_raw=True)
            if not sku:
                continue
            score = int(float(row.get("attention_score", 0) or 0))
            compact.append(f"{sku}({score})")
        if compact:
            lines.append(f"{label}: " + ", ".join(compact[:5]))
    return lines


def _extend_ai_conclusion_with_monitoring(base_text: str, funnel_lines: List[str], sku_lines: List[str]) -> str:
    chunks = [_clean_text(base_text)]
    if funnel_lines:
        chunks.append("ВОРОНКА ПРОДАЖ:")
        chunks.extend(f"- {line}" for line in funnel_lines[:3])
    if sku_lines:
        chunks.append("МОНИТОРИНГ ТОВАРОВ:")
        chunks.extend(f"- {line}" for line in sku_lines[:5])
    return "\n".join([line for line in chunks if str(line).strip()])


def _resolve_preliminary_ai_reasons(
    *,
    financial_finality_status: str,
    financial_completeness_pct: float,
    territorial_analysis_mode: str,
    territorial_recommendation_status: str,
    territorial_actionable_enabled: bool,
    territorial_suppressed_due_to_data_quality: bool,
    ads_analysis_enabled: bool,
    ads_rows_count: int,
) -> List[str]:
    reasons: List[str] = []
    if str(financial_finality_status or "").strip().lower() != "final":
        reasons.append("финансовый контур не финализирован")
    if float(financial_completeness_pct) < 80.0:
        reasons.append("низкая полнота финансовых данных")
    if (
        str(territorial_analysis_mode or "").strip().lower() in {"", "preview", "disabled"}
        or str(territorial_recommendation_status or "").strip().lower() not in {"actionable"}
        or not bool(territorial_actionable_enabled)
        or bool(territorial_suppressed_due_to_data_quality)
    ):
        reasons.append("территориальный анализ в ограниченном режиме")
    if not bool(ads_analysis_enabled) or int(ads_rows_count) <= 0:
        reasons.append("недостаточно данных по рекламе")
    return reasons


def _soften_recommendations_for_preliminary(recommendations: List[str], reasons: List[str]) -> List[str]:
    reasons_text = "; ".join([_clean_text(item, reject_unsafe_raw=False) for item in reasons if _clean_text(item, reject_unsafe_raw=False)])
    reasons_text = reasons_text or "ограниченное качество данных"
    softened: List[str] = [
        "Рекомендации ниже являются гипотезами до подтверждения данных (" + reasons_text + ")."
    ]
    for item in recommendations:
        text = _clean_text(item)
        if not text:
            continue
        softened.append("Гипотеза: " + text.replace("LIQUIDATE", "перепроверить"))
        if len(softened) >= 4:
            break
    if len(softened) == 1:
        softened.append("Гипотеза: сохранить текущий курс и перепроверить показатели на следующем цикле.")
    return softened


def _prepend_preliminary_conclusion(base_text: str, reasons: List[str]) -> str:
    reasons_text = "; ".join([_clean_text(item, reject_unsafe_raw=False) for item in reasons if _clean_text(item, reject_unsafe_raw=False)])
    reasons_text = reasons_text or "ограниченное качество данных"
    prefix = "Предварительный вывод: высокие по влиянию действия требуют подтверждения (" + reasons_text + ")."
    text = _clean_text(base_text)
    if not text:
        return prefix
    if text.startswith("Предварительный вывод:"):
        return text
    return prefix + "\n" + text


def _build_ai_conclusion_fallback(
    *,
    run_date: str,
    daily_kpi: Dict[str, Any],
    render_kpi: Dict[str, Any],
    cabinet_funnel: Dict[str, Any],
    financial_finality_status: str,
) -> str:
    orders_confirmed = bool(daily_kpi.get("orders_count_confirmed", False))
    orders_value = render_kpi.get("orders_count", daily_kpi.get("daily_orders_count"))
    margin_value = render_kpi.get("margin_pct")
    funnel = cabinet_funnel.get("funnel", {}) if isinstance(cabinet_funnel, dict) else {}
    if not isinstance(funnel, dict):
        funnel = {}
    conversion_value = funnel.get("view_to_order_conversion", funnel.get("click_to_order_conversion_pct"))

    parts: List[str] = [f"Операционный день: {run_date}."]
    if not orders_confirmed:
        parts.append("Данные по заказам пока не подтверждены.")
    else:
        parts.append("Заказы за день: " + format_int_or_unknown(orders_value, unknown_label="нет данных") + ".")

    if is_missing_value(margin_value):
        parts.append("Маржа: недостаточно данных для расчета.")
    else:
        parts.append("Маржа: " + format_pct_or_unknown(margin_value, unknown_label="недостаточно данных для расчета") + ".")

    if is_missing_value(conversion_value):
        parts.append("Конверсия просмотр → заказ: недостаточно данных.")
    else:
        parts.append("Конверсия просмотр → заказ: " + format_pct_or_unknown(conversion_value, unknown_label="недостаточно данных") + ".")

    if str(financial_finality_status or "").strip().lower() != "final":
        parts.append("Финансовые показатели носят предварительный характер.")

    return " ".join(parts)


def run_daily_email_stage(payload: Dict[str, Any]) -> Dict[str, Any]:
    sync_from_entry(globals())

    data: Dict[str, Any] = dict(payload or {})
    source_mode = str(data.get("source_mode") or "").strip().lower()
    data_mode = str(data.get("data_mode") or "").strip().lower()
    if not data_mode:
        data_mode = "api" if (source_mode == "wb_api" and not bool(data.get("local_financial_fallback_used", False))) else "raw_reports_fallback"
    non_api_mode = bool(data.get("non_api_mode", data_mode != "api"))
    non_api_label = "недостаточно данных (non-API mode)"
    non_api_notice = (
        "Отчет собран в ограниченном режиме по raw-отчетам WB, "
        "часть метрик может быть недоступна до подключения API"
    )
    job = data.get("job", {})
    if not isinstance(job, dict):
        job = {}
    daily_kpi = data.get("daily_kpi", {})
    if not isinstance(daily_kpi, dict):
        daily_kpi = {}
    ads_summary = data.get("ads_summary", {})
    if not isinstance(ads_summary, dict):
        ads_summary = {}
    decisions_summary = data.get("decisions_summary", {})
    if not isinstance(decisions_summary, dict):
        decisions_summary = {}
    logistics_summary = data.get("logistics_summary", {})
    if not isinstance(logistics_summary, dict):
        logistics_summary = {}
    totals = data.get("totals", {})
    if not isinstance(totals, dict):
        totals = {}
    data_quality = data.get("data_quality", {})
    if not isinstance(data_quality, dict):
        data_quality = {}
    event_date_model = data.get("event_date_model", {})
    if not isinstance(event_date_model, dict):
        event_date_model = {}
    order_kpi = data.get("order_kpi", {})
    if not isinstance(order_kpi, dict):
        order_kpi = {}
    buyout_kpi = data.get("buyout_kpi", {})
    if not isinstance(buyout_kpi, dict):
        buyout_kpi = {}
    financial_kpi = data.get("financial_kpi", {})
    if not isinstance(financial_kpi, dict):
        financial_kpi = {}
    daily_status_matrix = data.get("daily_status_matrix", {})
    if not isinstance(daily_status_matrix, dict):
        daily_status_matrix = {}
    render_kpi = data.get("render_kpi", {})
    if not isinstance(render_kpi, dict):
        render_kpi = {}
    cabinet_funnel = data.get("cabinet_funnel", {})
    if not isinstance(cabinet_funnel, dict):
        cabinet_funnel = {}
    funnel_alerts = data.get("funnel_alerts", {})
    if not isinstance(funnel_alerts, dict):
        funnel_alerts = {}
    sku_watchlists = data.get("sku_watchlists", {})
    if not isinstance(sku_watchlists, dict):
        sku_watchlists = {}
    sku_alerts = data.get("sku_alerts", {})
    if not isinstance(sku_alerts, dict):
        sku_alerts = {}
    report_guardrails = data.get("report_guardrails", {})
    if not isinstance(report_guardrails, dict):
        report_guardrails = {}

    decision_groups: Dict[str, List[Dict[str, Any]]] = {}
    if isinstance(decisions_summary, dict):
        for key in ("scale", "fix", "watch", "liquidate"):
            rows = decisions_summary.get(key, [])
            decision_groups[key] = [x for x in rows if isinstance(x, dict)] if isinstance(rows, list) else []
    else:
        decision_groups = {"scale": [], "fix": [], "watch": [], "liquidate": []}

    short_recommendations_raw = _build_short_recommendations(
        decision_groups=decision_groups,
        logistics_summary=logistics_summary if isinstance(logistics_summary, dict) else {},
    )
    short_recommendations = _clean_lines(short_recommendations_raw, limit=5)

    base_ai_day_conclusion_raw = _build_ai_day_conclusion(
        run_date=str(data.get("run_date") or ""),
        totals=totals if isinstance(totals, dict) else {},
        daily_kpi=daily_kpi if isinstance(daily_kpi, dict) else {},
        data_quality=data_quality if isinstance(data_quality, dict) else {},
        key_insights=data.get("key_insights", []),
        recommendations=short_recommendations,
        event_date_model=event_date_model if isinstance(event_date_model, dict) else {},
        order_kpi=order_kpi if isinstance(order_kpi, dict) else {},
        buyout_kpi=buyout_kpi if isinstance(buyout_kpi, dict) else {},
        financial_kpi=financial_kpi if isinstance(financial_kpi, dict) else {},
        daily_status_matrix=daily_status_matrix if isinstance(daily_status_matrix, dict) else {},
    )
    base_ai_day_conclusion = _clean_text(base_ai_day_conclusion_raw)

    funnel_brief_lines = _build_funnel_email_brief(
        cabinet_funnel=cabinet_funnel if isinstance(cabinet_funnel, dict) else {},
        funnel_alerts=funnel_alerts if isinstance(funnel_alerts, dict) else {},
    )
    sku_monitor_brief_lines = _build_sku_monitor_email_brief(
        sku_watchlists=sku_watchlists if isinstance(sku_watchlists, dict) else {},
    )

    ai_day_conclusion_email = _extend_ai_conclusion_with_monitoring(
        base_text=base_ai_day_conclusion,
        funnel_lines=funnel_brief_lines,
        sku_lines=sku_monitor_brief_lines,
    )

    key_insights_enhanced = _clean_lines(data.get("key_insights", []), limit=6)

    sku_attribution_status = str(
        data_quality.get("sku_attribution_status", report_guardrails.get("sku_attribution_status", "ok")) or "ok"
    ).strip().lower()
    financial_finality_status = str(
        data_quality.get("financial_finality_status", report_guardrails.get("financial_finality_status", "unavailable"))
        or "unavailable"
    ).strip().lower()
    financial_completeness_pct = (
        _safe_float(
            data.get(
                "financial_completeness_pct",
                financial_kpi.get(
                    "completeness_pct",
                    data_quality.get("financial_completeness_pct", 0.0),
                ),
            )
        )
        or 0.0
    )

    territorial_analysis_mode = str(
        data_quality.get("territorial_analysis_mode", report_guardrails.get("territorial_analysis_mode", "disabled")) or "disabled"
    ).strip().lower()
    territorial_recommendation_status = str(
        data_quality.get(
            "territorial_recommendation_status",
            report_guardrails.get("territorial_recommendation_status", "blocked_by_data"),
        )
        or "blocked_by_data"
    ).strip().lower()
    territorial_actionable_enabled = bool(report_guardrails.get("territorial_actionable_enabled", False))
    territorial_suppressed_due_to_data_quality = bool(data_quality.get("territorial_suppressed_due_to_data_quality", False))
    ads_analysis_enabled = bool(report_guardrails.get("ads_analysis_enabled", True))
    ads_rows_count = int(data.get("ads_rows_count", 0) or 0)

    preliminary_ai_reasons = _resolve_preliminary_ai_reasons(
        financial_finality_status=financial_finality_status,
        financial_completeness_pct=float(financial_completeness_pct),
        territorial_analysis_mode=territorial_analysis_mode,
        territorial_recommendation_status=territorial_recommendation_status,
        territorial_actionable_enabled=territorial_actionable_enabled,
        territorial_suppressed_due_to_data_quality=territorial_suppressed_due_to_data_quality,
        ads_analysis_enabled=ads_analysis_enabled,
        ads_rows_count=ads_rows_count,
    )
    preliminary_ai_mode = bool(preliminary_ai_reasons)

    if preliminary_ai_mode:
        short_recommendations = _soften_recommendations_for_preliminary(short_recommendations, preliminary_ai_reasons)
        ai_day_conclusion_email = _prepend_preliminary_conclusion(ai_day_conclusion_email, preliminary_ai_reasons)
        key_insights_enhanced.insert(0, "Рекомендации переведены в режим гипотез до подтверждения качества данных.")

    if sku_attribution_status == "broken":
        key_insights_enhanced = [
            str(line)
            for line in key_insights_enhanced
            if str(line).strip()
            and "unassigned" not in str(line).lower()
            and "territorial" not in str(line).lower()
        ]
        key_insights_enhanced.insert(
            0,
            "Технический статус: атрибуция SKU нарушена, поэтому часть SKU-выводов временно скрыта.",
        )

    if financial_finality_status != "final":
        key_insights_enhanced.insert(
            0,
            "Финансовые показатели за день предварительные и требуют повторной проверки после финализации данных.",
        )

    if sku_monitor_brief_lines:
        key_insights_enhanced.append("Мониторинг товаров сформирован по группам: рост, риск, неликвид, реклама, конверсия.")
    if funnel_brief_lines and not non_api_mode:
        key_insights_enhanced.append("Воронка продаж включена в управленческое резюме.")

    if non_api_mode:
        key_insights_enhanced.insert(0, non_api_notice + ".")
        short_recommendations.insert(
            0,
            "Фокусироваться только на подтвержденных финансовых событиях до подключения API.",
        )

    key_insights_enhanced = _clean_lines(key_insights_enhanced, limit=6)
    short_recommendations = _clean_lines(short_recommendations, limit=5)

    if not key_insights_enhanced:
        key_insights_enhanced = ["Ключевые выводы сформированы на основе подтвержденных данных текущего цикла."]
    if not short_recommendations:
        short_recommendations = ["Сохранить текущую стратегию и перепроверить KPI на следующем цикле."]

    if not _clean_text(ai_day_conclusion_email):
        ai_day_conclusion_email = _build_ai_conclusion_fallback(
            run_date=str(data.get("run_date") or ""),
            daily_kpi=daily_kpi,
            render_kpi=render_kpi,
            cabinet_funnel=cabinet_funnel,
            financial_finality_status=financial_finality_status,
        )

    net_profit_for_summary = data.get("net_profit")
    margin_pct_for_summary = data.get("margin_pct_total")
    profitability_pct_for_summary = data.get("profitability_pct_total")
    daily_orders_count_for_summary = render_kpi.get("orders_count", data.get("daily_orders_count"))
    avg_check_for_summary = render_kpi.get("avg_check", data.get("avg_check"))
    daily_orders_amount_for_summary = render_kpi.get("orders_amount", data.get("daily_orders_amount"))
    daily_buyouts_count_for_summary = render_kpi.get("buyouts_count", data.get("daily_buyouts_count"))
    daily_buyouts_amount_for_summary = render_kpi.get("buyouts_amount", data.get("daily_buyouts_amount"))
    ads_summary_for_email = ads_summary if isinstance(ads_summary, dict) else {}
    ads_rows_for_summary = int(data.get("ads_rows_count", 0) or 0)
    ads_impressions_for_summary = int(data.get("ads_impressions", 0) or 0)
    ads_clicks_for_summary = int(data.get("ads_clicks", 0) or 0)
    ads_orders_for_summary = int(data.get("ads_orders", 0) or 0)
    ads_loaded_from_file_for_summary = bool(data.get("ads_loaded_from_file", False))
    ads_source_file_for_summary = str(data.get("ads_source_file") or "")
    ads_attribution_quality_for_summary = str(data.get("ads_attribution_quality") or "unknown")
    funnel_snapshot_for_summary = cabinet_funnel if isinstance(cabinet_funnel, dict) else {}

    if non_api_mode:
        daily_orders_count_for_summary = None
        avg_check_for_summary = None
        daily_orders_amount_for_summary = None
        daily_buyouts_count_for_summary = None
        daily_buyouts_amount_for_summary = None
        margin_pct_for_summary = None
        profitability_pct_for_summary = None
        ads_summary_for_email = {}
        ads_rows_for_summary = 0
        ads_impressions_for_summary = 0
        ads_clicks_for_summary = 0
        ads_orders_for_summary = 0
        ads_loaded_from_file_for_summary = False
        ads_source_file_for_summary = ""
        ads_attribution_quality_for_summary = "insufficient_data"

        if (financial_finality_status != "final") or (float(financial_completeness_pct) < 95.0):
            net_profit_for_summary = None

        if isinstance(funnel_snapshot_for_summary, dict):
            funnel_snapshot_for_summary = dict(funnel_snapshot_for_summary)
            funnel_payload = funnel_snapshot_for_summary.get("funnel", {})
            if isinstance(funnel_payload, dict):
                funnel_payload = dict(funnel_payload)
                funnel_payload["view_to_order_conversion"] = None
                funnel_payload["click_to_order_conversion_pct"] = None
                funnel_payload["buyout_rate"] = None
                funnel_payload["order_to_buyout_conversion_pct"] = None
                funnel_snapshot_for_summary["funnel"] = funnel_payload
            status_payload = funnel_snapshot_for_summary.get("status", {})
            if isinstance(status_payload, dict):
                status_payload = dict(status_payload)
                status_payload["traffic"] = "insufficient_data"
                status_payload["conversion"] = "insufficient_data"
                status_payload["buyout_stage"] = "insufficient_data"
                funnel_snapshot_for_summary["status"] = status_payload

    email_summary_payload = build_email_summary(
        daily_kpi=daily_kpi if isinstance(daily_kpi, dict) else {},
        ads_summary=ads_summary_for_email,
        net_profit=net_profit_for_summary,
        gross_profit=data.get("gross_profit_total"),
        cost_price=data.get("cost_price_total"),
        wb_commission=data.get("wb_commission"),
        logistics=data.get("logistics_total"),
        storage=data.get("storage_total"),
        penalties=data.get("penalties_total"),
        deductions=data.get("deductions_total"),
        ads_spend_total=data.get("ads_spend_total"),
        margin_pct=margin_pct_for_summary,
        profitability_pct=profitability_pct_for_summary,
        financial_completeness_pct=float(data.get("financial_completeness_pct", 0.0) or 0.0),
        financial_partial=bool(data.get("financial_partial", False)),
        ads_rows=ads_rows_for_summary,
        ads_impressions=ads_impressions_for_summary,
        ads_clicks=ads_clicks_for_summary,
        ads_orders=ads_orders_for_summary,
        ads_loaded_from_file=ads_loaded_from_file_for_summary,
        ads_source_file=ads_source_file_for_summary,
        ads_attribution_quality=ads_attribution_quality_for_summary,
        daily_revenue=render_kpi.get("buyouts_amount", data.get("daily_buyouts_amount")),
        financial_revenue=render_kpi.get("revenue", data.get("revenue_total")),
        daily_orders_count=daily_orders_count_for_summary,
        avg_check=avg_check_for_summary,
        daily_orders_amount=daily_orders_amount_for_summary,
        daily_buyouts_count=daily_buyouts_count_for_summary,
        daily_buyouts_amount=daily_buyouts_amount_for_summary,
        key_insights=key_insights_enhanced,
        recommendations=short_recommendations,
        ai_day_conclusion=ai_day_conclusion_email,
        event_date_model=event_date_model if isinstance(event_date_model, dict) else {},
        order_kpi=order_kpi if isinstance(order_kpi, dict) else {},
        buyout_kpi=buyout_kpi if isinstance(buyout_kpi, dict) else {},
        financial_kpi=financial_kpi if isinstance(financial_kpi, dict) else {},
        daily_status_matrix=daily_status_matrix if isinstance(daily_status_matrix, dict) else {},
        render_kpi=render_kpi if isinstance(render_kpi, dict) else {},
        funnel_snapshot=funnel_snapshot_for_summary,
        sku_watchlists=sku_watchlists if isinstance(sku_watchlists, dict) else {},
        sku_alerts=sku_alerts if isinstance(sku_alerts, dict) else {},
        sku_attribution_status=sku_attribution_status,
        financial_finality_status=financial_finality_status,
        report_reliability_level=str(
            data_quality.get("report_reliability_level", report_guardrails.get("report_reliability_level", "medium"))
            or "medium"
        ),
    )

    email_summary_payload["ai_guidance_mode"] = "preliminary" if preliminary_ai_mode else "standard"
    email_summary_payload["ai_guardrail_reasons"] = [_clean_text(item) for item in preliminary_ai_reasons if _clean_text(item)]
    email_summary_payload["data_mode"] = data_mode
    email_summary_payload["non_api_mode"] = non_api_mode
    email_summary_payload["non_api_notice"] = non_api_notice if non_api_mode else ""

    if non_api_mode:
        display_payload = email_summary_payload.get("display", {})
        if not isinstance(display_payload, dict):
            display_payload = {}
        for key in ("orders_count", "buyouts_count", "orders_amount", "buyouts_amount", "avg_check", "margin_pct", "profitability_pct"):
            display_payload[key] = non_api_label
        if (financial_finality_status != "final") or (float(financial_completeness_pct) < 95.0):
            display_payload["net_profit"] = non_api_label
        email_summary_payload["display"] = display_payload

    job["email_summary"] = email_summary_payload

    data.update(
        {
            "job": job,
            "decision_groups": decision_groups,
            "short_recommendations": short_recommendations,
            "ai_day_conclusion": base_ai_day_conclusion,
            "funnel_brief_lines": funnel_brief_lines,
            "sku_monitor_brief_lines": sku_monitor_brief_lines,
        }
    )
    return data





