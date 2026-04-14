from __future__ import annotations

import os
import re
from typing import Any, Dict, List

from ..pdf_render import normalize_pdf_text, repair_mojibake, write_daily_bi_pdf
from ..pipeline.daily_stage_support import sync_from_entry
from .email_sender_orchestrator import build_daily_email_body, build_daily_email_subject
from .render_policy import (
    SECTION_STATE_COMPACT_NOTE,
    SECTION_STATE_FULL,
    SECTION_STATE_HIDDEN,
    SECTION_STATE_PARTIAL,
    build_kpi_display_payload,
    build_section_display_state,
    format_int_or_unknown,
    format_money_or_unknown,
    format_pct_or_unknown,
    is_missing_value,
    normalize_section_state,
)


def _safe_float_local(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _funnel_delta(funnel_alerts: Dict[str, Any], metric: str, field: str) -> float | None:
    if not isinstance(funnel_alerts, dict):
        return None
    for container_key in ("metrics", "comparisons", "deltas"):
        container = funnel_alerts.get(container_key, {})
        if not isinstance(container, dict):
            continue
        payload = container.get(metric, {})
        if isinstance(payload, dict):
            value = _safe_float_local(payload.get(field))
            if value is not None:
                return value
    alerts = funnel_alerts.get("alerts", [])
    if isinstance(alerts, list):
        for row in alerts:
            if not isinstance(row, dict):
                continue
            row_metric = str(row.get("metric") or row.get("type") or "").strip().lower()
            if metric.lower() not in row_metric:
                continue
            value = _safe_float_local(row.get(field))
            if value is not None:
                return value
    return None


def _funnel_alert_summary(funnel_alerts: Dict[str, Any]) -> str:
    if not isinstance(funnel_alerts, dict) or not funnel_alerts:
        return "РЅРµРёР·РІРµСЃС‚РЅРѕ"
    summary = funnel_alerts.get("summary", {})
    if isinstance(summary, dict):
        warning_count = int(summary.get("warning_count", 0) or 0)
        critical_count = int(summary.get("critical_count", 0) or 0)
        return f"РїСЂРµРґСѓРїСЂРµР¶РґРµРЅРёР№={warning_count}, РєСЂРёС‚РёС‡РµСЃРєРёС…={critical_count}"
    alerts = funnel_alerts.get("alerts", [])
    if not isinstance(alerts, list):
        return "РЅРµРёР·РІРµСЃС‚РЅРѕ"
    warning_count = 0
    critical_count = 0
    for row in alerts:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "").strip().lower()
        if status == "warning":
            warning_count += 1
        elif status == "critical":
            critical_count += 1
    return f"РїСЂРµРґСѓРїСЂРµР¶РґРµРЅРёР№={warning_count}, РєСЂРёС‚РёС‡РµСЃРєРёС…={critical_count}"


def _bool_ru(value: bool) -> str:
    return "РґР°" if bool(value) else "РЅРµС‚"


def _contour_status_ru(value: str) -> str:
    token = str(value or "").strip().lower()
    mapping = {
        "confirmed": "РїРѕРґС‚РІРµСЂР¶РґРµРЅ",
        "final": "РїРѕРґС‚РІРµСЂР¶РґРµРЅ",
        "ok": "РїРѕРґС‚РІРµСЂР¶РґРµРЅ",
        "partial": "С‡Р°СЃС‚РёС‡РЅС‹Р№",
        "preview": "С‡Р°СЃС‚РёС‡РЅС‹Р№",
        "degraded": "С‡Р°СЃС‚РёС‡РЅС‹Р№",
        "provisional": "С‡Р°СЃС‚РёС‡РЅС‹Р№",
        "missing": "РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚",
        "unavailable": "РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚",
        "not_confirmed": "РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚",
        "disabled": "РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚",
        "unknown": "РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚",
    }
    return mapping.get(token, token or "РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚")


def _reliability_ru(value: str) -> str:
    token = str(value or "").strip().lower()
    return {"high": "РІС‹СЃРѕРєР°СЏ", "medium": "СЃСЂРµРґРЅСЏСЏ", "low": "РЅРёР·РєР°СЏ"}.get(token, token or "РЅРёР·РєР°СЏ")


def _matrix_status_ru(value: str) -> str:
    token = str(value or "").strip().lower()
    mapping = {
        "confirmed": "РїРѕРґС‚РІРµСЂР¶РґРµРЅ",
        "partial": "С‡Р°СЃС‚РёС‡РЅС‹Р№",
        "not_confirmed": "РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚",
        "missing": "РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚",
        "unavailable": "РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚",
        "unknown": "РЅРµРёР·РІРµСЃС‚РЅРѕ",
    }
    return mapping.get(token, token or "РЅРµРёР·РІРµСЃС‚РЅРѕ")



def _sku_attribution_status_ru(value: str) -> str:
    token = str(value or "").strip().lower()
    return {"ok": "РЅРѕСЂРјР°", "broken": "РѕС€РёР±РєР°"}.get(token, token or "РЅРµРёР·РІРµСЃС‚РЅРѕ")
def _watchlist_groups_for_render() -> List[tuple[str, str]]:
    return [
        ("top_growth", "Р РѕСЃС‚"),
        ("top_risk", "Р РёСЃРє"),
        ("dead_stock", "РќРµР»РёРєРІРёРґ"),
        ("ad_inefficiency", "РќРµСЌС„С„РµРєС‚РёРІРЅР°СЏ СЂРµРєР»Р°РјР°"),
        ("conversion_drop", "РџР°РґРµРЅРёРµ РєРѕРЅРІРµСЂСЃРёРё"),
        ("logistics_risk", "Р›РѕРіРёСЃС‚РёС‡РµСЃРєРёР№ СЂРёСЃРє"),
    ]


def _watchlist_rows(sku_watchlists: Dict[str, Any], group: str, limit: int = 5) -> List[Dict[str, Any]]:
    watchlists = sku_watchlists.get("watchlists", {}) if isinstance(sku_watchlists, dict) else {}
    rows = watchlists.get(group, []) if isinstance(watchlists, dict) else []
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)][: max(0, int(limit))]


def _watchlist_line(row: Dict[str, Any]) -> str:
    sku = str(row.get("sku") or "").strip() or "n/a"
    attention = int(float(row.get("attention_score", 0) or 0))
    reason = str(row.get("reason") or "").strip()
    deltas = row.get("deltas", {})
    if not isinstance(deltas, dict):
        deltas = {}
    main_delta = _safe_float_local(
        deltas.get("net_profit_vs_7d_pct")
        if deltas.get("net_profit_vs_7d_pct") is not None
        else deltas.get("orders_vs_7d_pct")
    )
    delta_text = f", О”7d={format_pct_or_unknown(main_delta)}" if main_delta is not None else ""
    reason_text = f", {reason}" if reason else ""
    return f"РўРѕРІР°СЂ {sku} | РїСЂРёРѕСЂРёС‚РµС‚ {attention}{delta_text}{reason_text}"



def _compact_sku_list_clean(values: List[str], limit: int = 8) -> str:
    cleaned = [str(v).strip() for v in values if str(v).strip()]
    if not cleaned:
        return "вЂ”"
    shown = cleaned[: max(1, int(limit))]
    suffix = f", +{len(cleaned) - len(shown)}" if len(cleaned) > len(shown) else ""
    return ", ".join(shown) + suffix


def _sku_status_counts_from_health_rows(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {"growth": 0, "normal": 0, "risk": 0, "liquidation": 0}
    for row in rows:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "").strip().lower()
        if status in {"рост", "growth", "strong"}:
            counts["growth"] += 1
        elif status in {"нормально", "normal", "healthy", "ok"}:
            counts["normal"] += 1
        elif status in {"риск", "risk", "unstable"}:
            counts["risk"] += 1
        elif status in {"ликвидация", "liquidation", "liquidate"}:
            counts["liquidation"] += 1
        else:
            counts["normal"] += 1
    return counts


def _assert_sku_status_counts_match(
    summary_counts: Dict[str, int],
    detail_rows: List[Dict[str, Any]],
) -> None:
    expected = _sku_status_counts_from_health_rows(detail_rows)
    normalized_summary = {
        "growth": int(summary_counts.get("growth", 0) or 0),
        "normal": int(summary_counts.get("normal", 0) or 0),
        "risk": int(summary_counts.get("risk", 0) or 0),
        "liquidation": int(summary_counts.get("liquidation", 0) or 0),
    }
    if normalized_summary != expected:
        raise AssertionError(
            "sku_status_summary_mismatch: "
            f"summary={normalized_summary} detail={expected}"
        )


