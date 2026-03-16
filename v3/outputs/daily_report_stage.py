from __future__ import annotations

import os
import re
from typing import Any, Dict, List

from ..pdf_render import normalize_pdf_text, repair_mojibake, write_daily_bi_pdf
from ..pipeline.daily_stage_support import sync_from_entry
from .email_sender_orchestrator import build_daily_email_body, build_daily_email_subject
from .render_policy import format_int_or_unknown, format_money_or_unknown, format_pct_or_unknown, is_missing_value


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
        return "неизвестно"
    summary = funnel_alerts.get("summary", {})
    if isinstance(summary, dict):
        warning_count = int(summary.get("warning_count", 0) or 0)
        critical_count = int(summary.get("critical_count", 0) or 0)
        return f"предупреждений={warning_count}, критических={critical_count}"
    alerts = funnel_alerts.get("alerts", [])
    if not isinstance(alerts, list):
        return "неизвестно"
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
    return f"предупреждений={warning_count}, критических={critical_count}"


def _bool_ru(value: bool) -> str:
    return "да" if bool(value) else "нет"


def _contour_status_ru(value: str) -> str:
    token = str(value or "").strip().lower()
    mapping = {
        "confirmed": "подтвержден",
        "final": "подтвержден",
        "ok": "подтвержден",
        "partial": "частичный",
        "preview": "частичный",
        "degraded": "частичный",
        "provisional": "частичный",
        "missing": "отсутствует",
        "unavailable": "отсутствует",
        "not_confirmed": "отсутствует",
        "disabled": "отсутствует",
        "unknown": "отсутствует",
    }
    return mapping.get(token, token or "отсутствует")


def _reliability_ru(value: str) -> str:
    token = str(value or "").strip().lower()
    return {"high": "высокая", "medium": "средняя", "low": "низкая"}.get(token, token or "низкая")


def _matrix_status_ru(value: str) -> str:
    token = str(value or "").strip().lower()
    mapping = {
        "confirmed": "подтвержден",
        "partial": "частичный",
        "not_confirmed": "отсутствует",
        "missing": "отсутствует",
        "unavailable": "отсутствует",
        "unknown": "неизвестно",
    }
    return mapping.get(token, token or "неизвестно")



def _sku_attribution_status_ru(value: str) -> str:
    token = str(value or "").strip().lower()
    return {"ok": "норма", "broken": "ошибка"}.get(token, token or "неизвестно")
