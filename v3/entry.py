from __future__ import annotations
import argparse
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

from .analytics.abc_analysis import compute_abc
from .analytics.advertising_efficiency import build_advertising_efficiency
from .analytics.growth_simulator import simulate_growth
from .analytics.keywords import build_keyword_monitoring
from .analytics.logistics_ktr import build_logistics_ktr
from .analytics.opportunity_engine import compute_opportunity_scores
from .analytics.profit_contribution import build_profit_contribution
from .analytics.sku_health import compute_sku_health
from .analytics.territorial_distribution import build_territorial_distribution
from .config import load_seller_config
from .decisions import build_decisions_layer
from .history.history_snapshot_writer import write_daily_history_snapshot_and_build_patches
from .history.trend_anomalies import build_trend_anomalies, save_trend_anomalies
from .history.weekly_intelligence import build_weekly_intelligence, save_weekly_intelligence
from .daily_kpi_resolver import resolve_daily_kpi
from .domain.source_policy import SOURCE_UNKNOWN as _SOURCE_UNKNOWN
from .metrics import (
    assemble_ads_summary,
    assemble_daily_kpi,
    assemble_financial_kpi,
    build_cabinet_funnel_core,
    build_metrics_from_normalized,
)
from .memory.decision_logger import log_decisions
from .memory.decision_outcomes import evaluate_decision_outcomes, save_outcomes
from .normalization import normalize_raw_bundle
from .orchestrator import discover_sellers, run_audit
from .outputs.artifact_writer import (
    persist_result_job_if_possible,
    write_batch_summary,
    write_daily_ai_artifacts,
    write_daily_metrics_artifacts,
    write_facts_and_warnings,
    write_job,
    write_report_meta,
    write_weekly_facts_and_warnings,
)
from .outputs.email_summary_builder import build_email_summary
from .outputs.email_sender_orchestrator import build_daily_email_body as _build_daily_email_body_ru, orchestrate_daily_email_send
from .outputs.render_policy import format_int_or_unknown, format_money_or_unknown, format_pct_or_unknown
from .outputs.facts_builder import (
    attach_daily_facts_sections,
    attach_decision_memory_summary_to_facts,
    build_daily_facts_base,
)
from .paths import artifacts_dir, cabinet_root, input_dir
from .pdf_render import write_text_pdf
from .pipeline.assembly_unpacker import (
    apply_input_debug_assembly_patches,
    apply_metrics_assembly_patches,
    extract_financial_ads_warning_additions,
    unpack_ads_assembly,
    unpack_daily_kpi_assembly,
)
from .pipeline.input_debug_builder import build_input_debug
from .pipeline.job_builder import (
    attach_daily_job_decision_outcomes,
    attach_daily_job_history,
    attach_job_warnings,
    build_daily_job,
    build_weekly_job,
)
from .pipeline.warnings_collector import WarningsCollector
from .raw import build_raw_bundle
from .sources.wb_reports_loader import (
    load_local_reports,
    parse_funnel_report_xlsx,
    load_supplier_goods_daily_kpi,
)
from .sources import wb_reports_loader as _wb_reports_loader

_FALLBACK_SELLER_ID = "__missing_seller__"
_ALLOW_FALLBACK_ENV = "WB_ALLOW_MISSING_SELLER"
_BOOTSTRAP_MODE_ENV = "WB_BOOTSTRAP_MODE"
_REPORT_VERSION_ENV = "REPORT_VERSION"
_REPORT_VERSION_LEGACY = "legacy"
_REPORT_VERSION_V2 = "v2"


def _resolve_entry_report_version(context: Dict[str, Any] | None = None) -> str:
    raw_context_value = context.get("report_version") if isinstance(context, dict) else None
    raw_env_value = os.getenv(_REPORT_VERSION_ENV, "")
    explicit_mode = str(raw_env_value or raw_context_value or "").strip().lower()
    return _REPORT_VERSION_V2 if explicit_mode == _REPORT_VERSION_V2 else _REPORT_VERSION_LEGACY


def _bootstrap_mode_enabled() -> bool:
    return str(os.getenv(_BOOTSTRAP_MODE_ENV, "")).strip() == "1" or bool(os.getenv("PYTEST_CURRENT_TEST"))


def _default_date(timezone_name: str | None = None) -> str:
    resolved_timezone = str(timezone_name or os.getenv("TZ") or "Europe/Moscow").strip() or "Europe/Moscow"
    try:
        return datetime.now(ZoneInfo(resolved_timezone)).date().isoformat()
    except Exception:
        return date.today().isoformat()


def _resolve_requested_run_date(run_date: str | None, timezone_name: str) -> Dict[str, str]:
    requested_date = str(run_date or "").strip()
    if requested_date:
        datetime.strptime(requested_date, "%Y-%m-%d")
        return {
            "requested_date": requested_date,
            "resolved_date": requested_date,
            "resolution_reason": "explicit_cli_or_call_arg",
            "timezone": timezone_name,
        }

    resolved_date = _default_date(timezone_name)
    return {
        "requested_date": "",
        "resolved_date": resolved_date,
        "resolution_reason": "default_current_day_in_timezone",
        "timezone": timezone_name,
    }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _resolve_report_timezone(cfg: Dict[str, Any]) -> str:
    env_tz = str(os.getenv("TZ", "")).strip()
    if env_tz:
        return env_tz
    cfg_tz = str(cfg.get("timezone") or "").strip()
    if cfg_tz:
        return cfg_tz
    return "Europe/Moscow"


def _resolve_wb_period(run_date: str, timezone_name: str) -> Dict[str, Any]:
    requested_date = datetime.strptime(run_date, "%Y-%m-%d").date()
    applied_timezone = timezone_name
    try:
        local_today = datetime.now(ZoneInfo(timezone_name)).date()
    except Exception:
        applied_timezone = "UTC"
        local_today = datetime.now(timezone.utc).date()

    shifted_to_previous_day = False
    effective_date = requested_date
    if requested_date >= local_today:
        effective_date = local_today - timedelta(days=1)
        shifted_to_previous_day = True

    return {
        "run_date": run_date,
        "timezone": applied_timezone,
        "local_today": local_today.isoformat(),
        "date_from": effective_date.isoformat(),
        "date_to": effective_date.isoformat(),
        "shifted_to_previous_day": shifted_to_previous_day,
    }


