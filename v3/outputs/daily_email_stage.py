from __future__ import annotations

from typing import Any, Dict, List

from ..pipeline.daily_stage_support import sync_from_entry
from .render_policy import format_int_or_unknown, format_pct_or_unknown


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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

    line_1 = (
        "views="
        + format_int_or_unknown(views)
        + ", add_to_cart="
        + format_int_or_unknown(add_to_cart)
        + ", orders="
        + format_int_or_unknown(orders)
        + ", buyouts="
        + format_int_or_unknown(buyouts)
    )
    line_1b = (
        "viewв†’order="
        + format_pct_or_unknown(view_to_order)
        + ", cartв†’order="
        + format_pct_or_unknown(cart_to_order)
        + ", orderв†’buyout="
        + format_pct_or_unknown(buyout_rate)
        + ", CPO="
        + (f"{round(float(cpo), 2):.2f}" if _safe_float(cpo) is not None else "unknown")
    )
    line_2 = (
        "statuses: traffic="
        + str(status.get("traffic") or "unknown")
        + ", conversion="
        + str(status.get("conversion") or "unknown")
        + ", buyout_stage="
        + str(status.get("buyout_stage") or "unknown")
    )

    sku_diag_summary = (
        cabinet_funnel.get("sku_diagnostics", {}).get("summary", {})
        if isinstance(cabinet_funnel.get("sku_diagnostics"), dict)
        else {}
    )
    if not isinstance(sku_diag_summary, dict):
        sku_diag_summary = {}
    top_problem_groups = sku_diag_summary.get("top_problem_groups", [])
    if not isinstance(top_problem_groups, list):
        top_problem_groups = []
    top_problem_groups_text = ", ".join(
        f"{str(item.get('issue_type') or '')}:{int(item.get('count', 0) or 0)}"
        for item in top_problem_groups[:3]
        if isinstance(item, dict) and str(item.get("issue_type") or "").strip()
    )
    line_3 = (
        "sku_funnel: analyzed="
        + str(int(sku_diag_summary.get("analyzed_sku_count", 0) or 0))
        + "/"
        + str(int(sku_diag_summary.get("sku_count", 0) or 0))
        + ", top_issues="
        + (top_problem_groups_text or "none")
    )

    alerts_summary = ""
    if isinstance(funnel_alerts, dict) and funnel_alerts:
        if isinstance(funnel_alerts.get("summary"), dict):
            summary = funnel_alerts.get("summary", {})
            alerts_summary = (
                "alerts: warning="
                + str(summary.get("warning_count", 0))
                + ", critical="
                + str(summary.get("critical_count", 0))
            )
        else:
            alerts = funnel_alerts.get("alerts", [])
            if isinstance(alerts, list):
                warning_count = 0
                critical_count = 0
                for row in alerts:
                    if not isinstance(row, dict):
                        continue
                    row_status = str(row.get("status") or "").strip()
                    if row_status == "warning":
                        warning_count += 1
                    elif row_status == "critical":
                        critical_count += 1
                alerts_summary = f"alerts: warning={warning_count}, critical={critical_count}"
    return [line_1, line_1b, line_2, line_3] + ([alerts_summary] if alerts_summary else [])

def _build_sku_monitor_email_brief(sku_watchlists: Dict[str, Any]) -> List[str]:
    groups = [
        ("top_growth", "СЂРѕСЃС‚"),
        ("top_risk", "СЂРёСЃРє"),
        ("dead_stock", "dead_stock"),
        ("ad_inefficiency", "ad_ineff"),
        ("conversion_drop", "conv_drop"),
    ]
    lines: List[str] = []
    for key, label in groups:
        rows = _top_watchlist_rows(sku_watchlists, key, limit=5)
        if not rows:
            continue
        compact = []
        for row in rows:
            sku = str(row.get("sku") or "").strip()
            if not sku:
                continue
            compact.append(f"{sku}({int(float(row.get('attention_score', 0) or 0))})")
        if compact:
            lines.append(f"{label}: " + ", ".join(compact[:5]))
    return lines


def _extend_ai_conclusion_with_monitoring(base_text: str, funnel_lines: List[str], sku_lines: List[str]) -> str:
    chunks = [str(base_text or "").strip()]
    if funnel_lines:
        chunks.append("FUNNEL KPI:")
        chunks.extend(f"- {line}" for line in funnel_lines[:3])
    if sku_lines:
        chunks.append("SKU MONITOR:")
        chunks.extend(f"- {line}" for line in sku_lines[:5])
    return "\n".join([line for line in chunks if str(line).strip()])