def run_daily_report_stage(payload: Dict[str, Any]) -> Dict[str, Any]:
    sync_from_entry(globals())

    data: Dict[str, Any] = dict(payload or {})
    source_mode = str(data.get("source_mode") or "").strip().lower()
    data_mode = str(data.get("data_mode") or "").strip().lower()
    if not data_mode:
        data_mode = (
            "api"
            if (source_mode == "wb_api" and not bool(data.get("local_financial_fallback_used", False)))
            else "raw_reports_fallback"
        )
    non_api_mode = bool(data.get("non_api_mode", data_mode != "api"))
    non_api_notice = (
        "Отчет собран в ограниченном режиме по raw-отчетам WB, "
        "часть метрик может быть недоступна до подключения API"
    )
    out_dir = str(data.get("out_dir") or "")
    daily_kpi = data.get("daily_kpi", {})
    if not isinstance(daily_kpi, dict):
        daily_kpi = {}
    territorial_summary = data.get("territorial_summary", {})
    if not isinstance(territorial_summary, dict):
        territorial_summary = {}
    territorial_distribution = data.get("territorial_distribution", {})
    if not isinstance(territorial_distribution, dict):
        territorial_distribution = {}
    logistics_summary = data.get("logistics_summary", {})
    if not isinstance(logistics_summary, dict):
        logistics_summary = {}
    profit_contribution = data.get("profit_contribution", {})
    if not isinstance(profit_contribution, dict):
        profit_contribution = {}
    sku_metrics = data.get("sku_metrics", [])
    if not isinstance(sku_metrics, list):
        sku_metrics = []
    abc_rows = data.get("abc_rows", [])
    if not isinstance(abc_rows, list):
        abc_rows = []
    decision_groups = data.get("decision_groups", {})
    if not isinstance(decision_groups, dict):
        decision_groups = {"scale": [], "fix": [], "watch": [], "liquidate": []}
    director_strategy = data.get("director_strategy", {})
    if not isinstance(director_strategy, dict):
        director_strategy = {}
    job = data.get("job", {})
    if not isinstance(job, dict):
        job = {}
    warnings_collector = data.get("warnings_collector")
    if not isinstance(warnings_collector, WarningsCollector):
        warnings_collector = WarningsCollector()
    facts = data.get("facts", {})
    if not isinstance(facts, dict):
        facts = {}
    data_quality = data.get("data_quality", {})
    if not isinstance(data_quality, dict):
        data_quality = {}
    outcomes_payload = data.get("outcomes_payload", {})
    if not isinstance(outcomes_payload, dict):
        outcomes_payload = {}
    unassigned_costs = data.get("unassigned_costs", {})
    if not isinstance(unassigned_costs, dict):
        unassigned_costs = {}
    render_kpi = data.get("render_kpi", {})
    if not isinstance(render_kpi, dict):
        render_kpi = {}
    daily_status_matrix = data.get("daily_status_matrix", {})
    if not isinstance(daily_status_matrix, dict):
        daily_status_matrix = {}
    order_kpi = data.get("order_kpi", {})
    if not isinstance(order_kpi, dict):
        order_kpi = {}
    buyout_kpi = data.get("buyout_kpi", {})
    if not isinstance(buyout_kpi, dict):
        buyout_kpi = {}
    event_date_model = data.get("event_date_model", {})
    if not isinstance(event_date_model, dict):
        event_date_model = {}
    event_ledger = data.get("event_ledger", {})
    if not isinstance(event_ledger, dict):
        event_ledger = {}
    cabinet_funnel = data.get("cabinet_funnel", {})
    if not isinstance(cabinet_funnel, dict):
        cabinet_funnel = {}
    funnel_alerts = data.get("funnel_alerts", {})
    if not isinstance(funnel_alerts, dict):
        funnel_alerts = {}
    sku_watchlists = data.get("sku_watchlists", {})
    if not isinstance(sku_watchlists, dict):
        sku_watchlists = {}
    sales_funnel_summary = data.get("sales_funnel_summary", {})
    if not isinstance(sales_funnel_summary, dict):
        sales_funnel_summary = (
            cabinet_funnel.get("sku_diagnostics", {}).get("summary", {})
            if isinstance(cabinet_funnel.get("sku_diagnostics"), dict)
            else {}
        )
    if not isinstance(sales_funnel_summary, dict):
        sales_funnel_summary = {}
    report_guardrails = data.get("report_guardrails", {})
    advertising_efficiency = data.get("advertising_efficiency", {})
    if not isinstance(advertising_efficiency, dict):
        advertising_efficiency = {}
    portfolio_ads_summary = data.get(
        "portfolio_ads_summary",
        advertising_efficiency.get("portfolio_ads_summary", advertising_efficiency.get("summary", {}))
        if isinstance(advertising_efficiency, dict)
        else {},
    )
    if not isinstance(portfolio_ads_summary, dict):
        portfolio_ads_summary = {}
    query_profitability = data.get(
        "query_profitability",
        advertising_efficiency.get("query_profitability", {}) if isinstance(advertising_efficiency, dict) else {},
    )
    if not isinstance(query_profitability, dict):
        query_profitability = {}
    if not isinstance(report_guardrails, dict):
        report_guardrails = {}
    sku_attribution_status = str(
        data_quality.get("sku_attribution_status", report_guardrails.get("sku_attribution_status", "ok")) or "ok"
    ).strip().lower()
    financial_finality_status = str(
        data_quality.get("financial_finality_status", report_guardrails.get("financial_finality_status", "unavailable"))
        or "unavailable"
    ).strip().lower()
    territorial_analysis_enabled = bool(
        data_quality.get(
            "territorial_analysis_enabled",
            report_guardrails.get("territorial_analysis_enabled", sku_attribution_status != "broken"),
        )
    )
    profit_contribution_enabled = bool(
        data_quality.get(
            "profit_contribution_enabled",
            report_guardrails.get("profit_contribution_enabled", sku_attribution_status != "broken"),
        )
    )
    ads_analysis_enabled = bool(data_quality.get("ads_analysis_enabled", report_guardrails.get("ads_analysis_enabled", True)))
    sku_level_analytics_enabled = bool(
        territorial_analysis_enabled
        and profit_contribution_enabled
        and int(data_quality.get("valid_sku_count", 0) or 0) > 0
    )

    def _round_or_none(value: Any) -> float | None:
        if value is None:
            return None
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        return round(numeric, 2)

    def _int_or_none(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    def _first_number_early(*items: Any) -> float | None:
        for item in items:
            number = _safe_float_local(item)
            if number is not None:
                return number
        return None

    orders_count_value = render_kpi.get("orders_count", data.get("daily_orders_count"))
    orders_count_raw_value = orders_count_value
    orders_amount_value = render_kpi.get("orders_amount", data.get("daily_orders_amount"))
    buyouts_count_value = render_kpi.get("buyouts_count", data.get("daily_buyouts_count"))
    buyouts_amount_value = render_kpi.get("buyouts_amount", data.get("daily_buyouts_amount"))
    avg_check_value = render_kpi.get("avg_check", data.get("avg_check"))
    revenue_value = render_kpi.get("revenue", data.get("revenue_total"))
    net_profit_value = render_kpi.get("net_profit", data.get("net_profit"))
    margin_pct_value = render_kpi.get("margin_pct", data.get("margin_pct_total"))
    profitability_pct_value = render_kpi.get("profitability_pct", data.get("profitability_pct_total"))

    funnel = cabinet_funnel.get("funnel", {}) if isinstance(cabinet_funnel, dict) else {}
    if not isinstance(funnel, dict):
        funnel = {}
    if is_missing_value(orders_count_value):
        orders_count_value = _first_number_early(
            funnel.get("orders"),
            daily_kpi.get("daily_orders_count"),
            data.get("daily_orders_count"),
            data.get("orders"),
            data.get("sales_activity_qty"),
        )

    conversion_value = funnel.get("view_to_order_conversion", funnel.get("click_to_order_conversion_pct"))

    ads_efficiency_mode = str(
        portfolio_ads_summary.get("analysis_mode", advertising_efficiency.get("analysis_mode", "disabled"))
        if isinstance(advertising_efficiency, dict)
        else "disabled"
    ).strip().lower()
    portfolio_ad_spend = _safe_float_local(portfolio_ads_summary.get("portfolio_ad_spend", data.get("ads_spend_total")))
    portfolio_orders_from_ads = _safe_float_local(portfolio_ads_summary.get("portfolio_orders_from_ads", data.get("ads_orders")))
    portfolio_buyouts_from_ads = _safe_float_local(portfolio_ads_summary.get("portfolio_buyouts_from_ads"))
    portfolio_revenue_from_ads = _safe_float_local(portfolio_ads_summary.get("portfolio_revenue_from_ads", data.get("ads_revenue")))
    portfolio_profit_from_ads = _safe_float_local(portfolio_ads_summary.get("portfolio_profit_from_ads"))
    portfolio_romi = _safe_float_local(portfolio_ads_summary.get("portfolio_ROMI", data.get("ads_romi")))
    portfolio_drr = _safe_float_local(portfolio_ads_summary.get("portfolio_DRR"))
    portfolio_cpo = _safe_float_local(portfolio_ads_summary.get("portfolio_CPO"))
    cpo_value = portfolio_cpo if portfolio_cpo is not None else _safe_float_local(funnel.get("cpo", funnel.get("CPO")))
    top_profitable_queries_ads = portfolio_ads_summary.get("top_profitable_queries", []) if isinstance(portfolio_ads_summary, dict) else []
    if not isinstance(top_profitable_queries_ads, list):
        top_profitable_queries_ads = []
    top_unprofitable_queries_ads = portfolio_ads_summary.get("top_unprofitable_queries", []) if isinstance(portfolio_ads_summary, dict) else []
    if not isinstance(top_unprofitable_queries_ads, list):
        top_unprofitable_queries_ads = []

    def _safe_text(value: Any) -> str:
        return str(value or "").strip()

    def _sanitize_client_text(value: Any) -> str:
        text_value = repair_mojibake(_safe_text(value))
        if not text_value:
            return ""

        token_map = {
            "unknown": "РґР°РЅРЅС‹Рµ РЅРµ РїРѕРґС‚РІРµСЂР¶РґРµРЅС‹",
            "degraded": "С‡Р°СЃС‚РёС‡РЅРѕ",
            "partial": "С‡Р°СЃС‚РёС‡РЅРѕ",
            "confirmed": "РїРѕРґС‚РІРµСЂР¶РґРµРЅРѕ",
            "not_confirmed": "РґР°РЅРЅС‹Рµ РЅРµ РїРѕРґС‚РІРµСЂР¶РґРµРЅС‹",
            "attention_score": "РѕС†РµРЅРєР° РІРЅРёРјР°РЅРёСЏ",
            "baseline": "Р±Р°Р·РѕРІС‹Р№ СѓСЂРѕРІРµРЅСЊ",
            "traffic_problem": "РЅРёР·РєРёР№ С‚СЂР°С„РёРє",
            "ads_efficiency_problem": "РЅРµСЌС„С„РµРєС‚РёРІРЅР°СЏ СЂРµРєР»Р°РјР°",
            "monitor": "РЅР°Р±Р»СЋРґР°С‚СЊ",
            "discount_or_remove": "СЃРЅРёР¶Р°С‚СЊ С†РµРЅСѓ РёР»Рё РІС‹РІРѕРґРёС‚СЊ",
            "fallback": "СЂРµР·РµСЂРІРЅС‹Р№ РёСЃС‚РѕС‡РЅРёРє",
        }

        for source, target in token_map.items():
            text_value = re.sub(rf"(?i)\b{re.escape(source)}\b", target, text_value)

        def _humanize_snake(match: re.Match[str]) -> str:
            token = match.group(0).lower()
            if token in token_map:
                return token_map[token]
            return token.replace("_", " ")

        text_value = re.sub(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b", _humanize_snake, text_value)
        text_value = re.sub(r"\s{2,}", " ", text_value).strip()
        return text_value

    def _sanitize_line(line: str) -> str:
        if line == "\f":
            return line
        prefixes = ("### ", "## ", "# ", "- ")
        for prefix in prefixes:
            if line.startswith(prefix):
                return prefix + _sanitize_client_text(line[len(prefix):])
        return _sanitize_client_text(line)

    NO_DATA_LABEL = "нет данных"
    NOT_CONFIRMED_LABEL = "данные не подтверждены"
    INSUFFICIENT_DATA_LABEL = "недостаточно данных для расчета"
    _MISSING_DISPLAY_LABELS = {
        NO_DATA_LABEL,
        NOT_CONFIRMED_LABEL,
        INSUFFICIENT_DATA_LABEL,
    }

    def _unknown_label_for_value(value: Any, *, missing_label: str) -> str:
        token = str(value or "").strip().lower()
        if token in {"not_confirmed", "unknown"}:
            return NOT_CONFIRMED_LABEL
        if is_missing_value(value):
            return missing_label
        return missing_label

    def _with_preliminary(value: str, preliminary: bool) -> str:
        normalized = _sanitize_client_text(value)
        if preliminary and normalized and normalized not in _MISSING_DISPLAY_LABELS:
            return f"{normalized} (предварительно)"
        return normalized

    def _money_text(
        value: Any,
        *,
        preliminary: bool = False,
        decimals: int = 0,
        missing_label: str = NO_DATA_LABEL,
    ) -> str:
        return _with_preliminary(
            format_money_or_unknown(
                value,
                unknown_label=_unknown_label_for_value(value, missing_label=missing_label),
                decimals=decimals,
            ),
            preliminary,
        )

    def _int_text(value: Any, *, preliminary: bool = False, missing_label: str = NO_DATA_LABEL) -> str:
        return _with_preliminary(
            format_int_or_unknown(value, unknown_label=_unknown_label_for_value(value, missing_label=missing_label)),
            preliminary,
        )

    def _pct_text(value: Any, *, preliminary: bool = False, missing_label: str = NO_DATA_LABEL) -> str:
        return _with_preliminary(
            format_pct_or_unknown(value, unknown_label=_unknown_label_for_value(value, missing_label=missing_label)),
            preliminary,
        )

    def _action_ru(raw_action: Any) -> str:
        action = _sanitize_client_text(raw_action).lower()
        mapping = {
            "increase ads": "СѓСЃРёР»РёС‚СЊ СЂРµРєР»Р°РјСѓ",
            "improve listing": "СѓР»СѓС‡С€РёС‚СЊ РєР°СЂС‚РѕС‡РєСѓ",
            "rebalance stock": "РїРµСЂРµСЂР°СЃРїСЂРµРґРµР»РёС‚СЊ РѕСЃС‚Р°С‚РєРё",
            "monitor": "РЅР°Р±Р»СЋРґР°С‚СЊ",
            "discount or remove": "СЃРЅРёР¶Р°С‚СЊ С†РµРЅСѓ РёР»Рё РІС‹РІРѕРґРёС‚СЊ",
            "increase_ads": "СѓСЃРёР»РёС‚СЊ СЂРµРєР»Р°РјСѓ",
            "improve_listing": "СѓР»СѓС‡С€РёС‚СЊ РєР°СЂС‚РѕС‡РєСѓ",
            "rebalance_stock": "РїРµСЂРµСЂР°СЃРїСЂРµРґРµР»РёС‚СЊ РѕСЃС‚Р°С‚РєРё",
            "discount_or_remove": "СЃРЅРёР¶Р°С‚СЊ С†РµРЅСѓ РёР»Рё РІС‹РІРѕРґРёС‚СЊ",
        }
        for key, translated in mapping.items():
            if key in action:
                return translated
        return _sanitize_client_text(raw_action) or "С‚СЂРµР±СѓРµС‚СЃСЏ СЂРµС€РµРЅРёРµ"

    def _sku_lines(rows: Any, *, limit: int = 6) -> List[str]:
        if not isinstance(rows, list):
            return []
        result: List[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            sku = _sanitize_client_text(row.get("sku") or row.get("nm_id") or "")
            if not sku:
                continue
            reason = _sanitize_client_text(
                row.get("issue_reason_ru")
                or row.get("reason")
                or row.get("recommendation")
                or row.get("funnel_issue_reason")
                or row.get("action")
                or ""
            )
            delta_value = _safe_float_local(
                (row.get("deltas") or {}).get("net_profit_vs_7d_pct") if isinstance(row.get("deltas"), dict) else None
            )
            if delta_value is None:
                delta_value = _safe_float_local(
                    (row.get("deltas") or {}).get("orders_vs_7d_pct") if isinstance(row.get("deltas"), dict) else None
                )
            suffix = f", О”7d {_pct_text(delta_value, missing_label=INSUFFICIENT_DATA_LABEL)}" if delta_value is not None else ""
            line = f"SKU {sku} вЂ” {reason}" if reason else f"SKU {sku}"
            result.append(_sanitize_client_text(line + suffix))
            if len(result) >= limit:
                break
        return result

    def _first_non_empty_lines(candidates: List[str], *, limit: int) -> List[str]:
        prepared = [_sanitize_client_text(item) for item in candidates if _sanitize_client_text(item)]
        return prepared[:limit]

    def _problem_count(summary: Dict[str, Any], buckets: set[str]) -> int:
        rows = summary.get("top_problem_groups", []) if isinstance(summary, dict) else []
        if not isinstance(rows, list):
            return 0
        total = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            issue = _sanitize_client_text(row.get("issue_type") or "").lower()
            count = int(row.get("count", 0) or 0)
            if any(bucket in issue for bucket in buckets):
                total += max(0, count)
        return total

    financial_preliminary = financial_finality_status != "final"
    ads_preliminary = non_api_mode or ads_efficiency_mode in {"preview", "disabled"} or not ads_analysis_enabled

    scale_rows = decision_groups.get("scale", []) if isinstance(decision_groups.get("scale"), list) else []
    fix_rows = decision_groups.get("fix", []) if isinstance(decision_groups.get("fix"), list) else []
    watch_rows = decision_groups.get("watch", []) if isinstance(decision_groups.get("watch"), list) else []
    liquidate_rows = decision_groups.get("liquidate", []) if isinstance(decision_groups.get("liquidate"), list) else []

    risk_sku_count = len(fix_rows) + len(watch_rows) + len(liquidate_rows)

    summary_lines = _first_non_empty_lines(
        [str(x) for x in data.get("key_insights", [])] + [str(data.get("ai_day_conclusion") or "")],
        limit=4,
    )
    if not summary_lines:
        summary_lines = ["??????????? ??????? AI-????? ???????? ?? ?????? ????????? ??????."]

    page_1: List[str] = [
        "# AI-????? ???????? Wildberries",
        f"### ???????: {str(data.get('seller_id') or '')}",
        f"### ???? ???????: {str(data.get('run_date') or '')}",
        f"### ?????????? ??????: {_reliability_ru(str(data_quality.get('report_reliability_level', data.get('confidence', 'medium'))))}",
        "",
        "## ??????? ??????",
    ]
    page_1.extend(f"- {line}" for line in summary_lines)
    page_1.extend(
        [
            "",
            "## KPI ????????",
            "?????????? | ????????",
            f"??????? | {_money_text(revenue_value, preliminary=financial_preliminary, decimals=0)}",
            f"?????? ??????? | {_money_text(net_profit_value, preliminary=financial_preliminary, decimals=0)}",
            f"?????? ?? ??????? | {_money_text(portfolio_ad_spend, preliminary=ads_preliminary, decimals=0)}",
            f"?????? ??? ?????? | {_int_text(risk_sku_count)}",
            "",
            "## ??????? ????? AI",
            _sanitize_client_text(str(data.get("ai_day_conclusion") or "????? ??????????? ?? ????????? ?????????????? ??????.")),
        ]
    )

    page_2: List[str] = [
        "# ??????? ? ???????",
        "## ???????????? KPI",
        "?????????? | ????????",
        f"?????? | {_int_text(orders_count_value, missing_label=NO_DATA_LABEL)}",
        f"?????? | {_int_text(buyouts_count_value, missing_label=NO_DATA_LABEL)}",
        f"??????? ??? | {_money_text(avg_check_value, preliminary=not bool(daily_kpi.get('buyouts_amount_confirmed', False)), decimals=0)}",
        f"????????? ???????? ? ????? | {_pct_text(cabinet_funnel.get('funnel', {}).get('view_to_order_conversion') if isinstance(cabinet_funnel.get('funnel', {}), dict) else None)}",
        "",
        "## ?????????? KPI",
        "?????????? | ????????",
        f"??????? | {_money_text(revenue_value, preliminary=financial_preliminary, decimals=0)}",
        f"?????? ??????? | {_money_text(net_profit_value, preliminary=financial_preliminary, decimals=0)}",
        f"????? | {_pct_text(margin_pct_value, preliminary=financial_preliminary, missing_label=INSUFFICIENT_DATA_LABEL)}",
        f"?????????????? | {_pct_text(profitability_pct_value, preliminary=financial_preliminary)}",
        f"??????? ?????????? ?????? | {_pct_text(data.get('financial_completeness_pct'))}",
        "",
        "## ????????????? ???????",
        "?????????? | ????????",
        f"?????? ?? ??????? | {_money_text(portfolio_ad_spend, preliminary=ads_preliminary, decimals=0)}",
        f"??????? ?? ??????? | {_money_text(portfolio_revenue_from_ads, preliminary=ads_preliminary, decimals=0)}",
        f"??????? ?? ??????? | {_money_text(portfolio_profit_from_ads, preliminary=ads_preliminary, decimals=0)}",
        f"ROMI | {_pct_text(portfolio_romi, preliminary=ads_preliminary)}",
        f"DRR | {_pct_text(portfolio_drr, preliminary=ads_preliminary, missing_label=INSUFFICIENT_DATA_LABEL)}",
        f"CPO | {_money_text(cpo_value, preliminary=ads_preliminary, decimals=0, missing_label=INSUFFICIENT_DATA_LABEL)}",
    ]

    top_profitable_queries = [
        _sanitize_client_text(str(item.get("query") or ""))
        for item in top_profitable_queries_ads[:3]
        if isinstance(item, dict) and _sanitize_client_text(item.get("query"))
    ]
    top_unprofitable_queries = [
        _sanitize_client_text(str(item.get("query") or ""))
        for item in top_unprofitable_queries_ads[:3]
        if isinstance(item, dict) and _sanitize_client_text(item.get("query"))
    ]
    if top_profitable_queries:
        page_2.append("- ??? ??????????? ????????: " + "; ".join(top_profitable_queries))
    if top_unprofitable_queries:
        page_2.append("- ???? ????? ? ???????: " + "; ".join(top_unprofitable_queries))

    page_2.extend(
        [
            "",
            "- ????? ?????????? ? ????????? ?????? ????? ??????????????? ???????? ??-?? ????????? ????????????? ??????.",
        ]
    )

    low_traffic_count = _problem_count(sales_funnel_summary, {"traffic", "view", "impression"})
    conversion_drop_count = _problem_count(sales_funnel_summary, {"conversion", "cart_to_order", "buyout"})
    ads_ineff_count = len(top_unprofitable_queries_ads) + len(_watchlist_rows(sku_watchlists, "ad_inefficiency", limit=50))
    liquidate_count = len(liquidate_rows)

    liquidate_skus = _compact_sku_list_clean([str(row.get("sku") or "").strip() for row in liquidate_rows if isinstance(row, dict)], limit=8)

    page_3: List[str] = [
        "# ???????? ????????",
        "## ?????? ??????",
        f"- SKU ? ?????????? ??????? ???????: {_int_text(low_traffic_count)}",
        "## ??????? ?????????",
        f"- SKU ? ????????? ?????????: {_int_text(conversion_drop_count)}",
        "## ????????????? ???????",
        f"- ???????????? ????????? ????????? ????: {_int_text(ads_ineff_count)}",
        "## ?????? ? ???? ??????????",
        f"- ??????? ? ???? ??????????: {_int_text(liquidate_count)}",
        f"- SKU: {liquidate_skus}",
    ]

    def _decision_lines(rows: List[Dict[str, Any]], *, limit: int) -> List[str]:
        lines: List[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            sku = _sanitize_client_text(row.get("sku") or "")
            if not sku:
                continue
            action = _action_ru(row.get("action"))
            reason = _sanitize_client_text(row.get("reason") or row.get("funnel_issue_reason") or "")
            text_line = f"SKU {sku}: {action}"
            if reason:
                text_line += f" ({reason})"
            lines.append(text_line)
            if len(lines) >= limit:
                break
        return lines

    now_actions = _decision_lines(scale_rows + fix_rows + liquidate_rows, limit=10)
    if not now_actions:
        now_actions = _first_non_empty_lines([str(x) for x in data.get("short_recommendations", [])], limit=6)

    watch_actions = _decision_lines(watch_rows, limit=8)
    if not watch_actions:
        watch_actions = _sku_lines(_watchlist_rows(sku_watchlists, "top_risk", limit=8), limit=8)

    not_confirmed_lines: List[str] = []
    if not bool(daily_kpi.get("orders_count_confirmed", False)):
        not_confirmed_lines.append("Р—Р°РєР°Р·С‹ РґРЅСЏ: РґР°РЅРЅС‹Рµ РЅРµ РїРѕРґС‚РІРµСЂР¶РґРµРЅС‹")
    if not bool(daily_kpi.get("buyouts_count_confirmed", False)):
        not_confirmed_lines.append("Р’С‹РєСѓРїС‹ РґРЅСЏ: РґР°РЅРЅС‹Рµ РЅРµ РїРѕРґС‚РІРµСЂР¶РґРµРЅС‹")
    if not ads_analysis_enabled:
        not_confirmed_lines.append("Р РµРєР»Р°РјРЅС‹Рµ РјРµС‚СЂРёРєРё: РґР°РЅРЅС‹Рµ РЅРµ РїРѕРґС‚РІРµСЂР¶РґРµРЅС‹")
    if financial_preliminary:
        not_confirmed_lines.append("Р¤РёРЅР°РЅСЃРѕРІС‹Рµ РјРµС‚СЂРёРєРё: РїСЂРµРґРІР°СЂРёС‚РµР»СЊРЅС‹Рµ")
    if not not_confirmed_lines:
        not_confirmed_lines.append("Р’СЃРµ РєСЂРёС‚РёС‡РЅС‹Рµ РјРµС‚СЂРёРєРё РїРѕРґС‚РІРµСЂР¶РґРµРЅС‹")

    page_4: List[str] = [
        "# ???????????? ??",
        "## ??? ?????? ??????",
    ]
    page_4.extend(f"- {line}" for line in now_actions[:10])
    page_4.extend(["", "## ??? ?????????"])
    page_4.extend(f"- {line}" for line in watch_actions[:10])
    page_4.extend(["", "## ??? ???? ?? ???????????? ? ??????? ????????????"])
    page_4.extend(f"- {line}" for line in not_confirmed_lines)

    growth_lines = _sku_lines(_watchlist_rows(sku_watchlists, "top_growth", limit=10), limit=10)
    risk_lines = _sku_lines(_watchlist_rows(sku_watchlists, "top_risk", limit=10), limit=10)
    watch_lines = _decision_lines(watch_rows, limit=10)
    liquidate_lines = _decision_lines(liquidate_rows, limit=10)

    if not growth_lines:
        growth_lines = ["??? ?????????? SKU ????? ?? ??????? ??????."]
    if not risk_lines:
        risk_lines = ["??? ?????????? SKU ????? ?? ??????? ??????."]
    if not watch_lines:
        watch_lines = ["??? SKU ??? ?????? ??????????."]
    if not liquidate_lines:
        liquidate_lines = ["??? SKU ? ???? ??????????."]

    page_5: List[str] = [
        "# ?????????? ???????",
        "## ????",
    ]
    page_5.extend(f"- {line}" for line in growth_lines[:8])
    page_5.extend(["", "## ????"])
    page_5.extend(f"- {line}" for line in risk_lines[:8])
    page_5.extend(["", "## ?????????"])
    page_5.extend(f"- {line}" for line in watch_lines[:8])
    page_5.extend(["", "## ?????????????"])
    page_5.extend(f"- {line}" for line in liquidate_lines[:8])

    confirmed_items: List[str] = []
    not_confirmed_items: List[str] = []

    if bool(data.get("ads_rows_count", 0) or portfolio_ad_spend):
        confirmed_items.append("???????")
    else:
        not_confirmed_items.append("???????")

    if float(data.get("financial_completeness_pct", 0.0) or 0.0) > 0:
        confirmed_items.append("????? ?????????? ?????")
    else:
        not_confirmed_items.append("?????????? ??????")

    if bool(daily_kpi.get("orders_count_confirmed", False)):
        confirmed_items.append("?????? ???")
    else:
        not_confirmed_items.append("?????? ???")

    if bool(daily_kpi.get("buyouts_count_confirmed", False)):
        confirmed_items.append("?????? ???")
    else:
        not_confirmed_items.append("?????? ???")

    influence_text = (
        "?????? ?? ??????? ? ????????? ????????????? ????? ???????????? ??? ???????? ?? ??????? ????????????? ????????."
        if financial_preliminary or ads_preliminary
        else "???????? ?????? ????? ???????????? ??? ???????????? ?????????? ?????????."
    )

    page_6: List[str] = [
        "# ???????? ??????",
        "?????????? | ????????",
        f"???????? ?????? (SKU) | {_int_text(data_quality.get('valid_sku_count', 0))}",
        f"?????? ? ???????? | {_int_text(data_quality.get('invalid_sku_rows', 0))}",
        f"?? ?????????????? ?????? | {_int_text(data_quality.get('unassigned_rows_true', data_quality.get('unassigned_rows', 0)))}",
        f"??????? ?????????? ?????? | {_pct_text(data.get('financial_completeness_pct'))}",
        f"?????? ??????????? ??????? | {_contour_status_ru(financial_finality_status)}",
        f"?????????? ?????? | {_reliability_ru(str(data_quality.get('report_reliability_level', 'medium')))}",
        "",
        "## ????????????",
    ]
    page_6.extend(f"- {_sanitize_client_text(item)}" for item in confirmed_items)
    page_6.extend(["", "## ?? ????????????"])
    page_6.extend(f"- {_sanitize_client_text(item)}" for item in not_confirmed_items)
    page_6.extend(["", "## ??? ??? ?????? ?? ??????", f"- {influence_text}"])

    page_7: List[str] = [
        "# ??? ????? AI ????????",
        "- ????????? ??????????? ???????, ??????? ? ???????? ???????.",
        "- ??????? ????? ????? ? ???? ?????? ?? SKU.",
        "- ???????? ???????????? ????????: ???????, ?????????, ?????????, ?????????????.",
        "- ???????????? ???????? ?????? ? ???????? ??????? ?????????? ???????.",
        "- ????????? ???????? ???????????? ??? ???????????? ? ????????? ????????.",
        "",
        "## ???? ??? ???????",
        "- ???? ??????????? ????? ?? ????? ?? ?????? ????????.",
    ]

    def _ru(escaped: str) -> str:
        if not isinstance(escaped, str):
            return str(escaped)
        repaired = repair_mojibake(escaped)
        if repaired and repaired != escaped:
            return repaired
        if "\\u" not in escaped:
            return escaped
        try:
            return escaped.encode("ascii").decode("unicode_escape")
        except UnicodeEncodeError:
            return escaped

    def _clean_client(value: Any) -> str:
        txt = normalize_pdf_text(str(value or "")).strip()
        txt = re.sub(r"\b[a-z]+(?:_[a-z0-9]+)+\b", "", txt)
        txt = re.sub(r"\s{2,}", " ", txt).strip()
        return txt

    summary_lines_client = [
        _clean_client(x)
        for x in data.get("key_insights", [])
        if _clean_client(x)
    ][:3]
    if not summary_lines_client:
        summary_lines_client = [_ru("РљР»СЋС‡РµРІС‹Рµ РІС‹РІРѕРґС‹ СЃС„РѕСЂРјРёСЂРѕРІР°РЅС‹ РїРѕ РґРѕСЃС‚СѓРїРЅС‹Рј РґР°РЅРЅС‹Рј.")]

    risk_count_client = len(fix_rows) + len(watch_rows) + len(liquidate_rows)

    page_1 = [
        "# " + _ru("AI-Р°СѓРґРёС‚ РєР°Р±РёРЅРµС‚Р° Wildberries"),
        f"### {_ru('РљР°Р±РёРЅРµС‚')}: {str(data.get('seller_id') or '')}",
        f"### {_ru('Р”Р°С‚Р° Р°РЅР°Р»РёР·Р°')}: {str(data.get('run_date') or '')}",
        f"### {_ru('РќР°РґРµР¶РЅРѕСЃС‚СЊ РґР°РЅРЅС‹С…')}: {_reliability_ru(str(data_quality.get('report_reliability_level', data.get('confidence', 'medium'))))}",
        "",
        "## " + _ru("РљСЂР°С‚РєРѕРµ СЂРµР·СЋРјРµ"),
    ]
    page_1.extend(f"- {_clean_client(line)}" for line in summary_lines_client)
    page_1.extend([
        "",
        "## " + _ru("KPI РєР°СЂС‚РѕС‡РєРё"),
        _ru("РџРѕРєР°Р·Р°С‚РµР»СЊ") + " | " + _ru("Р—РЅР°С‡РµРЅРёРµ"),
        _ru("К перечислению продавцу") + f" | {_money_text(revenue_value, preliminary=financial_preliminary, decimals=0)}",
        _ru("Р§РёСЃС‚Р°СЏ РїСЂРёР±С‹Р»СЊ") + f" | {_money_text(net_profit_value, preliminary=financial_preliminary, decimals=0)}",
        _ru("Р Р°СЃС…РѕРґ РЅР° СЂРµРєР»Р°РјСѓ") + f" | {_money_text(portfolio_ad_spend, preliminary=ads_preliminary, decimals=0)}",
        _ru("РўРѕРІР°СЂС‹ РїРѕРґ СЂРёСЃРєРѕРј") + f" | {_int_text(risk_count_client)}",
        "",
        "## " + _ru("Р“Р»Р°РІРЅС‹Р№ РІС‹РІРѕРґ AI"),
        _clean_client(str(data.get('ai_day_conclusion') or '')) or _ru("Р’С‹РІРѕРґ С„РѕСЂРјРёСЂСѓРµС‚СЃСЏ РїРѕ РґР°РЅРЅС‹Рј С‚РµРєСѓС‰РµРіРѕ РґРЅСЏ."),
    ])

    page_2 = [
        "# " + _ru("Р¤РёРЅР°РЅСЃС‹ Рё СЂРµРєР»Р°РјР°"),
        "## " + _ru("РљРѕРјРјРµСЂС‡РµСЃРєРёРµ KPI"),
        _ru("РџРѕРєР°Р·Р°С‚РµР»СЊ") + " | " + _ru("Р—РЅР°С‡РµРЅРёРµ"),
        _ru("Р—Р°РєР°Р·С‹") + f" | {_int_text(orders_count_value, missing_label=NO_DATA_LABEL)}",
        _ru("Р’С‹РєСѓРїС‹") + f" | {_int_text(buyouts_count_value, missing_label=NO_DATA_LABEL)}",
        _ru("РЎСЂРµРґРЅРёР№ С‡РµРє") + f" | {_money_text(avg_check_value, preliminary=not bool(daily_kpi.get('buyouts_amount_confirmed', False)), decimals=0)}",
        _ru("РљРѕРЅРІРµСЂСЃРёСЏ РІ Р·Р°РєР°Р·") + f" | {_pct_text(conversion_value, missing_label=INSUFFICIENT_DATA_LABEL)}",
        "",
        "## " + _ru("Р¤РёРЅР°РЅСЃРѕРІС‹Рµ KPI"),
        _ru("РџРѕРєР°Р·Р°С‚РµР»СЊ") + " | " + _ru("Р—РЅР°С‡РµРЅРёРµ"),
        _ru("К перечислению продавцу") + f" | {_money_text(revenue_value, preliminary=financial_preliminary, decimals=0)}",
        _ru("Р§РёСЃС‚Р°СЏ РїСЂРёР±С‹Р»СЊ") + f" | {_money_text(net_profit_value, preliminary=financial_preliminary, decimals=0)}",
        "Маржа" + f" | {_pct_text(margin_pct_value, preliminary=financial_preliminary, missing_label=INSUFFICIENT_DATA_LABEL)}",
        _ru("РџРѕР»РЅРѕС‚Р° С„РёРЅР°РЅСЃРѕРІС‹С… РґР°РЅРЅС‹С…") + f" | {_pct_text(data.get('financial_completeness_pct'))}",
        "",
        "## " + _ru("Р­С„С„РµРєС‚РёРІРЅРѕСЃС‚СЊ СЂРµРєР»Р°РјС‹"),
        _ru("РџРѕРєР°Р·Р°С‚РµР»СЊ") + " | " + _ru("Р—РЅР°С‡РµРЅРёРµ"),
        _ru("Р Р°СЃС…РѕРґ РЅР° СЂРµРєР»Р°РјСѓ") + f" | {_money_text(portfolio_ad_spend, preliminary=ads_preliminary, decimals=0)}",
        _ru("Р’С‹СЂСѓС‡РєР° РёР· СЂРµРєР»Р°РјС‹") + f" | {_money_text(portfolio_revenue_from_ads, preliminary=ads_preliminary, decimals=0)}",
        _ru("РџСЂРёР±С‹Р»СЊ РёР· СЂРµРєР»Р°РјС‹") + f" | {_money_text(portfolio_profit_from_ads, preliminary=ads_preliminary, decimals=0)}",
        f"ROMI | {_pct_text(portfolio_romi, preliminary=ads_preliminary)}",
        f"DRR | {_pct_text(portfolio_drr, preliminary=ads_preliminary, missing_label=INSUFFICIENT_DATA_LABEL)}",
        f"CPO | {_money_text(cpo_value, preliminary=ads_preliminary, decimals=0, missing_label=INSUFFICIENT_DATA_LABEL)}",
        "",
        "- " + _ru("Р§Р°СЃС‚СЊ С„РёРЅР°РЅСЃРѕРІС‹С… Рё СЂРµРєР»Р°РјРЅС‹С… РјРµС‚СЂРёРє РЅРѕСЃРёС‚ РїСЂРµРґРІР°СЂРёС‚РµР»СЊРЅС‹Р№ С…Р°СЂР°РєС‚РµСЂ РёР·-Р·Р° РЅРµРїРѕР»РЅРѕРіРѕ РїРѕРґС‚РІРµСЂР¶РґРµРЅРёСЏ РґР°РЅРЅС‹С…."),
    ]

    page_3 = [
        "# " + _ru("РљР»СЋС‡РµРІС‹Рµ РїСЂРѕР±Р»РµРјС‹"),
        "## " + _ru("РќРёР·РєРёР№ С‚СЂР°С„РёРє"),
        f"- {_ru('РЎР»Р°Р±С‹Р№ С‚СЂР°С„РёРє Р·Р°С„РёРєСЃРёСЂРѕРІР°РЅ Сѓ')} {_int_text(low_traffic_count)} SKU",
        "## " + _ru("РџР°РґРµРЅРёРµ РєРѕРЅРІРµСЂСЃРёРё"),
        f"- {_ru('РџСЂРѕР±Р»РµРјР° РєРѕРЅРІРµСЂСЃРёРё Сѓ')} {_int_text(conversion_drop_count)} SKU",
        "## " + _ru("РќРµСЌС„С„РµРєС‚РёРІРЅР°СЏ СЂРµРєР»Р°РјР°"),
        f"- {_ru('Р—РѕРЅС‹ СЂРёСЃРєР° РІ СЂРµРєР»Р°РјРµ')}: {_int_text(ads_ineff_count)}",
        "## " + _ru("РўРѕРІР°СЂС‹ РІ Р·РѕРЅРµ Р»РёРєРІРёРґР°С†РёРё"),
        f"- {_ru('Р’ Р·РѕРЅРµ Р»РёРєРІРёРґР°С†РёРё')}: {_int_text(liquidate_count)} SKU",
    ]

    page_4 = [
        "# " + _ru("Р РµРєРѕРјРµРЅРґР°С†РёРё AI"),
        "## " + _ru("Р§С‚Рѕ РґРµР»Р°С‚СЊ СЃРµР№С‡Р°СЃ"),
        "- " + _ru("РЈСЃРёР»РёС‚СЊ СЂР°Р±РѕС‚Сѓ СЃ РєР°СЂС‚РѕС‡РєР°РјРё SKU СЃ СЃРЅРёР¶РµРЅРЅРѕР№ РєРѕРЅРІРµСЂСЃРёРµР№."),
        "- " + _ru("РџРµСЂРµСЂР°СЃРїСЂРµРґРµР»РёС‚СЊ СЂРµРєР»Р°РјРЅС‹Р№ Р±СЋРґР¶РµС‚ РёР· СѓР±С‹С‚РѕС‡РЅС‹С… Р·Р°РїСЂРѕСЃРѕРІ."),
        "## " + _ru("Р§С‚Рѕ РЅР°Р±Р»СЋРґР°С‚СЊ"),
        "- " + _ru("РћС‚СЃР»РµР¶РёРІР°С‚СЊ РґРёРЅР°РјРёРєСѓ РІС‹РєСѓРїР° Рё РјР°СЂР¶Рё РїРѕ СЂРёСЃРєРѕРІС‹Рј SKU."),
        "## " + _ru("Р§С‚Рѕ РїРѕРєР° РЅРµ РїРѕРґС‚РІРµСЂР¶РґРµРЅРѕ Рё С‚СЂРµР±СѓРµС‚ РїРµСЂРµРїСЂРѕРІРµСЂРєРё"),
    ]
    page_4.extend(f"- {_clean_client(line)}" for line in not_confirmed_lines)

    growth_skus = [str(x.get('sku') or '').strip() for x in _watchlist_rows(sku_watchlists, 'top_growth', limit=8) if isinstance(x, dict)]
    risk_skus = [str(x.get('sku') or '').strip() for x in _watchlist_rows(sku_watchlists, 'top_risk', limit=8) if isinstance(x, dict)]
    watch_skus = [str(x.get('sku') or '').strip() for x in watch_rows if isinstance(x, dict)][:8]
    liquidate_skus = [str(x.get('sku') or '').strip() for x in liquidate_rows if isinstance(x, dict)][:8]

    def _sku_block(title_ru: str, skus: List[str]) -> List[str]:
        lines = ["## " + title_ru]
        clean = [s for s in skus if s]
        if not clean:
            lines.append("- " + _ru("РќРµС‚ РґР°РЅРЅС‹С…"))
        else:
            lines.extend(f"- SKU {sku}" for sku in clean)
        return lines

    page_5 = ["# " + _ru("РњРѕРЅРёС‚РѕСЂРёРЅРі С‚РѕРІР°СЂРѕРІ")]
    page_5.extend(_sku_block(_ru("Р РѕСЃС‚"), growth_skus))
    page_5.extend(_sku_block(_ru("Р РёСЃРє"), risk_skus))
    page_5.extend(_sku_block(_ru("РќР°Р±Р»СЋРґР°С‚СЊ"), watch_skus))
    page_5.extend(_sku_block(_ru("Р›РёРєРІРёРґРёСЂРѕРІР°С‚СЊ"), liquidate_skus))

    page_6 = [
        "# " + _ru("РљР°С‡РµСЃС‚РІРѕ РґР°РЅРЅС‹С…"),
        _ru("РџРѕРєР°Р·Р°С‚РµР»СЊ") + " | " + _ru("Р—РЅР°С‡РµРЅРёРµ"),
        _ru("Р’Р°Р»РёРґРЅС‹Рµ С‚РѕРІР°СЂС‹ (SKU)") + f" | {_int_text(data_quality.get('valid_sku_count', 0))}",
        _ru("РЎС‚СЂРѕРєРё СЃ РѕС€РёР±РєР°РјРё") + f" | {_int_text(data_quality.get('invalid_sku_rows', 0))}",
        _ru("РќРµ СЂР°СЃРїСЂРµРґРµР»С‘РЅРЅС‹Рµ СЃС‚СЂРѕРєРё") + f" | {_int_text(data_quality.get('unassigned_rows_true', data_quality.get('unassigned_rows', 0)))}",
        _ru("РџРѕР»РЅРѕС‚Р° С„РёРЅР°РЅСЃРѕРІС‹С… РґР°РЅРЅС‹С…") + f" | {_pct_text(data.get('financial_completeness_pct'))}",
        _ru("РЎС‚Р°С‚СѓСЃ С„РёРЅР°РЅСЃРѕРІРѕРіРѕ РєРѕРЅС‚СѓСЂР°") + f" | {_contour_status_ru(financial_finality_status)}",
        _ru("РќР°РґРµР¶РЅРѕСЃС‚СЊ РѕС‚С‡РµС‚Р°") + f" | {_reliability_ru(str(data_quality.get('report_reliability_level', 'medium')))}",
        "",
        "## " + _ru("РџРѕРґС‚РІРµСЂР¶РґРµРЅРѕ"),
        "- " + _ru("СЂРµРєР»Р°РјР°"),
        "- " + _ru("С‡Р°СЃС‚СЊ С„РёРЅР°РЅСЃРѕРІС‹С… СЃС‚СЂРѕРє"),
        "",
        "## " + _ru("РќРµ РїРѕРґС‚РІРµСЂР¶РґРµРЅРѕ"),
        "- " + _ru("Р·Р°РєР°Р·С‹ РґРЅСЏ"),
        "- " + _ru("РІС‹РєСѓРїС‹ РґРЅСЏ"),
        "",
        "## " + _ru("РљР°Рє СЌС‚Рѕ РІР»РёСЏРµС‚ РЅР° РІС‹РІРѕРґС‹"),
        "- " + _ru("Р§Р°СЃС‚СЊ РІС‹РІРѕРґРѕРІ РїРѕ РїСЂРёР±С‹Р»Рё Рё СЂРµРєР»Р°РјРµ С‚СЂРµР±СѓРµС‚ РїРµСЂРµРїСЂРѕРІРµСЂРєРё РїРѕСЃР»Рµ С„РёРЅР°Р»СЊРЅРѕРіРѕ РїРѕРґС‚РІРµСЂР¶РґРµРЅРёСЏ РґР°РЅРЅС‹С…."),
    ]

    page_7 = [
        "# " + _ru("Р§С‚Рѕ СѓРјРµРµС‚ AI Р”РёСЂРµРєС‚РѕСЂ"),
        "- " + _ru("Р•Р¶РµРґРЅРµРІРЅРѕ Р°РЅР°Р»РёР·РёСЂСѓРµС‚ С„РёРЅР°РЅСЃС‹, СЂРµРєР»Р°РјСѓ Рё РІРѕСЂРѕРЅРєСѓ РїСЂРѕРґР°Р¶."),
        "- " + _ru("РќР°С…РѕРґРёС‚ С‚РѕС‡РєРё СЂРѕСЃС‚Р° Рё Р·РѕРЅС‹ РїРѕС‚РµСЂСЊ РїРѕ SKU."),
        "- " + _ru("Р¤РѕСЂРјРёСЂСѓРµС‚ РїРѕРЅСЏС‚РЅС‹Рµ СЂРµРєРѕРјРµРЅРґР°С†РёРё РґР»СЏ РІР»Р°РґРµР»СЊС†Р° РєР°Р±РёРЅРµС‚Р°."),
        "",
        "## " + _ru("Р”РµРјРѕ РґР»СЏ РєР»РёРµРЅС‚Р°"),
        "- " + _ru("РњРѕРіСѓ РїРѕРґРіРѕС‚РѕРІРёС‚СЊ С‚Р°РєРѕР№ Р¶Рµ Р°СѓРґРёС‚ РїРѕ РІР°С€РµРјСѓ РєР°Р±РёРЅРµС‚Сѓ."),
    ]

    funnel_section_lines = list(page_2)
    sku_monitor_lines = list(page_5)

    important_warnings = _important_warnings(warnings_collector.export_warnings())

    report_pages: List[List[str]] = [
        page_1,
        page_2,
        page_3,
        page_4,
        page_5,
        page_6,
        page_7,
    ]
    report_pages = [[_sanitize_line(str(line)) for line in page] for page in report_pages]

    def _first_number_local(*items: Any) -> float | None:
        for item in items:
            number = _safe_float_local(item)
            if number is not None:
                return number
        return None

    financial_kpi_payload = data.get("financial_kpi", {})
    if not isinstance(financial_kpi_payload, dict):
        financial_kpi_payload = {}
    email_summary_payload = job.get("email_summary", {})
    if not isinstance(email_summary_payload, dict):
        email_summary_payload = {}
    financial_components_payload = (
        financial_kpi_payload.get("components", {})
        if isinstance(financial_kpi_payload.get("components"), dict)
        else {}
    )

    def _component_available(*keys: str) -> bool:
        for key in keys:
            payload = financial_components_payload.get(key, {})
            if isinstance(payload, dict) and payload.get("available") is not None:
                return bool(payload.get("available"))
        return True

    watchlists_payload = sku_watchlists.get("watchlists", {}) if isinstance(sku_watchlists, dict) else {}
    if not isinstance(watchlists_payload, dict):
        watchlists_payload = {}

    def _watch_count(key: str) -> int:
        rows = watchlists_payload.get(key, [])
        return len(rows) if isinstance(rows, list) else 0

    fallback_growth_count = _watch_count("top_growth")
    fallback_risk_count = _watch_count("top_risk")
    fallback_liquidation_count = max(_watch_count("dead_stock"), len(decision_groups.get("liquidate", [])))
    normal_base = int(data_quality.get("valid_sku_count", 0) or 0)
    if normal_base <= 0:
        normal_base = len([row for row in sku_metrics if isinstance(row, dict)])
    fallback_normal_count = (
        max(normal_base - fallback_growth_count - fallback_risk_count - fallback_liquidation_count, 0)
        if normal_base > 0
        else _watch_count("watch_list")
    )

    growth_count = fallback_growth_count
    normal_count = fallback_normal_count
    risk_count = fallback_risk_count
    liquidation_count = fallback_liquidation_count

    seller_id_for_visual = str(data.get("seller_id") or "")
    report_date_for_visual = str(data.get("run_date") or "")
    operational_day_for_visual = str(event_date_model.get("operational_date") or report_date_for_visual)

    seller_payout_visual = _first_number_local(
        financial_kpi_payload.get("seller_payout"),
        data.get("seller_payout_total"),
        data.get("revenue_total"),
        revenue_value,
        email_summary_payload.get("financial_revenue"),
    )
    gross_revenue_visual = _first_number_local(
        financial_kpi_payload.get("gross_revenue"),
        data.get("gross_revenue_total"),
    )
    wb_realized_revenue_visual = _first_number_local(
        financial_kpi_payload.get("wb_realized_revenue"),
        data.get("wb_realized_revenue_total"),
    )
    revenue_visual = _first_number_local(
        financial_kpi_payload.get("revenue"),
        data.get("revenue_total"),
        seller_payout_visual,
    )
    net_profit_visual = _first_number_local(
        net_profit_value,
        data.get("net_profit"),
        financial_kpi_payload.get("net_profit"),
        email_summary_payload.get("net_profit"),
    )
    ad_spend_visual = _first_number_local(
        portfolio_ad_spend,
        data.get("ads_spend_total"),
        financial_kpi_payload.get("ads_spend"),
        email_summary_payload.get("ads_spend"),
    )
    orders_visual = _first_number_local(
        orders_count_value,
        order_kpi.get("orders_count"),
        funnel.get("orders"),
        daily_kpi.get("daily_orders_count"),
    )

    commission_visual = _first_number_local(
        data.get("wb_commission"),
        financial_kpi_payload.get("wb_commission"),
        email_summary_payload.get("wb_commission"),
    )
    acquiring_visual = _first_number_local(data.get("acquiring_total"), financial_kpi_payload.get("acquiring"))
    pvz_service_visual = _first_number_local(data.get("pvz_service_total"), financial_kpi_payload.get("pvz_service"))
    logistics_visual = _first_number_local(
        data.get("logistics_total"),
        data.get("logistics"),
        financial_kpi_payload.get("logistics"),
        email_summary_payload.get("logistics"),
    )
    storage_visual = _first_number_local(
        data.get("storage_total"),
        data.get("storage"),
        financial_kpi_payload.get("storage"),
        email_summary_payload.get("storage"),
    )
    deductions_visual = _first_number_local(data.get("deductions_total"), financial_kpi_payload.get("deductions"))
    loyalty_program_visual = _first_number_local(data.get("loyalty_program_total"), financial_kpi_payload.get("loyalty_program"))
    loyalty_points_visual = _first_number_local(
        data.get("loyalty_points_withheld_total"),
        financial_kpi_payload.get("loyalty_points_withheld"),
    )
    other_adjustments_visual = _first_number_local(
        data.get("other_adjustments_total"),
        financial_kpi_payload.get("other_adjustments"),
    )
    penalties_visual = _first_number_local(data.get("penalties_total"), financial_kpi_payload.get("penalties"))
    cost_price_visual = _first_number_local(
        data.get("cost_price_total"),
        financial_kpi_payload.get("cost_price"),
        email_summary_payload.get("cost_price"),
    )
    tax_visual = _first_number_local(data.get("tax_total"), financial_kpi_payload.get("tax"), email_summary_payload.get("tax"))

    if not _component_available("revenue", "seller_payout"):
        seller_payout_visual = None
        revenue_visual = None
    if not _component_available("commission"):
        commission_visual = None
    if not _component_available("logistics"):
        logistics_visual = None
    if not _component_available("storage"):
        storage_visual = None
    if not _component_available("deductions"):
        deductions_visual = None
    if not _component_available("acquiring"):
        acquiring_visual = None
    if not _component_available("pvz_service"):
        pvz_service_visual = None
    if not _component_available("penalties"):
        penalties_visual = None
    if not _component_available("cost_price"):
        cost_price_visual = None
    if not _component_available("tax"):
        tax_visual = None
    if not _component_available("ads_spend"):
        ad_spend_visual = None
    if not _component_available("net_profit"):
        net_profit_visual = None
    profit_base_visual = _first_number_local(gross_revenue_visual, revenue_visual)

    def _nz(value: Any) -> float:
        return float(value) if value is not None else 0.0

    explained_net_profit = (
        _nz(profit_base_visual)
        - _nz(cost_price_visual)
        - _nz(commission_visual)
        - _nz(acquiring_visual)
        - _nz(pvz_service_visual)
        - _nz(logistics_visual)
        - _nz(storage_visual)
        - _nz(penalties_visual)
        - _nz(deductions_visual)
        - _nz(loyalty_program_visual)
        - _nz(loyalty_points_visual)
        - _nz(other_adjustments_visual)
        - _nz(ad_spend_visual)
        - _nz(tax_visual)
    )
    net_profit_explain_delta = (
        round(_nz(net_profit_visual) - explained_net_profit, 2)
        if net_profit_visual is not None
        else None
    )

    financial_structure_complete = all(
        component is not None
        for component in (
            profit_base_visual,
            commission_visual,
            acquiring_visual,
            pvz_service_visual,
            logistics_visual,
            storage_visual,
            deductions_visual,
            cost_price_visual,
            tax_visual,
            ad_spend_visual,
        )
    )
    net_profit_reliable = (
        financial_structure_complete
        and financial_finality_status == "final"
        and float(data.get("financial_completeness_pct", 0.0) or 0.0) >= 95.0
    )
    net_profit_exact_visual = net_profit_visual if net_profit_reliable else None
    if not net_profit_reliable:
        net_profit_visual = None
        explained_net_profit = None
        net_profit_explain_delta = None
    operating_profit_without_cogs: float | None = None
    if profit_base_visual is not None:
        operating_components = (
            commission_visual,
            acquiring_visual,
            pvz_service_visual,
            logistics_visual,
            storage_visual,
            penalties_visual,
            deductions_visual,
            loyalty_program_visual,
            loyalty_points_visual,
            other_adjustments_visual,
            ad_spend_visual,
            tax_visual,
        )
        if any(component is not None for component in operating_components):
            operating_profit_without_cogs = (
                _nz(profit_base_visual)
                - _nz(commission_visual)
                - _nz(acquiring_visual)
                - _nz(pvz_service_visual)
                - _nz(logistics_visual)
                - _nz(storage_visual)
                - _nz(penalties_visual)
                - _nz(deductions_visual)
                - _nz(loyalty_program_visual)
                - _nz(loyalty_points_visual)
                - _nz(other_adjustments_visual)
                - _nz(ad_spend_visual)
                - _nz(tax_visual)
            )
    loyalty_total_visual = (
        _nz(loyalty_program_visual) + _nz(loyalty_points_visual)
        if (loyalty_program_visual is not None or loyalty_points_visual is not None)
        else None
    )

    expense_structure_payload = {
        "commission": commission_visual,
        "acquiring": acquiring_visual,
        "pvz_service": pvz_service_visual,
        "logistics": logistics_visual,
        "storage": storage_visual,
        "penalties": penalties_visual,
        "deductions": deductions_visual,
        "loyalty_program": loyalty_program_visual,
        "loyalty_points_withheld": loyalty_points_visual,
        "loyalty_total": loyalty_total_visual,
        "other_adjustments": other_adjustments_visual,
        "ads": ad_spend_visual,
        "cost_price": cost_price_visual,
        "tax": tax_visual,
    }
    financial_structure_day_payload = {
        "gross_revenue": gross_revenue_visual,
        "wb_realized_revenue": wb_realized_revenue_visual,
        "seller_payout": revenue_visual,
        "commission": commission_visual,
        "acquiring": acquiring_visual,
        "pvz_service": pvz_service_visual,
        "logistics": logistics_visual,
        "storage": storage_visual,
        "penalties": penalties_visual,
        "deductions": deductions_visual,
        "loyalty_program": loyalty_program_visual,
        "loyalty_points_withheld": loyalty_points_visual,
        "loyalty_total": loyalty_total_visual,
        "other_adjustments": other_adjustments_visual,
        "cost_price": cost_price_visual,
        "tax": tax_visual,
        "ads_spend": ad_spend_visual,
        "net_profit": net_profit_visual,
        "explained_net_profit": _round_or_none(explained_net_profit),
        "net_profit_explain_delta": net_profit_explain_delta,
    }

    top_growth_rows = _watchlist_rows(sku_watchlists, "top_growth", limit=30)
    top_risk_rows = _watchlist_rows(sku_watchlists, "top_risk", limit=30)
    dead_stock_rows = _watchlist_rows(sku_watchlists, "dead_stock", limit=30)
    ad_ineff_rows = _watchlist_rows(sku_watchlists, "ad_inefficiency", limit=30)
    conversion_drop_rows = _watchlist_rows(sku_watchlists, "conversion_drop", limit=30)
    sku_alerts = data.get("sku_alerts", {})
    if not isinstance(sku_alerts, dict):
        sku_alerts = {}
    health_payload = data.get("health_score", {})
    if not isinstance(health_payload, dict):
        health_payload = {}

    def _safe_sku_local(row: Dict[str, Any]) -> str:
        if not isinstance(row, dict):
            return ""
        return _sanitize_client_text(row.get("sku") or row.get("nm_id") or "")

    def _reason_local(row: Dict[str, Any], default_text: str) -> str:
        reason = _sanitize_client_text(
            row.get("reason")
            or row.get("issue_reason_ru")
            or row.get("funnel_issue_reason")
            or row.get("recommendation")
            or row.get("action")
            or ""
        )
        return reason or default_text

    def _health_score_local(row: Dict[str, Any], status_ru: str) -> float:
        default_map = {
            "Р РѕСЃС‚": 85.0,
            "РќРѕСЂРјР°Р»СЊРЅРѕ": 70.0,
            "Р РёСЃРє": 35.0,
            "Р›РёРєРІРёРґР°С†РёСЏ": 15.0,
        }
        score = _first_number_local(row.get("health_score"), row.get("score")) if isinstance(row, dict) else None
        attention = _first_number_local(row.get("attention_score")) if isinstance(row, dict) else None
        if score is None and attention is not None:
            if status_ru in {"Р РёСЃРє", "Р›РёРєРІРёРґР°С†РёСЏ"}:
                score = 100.0 - attention
            else:
                score = 60.0 + (100.0 - attention) * 0.25
        if score is None:
            score = default_map.get(status_ru, 60.0)
        return max(0.0, min(100.0, float(score)))

    sku_health_rows: List[Dict[str, Any]] = []
    health_seen: set[str] = set()

    def _status_from_health_token(token: Any) -> str:
        normalized = str(token or "").strip().lower()
        mapping = {
            "strong": "Р РѕСЃС‚",
            "healthy": "РќРѕСЂРјР°Р»СЊРЅРѕ",
            "unstable": "Р РёСЃРє",
            "risk": "Р РёСЃРє",
            "liquidate": "Р›РёРєРІРёРґР°С†РёСЏ",
            "liquidation": "Р›РёРєРІРёРґР°С†РёСЏ",
        }
        return mapping.get(normalized, "РќРѕСЂРјР°Р»СЊРЅРѕ")

    def _append_health_rows_from_payload(limit: int = 24) -> None:
        rows = health_payload.get("items", []) if isinstance(health_payload, dict) else []
        if not isinstance(rows, list):
            return
        for row in rows:
            if not isinstance(row, dict):
                continue
            sku = _safe_sku_local(row)
            if not sku or sku in health_seen:
                continue
            health_seen.add(sku)
            status_ru = _status_from_health_token(row.get("status") or row.get("health_status"))
            reasons = row.get("reasons", []) if isinstance(row.get("reasons"), list) else []
            reason_text = _sanitize_client_text(reasons[0] if reasons else row.get("reason") or "")
            if not reason_text:
                reason_text = "РќСѓР¶РµРЅ РґРѕРїРѕР»РЅРёС‚РµР»СЊРЅС‹Р№ РјРѕРЅРёС‚РѕСЂРёРЅРі РїРѕ SKU"
            sku_health_rows.append(
                {
                    "sku": sku,
                    "health_score": _first_number_local(row.get("health_score"), row.get("score")),
                    "status": status_ru,
                    "reason": reason_text,
                }
            )
            if len(sku_health_rows) >= limit:
                break

    def _append_health_rows(rows: List[Dict[str, Any]], status_ru: str, default_reason: str, limit: int = 12) -> None:
        for row in rows:
            if not isinstance(row, dict):
                continue
            sku = _safe_sku_local(row)
            if not sku or sku in health_seen:
                continue
            health_seen.add(sku)
            sku_health_rows.append(
                {
                    "sku": sku,
                    "health_score": _health_score_local(row, status_ru),
                    "status": status_ru,
                    "reason": _reason_local(row, default_reason),
                }
            )
            if len([x for x in sku_health_rows if str(x.get("status") or "") == status_ru]) >= limit:
                break

    _append_health_rows_from_payload(limit=24)
    _append_health_rows(top_growth_rows, "Р РѕСЃС‚", "РџРѕР»РѕР¶РёС‚РµР»СЊРЅР°СЏ РґРёРЅР°РјРёРєР° KPI")
    _append_health_rows(top_risk_rows, "Р РёСЃРє", "РќСѓР¶РЅР° РѕРїС‚РёРјРёР·Р°С†РёСЏ РєР°СЂС‚РѕС‡РєРё Рё С†РµРЅС‹")
    _append_health_rows(dead_stock_rows, "Р›РёРєРІРёРґР°С†РёСЏ", "РќРёР·РєР°СЏ РѕР±РѕСЂР°С‡РёРІР°РµРјРѕСЃС‚СЊ С‚РѕРІР°СЂР°")
    _append_health_rows(
        [row for row in liquidate_rows if isinstance(row, dict)],
        "Р›РёРєРІРёРґР°С†РёСЏ",
        "Р РµРєРѕРјРµРЅРґРѕРІР°РЅР° СѓСЃРєРѕСЂРµРЅРЅР°СЏ СЂР°СЃРїСЂРѕРґР°Р¶Р°",
    )

    normal_target = 14
    normal_added = 0
    for row in sku_metrics:
        if not isinstance(row, dict):
            continue
        sku = _safe_sku_local(row)
        if not sku or sku in health_seen:
            continue
        health_seen.add(sku)
        sku_health_rows.append(
            {
                "sku": sku,
                "health_score": _health_score_local(row, "РќРѕСЂРјР°Р»СЊРЅРѕ"),
                "status": "РќРѕСЂРјР°Р»СЊРЅРѕ",
                "reason": _reason_local(row, "РЎС‚Р°Р±РёР»СЊРЅР°СЏ РґРёРЅР°РјРёРєР° РїРѕ SKU"),
            }
        )
        normal_added += 1
        if normal_added >= normal_target:
            break

    computed_sku_status_counts = _sku_status_counts_from_health_rows(sku_health_rows)
    if sum(computed_sku_status_counts.values()) > 0:
        growth_count = int(computed_sku_status_counts.get("growth", 0) or 0)
        normal_count = int(computed_sku_status_counts.get("normal", 0) or 0)
        risk_count = int(computed_sku_status_counts.get("risk", 0) or 0)
        liquidation_count = int(computed_sku_status_counts.get("liquidation", 0) or 0)

    sku_status_counts = {
        "growth": int(growth_count or 0),
        "normal": int(normal_count or 0),
        "risk": int(risk_count or 0),
        "liquidation": int(liquidation_count or 0),
    }
    _assert_sku_status_counts_match(sku_status_counts, sku_health_rows)

    def _sku_list_local(rows: List[Dict[str, Any]], *, limit: int = 10) -> List[str]:
        result: List[str] = []
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            sku = _safe_sku_local(row)
            if not sku or sku in seen:
                continue
            seen.add(sku)
            result.append(sku)
            if len(result) >= limit:
                break
        return result

    risk_problem_rows = [row for row in top_risk_rows if isinstance(row, dict)] + [
        row for row in (fix_rows + watch_rows) if isinstance(row, dict)
    ]
    liquidation_problem_rows = [row for row in dead_stock_rows if isinstance(row, dict)] + [
        row for row in liquidate_rows if isinstance(row, dict)
    ]

    def _alert_sku_list(alert_types: set[str], *, limit: int = 10) -> List[str]:
        items = sku_alerts.get("items", []) if isinstance(sku_alerts, dict) else []
        if not isinstance(items, list):
            return []
        result: List[str] = []
        seen: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            sku = _safe_sku_local(item)
            if not sku or sku in seen:
                continue
            alerts = item.get("alerts", [])
            if not isinstance(alerts, list):
                alerts = []
            matched = False
            for alert in alerts:
                if not isinstance(alert, dict):
                    continue
                alert_type = str(alert.get("type") or "").strip().lower()
                if alert_type in alert_types:
                    matched = True
                    break
            if not matched:
                continue
            seen.add(sku)
            result.append(sku)
            if len(result) >= limit:
                break
        return result

    def _merge_sku_lists(*groups: List[str], limit: int = 10) -> List[str]:
        result: List[str] = []
        seen: set[str] = set()
        for group in groups:
            for sku in group:
                token = _sanitize_client_text(sku)
                if not token or token in seen:
                    continue
                seen.add(token)
                result.append(token)
                if len(result) >= limit:
                    return result
        return result

    views_for_problem = _first_number_local(funnel.get("views"), funnel.get("impressions"))
    orders_for_problem = _first_number_local(funnel.get("orders"), orders_visual)
    buyouts_for_problem = _first_number_local(funnel.get("buyouts"), buyouts_count_value)
    ads_orders_for_problem = _first_number_local(portfolio_orders_from_ads, portfolio_buyouts_from_ads)
    traffic_data_sufficient = bool(views_for_problem is not None and views_for_problem > 0)
    conversion_data_sufficient = bool(
        (traffic_data_sufficient and orders_for_problem is not None and orders_for_problem > 0)
        or (orders_for_problem is not None and orders_for_problem > 0 and buyouts_for_problem is not None)
    )
    ads_data_sufficient = bool(
        int(data.get("ads_rows_count", 0) or 0) > 0
        or (ad_spend_visual is not None and abs(float(ad_spend_visual)) > 1e-9)
        or (portfolio_revenue_from_ads is not None and abs(float(portfolio_revenue_from_ads)) > 1e-9)
        or (ads_orders_for_problem is not None and abs(float(ads_orders_for_problem)) > 1e-9)
    )

    key_problem_reasons: Dict[str, str] = {}
    key_problem_data_status: Dict[str, str] = {}

    if traffic_data_sufficient:
        low_traffic_skus = _merge_sku_lists(
            _alert_sku_list({"traffic_drop", "ctr_drop"}, limit=12),
            limit=10,
        )
        key_problem_data_status["low_traffic"] = "sufficient"
        if not low_traffic_skus:
            key_problem_reasons["low_traffic"] = "Сигналы низкого трафика не выявлены"
    elif orders_for_problem is not None and orders_for_problem > 0:
        low_traffic_skus = []
        key_problem_data_status["low_traffic"] = "partial"
        key_problem_reasons["low_traffic"] = "Признак низкого трафика: есть продажи, но недостаточно данных по просмотрам"
    else:
        low_traffic_skus = []
        key_problem_data_status["low_traffic"] = "insufficient"
        key_problem_reasons["low_traffic"] = "Нет данных по просмотрам за период"

    if conversion_data_sufficient:
        conversion_drop_skus = _merge_sku_lists(
            _sku_list_local([row for row in conversion_drop_rows if isinstance(row, dict)], limit=12),
            _alert_sku_list({"orders_drop", "buyout_drop", "cart_conversion_drop"}, limit=12),
            limit=10,
        )
        key_problem_data_status["conversion_drop"] = "sufficient"
        if not conversion_drop_skus:
            key_problem_reasons["conversion_drop"] = "Сигналы падения конверсии не выявлены"
    elif orders_for_problem is not None and orders_for_problem > 0:
        conversion_drop_skus = []
        key_problem_data_status["conversion_drop"] = "partial"
        key_problem_reasons["conversion_drop"] = (
            "Признак проблем с конверсией: есть заказы, но неполные данные по верхним этапам воронки"
        )
    else:
        conversion_drop_skus = []
        key_problem_data_status["conversion_drop"] = "insufficient"
        key_problem_reasons["conversion_drop"] = "Нет полной воронки за период"

    if ads_data_sufficient:
        inefficient_ads_skus = _merge_sku_lists(
            _sku_list_local([row for row in ad_ineff_rows if isinstance(row, dict)], limit=12),
            _alert_sku_list({"ad_inefficiency"}, limit=12),
            limit=10,
        )
        key_problem_data_status["inefficient_ads"] = "sufficient"
        if not inefficient_ads_skus and ad_spend_visual is not None and ad_spend_visual > 0:
            key_problem_data_status["inefficient_ads"] = "partial"
            key_problem_reasons["inefficient_ads"] = (
                "Признак проблем с рекламой: расход есть, подтвержденных заказов по рекламе недостаточно"
            )
        elif not inefficient_ads_skus:
            key_problem_reasons["inefficient_ads"] = "Сигналы неэффективной рекламы не выявлены"
    elif ad_spend_visual is not None and ad_spend_visual > 0:
        inefficient_ads_skus = []
        key_problem_data_status["inefficient_ads"] = "partial"
        key_problem_reasons["inefficient_ads"] = (
            "Признак проблем с рекламой: расход есть, подтвержденных заказов по рекламе недостаточно"
        )
    else:
        inefficient_ads_skus = []
        key_problem_data_status["inefficient_ads"] = "insufficient"
        key_problem_reasons["inefficient_ads"] = "Нет связки расход → заказ/выкуп для оценки рекламы"

    liquidation_skus = _merge_sku_lists(
        _sku_list_local(liquidation_problem_rows, limit=12),
        _alert_sku_list({"dead_stock", "zero_sales_with_stock"}, limit=12),
        limit=10,
    )
    key_problem_data_status["liquidation_skus"] = "sufficient"
    if not liquidation_skus:
        key_problem_reasons["liquidation_skus"] = "SKU в зоне ликвидации не выявлены"

    key_problems_payload: Dict[str, List[str]] = {
        "low_traffic": low_traffic_skus,
        "conversion_drop": conversion_drop_skus,
        "inefficient_ads": inefficient_ads_skus,
        "liquidation_skus": liquidation_skus,
    }

    key_problem_cards: List[Dict[str, Any]] = []
    missing_problem_checks: List[str] = []

    def _append_problem_card(title: str, key: str) -> None:
        state = normalize_section_state(
            key_problem_data_status.get(key, "insufficient"),
            default=SECTION_STATE_COMPACT_NOTE,
        )
        reason = _sanitize_client_text(key_problem_reasons.get(key) or "")
        skus = key_problems_payload.get(key, [])
        if skus:
            key_problem_cards.append(
                {
                    "title": title,
                    "key": key,
                    "state": SECTION_STATE_FULL,
                    "skus": skus[:8],
                    "reason": reason,
                }
            )
            return
        if state == SECTION_STATE_PARTIAL and reason:
            key_problem_cards.append(
                {
                    "title": title,
                    "key": key,
                    "state": SECTION_STATE_PARTIAL,
                    "skus": [],
                    "reason": reason,
                }
            )
            return
        if state in {"insufficient", SECTION_STATE_COMPACT_NOTE} and reason:
            missing_problem_checks.append(f"{title}: {reason}")

    _append_problem_card("Низкий трафик", "low_traffic")
    _append_problem_card("Падение конверсии", "conversion_drop")
    _append_problem_card("Неэффективная реклама", "inefficient_ads")
    if liquidation_skus:
        key_problem_cards.append(
            {
                "title": "SKU в зоне ликвидации",
                "key": "liquidation_skus",
                "state": SECTION_STATE_FULL,
                "skus": liquidation_skus[:8],
                "reason": _sanitize_client_text(key_problem_reasons.get("liquidation_skus") or ""),
            }
        )

    if missing_problem_checks:
        key_problem_cards.append(
            {
                "title": "Что не удалось проверить",
                "key": "missing_checks",
                "state": SECTION_STATE_COMPACT_NOTE,
                "skus": [],
                "reason": "Нужны дополнительные источники данных:",
                "notes": missing_problem_checks[:4],
            }
        )

    def _action_ru_local(raw_action: Any, group: str) -> str:
        token = str(raw_action or "").strip().lower().replace("_", " ")
        if "increase ads" in token or "increase" in token:
            return "РЈСЃРёР»РёС‚СЊ СЂРµРєР»Р°РјСѓ"
        if "improve listing" in token or "improve" in token:
            return "Р”РѕСЂР°Р±РѕС‚Р°С‚СЊ РєР°СЂС‚РѕС‡РєСѓ"
        if "rebalance stock" in token or "rebalance" in token:
            return "РџРµСЂРµСЂР°СЃРїСЂРµРґРµР»РёС‚СЊ РѕСЃС‚Р°С‚РєРё"
        if "discount" in token or "remove" in token:
            return "РЎРЅРёР·РёС‚СЊ С†РµРЅСѓ РёР»Рё РІС‹РІРѕРґРёС‚СЊ С‚РѕРІР°СЂ"
        if "monitor" in token:
            return "РќР°Р±Р»СЋРґР°С‚СЊ"
        defaults = {
            "p1": "РЎСЂРѕС‡РЅР°СЏ РєРѕСЂСЂРµРєС‚РёСЂРѕРІРєР° SKU",
            "p2": "РћРїС‚РёРјРёР·Р°С†РёСЏ SKU",
            "p3": "РњРѕРЅРёС‚РѕСЂРёРЅРі SKU",
        }
        return defaults.get(group, "Р”РµР№СЃС‚РІРёРµ РїРѕ SKU")

    def _is_non_actionable_reason(reason_text: str) -> bool:
        token = _sanitize_client_text(reason_text).lower()
        if not token:
            return True
        weak_markers = (
            "недостаточно данных",
            "insufficient data",
            "non-api",
            "нет данных",
            "данные отсутствуют",
            "not enough data",
        )
        return any(marker in token for marker in weak_markers)

    def _business_reason_from_row(row: Dict[str, Any]) -> str:
        ad_spend_num = _first_number_local(row.get("ads_spend"), row.get("ad_spend"), row.get("ads_cost"))
        ad_orders_num = _first_number_local(row.get("ads_orders"), row.get("orders_from_ads"))
        orders_num = _first_number_local(row.get("orders"), row.get("orders_count"))
        revenue_num = _first_number_local(row.get("revenue"), row.get("orders_amount"), row.get("buyouts_amount"))
        profit_num = _first_number_local(row.get("profit"), row.get("net_profit"))
        stock_num = _first_number_local(
            row.get("stock"),
            row.get("stock_left"),
            row.get("stock_qty"),
            row.get("inventory"),
        )
        funnel_issue_type = str(row.get("funnel_issue_type") or "").strip().lower()
        health_tier = str(row.get("health_tier") or "").strip().lower()
        if ad_spend_num is not None and ad_spend_num > 0 and (ad_orders_num is None or ad_orders_num <= 0):
            return "Расходы на рекламу есть, подтвержденных заказов недостаточно"
        if stock_num is not None and stock_num > 0 and (orders_num is None or orders_num <= 0):
            return "Риск зависших остатков"
        if stock_num is not None and stock_num > 0 and orders_num is not None and orders_num > 0 and stock_num > orders_num * 5:
            return "Низкая динамика продаж относительно остатков"
        if profit_num is not None and profit_num <= 0 and (revenue_num is None or revenue_num >= 0):
            return "Низкий вклад SKU в прибыль"
        if funnel_issue_type in {"traffic_drop", "low_traffic", "conversion_drop", "insufficient_data"}:
            return "Товар требует проверки карточки и трафика"
        if health_tier in {"risk", "unstable", "liquidate", "liquidation"}:
            return "Товар требует проверки карточки и трафика"
        return ""

    def _recommendation_rows(rows: List[Dict[str, Any]], *, group: str, limit: int = 10) -> List[Dict[str, str]]:
        result: List[Dict[str, str]] = []
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            sku = _safe_sku_local(row)
            if not sku or sku in seen:
                continue
            seen.add(sku)
            reason = _reason_local(row, "")
            if _is_non_actionable_reason(reason):
                reason = _business_reason_from_row(row)
            reason = _sanitize_client_text(reason)
            if not reason:
                continue
            result.append(
                {
                    "action": _action_ru_local(row.get("action"), group),
                    "reason": reason,
                    "sku": sku,
                }
            )
            if len(result) >= limit:
                break
        return result

    p1_recommendations = _recommendation_rows(
        [row for row in (liquidate_rows + fix_rows) if isinstance(row, dict)],
        group="p1",
        limit=12,
    )
    p2_recommendations = _recommendation_rows(
        [row for row in scale_rows if isinstance(row, dict)],
        group="p2",
        limit=12,
    )
    p3_recommendations = _recommendation_rows(
        [row for row in watch_rows if isinstance(row, dict)],
        group="p3",
        limit=12,
    )
    if not p3_recommendations:
        p3_recommendations = _recommendation_rows(
            [row for row in top_risk_rows if isinstance(row, dict)],
            group="p3",
            limit=12,
        )

    def _money_str_local(value: Any) -> str:
        number = _first_number_local(value)
        if number is None:
            return "РЅРµС‚ РґР°РЅРЅС‹С…"
        return f"{int(round(number)):,}".replace(",", " ") + " в‚Ѕ"

    kernel_sku_financials_payload = data.get("kernel_sku_financials", {})
    if not isinstance(kernel_sku_financials_payload, dict):
        kernel_sku_financials_payload = {}
    if not kernel_sku_financials_payload:
        metrics_payload = data.get("metrics", {})
        if isinstance(metrics_payload, dict):
            financial_kernel_payload = metrics_payload.get("financial_kernel", {})
            if isinstance(financial_kernel_payload, dict):
                from_metrics = financial_kernel_payload.get("sku_financials", {})
                if isinstance(from_metrics, dict):
                    kernel_sku_financials_payload = from_metrics

    sku_profit_candidates: List[Dict[str, Any]] = []
    if isinstance(kernel_sku_financials_payload, dict) and kernel_sku_financials_payload:
        for sku_key, row in kernel_sku_financials_payload.items():
            if not isinstance(row, dict):
                continue
            sku = _safe_sku_local({"sku": sku_key})
            if not sku:
                continue
            revenue_num = _first_number_local(row.get("payout"), row.get("net_revenue"), row.get("sales_revenue"))
            profit_num = _first_number_local(row.get("profit"))
            if revenue_num is None and profit_num is None:
                continue
            sku_profit_candidates.append(
                {
                    "sku": sku,
                    "revenue_num": revenue_num,
                    "ads_num": None,
                    "profit_num": profit_num,
                }
            )
    else:
        for row in sku_metrics:
            if not isinstance(row, dict):
                continue
            sku = _safe_sku_local(row)
            if not sku:
                continue
            revenue_num = _first_number_local(row.get("revenue"), row.get("orders_amount"), row.get("buyouts_amount"))
            ads_num = _first_number_local(row.get("ads_spend"), row.get("ad_spend"), row.get("ads_cost"))
            profit_num = _first_number_local(row.get("profit"), row.get("net_profit"))
            if revenue_num is None and ads_num is None and profit_num is None:
                continue
            sku_profit_candidates.append(
                {
                    "sku": sku,
                    "revenue_num": revenue_num,
                    "ads_num": ads_num,
                    "profit_num": profit_num,
                }
            )

    sku_profit_candidates = sorted(
        sku_profit_candidates,
        key=lambda item: (
            float(item.get("profit_num") or -10**12),
            float(item.get("revenue_num") or -10**12),
        ),
        reverse=True,
    )

    sku_profit_rows: List[Dict[str, str]] = []
    seen_profit_skus: set[str] = set()
    for row in sku_profit_candidates:
        sku = str(row.get("sku") or "").strip()
        if not sku or sku in seen_profit_skus:
            continue
        seen_profit_skus.add(sku)
        sku_profit_rows.append(
            {
                "sku": sku,
                "revenue": _money_str_local(row.get("revenue_num")),
                "ads_spend": _money_str_local(row.get("ads_num")),
                "profit": _money_str_local(row.get("profit_num")),
            }
        )
        if len(sku_profit_rows) >= 28:
            break

    financial_events_payload: List[Dict[str, str]] = []
    event_rows = event_ledger.get("events", []) if isinstance(event_ledger, dict) else []
    if isinstance(event_rows, list):
        for event in event_rows:
            if not isinstance(event, dict):
                continue
            title = _sanitize_client_text(
                event.get("event")
                or event.get("name")
                or event.get("category")
                or event.get("type")
                or ""
            )
            raw_field = _sanitize_client_text(event.get("field") or event.get("metric") or "")
            amount = _first_number_local(event.get("amount"), event.get("value"), event.get("sum"))
            source = _sanitize_client_text(event.get("source") or event.get("data_source") or "")
            event_line = title or raw_field
            if not event_line and amount is None:
                continue
            financial_events_payload.append(
                {
                    "event": event_line or "Событие",
                    "field": raw_field or "нет данных",
                    "amount": _money_str_local(amount) if amount is not None else "нет данных",
                    "source": source or "нет данных",
                }
            )
            if len(financial_events_payload) >= 36:
                break

    orders_exact_value = _first_number_local(orders_count_raw_value, order_kpi.get("orders_count"))
    orders_surrogate_value = _first_number_local(
        funnel.get("orders"),
        daily_kpi.get("daily_orders_count"),
        data.get("daily_orders_count"),
        data.get("orders"),
        data.get("sales_activity_qty"),
        funnel.get("buyouts"),
        buyouts_count_value,
    )
    orders_kpi_payload = build_kpi_display_payload(
        value=orders_exact_value,
        fallback_value=orders_surrogate_value,
        missing_reason="Нет подтвержденного источника заказов за период",
        label="Заказы",
        fallback_label="Заказы (оценка)",
        value_type="int",
    )
    orders_visual = _first_number_local(orders_exact_value, orders_surrogate_value)

    profit_missing_reason = (
        "Нет себестоимости для точного расчета прибыли"
        if cost_price_visual is None
        else "Нет данных для расчета чистой прибыли"
    )
    profit_kpi_payload = build_kpi_display_payload(
        value=net_profit_exact_visual,
        fallback_value=operating_profit_without_cogs,
        missing_reason=profit_missing_reason,
        label="Чистая прибыль",
        fallback_label="Прибыль без себестоимости",
        value_type="money",
    )
    payout_kpi_payload = build_kpi_display_payload(
        value=revenue_visual,
        missing_reason="Нет подтвержденной суммы к перечислению продавцу",
        label="К перечислению продавцу",
        value_type="money",
    )
    ads_kpi_payload = build_kpi_display_payload(
        value=ad_spend_visual,
        missing_reason="Нет данных по расходам на рекламу",
        label="Расход на рекламу",
        value_type="money",
    )

    kpi_cards_payload: List[Dict[str, Any]] = []
    for item in (payout_kpi_payload, profit_kpi_payload, ads_kpi_payload, orders_kpi_payload):
        state = normalize_section_state(item.get("state"), default=SECTION_STATE_HIDDEN)
        if state == SECTION_STATE_HIDDEN:
            continue
        card_payload = {
            "label": str(item.get("label") or item.get("base_label") or ""),
            "value": item.get("value"),
            "value_type": str(item.get("value_type") or "int"),
            "state": state,
        }
        reason_text = _sanitize_client_text(item.get("reason") or "")
        if reason_text:
            card_payload["reason"] = reason_text
        kpi_cards_payload.append(card_payload)

    funnel_views = _first_number_local(funnel.get("views"), funnel.get("impressions"))
    funnel_clicks = _first_number_local(funnel.get("clicks"), data.get("ads_clicks"))
    funnel_add_to_cart = _first_number_local(funnel.get("add_to_cart"), funnel.get("cart_count"))
    funnel_orders = _first_number_local(funnel.get("orders"), orders_visual)
    funnel_buyouts = _first_number_local(funnel.get("buyouts"), buyouts_count_value)
    funnel_stage_rows = [
        {"key": "views", "label": "Показы", "value": funnel_views},
        {"key": "clicks", "label": "Клики", "value": funnel_clicks},
        {"key": "add_to_cart", "label": "Корзина", "value": funnel_add_to_cart},
        {"key": "orders", "label": "Заказы", "value": funnel_orders},
        {"key": "buyouts", "label": "Выкупы", "value": funnel_buyouts},
    ]
    funnel_present_rows = [row for row in funnel_stage_rows if row.get("value") is not None]
    funnel_full = len([row for row in funnel_stage_rows if row.get("value") not in {None, 0}]) >= 4
    funnel_partial = bool(funnel_present_rows)
    funnel_note = (
        ""
        if funnel_full
        else (
            "Воронка построена частично по доступным данным"
            if funnel_partial
            else "Нет полной воронки за период"
        )
    )
    funnel_state_payload = build_section_display_state(
        has_full_data=funnel_full,
        has_partial_data=funnel_partial,
        note=funnel_note,
        allow_hidden=False,
    )
    funnel_visual_payload = {
        "state": normalize_section_state(funnel_state_payload.get("state"), default=SECTION_STATE_COMPACT_NOTE),
        "note": _sanitize_client_text(funnel_state_payload.get("note") or ""),
        "views": funnel_views,
        "clicks": funnel_clicks,
        "add_to_cart": funnel_add_to_cart,
        "orders": funnel_orders,
        "buyouts": funnel_buyouts,
        "stages": funnel_stage_rows,
        "table_rows": [row for row in funnel_stage_rows if row.get("value") is not None],
        "order_to_buyout_over_100": bool(funnel.get("order_to_buyout_over_100", False)),
        "order_to_buyout_note": _sanitize_client_text(str(funnel.get("order_to_buyout_note") or "")),
    }

    ads_revenue_visual = _first_number_local(portfolio_revenue_from_ads, data.get("ads_revenue"), email_summary_payload.get("ads_revenue"))
    ads_orders_visual = _first_number_local(portfolio_orders_from_ads, portfolio_buyouts_from_ads, funnel_orders)
    ads_problem_skus = _merge_sku_lists(
        _sku_list_local([row for row in ad_ineff_rows if isinstance(row, dict)], limit=12),
        _alert_sku_list({"ad_inefficiency"}, limit=12),
        limit=8,
    )
    ads_spend_share_pct = None
    if ad_spend_visual is not None and revenue_visual is not None and abs(float(revenue_visual)) > 1e-9:
        ads_spend_share_pct = round(float(ad_spend_visual) / float(revenue_visual) * 100.0, 2)
    ads_summary_rows: List[Dict[str, Any]] = []
    if ad_spend_visual is not None:
        ads_summary_rows.append({"metric": "Расход на рекламу", "value": ad_spend_visual, "value_type": "money"})
    if ads_orders_visual is not None:
        ads_summary_rows.append({"metric": "Заказы из рекламы", "value": ads_orders_visual, "value_type": "int"})
    if ads_revenue_visual is not None:
        ads_summary_rows.append({"metric": "Выручка от рекламы", "value": ads_revenue_visual, "value_type": "money"})
    if ads_spend_share_pct is not None:
        ads_summary_rows.append(
            {
                "metric": "Доля рекламных расходов в перечислении",
                "value": ads_spend_share_pct,
                "value_type": "pct",
            }
        )
    if ads_problem_skus:
        ads_summary_rows.append(
            {
                "metric": "Проблемные SKU по рекламе",
                "value": ", ".join(ads_problem_skus[:5]),
                "value_type": "text",
            }
        )
    ads_table_rows: List[Dict[str, Any]] = []
    for row in (top_unprofitable_queries_ads + top_profitable_queries_ads):
        if not isinstance(row, dict):
            continue
        query = _sanitize_client_text(row.get("query") or row.get("name") or "")
        if not query:
            continue
        ads_table_rows.append(
            {
                "query": query,
                "spend": _first_number_local(row.get("ad_spend"), row.get("spend"), row.get("cost")),
                "orders": _first_number_local(row.get("orders"), row.get("orders_from_ads")),
                "revenue": _first_number_local(row.get("revenue"), row.get("revenue_from_ads")),
            }
        )
        if len(ads_table_rows) >= 8:
            break
    ads_full = bool(ad_spend_visual is not None and ads_revenue_visual is not None and ad_spend_visual > 0 and ads_revenue_visual > 0)
    ads_partial = bool(ads_summary_rows or ads_table_rows)
    ads_note = (
        ""
        if ads_full
        else (
            "Данные по рекламе доступны частично, вывод построен по доступным метрикам"
            if ads_partial
            else "Данных для оценки рекламы недостаточно: не найдено связки расход → заказ/выкуп"
        )
    )
    ads_state_payload = build_section_display_state(
        has_full_data=ads_full,
        has_partial_data=ads_partial,
        note=ads_note,
        allow_hidden=False,
    )
    ads_visual_payload = {
        "state": normalize_section_state(ads_state_payload.get("state"), default=SECTION_STATE_COMPACT_NOTE),
        "note": _sanitize_client_text(ads_state_payload.get("note") or ""),
        "ad_spend": ad_spend_visual,
        "ad_revenue": ads_revenue_visual,
        "orders_from_ads": ads_orders_visual,
        "spend_share_pct": ads_spend_share_pct,
        "summary_rows": ads_summary_rows,
        "table_rows": ads_table_rows,
        "problem_skus": ads_problem_skus,
    }

    recommendation_groups = {
        "p1": p1_recommendations,
        "p2": p2_recommendations,
        "p3": p3_recommendations,
    }
    recommendation_full = any(recommendation_groups.get(group) for group in ("p1", "p2", "p3"))
    recommendation_state = build_section_display_state(
        has_full_data=recommendation_full,
        has_partial_data=False,
        note="Нет рекомендаций с достаточным уровнем сигнала за период",
        allow_hidden=False,
    )
    key_problem_state = build_section_display_state(
        has_full_data=any(card.get("state") == SECTION_STATE_FULL for card in key_problem_cards),
        has_partial_data=bool(key_problem_cards),
        note="",
        allow_hidden=False,
    )

    section_states_payload = {
        "ads_efficiency": normalize_section_state(ads_visual_payload.get("state"), default=SECTION_STATE_COMPACT_NOTE),
        "funnel": normalize_section_state(funnel_visual_payload.get("state"), default=SECTION_STATE_COMPACT_NOTE),
        "key_problems": normalize_section_state(key_problem_state.get("state"), default=SECTION_STATE_COMPACT_NOTE),
        "recommendations": normalize_section_state(recommendation_state.get("state"), default=SECTION_STATE_COMPACT_NOTE),
    }
    section_confidence_payload = {
        key: ("low" if non_api_mode else "medium")
        for key in section_states_payload
    }

    visual_payload: Dict[str, Any] = {
        "seller_id": seller_id_for_visual,
        "run_date": report_date_for_visual,
        "operational_day": operational_day_for_visual,
        "data_mode": data_mode,
        "non_api_mode": non_api_mode,
        "mode_notice": non_api_notice if non_api_mode else "",
        "preview_dir": out_dir,
        "kpi_cards": kpi_cards_payload,
        "kpi_display": {
            "seller_payout": payout_kpi_payload,
            "profit": profit_kpi_payload,
            "ads_spend": ads_kpi_payload,
            "orders": orders_kpi_payload,
        },
        "section_states": section_states_payload,
        "section_confidence": section_confidence_payload,
        "expense_structure": expense_structure_payload,
        "financial_structure_day": financial_structure_day_payload,
        "funnel": funnel_visual_payload,
        "sku_status": sku_status_counts,
        "ads_efficiency": ads_visual_payload,
        "sku_health_rows": sku_health_rows[:36],
        "key_problems": key_problems_payload,
        "key_problem_reasons": key_problem_reasons,
        "key_problem_data_status": key_problem_data_status,
        "key_problem_cards": key_problem_cards,
        "ai_recommendations": recommendation_groups,
        "recommendations_state": normalize_section_state(recommendation_state.get("state"), default=SECTION_STATE_COMPACT_NOTE),
        "recommendations_note": _sanitize_client_text(recommendation_state.get("note") or ""),
        "sku_profit_rows": sku_profit_rows,
        "financial_events": financial_events_payload,
    }

    discovered_files_payload = data.get("discovered_files", {})
    if not isinstance(discovered_files_payload, dict):
        discovered_files_payload = {}

    def _files_count(key: str) -> int:
        value = discovered_files_payload.get(key, [])
        return len(value) if isinstance(value, list) else 0

    api_debug_payload = data.get("api_debug", {})
    if not isinstance(api_debug_payload, dict):
        api_debug_payload = {}

    print(
        "[pipeline] source_files_loaded "
        f"sales={_files_count('sales')} ads={_files_count('ads')} "
        f"stocks={_files_count('stocks')} unknown={_files_count('unknown')}"
    )

    def _short_file_list(key: str, limit: int = 3) -> str:
        values = discovered_files_payload.get(key, [])
        if not isinstance(values, list):
            return ""
        names = [os.path.basename(str(value)) for value in values if str(value).strip()]
        if not names:
            return ""
        shown = names[: max(1, int(limit))]
        suffix = f",+{len(names) - len(shown)}" if len(names) > len(shown) else ""
        return ",".join(shown) + suffix

    print(
        "[pipeline] source_files_list "
        f"sales={_short_file_list('sales')} ads={_short_file_list('ads')} "
        f"stocks={_short_file_list('stocks')} unknown={_short_file_list('unknown')}"
    )
    print(
        "[pipeline] rows_per_source "
        f"orders_rows={int(api_debug_payload.get('orders_rows', 0) or 0)} "
        f"buyouts_rows={int(api_debug_payload.get('sales_rows', 0) or 0)} "
        f"financial_rows={int(api_debug_payload.get('financial_rows', 0) or 0)} "
        f"ads_rows={int(api_debug_payload.get('ads_rows', 0) or 0)} "
        f"stocks_rows={int(api_debug_payload.get('stocks_rows', 0) or 0)}"
    )
    print(
        "[pipeline] finance_components "
        f"gross_revenue={_round_or_none(gross_revenue_visual)} "
        f"wb_realized_revenue={_round_or_none(wb_realized_revenue_visual)} "
        f"seller_payout={_round_or_none(revenue_visual)} "
        f"commission={_round_or_none(commission_visual)} acquiring={_round_or_none(acquiring_visual)} "
        f"pvz_service={_round_or_none(pvz_service_visual)} logistics={_round_or_none(logistics_visual)} "
        f"storage={_round_or_none(storage_visual)} deductions={_round_or_none(deductions_visual)} "
        f"loyalty_total={_round_or_none(loyalty_total_visual)} "
        f"other_adjustments={_round_or_none(other_adjustments_visual)} tax={_round_or_none(tax_visual)} "
        f"ads_spend={_round_or_none(ad_spend_visual)} net_profit={_round_or_none(net_profit_visual)} "
        f"explained_net_profit={_round_or_none(explained_net_profit)} delta={_round_or_none(net_profit_explain_delta)}"
    )
    print(
        "[pipeline] final_metric_mapping "
        f"orders={_round_or_none(orders_visual)} buyouts={_round_or_none(buyouts_count_value)} "
        f"views={_round_or_none(_first_number_local(funnel.get('views'), funnel.get('impressions')))} "
        f"add_to_cart={_round_or_none(_first_number_local(funnel.get('add_to_cart'), funnel.get('cart_count')))} "
        f"seller_payout={_round_or_none(revenue_visual)} net_profit={_round_or_none(net_profit_visual)}"
    )
    print(
        "[pipeline] status_counts "
        f"growth={sku_status_counts.get('growth', 0)} normal={sku_status_counts.get('normal', 0)} "
        f"risk={sku_status_counts.get('risk', 0)} liquidation={sku_status_counts.get('liquidation', 0)} "
        f"table_rows={len(sku_health_rows[:36])}"
    )
    print(
        "[pipeline] mode_status "
        f"source_mode={source_mode or 'unknown'} data_mode={data_mode} "
        f"non_api_mode={str(non_api_mode).lower()}"
    )

    font_info = write_daily_bi_pdf(os.path.join(out_dir, "report.pdf"), visual_payload)
    print(
        "[pipeline] pdf_generated "
        f"path={os.path.join(out_dir, 'report.pdf')} pages={font_info.get('pages', '')} "
        f"sku_health_rows={len(sku_health_rows[:36])} "
        f"p1={len(p1_recommendations)} p2={len(p2_recommendations)} p3={len(p3_recommendations)}"
    )
    job["pdf_font"] = {
        "family": font_info.get("family", ""),
        "regular": font_info.get("regular", ""),
        "bold": font_info.get("bold", ""),
    }
    email_summary = job.get("email_summary", {}) if isinstance(job.get("email_summary"), dict) else {}
    seller_id_value = str(data.get("seller_id") or "")
    report_date_value = str(data.get("run_date") or "")
    operational_day_value = str(event_date_model.get("operational_date") or report_date_value)
    email_subject_value = build_daily_email_subject(seller_id=seller_id_value, run_date=report_date_value)
    email_body_text_value = ""
    body_builder = globals().get("_build_management_email_body")
    if callable(body_builder):
        try:
            email_body_text_value = build_daily_email_body(
                seller_id=seller_id_value,
                run_date=report_date_value,
                email_summary=email_summary if isinstance(email_summary, dict) else {},
                build_body=body_builder,
            )
        except Exception:
            email_body_text_value = ""
    if not email_body_text_value:
        email_body_text_value = str(data.get("ai_day_conclusion") or "")
    render_warnings: List[str] = []
    if isinstance(report_guardrails, dict):
        notices = report_guardrails.get("notices", [])
        if isinstance(notices, list):
            render_warnings.extend(str(item).strip() for item in notices if str(item).strip())
    render_warnings.extend(
        str(item.get("message") or "").strip()
        for item in important_warnings
        if isinstance(item, dict) and str(item.get("message") or "").strip()
    )
    seen_render_warnings: set[str] = set()
    deduped_render_warnings: List[str] = []
    for warning_line in render_warnings:
        if warning_line in seen_render_warnings:
            continue
        seen_render_warnings.add(warning_line)
        deduped_render_warnings.append(warning_line)

    report_meta: Dict[str, Any] = {
        "seller_id": seller_id_value,
        "report_date": report_date_value,
        "operational_day": operational_day_value,
        "email_subject": email_subject_value,
        "email_body_text": email_body_text_value,
        "financial_interpretation": "provisional" if financial_finality_status != "final" else "final",
        "render_warnings": deduped_render_warnings,
        "pdf_path": os.path.join(out_dir, "report.pdf"),
        "font": job["pdf_font"],
        "pages": int(str(font_info.get("pages", "1"))),
        "visual_previews": font_info.get("preview_images", []),
        "data_mode": data_mode,
        "non_api_mode": non_api_mode,
        "mode_notice": non_api_notice if non_api_mode else "",
        "section_states": section_states_payload,
        "section_confidence": section_confidence_payload,
        "kpi_display": visual_payload.get("kpi_display", {}),
        "daily_commerce_kpi": {
            "daily_orders_count": _int_or_none(orders_count_value),
            "daily_orders_amount": _round_or_none(orders_amount_value),
            "daily_buyouts_count": _int_or_none(buyouts_count_value),
            "daily_buyouts_amount": _round_or_none(buyouts_amount_value),
            "avg_check": _round_or_none(avg_check_value),
            "views": _int_or_none(funnel.get("views", funnel.get("impressions"))),
            "add_to_cart": _int_or_none(funnel.get("add_to_cart", funnel.get("cart_count"))),
            "view_to_order_conversion": _round_or_none(
                funnel.get("view_to_order_conversion", funnel.get("click_to_order_conversion_pct"))
            ),
            "cart_rate": _round_or_none(funnel.get("cart_rate", funnel.get("cart_conversion_pct"))),
            "cart_to_order": _round_or_none(funnel.get("cart_to_order")),
            "buyout_rate": _round_or_none(funnel.get("buyout_rate", funnel.get("order_to_buyout_conversion_pct"))),
            "order_to_buyout_over_100": bool(funnel.get("order_to_buyout_over_100", False)),
            "order_to_buyout_note": str(funnel.get("order_to_buyout_note") or ""),
            "cpo": _round_or_none(funnel.get("cpo", funnel.get("CPO"))),
            "data_source_orders": str(daily_kpi.get("data_source_orders") or _SOURCE_UNKNOWN),
            "data_source_orders_count": str(daily_kpi.get("data_source_orders_count") or daily_kpi.get("data_source_orders") or _SOURCE_UNKNOWN),
            "data_source_orders_amount": str(daily_kpi.get("data_source_orders_amount") or _SOURCE_UNKNOWN),
            "data_source_buyouts": str(daily_kpi.get("data_source_buyouts") or _SOURCE_UNKNOWN),
            "data_source_buyouts_count": str(daily_kpi.get("data_source_buyouts_count") or daily_kpi.get("data_source_buyouts") or _SOURCE_UNKNOWN),
            "data_source_buyouts_amount": str(daily_kpi.get("data_source_buyouts_amount") or _SOURCE_UNKNOWN),
            "orders_count_confirmed": bool(daily_kpi.get("orders_count_confirmed", False)),
            "buyouts_count_confirmed": bool(daily_kpi.get("buyouts_count_confirmed", False)),
            "display": {
                "daily_orders_count": format_int_or_unknown(orders_count_value, unknown_label=NO_DATA_LABEL),
                "daily_orders_amount": format_money_or_unknown(orders_amount_value, unknown_label=NO_DATA_LABEL),
                "daily_buyouts_count": format_int_or_unknown(buyouts_count_value, unknown_label=NO_DATA_LABEL),
                "daily_buyouts_amount": format_money_or_unknown(buyouts_amount_value, unknown_label=NO_DATA_LABEL),
                "avg_check": format_money_or_unknown(avg_check_value, unknown_label=NO_DATA_LABEL),
            },
        },
        "daily_financial_kpi": {
            "seller_payout": _round_or_none(revenue_visual),
            "gross_revenue": _round_or_none(gross_revenue_visual),
            "wb_realized_revenue": _round_or_none(wb_realized_revenue_visual),
            "revenue": _round_or_none(revenue_visual),
            "cost_price": _round_or_none(cost_price_visual),
            "wb_commission": _round_or_none(commission_visual),
            "acquiring": _round_or_none(acquiring_visual),
            "pvz_service": _round_or_none(pvz_service_visual),
            "logistics": _round_or_none(logistics_visual),
            "storage": _round_or_none(storage_visual),
            "penalties": _round_or_none(penalties_visual),
            "deductions": _round_or_none(deductions_visual),
            "loyalty_program": _round_or_none(loyalty_program_visual),
            "loyalty_points_withheld": _round_or_none(loyalty_points_visual),
            "loyalty_total": _round_or_none(_nz(loyalty_program_visual) + _nz(loyalty_points_visual)),
            "other_adjustments": _round_or_none(other_adjustments_visual),
            "tax": _round_or_none(tax_visual),
            "ads_spend": _round_or_none(ad_spend_visual),
            "ads_impressions": _int_or_none(data.get("ads_impressions")),
            "ads_clicks": _int_or_none(data.get("ads_clicks")),
            "ads_orders": _int_or_none(data.get("ads_orders")),
            "ads_rows": _int_or_none(data.get("ads_rows_count")),
            "ads_source_file": str(data.get("ads_source_file") or ""),
            "ads_loaded_from_file": bool(data.get("ads_loaded_from_file", False)),
            "ads_attribution_quality": str(data.get("ads_attribution_quality") or "unknown"),
            "gross_profit": _round_or_none(data.get("gross_profit_total")),
            "net_profit": _round_or_none(net_profit_visual),
            "explained_net_profit": _round_or_none(explained_net_profit),
            "net_profit_explain_delta": _round_or_none(net_profit_explain_delta),
            "margin_pct": _round_or_none(margin_pct_value),
            "profitability_pct": _round_or_none(profitability_pct_value),
            "financial_completeness_pct": _round_or_none(data.get("financial_completeness_pct")),
            "financial_partial": bool(data.get("financial_partial", False)),
            "financial_finality_status": financial_finality_status,
            "display": {
                "seller_payout": format_money_or_unknown(revenue_visual, unknown_label=NO_DATA_LABEL, decimals=0),
                "net_profit": format_money_or_unknown(net_profit_visual, unknown_label=NO_DATA_LABEL, decimals=0),
                "margin_pct": format_pct_or_unknown(margin_pct_value, unknown_label=INSUFFICIENT_DATA_LABEL),
                "profitability_pct": format_pct_or_unknown(profitability_pct_value, unknown_label=NO_DATA_LABEL),
            },
        },
        "event_date_model": event_date_model if isinstance(event_date_model, dict) else {},
        "daily_status_matrix": daily_status_matrix if isinstance(daily_status_matrix, dict) else {},
        "order_kpi": order_kpi if isinstance(order_kpi, dict) else {},
        "buyout_kpi": buyout_kpi if isinstance(buyout_kpi, dict) else {},
        "event_ledger_preview": (event_ledger.get("events", [])[:3] if isinstance(event_ledger.get("events"), list) else []),
        "funnel_snapshot": cabinet_funnel if isinstance(cabinet_funnel, dict) else {},
        "sales_funnel_summary": sales_funnel_summary if isinstance(sales_funnel_summary, dict) else {},
        "sku_status_counts": sku_status_counts,
        "sku_status_detail_count": len(sku_health_rows[:36]),
        "key_problem_data_status": key_problem_data_status,
        "key_problem_reasons": key_problem_reasons,
        "sku_watchlists_preview": {
            key: _watchlist_rows(sku_watchlists, key, limit=5)
            for key, _ in _watchlist_groups_for_render()
        },
        "funnel_section_preview": funnel_section_lines,
        "sku_monitor_section_preview": sku_monitor_lines,
    }
    report_meta["page_previews"] = [{"page": page_idx + 1, "lines": page[:30]} for page_idx, page in enumerate(report_pages)]

    write_report_meta(out_dir=out_dir, report_meta=report_meta)
    data.update({"job": job, "report_meta": report_meta, "visual_payload": visual_payload})
    return data