def _merge_financial_rows(sales_rows: List[Dict[str, Any]], orders_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    numeric_fields = (
        "revenue",
        "profit",
        "orders",
        "buys",
        "sales_count",
        "logistics",
        "penalties",
        "storage",
        "deductions",
    )
    bucket: Dict[str, Dict[str, Any]] = {}

    def _row_key(row: Dict[str, Any]) -> str:
        sku = str(row.get("sku") or "").strip()
        if sku:
            return sku
        seller_sku = str(row.get("seller_sku") or "").strip()
        if seller_sku:
            return f"seller:{seller_sku}"
        return ""

    def _upsert(row: Dict[str, Any]) -> None:
        if not isinstance(row, dict):
            return
        key = _row_key(row)
        if not key:
            return
        if key not in bucket:
            bucket[key] = {
                "sku": str(row.get("sku") or "").strip(),
                "seller_sku": str(row.get("seller_sku") or "").strip(),
                "warehouse": str(row.get("warehouse") or "").strip(),
                "revenue": 0.0,
                "profit": 0.0,
                "orders": 0.0,
                "buys": 0.0,
                "sales_count": 0.0,
                "logistics": 0.0,
                "penalties": 0.0,
                "storage": 0.0,
                "deductions": 0.0,
            }
        dst = bucket[key]
        if not dst.get("sku"):
            dst["sku"] = str(row.get("sku") or "").strip()
        if not dst.get("seller_sku"):
            dst["seller_sku"] = str(row.get("seller_sku") or "").strip()
        if not dst.get("warehouse"):
            dst["warehouse"] = str(row.get("warehouse") or "").strip()
        for field in numeric_fields:
            dst[field] = float(dst.get(field, 0.0) or 0.0) + float(row.get(field, 0.0) or 0.0)

    for source_row in sales_rows:
        _upsert(source_row)
    for source_row in orders_rows:
        _upsert(source_row)

    out: List[Dict[str, Any]] = []
    for row in bucket.values():
        item = dict(row)
        for field in numeric_fields:
            item[field] = round(float(item.get(field, 0.0) or 0.0), 2)
        if not item.get("seller_sku"):
            item.pop("seller_sku", None)
        if not item.get("warehouse"):
            item.pop("warehouse", None)
        out.append(item)
    return out


def _extract_sku_metrics(metrics: Any) -> List[Dict[str, Any]]:
    if isinstance(metrics, list):
        return [item for item in metrics if isinstance(item, dict)]
    if not isinstance(metrics, dict):
        return []

    for key in ("sku_metrics", "items", "skus"):
        value = metrics.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    by_sku = metrics.get("metrics_by_sku")
    if isinstance(by_sku, dict):
        rows: List[Dict[str, Any]] = []
        for sku, payload in by_sku.items():
            if isinstance(payload, dict):
                row = dict(payload)
                row.setdefault("sku", str(sku))
                rows.append(row)
        return rows
    return []


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _daily_relative_diff_pct(actual: float, expected: float) -> float:
    denominator = abs(expected)
    if denominator <= 1e-9:
        return 0.0 if abs(actual) <= 1e-9 else 100.0
    return abs(actual - expected) / denominator * 100.0


def _append_daily_kpi_mismatch_warning(
    warnings_collector: WarningsCollector,
    summary_daily_kpi: Dict[str, Any],
    supplier_goods_daily: Dict[str, Any],
) -> None:
    if (
        not isinstance(supplier_goods_daily, dict)
        or not bool(supplier_goods_daily.get("found"))
        or not bool(supplier_goods_daily.get("kpi_confirmed", True))
    ):
        return
    if not isinstance(summary_daily_kpi, dict):
        return

    checks = {
        "orders_count": (
            _safe_float(summary_daily_kpi.get("daily_orders_count", 0)),
            _safe_float(supplier_goods_daily.get("orders_count", 0)),
        ),
        "orders_amount": (
            _safe_float(summary_daily_kpi.get("daily_orders_amount", 0.0)),
            _safe_float(supplier_goods_daily.get("orders_amount", 0.0)),
        ),
        "buyouts_count": (
            _safe_float(summary_daily_kpi.get("daily_buyouts_count", 0)),
            _safe_float(supplier_goods_daily.get("buyouts_count", 0)),
        ),
        "buyouts_amount": (
            _safe_float(summary_daily_kpi.get("daily_buyouts_amount", 0.0)),
            _safe_float(supplier_goods_daily.get("buyouts_amount", 0.0)),
        ),
    }
    debug: Dict[str, Any] = {}
    mismatch_detected = False
    for key, (actual, expected) in checks.items():
        diff_pct = _daily_relative_diff_pct(actual, expected)
        debug[key] = {
            "summary_value": round(actual, 4),
            "supplier_goods_value": round(expected, 4),
            "diff_pct": round(diff_pct, 4),
        }
        if diff_pct > 1.0:
            mismatch_detected = True

    if mismatch_detected:
        warnings_collector.extend_warnings(
            [
                {
                    "code": "daily_kpi_mismatch_with_supplier_goods_report",
                    "message": "daily KPI mismatch with WB supplier goods report",
                    "debug": debug,
                }
            ]
        )


def _format_int(value: Any) -> str:
    number = int(round(_safe_float(value)))
    return f"{number:,}".replace(",", " ")


def _format_money(value: Any) -> str:
    amount = _safe_float(value)
    rounded = int(round(amount))
    return f"{rounded:,}".replace(",", " ") + " ?"


def _format_money_2(value: Any) -> str:
    amount = _safe_float(value)
    return f"{amount:,.2f}".replace(",", " ") + " ?"


def _format_pct(value: Any) -> str:
    return f"{_safe_float(value):.1f} %"


def _format_ktr(value: Any) -> str:
    return f"{_safe_float(value):.2f}"


def _confidence_ru(value: str) -> str:
    mapping = {
        "high": "РІС‹СЃРѕРєР°СЏ",
        "medium": "СЃСЂРµРґРЅСЏСЏ",
        "low": "РЅРёР·РєР°СЏ",
    }
    return mapping.get(str(value or "").strip().lower(), str(value or "РЅРёР·РєР°СЏ"))


def _compact_sku_list(items: List[str], limit: int = 8) -> str:
    clean = [str(x).strip() for x in items if str(x).strip()]
    if not clean:
        return "вЂ”"
    if len(clean) <= limit:
        return ", ".join(clean)
    return ", ".join(clean[:limit]) + f" (+{len(clean) - limit})"


def _top_profit_rows(
    profit_contribution: Dict[str, Any],
    sku_metrics: List[Dict[str, Any]],
    abc_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    abc_map = {str(row.get("sku") or ""): str(row.get("abc_class") or "") for row in abc_rows if isinstance(row, dict)}
    pclass_map: Dict[str, str] = {}
    for key, label in (("p1", "P1"), ("p2", "P2"), ("p3", "P3")):
        rows = profit_contribution.get(key, [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict):
                sku = str(row.get("sku") or "").strip()
                if sku:
                    pclass_map[sku] = label

    metrics_map = {
        str(row.get("sku") or "").strip(): row
        for row in sku_metrics
        if isinstance(row, dict) and str(row.get("sku") or "").strip()
    }
    top = profit_contribution.get("top_profit_skus", [])
    out: List[Dict[str, Any]] = []
    if isinstance(top, list):
        for row in top[:5]:
            if not isinstance(row, dict):
                continue
            sku = str(row.get("sku") or "").strip()
            if not sku:
                continue
            metrics_row = metrics_map.get(sku, {})
            out.append(
                {
                    "sku": sku,
                    "profit": _safe_float(metrics_row.get("profit", row.get("profit", 0.0))),
                    "margin_pct": _safe_float(metrics_row.get("margin_pct", 0.0)),
                    "profit_class": pclass_map.get(sku, ""),
                    "abc_class": abc_map.get(sku, ""),
                }
            )

    if out:
        return out

    fallback = sorted(
        [row for row in sku_metrics if isinstance(row, dict)],
        key=lambda x: _safe_float(x.get("profit", 0.0)),
        reverse=True,
    )[:5]
    for row in fallback:
        sku = str(row.get("sku") or "").strip()
        if not sku:
            continue
        out.append(
            {
                "sku": sku,
                "profit": _safe_float(row.get("profit", 0.0)),
                "margin_pct": _safe_float(row.get("margin_pct", 0.0)),
                "profit_class": pclass_map.get(sku, ""),
                "abc_class": abc_map.get(sku, ""),
            }
        )
    return out


def _important_warnings(warnings: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    keep_codes = {
        "invalid_sku_filtered",
        "invalid_sku_reason_breakdown",
        "unassigned_costs_detected",
        "decision_memory_updated",
        "decision_outcomes_evaluated",
        "no_decisions_ready_for_outcome",
        "sales_report_missing",
        "ads_report_missing",
        "stocks_report_missing",
        "ads_file_loaded",
        "ads_spend_applied_to_profit",
        "ads_attribution_partial",
        "net_profit_reduced_by_ads",
        "input_files_missing",
        "low_total_profit",
        "profit_concentration_high",
        "wb_token_missing",
        "wb_api_empty",
        "wb_api_zero_sales_rows",
        "wb_api_financial_degraded",
        "financial_data_missing",
        "cost_price_missing",
        "wb_commission_missing",
        "expense_attribution_partial",
        "net_profit_partial",
        "financial_margin_not_final",
        "sales_activity_zero_revenue",
        "daily_kpi_fallback_used",
        "weak_kpi_source",
        "daily_orders_count_unknown",
        "daily_buyouts_count_unknown",
        "daily_kpi_unknown",
        "totals_orders_buys_not_confirmed",
        "quantity_orders_fallback_blocked",
        "daily_kpi_mismatch_with_supplier_goods_report",
        "territorial_distribution_built",
        "insufficient_warehouse_data",
        "high_ktr_detected",
    }
    seen: set[str] = set()
    out: List[Dict[str, str]] = []
    for item in warnings:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        if code not in keep_codes or code in seen:
            continue
        seen.add(code)
        out.append({"code": code, "message": str(item.get("message") or "")})
        if len(out) >= 7:
            break
    return out


def _warning_message_ru(code: str, message: str) -> str:
    text = str(message or "").strip()
    number_match = re.search(r"(-?\d+)", text)
    number = number_match.group(1) if number_match else None
    mapping = {
        "invalid_sku_filtered": (
            f"РћС‚С„РёР»СЊС‚СЂРѕРІР°РЅС‹ РЅРµРІР°Р»РёРґРЅС‹Рµ SKU-СЃС‚СЂРѕРєРё: {number}."
            if number is not None
            else "РќРµРІР°Р»РёРґРЅС‹Рµ SKU-СЃС‚СЂРѕРєРё РѕС‚С„РёР»СЊС‚СЂРѕРІР°РЅС‹."
        ),
        "invalid_sku_reason_breakdown": "Р•СЃС‚СЊ СЃС‚СЂРѕРєРё СЃ РЅРµРІР°Р»РёРґРЅС‹Рј SKU РїРѕ РЅРµСЃРєРѕР»СЊРєРёРј С‚РёРїР°Рј РѕС€РёР±РѕРє.",
        "unassigned_costs_detected": "Р§Р°СЃС‚СЊ СЂР°СЃС…РѕРґРѕРІ РЅРµ РїСЂРёРІСЏР·Р°РЅР° Рє SKU Рё СѓС‡С‚РµРЅР° РѕС‚РґРµР»СЊРЅРѕ.",
        "decision_memory_updated": (
            f"РџР°РјСЏС‚СЊ СЂРµС€РµРЅРёР№ AI РѕР±РЅРѕРІР»РµРЅР°: РґРѕР±Р°РІР»РµРЅРѕ {number} Р·Р°РїРёСЃРµР№."
            if number is not None
            else "РџР°РјСЏС‚СЊ СЂРµС€РµРЅРёР№ AI РѕР±РЅРѕРІР»РµРЅР°."
        ),
        "decision_outcomes_evaluated": (
            f"Р’С‹РїРѕР»РЅРµРЅР° РѕС†РµРЅРєР° СЂРµР·СѓР»СЊС‚Р°С‚РѕРІ СЂРµС€РµРЅРёР№: {number}."
            if number is not None
            else "Р’С‹РїРѕР»РЅРµРЅР° РѕС†РµРЅРєР° СЂРµР·СѓР»СЊС‚Р°С‚РѕРІ РїСЂРѕС€Р»С‹С… СЂРµС€РµРЅРёР№."
        ),
        "no_decisions_ready_for_outcome": "РџРѕРєР° РЅРµС‚ СЂРµС€РµРЅРёР№, РіРѕС‚РѕРІС‹С… Рє РѕС†РµРЅРєРµ СЂРµР·СѓР»СЊС‚Р°С‚Р°.",
        "sales_report_missing": "РќРµ РЅР°Р№РґРµРЅ РІР°Р»РёРґРЅС‹Р№ РѕС‚С‡РµС‚ РїСЂРѕРґР°Р¶.",
        "ads_report_missing": "РќРµ РЅР°Р№РґРµРЅ РІР°Р»РёРґРЅС‹Р№ СЂРµРєР»Р°РјРЅС‹Р№ РѕС‚С‡РµС‚.",
        "stocks_report_missing": "РќРµ РЅР°Р№РґРµРЅ РІР°Р»РёРґРЅС‹Р№ РѕС‚С‡РµС‚ РѕСЃС‚Р°С‚РєРѕРІ.",
        "ads_file_loaded": "Р РµРєР»Р°РјРЅС‹Р№ С„Р°Р№Р» СѓСЃРїРµС€РЅРѕ Р·Р°РіСЂСѓР¶РµРЅ.",
        "ads_spend_applied_to_profit": "Р РµРєР»Р°РјРЅС‹Рµ СЂР°СЃС…РѕРґС‹ СѓС‡С‚РµРЅС‹ РїСЂРё СЂР°СЃС‡РµС‚Рµ С‡РёСЃС‚РѕР№ РїСЂРёР±С‹Р»Рё.",
        "ads_attribution_partial": "Р’ СЂРµРєР»Р°РјРЅРѕР№ Р°С‚СЂРёР±СѓС†РёРё РµСЃС‚СЊ Р°СЃСЃРѕС†РёРёСЂРѕРІР°РЅРЅС‹Рµ РєРѕРЅРІРµСЂСЃРёРё, РїРѕРєР°Р·Р°С‚РµР»Рё СЃРјРµС€Р°РЅРЅС‹Рµ.",
        "net_profit_reduced_by_ads": "Р§РёСЃС‚Р°СЏ РїСЂРёР±С‹Р»СЊ СѓРјРµРЅСЊС€РµРЅР° РЅР° СЃСѓРјРјСѓ СЂРµРєР»Р°РјРЅС‹С… СЂР°СЃС…РѕРґРѕРІ.",
        "input_files_missing": "Р’Рѕ РІС…РѕРґРЅРѕР№ РїР°РїРєРµ РЅРµС‚ Р»РѕРєР°Р»СЊРЅС‹С… РѕС‚С‡РµС‚РѕРІ.",
        "low_total_profit": "РЎСѓРјРјР°СЂРЅР°СЏ РїСЂРёР±С‹Р»СЊ РїРѕ SKU РЅРµРїРѕР»РѕР¶РёС‚РµР»СЊРЅР°СЏ.",
        "profit_concentration_high": "РљРѕРЅС†РµРЅС‚СЂР°С†РёСЏ РїСЂРёР±С‹Р»Рё РІ РѕРґРЅРѕРј SKU СЃР»РёС€РєРѕРј РІС‹СЃРѕРєР°СЏ.",
        "wb_token_missing": "РћС‚СЃСѓС‚СЃС‚РІСѓРµС‚ WB С‚РѕРєРµРЅ РґР»СЏ РІРЅРµС€РЅРµРіРѕ РёСЃС‚РѕС‡РЅРёРєР°.",
        "wb_api_zero_sales_rows": "WB API РІРµСЂРЅСѓР» 0 СЃС‚СЂРѕРє РїСЂРѕРґР°Р¶ Р·Р° РІС‹Р±СЂР°РЅРЅС‹Р№ РїРµСЂРёРѕРґ.",
        "wb_api_financial_degraded": "Р¤РёРЅР°РЅСЃРѕРІС‹Рµ РґР°РЅРЅС‹Рµ WB API РЅРµ РїРѕР»СѓС‡РµРЅС‹, РёСЃРїРѕР»СЊР·РѕРІР°РЅ РґРµРіСЂР°РґРёСЂРѕРІР°РЅРЅС‹Р№ СЂРµР¶РёРј.",
        "financial_data_missing": "Р”Р°РЅРЅС‹Рµ Рѕ РїСЂРѕРґР°Р¶Р°С… РЅРµ РїРѕР»СѓС‡РµРЅС‹.",
        "cost_price_missing": "РЎРµР±РµСЃС‚РѕРёРјРѕСЃС‚СЊ РЅРµ РїРѕРґС‚РІРµСЂР¶РґРµРЅР°, С„РёРЅР°РЅСЃРѕРІС‹Р№ РєРѕРЅС‚СѓСЂ С‡Р°СЃС‚РёС‡РЅС‹Р№.",
        "wb_commission_missing": "РљРѕРјРёСЃСЃРёСЏ WB РЅРµ РїРѕРґС‚РІРµСЂР¶РґРµРЅР°, С„РёРЅР°РЅСЃРѕРІС‹Р№ РєРѕРЅС‚СѓСЂ С‡Р°СЃС‚РёС‡РЅС‹Р№.",
        "expense_attribution_partial": "Р§Р°СЃС‚СЊ СЂР°СЃС…РѕРґРѕРІ Р°С‚СЂРёР±СѓС‚РёСЂРѕРІР°РЅР° РЅРµРїРѕР»РЅРѕ (РµСЃС‚СЊ invalid/unassigned СЃС‚СЂРѕРєРё).",
        "net_profit_partial": "Р§РёСЃС‚Р°СЏ РїСЂРёР±С‹Р»СЊ СЂР°СЃСЃС‡РёС‚Р°РЅР° С‡Р°СЃС‚РёС‡РЅРѕ РёР·-Р·Р° РЅРµРїРѕР»РЅС‹С… С„РёРЅР°РЅСЃРѕРІС‹С… РєРѕРјРїРѕРЅРµРЅС‚РѕРІ.",
        "financial_margin_not_final": "РњР°СЂР¶РёРЅР°Р»СЊРЅРѕСЃС‚СЊ РЅРµ С„РёРЅР°Р»СЊРЅР°СЏ, С‚Р°Рє РєР°Рє С„РёРЅР°РЅСЃРѕРІС‹Р№ РєРѕРЅС‚СѓСЂ С‡Р°СЃС‚РёС‡РЅС‹Р№.",
        "sales_activity_zero_revenue": "Р•СЃС‚СЊ РїСЂРѕРґР°Р¶Рё РїРѕ SKU, РЅРѕ РІС‹СЂСѓС‡РєР° РїРѕ РЅРёРј РЅРµ Р°С‚СЂРёР±СѓС‚РёСЂРѕРІР°РЅР°.",
        "daily_kpi_fallback_used": "Supplier goods report РЅРµ РЅР°Р№РґРµРЅ, РёСЃРїРѕР»СЊР·РѕРІР°РЅ API fallback РґР»СЏ daily KPI.",
        "weak_kpi_source": "Daily KPI СЂР°СЃСЃС‡РёС‚Р°РЅС‹ РёР· СЃР»Р°Р±РѕРіРѕ РёСЃС‚РѕС‡РЅРёРєР° metrics totals fallback.",
        "daily_orders_count_unknown": "РљРѕР»РёС‡РµСЃС‚РІРѕ Р·Р°РєР°Р·РѕРІ Р·Р° РґРµРЅСЊ РЅРµ РїРѕРґС‚РІРµСЂР¶РґРµРЅРѕ РЅРё РѕРґРЅРёРј РІР°Р»РёРґРЅС‹Рј РёСЃС‚РѕС‡РЅРёРєРѕРј.",
        "daily_buyouts_count_unknown": "РљРѕР»РёС‡РµСЃС‚РІРѕ РІС‹РєСѓРїРѕРІ Р·Р° РґРµРЅСЊ РЅРµ РїРѕРґС‚РІРµСЂР¶РґРµРЅРѕ РЅРё РѕРґРЅРёРј РІР°Р»РёРґРЅС‹Рј РёСЃС‚РѕС‡РЅРёРєРѕРј.",
        "daily_kpi_unknown": "Daily KPI РїРѕ Р·Р°РєР°Р·Р°Рј/РІС‹РєСѓРїР°Рј РЅРµ РїРѕРґС‚РІРµСЂР¶РґРµРЅС‹ РІР°Р»РёРґРЅС‹Рј РёСЃС‚РѕС‡РЅРёРєРѕРј.",
        "totals_orders_buys_not_confirmed": "Р’ totals Р·Р°РєР°Р·С‹/РІС‹РєСѓРїС‹ РЅРµ РїРѕРґС‚РІРµСЂР¶РґРµРЅС‹ Рё РЅРµ РїРѕРґСЃС‚Р°РІР»СЏСЋС‚СЃСЏ РёР· quantity/activity.",
        "quantity_orders_fallback_blocked": "РљРѕР»РѕРЅРєР° quantity РЅРµ РјРѕР¶РµС‚ РёСЃРїРѕР»СЊР·РѕРІР°С‚СЊСЃСЏ РєР°Рє fallback РґР»СЏ orders/buyouts count.",
        "daily_kpi_mismatch_with_supplier_goods_report": "Daily KPI РЅРµ СЃРѕРІРїР°РґР°РµС‚ СЃ supplier goods report WB.",
        "territorial_distribution_built": (
            f"Р Р°СЃСЃС‡РёС‚Р°РЅРѕ С‚РµСЂСЂРёС‚РѕСЂРёР°Р»СЊРЅРѕРµ СЂР°СЃРїСЂРµРґРµР»РµРЅРёРµ РґР»СЏ {number} SKU."
            if number is not None
            else "Р Р°СЃСЃС‡РёС‚Р°РЅРѕ С‚РµСЂСЂРёС‚РѕСЂРёР°Р»СЊРЅРѕРµ СЂР°СЃРїСЂРµРґРµР»РµРЅРёРµ SKU."
        ),
        "insufficient_warehouse_data": "РќРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РґР°РЅРЅС‹С… РїРѕ СЃРєР»Р°РґР°Рј РґР»СЏ РїРѕР»РЅРѕРіРѕ С‚РµСЂСЂРёС‚РѕСЂРёР°Р»СЊРЅРѕРіРѕ Р°РЅР°Р»РёР·Р°.",
        "high_ktr_detected": (
            f"РћР±РЅР°СЂСѓР¶РµРЅ РІС‹СЃРѕРєРёР№ KTR Сѓ {number} SKU."
            if number is not None
            else "РћР±РЅР°СЂСѓР¶РµРЅС‹ SKU СЃ РІС‹СЃРѕРєРёРј KTR."
        ),
    }
    base = mapping.get(code, text or "РџСЂРµРґСѓРїСЂРµР¶РґРµРЅРёРµ СЃРёСЃС‚РµРјС‹.")
    if code == "profit_concentration_high" and text:
        return text
    return base


def _build_key_insights(
    facts: Dict[str, Any],
    health_summary: Dict[str, Any],
    outcomes_payload: Dict[str, Any],
    decision_rows_added: int,
) -> List[str]:
    def _as_float_or_none(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    insights: List[str] = []
    conversion_view_to_order = _as_float_or_none(
        facts.get("conversion_view_to_order")
        if isinstance(facts, dict)
        else None
    )
    buyout_rate = _as_float_or_none(
        facts.get("buyout_rate")
        if isinstance(facts, dict)
        else None
    )
    cpo_value = _as_float_or_none(facts.get("CPO")) if isinstance(facts, dict) else None
    if cpo_value is None and isinstance(facts, dict):
        cpo_value = _as_float_or_none(facts.get("cpo"))

    if conversion_view_to_order is not None:
        if conversion_view_to_order < 1.0:
            insights.append(
                "РљРѕРЅРІРµСЂСЃРёСЏ РєР°СЂС‚РѕС‡РєРё РЅРёР¶Рµ 1%: РІРµСЂРѕСЏС‚РЅС‹ РїСЂРѕР±Р»РµРјС‹ РїРµСЂРІРѕРіРѕ С„РѕС‚Рѕ, С†РµРЅС‹, СЂРµР№С‚РёРЅРіР° РёР»Рё РѕС‚Р·С‹РІРѕРІ."
            )
        elif conversion_view_to_order > 3.0:
            insights.append("РљРѕРЅРІРµСЂСЃРёСЏ РєР°СЂС‚РѕС‡РєРё РІС‹С€Рµ 3%: РєР°СЂС‚РѕС‡РєР° С‚РѕРІР°СЂР° СЂР°Р±РѕС‚Р°РµС‚ СЃРёР»СЊРЅРѕ.")
    if buyout_rate is not None and buyout_rate < 50.0:
        insights.append(
            "Р”РѕР»СЏ РІС‹РєСѓРїР° РЅРёР¶Рµ 50%: РїСЂРѕРІРµСЂСЊС‚Рµ Р»РѕРіРёСЃС‚РёРєСѓ, РѕР¶РёРґР°РЅРёСЏ РєР»РёРµРЅС‚Р° Рё СЃРѕРѕС‚РІРµС‚СЃС‚РІРёРµ РєР°СЂС‚РѕС‡РєРё С‚РѕРІР°СЂСѓ."
        )
    if cpo_value is not None:
        insights.append(f"CPO РїРѕ Р·Р°РєР°Р·Р°Рј: {round(cpo_value, 2)}.")

    profit_summary = facts.get("profit_contribution_summary", {}) if isinstance(facts, dict) else {}
    p1_count = int((profit_summary or {}).get("p1_count", 0) or 0)
    if p1_count > 0:
        insights.append(f"{p1_count} SKU С„РѕСЂРјРёСЂСѓСЋС‚ РѕСЃРЅРѕРІРЅСѓСЋ РїСЂРёР±С‹Р»СЊ Р±РёР·РЅРµСЃР° (P1).")

    liquidate = int((health_summary or {}).get("LIQUIDATE", 0) or 0)
    if liquidate > 0:
        insights.append(f"{liquidate} SKU РЅР°С…РѕРґРёС‚СЃСЏ РІ Р·РѕРЅРµ Р»РёРєРІРёРґР°С†РёРё.")

    data_quality = facts.get("data_quality", {}) if isinstance(facts, dict) else {}
    invalid_rows = int((data_quality or {}).get("invalid_sku_rows", 0) or 0)
    if invalid_rows > 0:
        insights.append(f"{invalid_rows} СЃС‚СЂРѕРє СЂР°СЃС…РѕРґРѕРІ РЅРµ РїСЂРёРІСЏР·Р°РЅС‹ Рє РІР°Р»РёРґРЅРѕРјСѓ SKU.")

    memory_summary = facts.get("decision_memory_summary", {}) if isinstance(facts, dict) else {}
    total_logged = int((memory_summary or {}).get("total_logged", 0) or 0)
    if total_logged > 0:
        insights.append(f"Р’ РїР°РјСЏС‚Рё AI СѓР¶Рµ РЅР°РєРѕРїР»РµРЅРѕ {total_logged} СЂРµС€РµРЅРёР№.")
    if decision_rows_added > 0:
        insights.append(f"Р’ С‚РµРєСѓС‰РµРј Р·Р°РїСѓСЃРєРµ РґРѕР±Р°РІР»РµРЅРѕ {decision_rows_added} РЅРѕРІС‹С… СЂРµС€РµРЅРёР№ РІ РїР°РјСЏС‚СЊ.")

    evaluated = int((outcomes_payload or {}).get("evaluated", 0) or 0)
    if evaluated > 0:
        results = outcomes_payload.get("results", {}) if isinstance(outcomes_payload, dict) else {}
        success = int((results or {}).get("success", 0) or 0)
        neutral = int((results or {}).get("neutral", 0) or 0)
        fail = int((results or {}).get("fail", 0) or 0)
        insights.append(f"РћС†РµРЅРєР° СЂРµС€РµРЅРёР№: СѓСЃРїРµС€РЅС‹С… {success}, РЅРµР№С‚СЂР°Р»СЊРЅС‹С… {neutral}, РЅРµСѓРґР°С‡РЅС‹С… {fail}.")

    if not insights:
        insights.append("РљР»СЋС‡РµРІС‹Рµ РїРѕРєР°Р·Р°С‚РµР»Рё СЂР°СЃСЃС‡РёС‚Р°РЅС‹ Р±РµР· РєСЂРёС‚РёС‡РЅС‹С… РѕС‚РєР»РѕРЅРµРЅРёР№.")
    return insights[:5]


def _build_short_recommendations(
    decision_groups: Dict[str, List[Dict[str, Any]]],
    logistics_summary: Dict[str, Any],
) -> List[str]:
    recommendations: List[str] = []
    scale_count = len(decision_groups.get("scale", []))
    fix_count = len(decision_groups.get("fix", []))
    liquidate_count = len(decision_groups.get("liquidate", []))
    critical_logistics = int(logistics_summary.get("critical_count", 0) or 0)

    if scale_count > 0:
        recommendations.append("РЈСЃРёР»РёС‚СЊ SKU РёР· РіСЂСѓРїРїС‹ SCALE: РїРѕРґРґРµСЂР¶Р°С‚СЊ Р·Р°РїР°СЃ Рё РїРѕРІС‹СЃРёС‚СЊ СЂРµРєР»Р°РјРЅРѕРµ РїСЂРёСЃСѓС‚СЃС‚РІРёРµ.")
    if fix_count > 0:
        recommendations.append("РџСЂРёРѕСЂРёС‚РёР·РёСЂРѕРІР°С‚СЊ SKU РёР· РіСЂСѓРїРїС‹ FIX: РѕР±РЅРѕРІРёС‚СЊ РєР°СЂС‚РѕС‡РєРё, С†РµРЅСѓ Рё СЌРєРѕРЅРѕРјРёРєСѓ unit-СѓСЂРѕРІРЅСЏ.")
    if liquidate_count > 0:
        recommendations.append("РџРѕ SKU РёР· LIQUIDATE Р·Р°РїСѓСЃС‚РёС‚СЊ СЃС†РµРЅР°СЂРёР№ СѓСЃРєРѕСЂРµРЅРЅРѕР№ СЂР°СЃРїСЂРѕРґР°Р¶Рё Рё РѕС‡РёСЃС‚РєРё РѕСЃС‚Р°С‚РєРѕРІ.")
    if critical_logistics > 0:
        recommendations.append("РЎРЅРёР·РёС‚СЊ Р»РѕРіРёСЃС‚РёС‡РµСЃРєРёРµ РїРѕС‚РµСЂРё Сѓ critical SKU С‡РµСЂРµР· РїРµСЂРµСЂР°СЃРїСЂРµРґРµР»РµРЅРёРµ РїРѕ СЃРєР»Р°РґР°Рј.")

    if not recommendations:
        recommendations.append("РЎРѕС…СЂР°РЅРёС‚СЊ С‚РµРєСѓС‰РёР№ РєСѓСЂСЃ Рё РєРѕРЅС‚СЂРѕР»РёСЂРѕРІР°С‚СЊ РґРёРЅР°РјРёРєСѓ KPI Р±РµР· СЂРµР·РєРёС… РёР·РјРµРЅРµРЅРёР№.")
    return recommendations[:3]


def _build_ai_day_conclusion(
    run_date: str,
    totals: Dict[str, Any],
    daily_kpi: Dict[str, Any],
    data_quality: Dict[str, Any],
    key_insights: List[str],
    recommendations: List[str],
    event_date_model: Dict[str, Any] | None = None,
    order_kpi: Dict[str, Any] | None = None,
    buyout_kpi: Dict[str, Any] | None = None,
    financial_kpi: Dict[str, Any] | None = None,
    daily_status_matrix: Dict[str, Any] | None = None,
) -> str:
    safe_event_date_model = event_date_model if isinstance(event_date_model, dict) else {}
    safe_order_kpi = order_kpi if isinstance(order_kpi, dict) else {}
    safe_buyout_kpi = buyout_kpi if isinstance(buyout_kpi, dict) else {}
    safe_financial_kpi = financial_kpi if isinstance(financial_kpi, dict) else {}
    safe_status_matrix = daily_status_matrix if isinstance(daily_status_matrix, dict) else {}
    if not safe_order_kpi:
        safe_order_kpi = {
            "orders_count": int(round(_safe_float(daily_kpi.get("daily_orders_count", 0)))),
            "orders_count_confirmed": bool(daily_kpi.get("orders_count_confirmed", False)),
        }
    if not safe_buyout_kpi:
        safe_buyout_kpi = {
            "buyouts_count": int(round(_safe_float(daily_kpi.get("daily_buyouts_count", 0)))),
            "buyouts_count_confirmed": bool(daily_kpi.get("buyouts_count_confirmed", False)),
            "buyouts_amount": _safe_float(daily_kpi.get("daily_buyouts_amount", 0.0)),
            "buyouts_amount_confirmed": bool(daily_kpi.get("buyouts_amount_confirmed", False)),
        }
    if not safe_financial_kpi:
        safe_financial_kpi = {
            "revenue": _safe_float(totals.get("total_revenue", totals.get("revenue", 0.0))),
            "net_profit": _safe_float(totals.get("net_profit", totals.get("profit", totals.get("total_profit", 0.0)))),
            "margin_pct": _safe_float(totals.get("margin_pct", 0.0)),
            "is_partial": str(data_quality.get("financial_status", "ok") or "ok") == "partial",
            "confirmed": str(data_quality.get("financial_status", "ok") or "ok") == "ok",
        }
    if not safe_status_matrix:
        financial_status = str(data_quality.get("financial_status", "ok") or "ok")
        safe_status_matrix = {
            "orders": "confirmed" if bool(safe_order_kpi.get("orders_count_confirmed", False)) else "not_confirmed",
            "buyouts": "confirmed" if bool(safe_buyout_kpi.get("buyouts_count_confirmed", False)) else "not_confirmed",
            "financials": "confirmed" if financial_status == "ok" else ("partial" if financial_status == "partial" else "not_confirmed"),
        }

    operational_date = str(safe_event_date_model.get("operational_date") or run_date)
    orders_status = str(safe_status_matrix.get("orders") or "unknown")
    buyouts_status = str(safe_status_matrix.get("buyouts") or "unknown")
    financial_status = str(safe_status_matrix.get("financials") or "unknown")
    financial_partial = bool(safe_financial_kpi.get("is_partial", False))

    orders = safe_order_kpi.get("orders_count") if bool(safe_order_kpi.get("orders_count_confirmed", False)) else None
    buyouts = safe_buyout_kpi.get("buyouts_count") if bool(safe_buyout_kpi.get("buyouts_count_confirmed", False)) else None
    buyouts_revenue = safe_buyout_kpi.get("buyouts_amount") if bool(safe_buyout_kpi.get("buyouts_amount_confirmed", False)) else None
    financial_revenue = safe_financial_kpi.get("revenue")
    profit = safe_financial_kpi.get("net_profit")
    margin_pct = safe_financial_kpi.get("margin_pct") if financial_status == "confirmed" and not financial_partial else None
    main_insight = (key_insights[0] if key_insights else "РљСЂРёС‚РёС‡РЅС‹С… РѕС‚РєР»РѕРЅРµРЅРёР№ РїРѕ KPI РЅРµ РІС‹СЏРІР»РµРЅРѕ").rstrip(".")
    focus = (recommendations[0] if recommendations else "РЎРѕС…СЂР°РЅРёС‚СЊ С‚РµРєСѓС‰СѓСЋ РѕРїРµСЂР°С†РёРѕРЅРЅСѓСЋ СЃС‚СЂР°С‚РµРіРёСЋ").rstrip(".")

    if orders_status == "confirmed" and (financial_status != "confirmed" or financial_partial):
        return (
            f"Р—Р° РѕРїРµСЂР°С†РёРѕРЅРЅС‹Р№ РґРµРЅСЊ {operational_date} Р·Р°С„РёРєСЃРёСЂРѕРІР°РЅРѕ {format_int_or_unknown(orders)} Р·Р°РєР°Р·РѕРІ. "
            "РџРѕРґС‚РІРµСЂР¶РґРµРЅРЅС‹С… РІС‹РєСѓРїРѕРІ Рё РїРѕР»РЅРѕРіРѕ С„РёРЅР°РЅСЃРѕРІРѕРіРѕ РєРѕРЅС‚СѓСЂР° Р·Р° РїРµСЂРёРѕРґ РЅРµ РїРѕР»СѓС‡РµРЅРѕ, "
            "РїРѕСЌС‚РѕРјСѓ РІС‹СЂСѓС‡РєР°, РїСЂРёР±С‹Р»СЊ Рё РїСЂРѕРёР·РІРѕРґРЅС‹Рµ С„РёРЅР°РЅСЃРѕРІС‹Рµ KPI РЅРµ РёРЅС‚РµСЂРїСЂРµС‚РёСЂСѓСЋС‚СЃСЏ РєР°Рє РѕРєРѕРЅС‡Р°С‚РµР»СЊРЅС‹Рµ Р·РЅР°С‡РµРЅРёСЏ РґРЅСЏ. "
            f"Р“Р»Р°РІРЅС‹Р№ СЃРёРіРЅР°Р»: {main_insight}; С„РѕРєСѓСЃ СЃР»РµРґСѓСЋС‰РµРіРѕ РґРЅСЏ: {focus}."
        )
    if orders_status != "confirmed":
        return (
            f"Р—Р° РѕРїРµСЂР°С†РёРѕРЅРЅС‹Р№ РґРµРЅСЊ {operational_date} РґР°РЅРЅС‹Рµ РїРѕ Р·Р°РєР°Р·Р°Рј РїРѕРєР° РЅРµ РїРѕРґС‚РІРµСЂР¶РґРµРЅС‹. "
            "Р”Рѕ РїРѕРґС‚РІРµСЂР¶РґРµРЅРёСЏ РѕРїРµСЂР°С†РёРѕРЅРЅРѕРіРѕ Рё С„РёРЅР°РЅСЃРѕРІРѕРіРѕ РєРѕРЅС‚СѓСЂРѕРІ РёС‚РѕРіРѕРІС‹Рµ KPI РґРЅСЏ СЃС‡РёС‚Р°СЋС‚СЃСЏ РїСЂРµРґРІР°СЂРёС‚РµР»СЊРЅС‹РјРё. "
            f"Р“Р»Р°РІРЅС‹Р№ СЃРёРіРЅР°Р»: {main_insight}; С„РѕРєСѓСЃ СЃР»РµРґСѓСЋС‰РµРіРѕ РґРЅСЏ: {focus}."
        )

    return (
        f"Р—Р° РѕРїРµСЂР°С†РёРѕРЅРЅС‹Р№ РґРµРЅСЊ {operational_date} РїРѕР»СѓС‡РµРЅРѕ {format_int_or_unknown(orders)} Р·Р°РєР°Р·РѕРІ, "
        f"РІС‹РєСѓРїР»РµРЅРѕ {format_int_or_unknown(buyouts)} РЅР° СЃСѓРјРјСѓ {format_money_or_unknown(buyouts_revenue)}. "
        f"Р¤РёРЅР°РЅСЃРѕРІР°СЏ РІС‹СЂСѓС‡РєР°: {format_money_or_unknown(financial_revenue, decimals=0)}, "
        f"С‡РёСЃС‚Р°СЏ РїСЂРёР±С‹Р»СЊ: {format_money_or_unknown(profit, decimals=0)}, "
        f"РјР°СЂР¶Р°: {format_pct_or_unknown(margin_pct)}. "
        f"РЎС‚Р°С‚СѓСЃС‹ РєРѕРЅС‚СѓСЂРѕРІ: orders={orders_status}, buyouts={buyouts_status}, financials={financial_status}. "
        f"Р“Р»Р°РІРЅС‹Р№ СЃРёРіРЅР°Р»: {main_insight}; С„РѕРєСѓСЃ СЃР»РµРґСѓСЋС‰РµРіРѕ РґРЅСЏ: {focus}."
    )


def _build_management_email_body(
    seller_id: str,
    run_date: str,
    summary: Dict[str, Any],
) -> str:
    safe_summary = summary if isinstance(summary, dict) else {}
    body = _build_daily_email_body_ru(
        seller_id=seller_id,
        run_date=run_date,
        email_summary=safe_summary,
        build_body=lambda _seller_id, _run_date, _summary: "",
    )
    financial_finality_status = str(safe_summary.get("financial_finality_status") or "unknown").strip().lower()
    status_map = {
        "final": "подтверждено",
        "confirmed": "подтверждено",
        "partial": "частичный",
        "provisional": "предварительный",
        "lagged": "лаговый (другая дата)",
        "lagged_fallback": "лаговый (другая дата)",
        "not_aligned": "не выровнен по дате",
        "unavailable": "нет данных",
        "unknown": "нет данных",
    }
    status_label = status_map.get(financial_finality_status, status_map["unknown"])
    status_line = f"Статус финансового контура: {status_label}"
    finance_anchor = "ФИНАНСОВЫЕ ПОКАЗАТЕЛИ\n"
    if status_line not in body and finance_anchor in body:
        body = body.replace(finance_anchor, finance_anchor + f"- {status_line}\n", 1)
    if financial_finality_status != "final" and "РЕЖИМ РЕКОМЕНДАЦИЙ ИИ" not in body:
        body = body.replace("РЕКОМЕНДАЦИИ", "РЕЖИМ РЕКОМЕНДАЦИЙ ИИ", 1)
    return body

def _excel_candidate_paths(
    *,
    seller_input_dir: str,
    discovered_files: Dict[str, Any],
) -> List[str]:
    candidates: List[str] = []
    safe_discovered = discovered_files if isinstance(discovered_files, dict) else {}
    for key in ("sales", "funnel", "supplier_goods", "unknown", "stocks", "ads"):
        for raw_path in safe_discovered.get(key, []) if isinstance(safe_discovered.get(key), list) else []:
            path = str(raw_path or "").strip()
            if not path:
                continue
            ext = os.path.splitext(path)[1].lower()
            if ext not in {".xlsx", ".xls"}:
                continue
            if path not in candidates:
                candidates.append(path)

    if os.path.isdir(seller_input_dir):
        for root, _, files in os.walk(seller_input_dir):
            for name in sorted(files):
                path = os.path.join(root, name)
                if not os.path.isfile(path):
                    continue
                ext = os.path.splitext(path)[1].lower()
                if ext not in {".xlsx", ".xls"}:
                    continue
                if path not in candidates:
                    candidates.append(path)
    return candidates


def _looks_like_daily_file(path: str) -> bool:
    token = str(os.path.basename(path) or "").strip().lower()
    return any(
        marker in token
        for marker in (
            "ежеднев",
            "детализ",
            "daily",
            "supplier",
            "goods",
            "report",
            "реализац",
            "financial",
        )
    )


def _looks_like_funnel_file(path: str) -> bool:
    token = str(os.path.basename(path) or "").strip().lower()
    return any(
        marker in token
        for marker in (
            "воронк",
            "funnel",
            "товар",
            "goods",
            "карточ",
        )
    )


def parse_daily_report(path: str) -> Dict[str, Any]:
    try:
        if os.path.isfile(path):
            extracted = _wb_reports_loader._extract_supplier_goods_daily_kpi(path)  # type: ignore[attr-defined]
            if isinstance(extracted, dict) and extracted:
                out = dict(extracted)
                out["found"] = True
                out.setdefault("source_file", os.path.basename(path))
                out.setdefault("source_path", path)
                return out
    except Exception:
        pass

    input_root = path if os.path.isdir(path) else os.path.dirname(path)
    payload = load_supplier_goods_daily_kpi(input_root)
    if not isinstance(payload, dict):
        return {}
    if not bool(payload.get("found", False)):
        return {}
    return dict(payload)


def _parse_local_daily_payload(
    *,
    seller_input_dir: str,
    discovered_files: Dict[str, Any],
) -> Dict[str, Any]:
    candidates = _excel_candidate_paths(
        seller_input_dir=seller_input_dir,
        discovered_files=discovered_files if isinstance(discovered_files, dict) else {},
    )
    if not candidates:
        return {}

    ordered_candidates = sorted(
        candidates,
        key=lambda path: (0 if _looks_like_daily_file(path) else 1, os.path.basename(path).lower()),
    )
    for path in ordered_candidates:
        parsed = parse_daily_report(path)
        if not isinstance(parsed, dict) or not parsed:
            continue
        if not bool(parsed.get("found", False)):
            continue
        parsed.setdefault("source_file", os.path.basename(path))
        parsed.setdefault("source_path", path)
        return parsed

    parsed_from_dir = parse_daily_report(seller_input_dir)
    if isinstance(parsed_from_dir, dict) and bool(parsed_from_dir.get("found", False)):
        return parsed_from_dir
    return {}


def _parse_local_funnel_payload(
    *,
    seller_input_dir: str,
    discovered_files: Dict[str, Any],
) -> Dict[str, Any]:
    candidates = _excel_candidate_paths(
        seller_input_dir=seller_input_dir,
        discovered_files=discovered_files if isinstance(discovered_files, dict) else {},
    )
    if not candidates:
        return {}

    ordered_candidates = sorted(
        candidates,
        key=lambda path: (0 if _looks_like_funnel_file(path) else 1, os.path.basename(path).lower()),
    )
    for path in ordered_candidates:
        try:
            parsed = parse_funnel_report_xlsx(path)
        except Exception:
            parsed = {}
        if not isinstance(parsed, dict):
            continue
        sku_rows = parsed.get("sku_rows", [])
        if not isinstance(sku_rows, list) or not sku_rows:
            continue
        return {
            "source_file": os.path.basename(path),
            "source_path": path,
            "cabinet_totals": parsed.get("cabinet_totals", {}) if isinstance(parsed.get("cabinet_totals"), dict) else {},
            "sku_rows": sku_rows,
        }
    return {}


def _inject_parsed_daily_into_context(context: Dict[str, Any], daily_payload: Dict[str, Any]) -> Dict[str, Any]:
    ctx = dict(context or {})
    if not isinstance(daily_payload, dict) or not daily_payload:
        return ctx
    if not bool(daily_payload.get("found", False)):
        return ctx

    ctx["parsed_daily"] = daily_payload
    ctx["supplier_goods_daily"] = daily_payload

    input_debug = ctx.get("input_debug", {})
    if not isinstance(input_debug, dict):
        input_debug = {}
    input_debug["parsed_daily_report"] = {
        "found": True,
        "source_file": str(daily_payload.get("source_file") or ""),
        "source_path": str(daily_payload.get("source_path") or ""),
        "rows_used": int(daily_payload.get("rows_used", 0) or 0),
    }
    ctx["input_debug"] = input_debug
    return ctx


def _inject_parsed_funnel_into_context(context: Dict[str, Any], funnel_payload: Dict[str, Any]) -> Dict[str, Any]:
    ctx = dict(context or {})
    if not isinstance(funnel_payload, dict) or not funnel_payload:
        return ctx

    input_debug = ctx.get("input_debug", {})
    if not isinstance(input_debug, dict):
        input_debug = {}
    input_debug["funnel_xlsx"] = funnel_payload
    input_debug["funnel_report_xlsx"] = funnel_payload
    input_debug["funnel_source_file"] = str(funnel_payload.get("source_file") or "")
    ctx["input_debug"] = input_debug
    ctx["funnel_xlsx_payload"] = funnel_payload
    return ctx


def _apply_parsed_funnel_after_metrics(context: Dict[str, Any]) -> Dict[str, Any]:
    ctx = dict(context or {})
    funnel_payload = ctx.get("funnel_xlsx_payload", {})
    if not isinstance(funnel_payload, dict) or not funnel_payload:
        return ctx

    metrics = ctx.get("metrics", {})
    if not isinstance(metrics, dict):
        return ctx

    metrics["funnel_xlsx"] = funnel_payload
    metrics["funnel_report_xlsx"] = funnel_payload
    metrics_input_debug = metrics.get("input_debug", {})
    if not isinstance(metrics_input_debug, dict):
        metrics_input_debug = {}
    metrics_input_debug["funnel_xlsx"] = funnel_payload
    metrics["input_debug"] = metrics_input_debug

    cabinet_funnel = build_cabinet_funnel_core(
        run_date=str(ctx.get("run_date") or ""),
        metrics=metrics,
        ads_diagnostics=ctx.get("ads_diagnostics_summary", {}) if isinstance(ctx.get("ads_diagnostics_summary"), dict) else {},
    )
    if isinstance(cabinet_funnel, dict):
        ctx["cabinet_funnel"] = cabinet_funnel
        metrics["sales_funnel"] = cabinet_funnel
        if isinstance(cabinet_funnel.get("funnel"), dict):
            metrics["funnel"] = dict(cabinet_funnel.get("funnel") or {})
            facts = ctx.get("facts", {})
            if isinstance(facts, dict):
                facts["funnel"] = dict(cabinet_funnel.get("funnel") or {})
                facts["funnel_source"] = "funnel_xlsx"
                ctx["facts"] = facts

    ctx["metrics"] = metrics
    return ctx


def build_metrics(
    *,
    daily_data: Dict[str, Any],
    funnel_data: Dict[str, Any],
    api_data: Dict[str, Any],
    context: Dict[str, Any],
    run_metrics_stage: Any,
) -> Dict[str, Any]:
    _ = api_data
    ctx = dict(context or {})
    ctx = _inject_parsed_daily_into_context(ctx, daily_data if isinstance(daily_data, dict) else {})
    ctx = _inject_parsed_funnel_into_context(ctx, funnel_data if isinstance(funnel_data, dict) else {})
    ctx = run_metrics_stage(ctx)
    ctx = _apply_parsed_funnel_after_metrics(ctx)
    return ctx


def _run_daily_for_seller(repo_root: str, seller_id: str, run_date: str) -> Dict[str, Any]:
    from .pipeline.daily_ai_stage import run_daily_ai_stage
    from .pipeline.daily_input_stage import run_daily_input_stage
    from .pipeline.daily_metrics_stage import run_daily_metrics_stage
    from .pipeline.daily_output_stage import run_daily_output_stage

    print(
        "[entry] REPORT_VERSION "
        f"raw_env={os.environ.get(_REPORT_VERSION_ENV)!r} "
        f"resolved={_resolve_entry_report_version()} "
        f"cwd={os.getcwd()} "
        f"repo_root={repo_root} "
        f"repo_root_abs={os.path.abspath(repo_root)}"
    )
    wb_api_token_value = os.getenv("WB_API_TOKEN", "")
    print(
        "[python-entry] WB_API_TOKEN "
        f"present={str(bool(wb_api_token_value)).lower()} "
        f"len={len(wb_api_token_value)}"
    )
    print("[pipeline] stage=load_reports started")
    context = run_daily_input_stage(repo_root=repo_root, seller_id=seller_id, run_date=run_date)
    print("[pipeline] stage=load_reports finished")

    print("[pipeline] stage=parse started")
    parsed_daily = _parse_local_daily_payload(
        seller_input_dir=str(context.get("seller_input_dir") or ""),
        discovered_files=context.get("discovered_files", {}) if isinstance(context.get("discovered_files"), dict) else {},
    )
    funnel_payload = _parse_local_funnel_payload(
        seller_input_dir=str(context.get("seller_input_dir") or ""),
        discovered_files=context.get("discovered_files", {}) if isinstance(context.get("discovered_files"), dict) else {},
    )
    context = _inject_parsed_daily_into_context(context, parsed_daily if isinstance(parsed_daily, dict) else {})
    context = _inject_parsed_funnel_into_context(context, funnel_payload if isinstance(funnel_payload, dict) else {})
    print("[pipeline] stage=parse finished")

    print("[pipeline] stage=metrics started")
    context = build_metrics(
        daily_data=parsed_daily if isinstance(parsed_daily, dict) else {},
        funnel_data=funnel_payload if isinstance(funnel_payload, dict) else {},
        api_data=context.get("api_debug", {}) if isinstance(context.get("api_debug"), dict) else {},
        context=context,
        run_metrics_stage=run_daily_metrics_stage,
    )
    print("[pipeline] stage=metrics finished")

    print("[pipeline] stage=facts started")
    context = run_daily_ai_stage(context)
    output = run_daily_output_stage(context)
    print("[pipeline] stage=facts finished")
    return output


def _finalize_daily_delivery(result: Dict[str, Any], *, seller_id: str, run_date: str) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return result
    if str(result.get("status") or "") not in {"success", "partial_success"}:
        return result

    report_version = _resolve_entry_report_version(result)
    finalize_branch = "v2" if report_version == _REPORT_VERSION_V2 else "legacy"
    print(
        "[entry] finalize branch="
        f"{finalize_branch} "
        f"status={result.get('status')} "
        f"raw_env={os.environ.get(_REPORT_VERSION_ENV)!r} "
        f"resolved={report_version}"
    )
    if report_version == _REPORT_VERSION_V2:
        pdf_path = str(result.get("pdf_path") or "")
        if not pdf_path:
            pdf_path = os.path.join(str(result.get("artifacts_dir") or ""), "report_v2.pdf")
        email_summary = result.get("email_summary", {}) if isinstance(result, dict) else {}
        finalized_result = orchestrate_daily_email_send(
            job=result if isinstance(result, dict) else {},
            seller_id=seller_id,
            run_date=run_date,
            report_pdf_path=pdf_path,
            email_summary=email_summary if isinstance(email_summary, dict) else {},
            build_body=_build_management_email_body,
        )
        persist_result_job_if_possible(finalized_result if isinstance(finalized_result, dict) else {})
        return finalized_result

    report_pdf_path = os.path.join(str(result.get("artifacts_dir") or ""), "report.pdf")
    email_summary = result.get("email_summary", {}) if isinstance(result, dict) else {}
    finalized_result = orchestrate_daily_email_send(
        job=result if isinstance(result, dict) else {},
        seller_id=seller_id,
        run_date=run_date,
        report_pdf_path=report_pdf_path,
        email_summary=email_summary if isinstance(email_summary, dict) else {},
        build_body=_build_management_email_body,
    )
    persist_result_job_if_possible(finalized_result if isinstance(finalized_result, dict) else {})
    return finalized_result


def _failed_run_result(seller_id: str, run_date: str, mode: str, error: str) -> Dict[str, Any]:
    return {
        "seller_id": seller_id,
        "mode": mode,
        "run_date": run_date,
        "status": "failed",
        "error": error,
    }


def _batch_summary(run_date: str, results: List[Dict[str, Any]]) -> Dict[str, Any]:
    safe_results = [row for row in results if isinstance(row, dict)]
    non_fallback_results = [row for row in safe_results if str(row.get("seller_id") or "") != _FALLBACK_SELLER_ID]
    effective_results = non_fallback_results if non_fallback_results else safe_results
    success_count = sum(1 for row in effective_results if str(row.get("status") or "") == "success")
    partial_success_count = sum(1 for row in effective_results if str(row.get("status") or "") == "partial_success")
    failed_count = sum(
        1 for row in effective_results if str(row.get("status") or "") not in {"success", "partial_success"}
    )
    return {
        "run_date": run_date,
        "total_sellers": len(effective_results),
        "success_count": success_count,
        "partial_success_count": partial_success_count,
        "failed_count": failed_count,
        "results": effective_results,
    }


def _resolve_seller_repo_root(repo_root: str, seller_id: str) -> str:
    discovered = discover_sellers(repo_root)
    bootstrap_mode = _bootstrap_mode_enabled()
    if seller_id in discovered:
        return repo_root
    if seller_id == _FALLBACK_SELLER_ID:
        allow_fallback = str(os.getenv(_ALLOW_FALLBACK_ENV, "")).strip() == "1" and bootstrap_mode
        if allow_fallback and not discovered:
            print(
                f"[warn] fallback seller '{_FALLBACK_SELLER_ID}' enabled via "
                f"{_ALLOW_FALLBACK_ENV}=1 and {_BOOTSTRAP_MODE_ENV}=1; using debug fallback cabinet paths."
            )
            return repo_root
        raise ValueError(
            f"Refusing fallback seller '{_FALLBACK_SELLER_ID}'. "
            f"Fallback is allowed only in bootstrap/test mode "
            f"({_ALLOW_FALLBACK_ENV}=1 and {_BOOTSTRAP_MODE_ENV}=1)."
        )

    if discovered:
        raise FileNotFoundError(f"Seller '{seller_id}' not found. Discovered sellers: {', '.join(discovered)}")

    if bootstrap_mode:
        print(
            f"[warn] seller '{seller_id}' not discovered; running in bootstrap mode because no sellers exist in "
            f"{Path(repo_root) / 'cabinets'}."
        )
        return repo_root
    raise FileNotFoundError(
        f"No valid sellers found in {Path(repo_root) / 'cabinets'}. "
        f"Refusing bootstrap fallback in production mode. "
        f"Set {_BOOTSTRAP_MODE_ENV}=1 to allow bootstrap run."
    )


def _debug_seller_paths(repo_root: str, seller_id: str) -> None:
    cabinets_dir = Path(repo_root) / "cabinets"
    resolved_input_dir = Path(input_dir(repo_root, seller_id, create=False))
    input_exists = resolved_input_dir.is_dir()
    discovered_files = sorted([item.name for item in resolved_input_dir.iterdir() if item.is_file()]) if input_exists else []
    print(f"[debug] project_root={repo_root}")
    print(f"[debug] cabinets_dir={cabinets_dir}")
    print(f"[debug] seller_id={seller_id}")
    print(f"[debug] input_dir={resolved_input_dir}")
    print(f"[debug] input_exists={input_exists}")
    print(f"[debug] discovered_files={len(discovered_files)}")


def _log_result_summary(result: Dict[str, Any]) -> None:
    if not isinstance(result, dict):
        return
    api_debug = result.get("api_debug", {}) if isinstance(result.get("api_debug"), dict) else {}
    event_date_model = result.get("event_date_model", {}) if isinstance(result.get("event_date_model"), dict) else {}

    decisions_count = 0
    decisions = result.get("decisions", {})
    if isinstance(decisions, dict):
        if isinstance(decisions.get("rows"), list):
            decisions_count = len(decisions.get("rows", []))
        elif isinstance(decisions.get("items"), list):
            decisions_count = len(decisions.get("items", []))

    health_score_count = 0
    health_score = result.get("health_score", {})
    if isinstance(health_score, dict) and isinstance(health_score.get("items"), list):
        health_score_count = len(health_score.get("items", []))

    seller_id = str(result.get("seller_id") or "")
    report_date = str(event_date_model.get("report_date") or result.get("run_date") or "")
    print(
        "[summary] "
        f"seller_id={seller_id} report_date={report_date} "
        f"orders_rows={int(api_debug.get('orders_rows', 0) or 0)} "
        f"buyouts_rows={int(api_debug.get('sales_rows', 0) or 0)} "
        f"financial_rows={int(api_debug.get('financial_rows', 0) or 0)} "
        f"ads_rows={int(api_debug.get('ads_rows', 0) or 0)} "
        f"decisions_count={decisions_count} "
        f"health_score_count={health_score_count}"
    )
    if "email_transport_status" in result or "email_sent" in result or "email_attempted" in result:
        print(
            "[summary] "
            f"email_attempted={result.get('email_attempted')} "
            f"email_sent={result.get('email_sent')} "
            f"email_transport_status={result.get('email_transport_status')} "
            f"email_stage={result.get('email_stage')} "
            f"email_failure_reason_normalized={result.get('email_failure_reason_normalized')}"
        )


def run_for_seller(seller_id: str, run_date: str | None = None, repo_root: str | None = None) -> Dict[str, Any]:
    resolved_repo_root = repo_root or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    cfg_for_date = load_seller_config(resolved_repo_root, seller_id)
    report_timezone = _resolve_report_timezone(cfg_for_date)
    date_resolution = _resolve_requested_run_date(run_date, report_timezone)
    requested_run_date = str(date_resolution.get("requested_date") or "")
    resolved_run_date = str(date_resolution.get("resolved_date") or "")
    print(
        f"[date] seller={seller_id} requested_date={requested_run_date or '<empty>'} "
        f"resolved_date={resolved_run_date} timezone={report_timezone} "
        f"reason={date_resolution.get('resolution_reason')}"
    )
    try:
        seller_repo_root = _resolve_seller_repo_root(resolved_repo_root, seller_id)
        print(f"[resolve] seller_requested={seller_id} seller_resolved={seller_id}")
        print(f"[{seller_id}] pipeline started")
        _debug_seller_paths(seller_repo_root, seller_id)
        result = _run_daily_for_seller(seller_repo_root, seller_id, resolved_run_date)
        if str(result.get("status") or "") in {"success", "partial_success"}:
            result = _finalize_daily_delivery(
                result if isinstance(result, dict) else {},
                seller_id=seller_id,
                run_date=resolved_run_date,
            )

        status = str(result.get("status") or "")
        if status == "success":
            print(f"[{seller_id}] pipeline finished successfully")
        elif status == "partial_success":
            base_error = str(result.get("error") or "").strip()
            email_error = str(result.get("email_error") or "").strip()
            if email_error and email_error != base_error:
                details = f"{base_error}; {email_error}" if base_error else email_error
            else:
                details = base_error or email_error
            print(f"[{seller_id}] pipeline finished with partial_success: {details}")
            if str(result.get("email_transport_status") or "").strip().lower() == "failed":
                print(
                    f"[{seller_id}] email_failed "
                    f"stage={result.get('email_stage')} "
                    f"reason={result.get('email_failure_reason_normalized')}"
                )
        else:
            print(f"[{seller_id}] pipeline failed: {result.get('error')}")
        _log_result_summary(result if isinstance(result, dict) else {})
        return result
    except Exception as exc:
        print(f"[{seller_id}] pipeline failed: {exc}")
        return _failed_run_result(seller_id, resolved_run_date, mode="daily", error=str(exc))


def run_for_all_sellers(run_date: str | None = None, repo_root: str | None = None) -> Dict[str, Any]:
    resolved_repo_root = repo_root or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    resolved_run_date = run_date or _default_date()
    sellers = [seller for seller in discover_sellers(resolved_repo_root) if seller != _FALLBACK_SELLER_ID]
    print(f"[batch] discovered {len(sellers)} sellers")
    if sellers:
        print(f"[batch] discovered sellers: {' '.join(sellers)}")
    else:
        print("[warn] no valid seller cabinets found")

    results: List[Dict[str, Any]] = []
    for current_seller in sellers:
        results.append(run_for_seller(current_seller, run_date=resolved_run_date, repo_root=resolved_repo_root))

    summary = _batch_summary(resolved_run_date, results)
    summary["batch_summary_path"] = write_batch_summary(resolved_repo_root, summary)
    print("[batch] completed")
    print(f"success: {summary['success_count']}")
    print(f"partial_success: {summary['partial_success_count']}")
    print(f"failed: {summary['failed_count']}")
    return summary


def run_daily_batch(repo_root: str, seller_id: str | None, run_date: str | None) -> Dict[str, Any]:
    if seller_id:
        print(f"[batch] explicit seller: {seller_id}")
        result = run_for_seller(seller_id, run_date=run_date, repo_root=repo_root)
        summary_run_date = str(result.get("run_date") or run_date or "")
        summary = _batch_summary(summary_run_date, [result])
        print("[batch] completed")
        print(f"success: {summary['success_count']}")
        print(f"partial_success: {summary['partial_success_count']}")
        print(f"failed: {summary['failed_count']}")
        return summary
    return run_for_all_sellers(run_date=run_date, repo_root=repo_root)


def _run_daily(repo_root: str, seller_id: str | None, run_date: str | None) -> List[Dict[str, Any]]:
    if seller_id:
        return [run_for_seller(seller_id, run_date=run_date, repo_root=repo_root)]
    batch = run_for_all_sellers(run_date=run_date, repo_root=repo_root)
    return [row for row in batch.get("results", []) if isinstance(row, dict)]


def _run_weekly_for_seller(repo_root: str, seller_id: str, run_date: str) -> Dict[str, Any]:
    from .pipeline.weekly_pipeline_runner import run_weekly_pipeline_for_seller

    return run_weekly_pipeline_for_seller(repo_root, seller_id, run_date)


def _run_weekly(repo_root: str, seller_id: str | None, run_date: str) -> List[Dict[str, Any]]:
    sellers = [seller_id] if seller_id else discover_sellers(repo_root)
    if seller_id is None:
        if sellers:
            print(f"[batch] discovered sellers: {', '.join(sellers)}")
        else:
            print("[warn] no valid seller cabinets found")
    else:
        print(f"[batch] explicit seller: {seller_id}")
    results: List[Dict[str, Any]] = []
    for current_seller in sellers:
        try:
            seller_repo_root = _resolve_seller_repo_root(repo_root, current_seller)
            print(f"[{current_seller}] weekly pipeline started")
            _debug_seller_paths(seller_repo_root, current_seller)
            result = _run_weekly_for_seller(seller_repo_root, current_seller, run_date)
            print(f"[{current_seller}] weekly pipeline finished successfully")
            results.append(result)
        except Exception as exc:
            print(f"[{current_seller}] weekly pipeline failed: {exc}")
            results.append(_failed_run_result(current_seller, run_date, mode="weekly", error=str(exc)))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="WB AI Agent v3 skeleton (does not touch src/main.py)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_daily = sub.add_parser("daily", help="Run daily pipeline")
    p_daily.add_argument("--seller", default=None, help="seller_id, Р ВµРЎРѓР В»Р С‘ Р Р…Р Вµ Р В·Р В°Р Т‘Р В°Р Р… РІР‚вЂќ Р В·Р В°Р С—РЎС“РЎРѓРЎвЂљР С‘РЎвЂљ Р С—Р С• Р Р†РЎРѓР ВµР С cabinets/*")
    p_daily.add_argument("--date", default=None, help="YYYY-MM-DD")

    p_weekly = sub.add_parser("weekly", help="Run weekly intelligence from history snapshots")
    p_weekly.add_argument("--seller", default=None, help="seller_id, РµСЃР»Рё РЅРµ Р·Р°РґР°РЅ вЂ” Р·Р°РїСѓСЃС‚РёС‚ РїРѕ РІСЃРµРј cabinets/*")
    p_weekly.add_argument("--date", default=None, help="YYYY-MM-DD")

    p_audit = sub.add_parser("audit", help="Run audit pipeline (Excel input)")
    p_audit.add_argument("--seller", required=True, help="seller_id")
    p_audit.add_argument("--input", required=True, help="Path to Excel file")
    p_audit.add_argument("--date", default=None, help="YYYY-MM-DD")

    args = parser.parse_args()
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    if args.cmd == "daily":
        results = _run_daily(repo_root=repo_root, seller_id=args.seller, run_date=args.date)
    elif args.cmd == "weekly":
        results = _run_weekly(repo_root=repo_root, seller_id=args.seller, run_date=str(args.date or _default_date()))
    else:
        results = run_audit(
            repo_root=repo_root,
            seller_id=args.seller,
            run_date=str(args.date or _default_date()),
            audit_input=args.input,
        )

    ok = sum(1 for r in results if r.get("status") == "success")
    partial = sum(1 for r in results if r.get("status") == "partial_success")
    fail = sum(1 for r in results if r.get("status") not in {"success", "partial_success"})
    print(f"v3 finished: success={ok} partial_success={partial} failed={fail}")
    for r in results:
        print(f"- {r.get('seller_id')} {r.get('mode')} {r.get('run_date')} => {r.get('status')}")


if __name__ == "__main__":
    main()