def run_daily_email_stage(payload: Dict[str, Any]) -> Dict[str, Any]:
    sync_from_entry(globals())

    data: Dict[str, Any] = dict(payload or {})
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

    short_recommendations = _build_short_recommendations(
        decision_groups=decision_groups,
        logistics_summary=logistics_summary if isinstance(logistics_summary, dict) else {},
    )
    base_ai_day_conclusion = _build_ai_day_conclusion(
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
    key_insights_enhanced = data.get("key_insights", [])
    if not isinstance(key_insights_enhanced, list):
        key_insights_enhanced = []

    sku_attribution_status = str(
        data_quality.get("sku_attribution_status", report_guardrails.get("sku_attribution_status", "ok")) or "ok"
    ).strip().lower()
    financial_finality_status = str(
        data_quality.get("financial_finality_status", report_guardrails.get("financial_finality_status", "unavailable"))
        or "unavailable"
    ).strip().lower()

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
            "Technical issue: SKU attribution is broken, SKU-level business insights are temporarily suppressed.",
        )
    if financial_finality_status != "final":
        key_insights_enhanced.insert(
            0,
            "Financial KPI are provisional today; profitability metrics should be interpreted as partial.",
        )

    if sku_monitor_brief_lines:
        key_insights_enhanced = list(key_insights_enhanced) + [
            "SKU monitor СЃС„РѕСЂРјРёСЂРѕРІР°РЅ: С„РѕРєСѓСЃ РїРѕ risk/growth/ad/conversion РіСЂСѓРїРїР°Рј.",
        ]
    if funnel_brief_lines:
        key_insights_enhanced = list(key_insights_enhanced) + [
            "Funnel KPI РґРѕР±Р°РІР»РµРЅ РІ СѓРїСЂР°РІР»РµРЅС‡РµСЃРєСѓСЋ РІС‹Р¶РёРјРєСѓ.",
        ]

    job["email_summary"] = build_email_summary(
        daily_kpi=daily_kpi if isinstance(daily_kpi, dict) else {},
        ads_summary=ads_summary if isinstance(ads_summary, dict) else {},
        net_profit=data.get("net_profit"),
        gross_profit=data.get("gross_profit_total"),
        cost_price=data.get("cost_price_total"),
        wb_commission=data.get("wb_commission"),
        logistics=data.get("logistics_total"),
        storage=data.get("storage_total"),
        penalties=data.get("penalties_total"),
        deductions=data.get("deductions_total"),
        ads_spend_total=data.get("ads_spend_total"),
        margin_pct=data.get("margin_pct_total"),
        profitability_pct=data.get("profitability_pct_total"),
        financial_completeness_pct=float(data.get("financial_completeness_pct", 0.0) or 0.0),
        financial_partial=bool(data.get("financial_partial", False)),
        ads_rows=int(data.get("ads_rows_count", 0) or 0),
        ads_impressions=int(data.get("ads_impressions", 0) or 0),
        ads_clicks=int(data.get("ads_clicks", 0) or 0),
        ads_orders=int(data.get("ads_orders", 0) or 0),
        ads_loaded_from_file=bool(data.get("ads_loaded_from_file", False)),
        ads_source_file=str(data.get("ads_source_file") or ""),
        ads_attribution_quality=str(data.get("ads_attribution_quality") or "unknown"),
        daily_revenue=render_kpi.get("buyouts_amount", data.get("daily_buyouts_amount")),
        financial_revenue=render_kpi.get("revenue", data.get("revenue_total")),
        daily_orders_count=render_kpi.get("orders_count", data.get("daily_orders_count")),
        avg_check=render_kpi.get("avg_check", data.get("avg_check")),
        daily_orders_amount=render_kpi.get("orders_amount", data.get("daily_orders_amount")),
        daily_buyouts_count=render_kpi.get("buyouts_count", data.get("daily_buyouts_count")),
        daily_buyouts_amount=render_kpi.get("buyouts_amount", data.get("daily_buyouts_amount")),
        key_insights=key_insights_enhanced,
        recommendations=short_recommendations,
        ai_day_conclusion=ai_day_conclusion_email,
        event_date_model=event_date_model if isinstance(event_date_model, dict) else {},
        order_kpi=order_kpi if isinstance(order_kpi, dict) else {},
        buyout_kpi=buyout_kpi if isinstance(buyout_kpi, dict) else {},
        financial_kpi=financial_kpi if isinstance(financial_kpi, dict) else {},
        daily_status_matrix=daily_status_matrix if isinstance(daily_status_matrix, dict) else {},
        render_kpi=render_kpi if isinstance(render_kpi, dict) else {},
        funnel_snapshot=cabinet_funnel if isinstance(cabinet_funnel, dict) else {},
        sku_watchlists=sku_watchlists if isinstance(sku_watchlists, dict) else {},
        sku_alerts=sku_alerts if isinstance(sku_alerts, dict) else {},
        sku_attribution_status=sku_attribution_status,
        financial_finality_status=financial_finality_status,
        report_reliability_level=str(
            data_quality.get("report_reliability_level", report_guardrails.get("report_reliability_level", "medium"))
            or "medium"
        ),
    )

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