def _watchlist_groups_for_render() -> List[tuple[str, str]]:
    return [
        ("top_growth", "Рост"),
        ("top_risk", "Риск"),
        ("dead_stock", "Неликвид"),
        ("ad_inefficiency", "Неэффективная реклама"),
        ("conversion_drop", "Падение конверсии"),
        ("logistics_risk", "Логистический риск"),
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
    delta_text = f", Δ7d={format_pct_or_unknown(main_delta)}" if main_delta is not None else ""
    reason_text = f", {reason}" if reason else ""
    return f"Товар {sku} | приоритет {attention}{delta_text}{reason_text}"



def _compact_sku_list_clean(values: List[str], limit: int = 8) -> str:
    cleaned = [str(v).strip() for v in values if str(v).strip()]
    if not cleaned:
        return "—"
    shown = cleaned[: max(1, int(limit))]
    suffix = f", +{len(cleaned) - len(shown)}" if len(cleaned) > len(shown) else ""
    return ", ".join(shown) + suffix
def run_daily_report_stage(payload: Dict[str, Any]) -> Dict[str, Any]:
    sync_from_entry(globals())

    data: Dict[str, Any] = dict(payload or {})
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
            return round(float(value), 2)
        except (TypeError, ValueError):
            return None

    def _int_or_none(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    orders_count_value = render_kpi.get("orders_count", data.get("daily_orders_count"))
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

    conversion_value = funnel.get("view_to_order_conversion", funnel.get("click_to_order_conversion_pct"))

    ads_efficiency_mode = str(
        portfolio_ads_summary.get("analysis_mode", advertising_efficiency.get("analysis_mode", "disabled"))
        if isinstance(advertising_efficiency, dict)
        else "disabled"
    ).strip().lower()
    portfolio_ad_spend = _safe_float_local(portfolio_ads_summary.get("portfolio_ad_spend", data.get("ads_spend_total", 0.0)))
    portfolio_orders_from_ads = _safe_float_local(portfolio_ads_summary.get("portfolio_orders_from_ads", data.get("ads_orders", 0)))
    portfolio_buyouts_from_ads = _safe_float_local(portfolio_ads_summary.get("portfolio_buyouts_from_ads", 0.0))
    portfolio_revenue_from_ads = _safe_float_local(portfolio_ads_summary.get("portfolio_revenue_from_ads", data.get("ads_revenue", 0.0)))
    portfolio_profit_from_ads = _safe_float_local(portfolio_ads_summary.get("portfolio_profit_from_ads", 0.0))
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
            "unknown": "данные не подтверждены",
            "degraded": "частично",
            "partial": "частично",
            "confirmed": "подтверждено",
            "not_confirmed": "данные не подтверждены",
            "attention_score": "оценка внимания",
            "baseline": "базовый уровень",
            "traffic_problem": "низкий трафик",
            "ads_efficiency_problem": "неэффективная реклама",
            "monitor": "наблюдать",
            "discount_or_remove": "снижать цену или выводить",
            "fallback": "резервный источник",
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
            "increase ads": "усилить рекламу",
            "improve listing": "улучшить карточку",
            "rebalance stock": "перераспределить остатки",
            "monitor": "наблюдать",
            "discount or remove": "снижать цену или выводить",
            "increase_ads": "усилить рекламу",
            "improve_listing": "улучшить карточку",
            "rebalance_stock": "перераспределить остатки",
            "discount_or_remove": "снижать цену или выводить",
        }
        for key, translated in mapping.items():
            if key in action:
                return translated
        return _sanitize_client_text(raw_action) or "требуется решение"

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
            suffix = f", Δ7d {_pct_text(delta_value, missing_label=INSUFFICIENT_DATA_LABEL)}" if delta_value is not None else ""
            line = f"SKU {sku} — {reason}" if reason else f"SKU {sku}"
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
    ads_preliminary = ads_efficiency_mode in {"preview", "disabled"} or not ads_analysis_enabled

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
        f"??????? ?????????? ?????? | {_pct_text(data.get('financial_completeness_pct', 0.0))}",
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
        not_confirmed_lines.append("Заказы дня: данные не подтверждены")
    if not bool(daily_kpi.get("buyouts_count_confirmed", False)):
        not_confirmed_lines.append("Выкупы дня: данные не подтверждены")
    if not ads_analysis_enabled:
        not_confirmed_lines.append("Рекламные метрики: данные не подтверждены")
    if financial_preliminary:
        not_confirmed_lines.append("Финансовые метрики: предварительные")
    if not not_confirmed_lines:
        not_confirmed_lines.append("Все критичные метрики подтверждены")

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
        f"??????? ?????????? ?????? | {_pct_text(data.get('financial_completeness_pct', 0.0))}",
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
        summary_lines_client = [_ru("Ключевые выводы сформированы по доступным данным.")]

    risk_count_client = len(fix_rows) + len(watch_rows) + len(liquidate_rows)

    page_1 = [
        "# " + _ru("AI-аудит кабинета Wildberries"),
        f"### {_ru('Кабинет')}: {str(data.get('seller_id') or '')}",
        f"### {_ru('Дата анализа')}: {str(data.get('run_date') or '')}",
        f"### {_ru('Надежность данных')}: {_reliability_ru(str(data_quality.get('report_reliability_level', data.get('confidence', 'medium'))))}",
        "",
        "## " + _ru("Краткое резюме"),
    ]
    page_1.extend(f"- {_clean_client(line)}" for line in summary_lines_client)
    page_1.extend([
        "",
        "## " + _ru("KPI карточки"),
        _ru("Показатель") + " | " + _ru("Значение"),
        _ru("Выручка") + f" | {_money_text(revenue_value, preliminary=financial_preliminary, decimals=0)}",
        _ru("Чистая прибыль") + f" | {_money_text(net_profit_value, preliminary=financial_preliminary, decimals=0)}",
        _ru("Расход на рекламу") + f" | {_money_text(portfolio_ad_spend, preliminary=ads_preliminary, decimals=0)}",
        _ru("Товары под риском") + f" | {_int_text(risk_count_client)}",
        "",
        "## " + _ru("Главный вывод AI"),
        _clean_client(str(data.get('ai_day_conclusion') or '')) or _ru("Вывод формируется по данным текущего дня."),
    ])

    page_2 = [
        "# " + _ru("Финансы и реклама"),
        "## " + _ru("Коммерческие KPI"),
        _ru("Показатель") + " | " + _ru("Значение"),
        _ru("Заказы") + f" | {_int_text(orders_count_value, missing_label=NO_DATA_LABEL)}",
        _ru("Выкупы") + f" | {_int_text(buyouts_count_value, missing_label=NO_DATA_LABEL)}",
        _ru("Средний чек") + f" | {_money_text(avg_check_value, preliminary=not bool(daily_kpi.get('buyouts_amount_confirmed', False)), decimals=0)}",
        _ru("Конверсия в заказ") + f" | {_pct_text(conversion_value, missing_label=INSUFFICIENT_DATA_LABEL)}",
        "",
        "## " + _ru("Финансовые KPI"),
        _ru("Показатель") + " | " + _ru("Значение"),
        _ru("Выручка") + f" | {_money_text(revenue_value, preliminary=financial_preliminary, decimals=0)}",
        _ru("Чистая прибыль") + f" | {_money_text(net_profit_value, preliminary=financial_preliminary, decimals=0)}",
        _ru("Маржа") + f" | {_pct_text(margin_pct_value, preliminary=financial_preliminary, missing_label=INSUFFICIENT_DATA_LABEL)}",
        _ru("Полнота финансовых данных") + f" | {_pct_text(data.get('financial_completeness_pct', 0.0))}",
        "",
        "## " + _ru("Эффективность рекламы"),
        _ru("Показатель") + " | " + _ru("Значение"),
        _ru("Расход на рекламу") + f" | {_money_text(portfolio_ad_spend, preliminary=ads_preliminary, decimals=0)}",
        _ru("Выручка из рекламы") + f" | {_money_text(portfolio_revenue_from_ads, preliminary=ads_preliminary, decimals=0)}",
        _ru("Прибыль из рекламы") + f" | {_money_text(portfolio_profit_from_ads, preliminary=ads_preliminary, decimals=0)}",
        f"ROMI | {_pct_text(portfolio_romi, preliminary=ads_preliminary)}",
        f"DRR | {_pct_text(portfolio_drr, preliminary=ads_preliminary, missing_label=INSUFFICIENT_DATA_LABEL)}",
        f"CPO | {_money_text(cpo_value, preliminary=ads_preliminary, decimals=0, missing_label=INSUFFICIENT_DATA_LABEL)}",
        "",
        "- " + _ru("Часть финансовых и рекламных метрик носит предварительный характер из-за неполного подтверждения данных."),
    ]

    page_3 = [
        "# " + _ru("Ключевые проблемы"),
        "## " + _ru("Низкий трафик"),
        f"- {_ru('Слабый трафик зафиксирован у')} {_int_text(low_traffic_count)} SKU",
        "## " + _ru("Падение конверсии"),
        f"- {_ru('Проблема конверсии у')} {_int_text(conversion_drop_count)} SKU",
        "## " + _ru("Неэффективная реклама"),
        f"- {_ru('Зоны риска в рекламе')}: {_int_text(ads_ineff_count)}",
        "## " + _ru("Товары в зоне ликвидации"),
        f"- {_ru('В зоне ликвидации')}: {_int_text(liquidate_count)} SKU",
    ]

    page_4 = [
        "# " + _ru("Рекомендации AI"),
        "## " + _ru("Что делать сейчас"),
        "- " + _ru("Усилить работу с карточками SKU с сниженной конверсией."),
        "- " + _ru("Перераспределить рекламный бюджет из убыточных запросов."),
        "## " + _ru("Что наблюдать"),
        "- " + _ru("Отслеживать динамику выкупа и маржи по рисковым SKU."),
        "## " + _ru("Что пока не подтверждено и требует перепроверки"),
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
            lines.append("- " + _ru("Нет данных"))
        else:
            lines.extend(f"- SKU {sku}" for sku in clean)
        return lines

    page_5 = ["# " + _ru("Мониторинг товаров")]
    page_5.extend(_sku_block(_ru("Рост"), growth_skus))
    page_5.extend(_sku_block(_ru("Риск"), risk_skus))
    page_5.extend(_sku_block(_ru("Наблюдать"), watch_skus))
    page_5.extend(_sku_block(_ru("Ликвидировать"), liquidate_skus))

    page_6 = [
        "# " + _ru("Качество данных"),
        _ru("Показатель") + " | " + _ru("Значение"),
        _ru("Валидные товары (SKU)") + f" | {_int_text(data_quality.get('valid_sku_count', 0))}",
        _ru("Строки с ошибками") + f" | {_int_text(data_quality.get('invalid_sku_rows', 0))}",
        _ru("Не распределённые строки") + f" | {_int_text(data_quality.get('unassigned_rows_true', data_quality.get('unassigned_rows', 0)))}",
        _ru("Полнота финансовых данных") + f" | {_pct_text(data.get('financial_completeness_pct', 0.0))}",
        _ru("Статус финансового контура") + f" | {_contour_status_ru(financial_finality_status)}",
        _ru("Надежность отчета") + f" | {_reliability_ru(str(data_quality.get('report_reliability_level', 'medium')))}",
        "",
        "## " + _ru("Подтверждено"),
        "- " + _ru("реклама"),
        "- " + _ru("часть финансовых строк"),
        "",
        "## " + _ru("Не подтверждено"),
        "- " + _ru("заказы дня"),
        "- " + _ru("выкупы дня"),
        "",
        "## " + _ru("Как это влияет на выводы"),
        "- " + _ru("Часть выводов по прибыли и рекламе требует перепроверки после финального подтверждения данных."),
    ]

    page_7 = [
        "# " + _ru("Что умеет AI Директор"),
        "- " + _ru("Ежедневно анализирует финансы, рекламу и воронку продаж."),
        "- " + _ru("Находит точки роста и зоны потерь по SKU."),
        "- " + _ru("Формирует понятные рекомендации для владельца кабинета."),
        "",
        "## " + _ru("Демо для клиента"),
        "- " + _ru("Могу подготовить такой же аудит по вашему кабинету."),
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

    watchlists_payload = sku_watchlists.get("watchlists", {}) if isinstance(sku_watchlists, dict) else {}
    if not isinstance(watchlists_payload, dict):
        watchlists_payload = {}

    def _watch_count(key: str) -> int:
        rows = watchlists_payload.get(key, [])
        return len(rows) if isinstance(rows, list) else 0

    growth_count = _watch_count("top_growth")
    risk_count = _watch_count("top_risk")
    liquidation_count = max(_watch_count("dead_stock"), len(decision_groups.get("liquidate", [])))
    normal_base = int(data_quality.get("valid_sku_count", 0) or 0)
    if normal_base <= 0:
        normal_base = len([row for row in sku_metrics if isinstance(row, dict)])
    normal_count = max(normal_base - growth_count - risk_count - liquidation_count, 0) if normal_base > 0 else _watch_count("watch_list")

    seller_id_for_visual = str(data.get("seller_id") or "")
    report_date_for_visual = str(data.get("run_date") or "")
    operational_day_for_visual = str(event_date_model.get("operational_date") or report_date_for_visual)

    revenue_visual = _first_number_local(
        revenue_value,
        data.get("revenue_total"),
        financial_kpi_payload.get("revenue"),
        email_summary_payload.get("financial_revenue"),
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

    expense_structure_payload = {
        "commission": _first_number_local(data.get("wb_commission"), financial_kpi_payload.get("wb_commission"), email_summary_payload.get("wb_commission")),
        "logistics": _first_number_local(data.get("logistics_total"), data.get("logistics"), financial_kpi_payload.get("logistics"), email_summary_payload.get("logistics")),
        "storage": _first_number_local(data.get("storage_total"), data.get("storage"), financial_kpi_payload.get("storage"), email_summary_payload.get("storage")),
        "ads": ad_spend_visual,
        "cost_price": _first_number_local(data.get("cost_price_total"), financial_kpi_payload.get("cost_price"), email_summary_payload.get("cost_price")),
        "tax": _first_number_local(data.get("tax_total"), financial_kpi_payload.get("tax"), email_summary_payload.get("tax")),
    }
    financial_structure_day_payload = {
        "revenue": revenue_visual,
        "commission": expense_structure_payload.get("commission"),
        "logistics": expense_structure_payload.get("logistics"),
        "storage": expense_structure_payload.get("storage"),
        "cost_price": expense_structure_payload.get("cost_price"),
        "tax": expense_structure_payload.get("tax"),
        "ads_spend": ad_spend_visual,
        "net_profit": net_profit_visual,
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
            "Рост": 85.0,
            "Нормально": 70.0,
            "Риск": 35.0,
            "Ликвидация": 15.0,
        }
        score = _first_number_local(row.get("health_score"), row.get("score")) if isinstance(row, dict) else None
        attention = _first_number_local(row.get("attention_score")) if isinstance(row, dict) else None
        if score is None and attention is not None:
            if status_ru in {"Риск", "Ликвидация"}:
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
            "strong": "Рост",
            "healthy": "Нормально",
            "unstable": "Риск",
            "risk": "Риск",
            "liquidate": "Ликвидация",
            "liquidation": "Ликвидация",
        }
        return mapping.get(normalized, "Нормально")

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
                reason_text = "Нужен дополнительный мониторинг по SKU"
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
    _append_health_rows(top_growth_rows, "Рост", "Положительная динамика KPI")
    _append_health_rows(top_risk_rows, "Риск", "Нужна оптимизация карточки и цены")
    _append_health_rows(dead_stock_rows, "Ликвидация", "Низкая оборачиваемость товара")
    _append_health_rows(
        [row for row in liquidate_rows if isinstance(row, dict)],
        "Ликвидация",
        "Рекомендована ускоренная распродажа",
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
                "health_score": _health_score_local(row, "Нормально"),
                "status": "Нормально",
                "reason": _reason_local(row, "Стабильная динамика по SKU"),
            }
        )
        normal_added += 1
        if normal_added >= normal_target:
            break

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

    low_traffic_skus = _merge_sku_lists(
        _alert_sku_list({"traffic_drop", "ctr_drop"}, limit=12),
        limit=10,
    )
    conversion_drop_skus = _merge_sku_lists(
        _sku_list_local([row for row in conversion_drop_rows if isinstance(row, dict)], limit=12),
        _alert_sku_list({"orders_drop", "buyout_drop", "cart_conversion_drop"}, limit=12),
        limit=10,
    )
    inefficient_ads_skus = _merge_sku_lists(
        _sku_list_local([row for row in ad_ineff_rows if isinstance(row, dict)], limit=12),
        _alert_sku_list({"ad_inefficiency"}, limit=12),
        limit=10,
    )
    liquidation_skus = _merge_sku_lists(
        _sku_list_local(liquidation_problem_rows, limit=12),
        _alert_sku_list({"dead_stock", "zero_sales_with_stock"}, limit=12),
        limit=10,
    )

    key_problems_payload: Dict[str, List[str]] = {
        "low_traffic": low_traffic_skus,
        "conversion_drop": conversion_drop_skus,
        "inefficient_ads": inefficient_ads_skus,
        "liquidation_skus": liquidation_skus,
    }

    def _action_ru_local(raw_action: Any, group: str) -> str:
        token = str(raw_action or "").strip().lower().replace("_", " ")
        if "increase ads" in token or "increase" in token:
            return "Усилить рекламу"
        if "improve listing" in token or "improve" in token:
            return "Доработать карточку"
        if "rebalance stock" in token or "rebalance" in token:
            return "Перераспределить остатки"
        if "discount" in token or "remove" in token:
            return "Снизить цену или выводить товар"
        if "monitor" in token:
            return "Наблюдать"
        defaults = {
            "p1": "Срочная корректировка SKU",
            "p2": "Оптимизация SKU",
            "p3": "Мониторинг SKU",
        }
        return defaults.get(group, "Действие по SKU")

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
            reason = _reason_local(row, "Требуется действие по результатам AI-анализа")
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
            return "нет данных"
        return f"{int(round(number)):,}".replace(",", " ") + " ₽"

    sku_profit_candidates: List[Dict[str, Any]] = []
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

    visual_payload: Dict[str, Any] = {
        "seller_id": seller_id_for_visual,
        "run_date": report_date_for_visual,
        "operational_day": operational_day_for_visual,
        "preview_dir": out_dir,
        "kpi_cards": [
            {"label": "Выручка", "value": revenue_visual, "value_type": "money"},
            {"label": "Чистая прибыль", "value": net_profit_visual, "value_type": "money"},
            {"label": "Расход на рекламу", "value": ad_spend_visual, "value_type": "money"},
            {"label": "Заказы", "value": orders_visual, "value_type": "int"},
        ],
        "expense_structure": expense_structure_payload,
        "financial_structure_day": financial_structure_day_payload,
        "funnel": {
            "views": _first_number_local(funnel.get("views"), funnel.get("impressions")),
            "add_to_cart": _first_number_local(funnel.get("add_to_cart"), funnel.get("cart_count")),
            "orders": _first_number_local(funnel.get("orders"), orders_visual),
            "buyouts": _first_number_local(funnel.get("buyouts"), buyouts_count_value),
        },
        "sku_status": {
            "growth": growth_count,
            "normal": normal_count,
            "risk": risk_count,
            "liquidation": liquidation_count,
        },
        "ads_efficiency": {
            "ad_spend": ad_spend_visual,
            "ad_revenue": _first_number_local(portfolio_revenue_from_ads, data.get("ads_revenue"), email_summary_payload.get("ads_revenue")),
        },
        "sku_health_rows": sku_health_rows[:36],
        "key_problems": key_problems_payload,
        "ai_recommendations": {
            "p1": p1_recommendations,
            "p2": p2_recommendations,
            "p3": p3_recommendations,
        },
        "sku_profit_rows": sku_profit_rows,
    }

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
                "daily_orders_amount": format_money_or_unknown(orders_amount_value),
                "daily_buyouts_count": format_int_or_unknown(buyouts_count_value, unknown_label=NO_DATA_LABEL),
                "daily_buyouts_amount": format_money_or_unknown(buyouts_amount_value),
                "avg_check": format_money_or_unknown(avg_check_value),
            },
        },
        "daily_financial_kpi": {
            "revenue": _round_or_none(revenue_value),
            "cost_price": _round_or_none(data.get("cost_price_total")),
            "wb_commission": _round_or_none(data.get("wb_commission")),
            "ads_spend": _round_or_none(data.get("ads_spend_total")),
            "ads_impressions": int(data.get("ads_impressions", 0) or 0),
            "ads_clicks": int(data.get("ads_clicks", 0) or 0),
            "ads_orders": int(data.get("ads_orders", 0) or 0),
            "ads_rows": int(data.get("ads_rows_count", 0) or 0),
            "ads_source_file": str(data.get("ads_source_file") or ""),
            "ads_loaded_from_file": bool(data.get("ads_loaded_from_file", False)),
            "ads_attribution_quality": str(data.get("ads_attribution_quality") or "unknown"),
            "gross_profit": _round_or_none(data.get("gross_profit_total")),
            "net_profit": _round_or_none(net_profit_value),
            "margin_pct": _round_or_none(margin_pct_value),
            "profitability_pct": _round_or_none(profitability_pct_value),
            "financial_completeness_pct": round(float(data.get("financial_completeness_pct", 0.0) or 0.0), 2),
            "financial_partial": bool(data.get("financial_partial", False)),
            "financial_finality_status": financial_finality_status,
            "display": {
                "revenue": format_money_or_unknown(revenue_value, decimals=0),
                "net_profit": format_money_or_unknown(net_profit_value, decimals=0),
                "margin_pct": format_pct_or_unknown(margin_pct_value, unknown_label=INSUFFICIENT_DATA_LABEL),
                "profitability_pct": format_pct_or_unknown(profitability_pct_value),
            },
        },
        "event_date_model": event_date_model if isinstance(event_date_model, dict) else {},
        "daily_status_matrix": daily_status_matrix if isinstance(daily_status_matrix, dict) else {},
        "order_kpi": order_kpi if isinstance(order_kpi, dict) else {},
        "buyout_kpi": buyout_kpi if isinstance(buyout_kpi, dict) else {},
        "event_ledger_preview": (event_ledger.get("events", [])[:3] if isinstance(event_ledger.get("events"), list) else []),
        "funnel_snapshot": cabinet_funnel if isinstance(cabinet_funnel, dict) else {},
        "sales_funnel_summary": sales_funnel_summary if isinstance(sales_funnel_summary, dict) else {},
        "sku_watchlists_preview": {
            key: _watchlist_rows(sku_watchlists, key, limit=5)
            for key, _ in _watchlist_groups_for_render()
        },
        "funnel_section_preview": funnel_section_lines,
        "sku_monitor_section_preview": sku_monitor_lines,
    }
    report_meta["page_previews"] = [{"page": page_idx + 1, "lines": page[:30]} for page_idx, page in enumerate(report_pages)]

    write_report_meta(out_dir=out_dir, report_meta=report_meta)
    data.update({"job": job, "report_meta": report_meta})
    return data
