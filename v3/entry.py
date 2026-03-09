from __future__ import annotations
import argparse
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

from .analysis.ai_director import build_strategy_plan
from .analysis.decision_engine import build_decisions
from .analytics.abc_analysis import compute_abc
from .analytics.growth_simulator import simulate_growth
from .analytics.logistics_ktr import build_logistics_ktr
from .analytics.opportunity_engine import compute_opportunity_scores
from .analytics.profit_contribution import build_profit_contribution, save_profit_contribution
from .analytics.sku_health import compute_sku_health
from .analytics.territorial_distribution import build_territorial_distribution, save_territorial_distribution
from .config import load_seller_config
from .history.history_store import save_daily_history_snapshot
from .history.trend_anomalies import build_trend_anomalies, save_trend_anomalies
from .history.weekly_intelligence import build_weekly_intelligence, save_weekly_intelligence
from .memory.decision_logger import log_decisions
from .memory.decision_outcomes import evaluate_decision_outcomes, save_outcomes
from .orchestrator import discover_sellers, run_audit
from .paths import artifacts_dir, cabinet_root, input_dir, reports_dir
from .pdf_render import write_text_pdf
from .sources.wb_reports_loader import (
    build_facts_from_reports,
    build_metrics_from_reports,
    load_local_reports,
)
from .storage import write_json
from src.mailer_yandex import send_email_with_pdf

_FALLBACK_SELLER_ID = "__missing_seller__"
_ALLOW_FALLBACK_ENV = "WB_ALLOW_MISSING_SELLER"


def _default_date() -> str:
    return date.today().isoformat()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _resolve_report_timezone(cfg: Dict[str, Any]) -> str:
    env_tz = str(os.getenv("TZ", "")).strip()
    if env_tz:
        return env_tz
    cfg_tz = str(cfg.get("timezone") or "").strip()
    if cfg_tz:
        return cfg_tz
    return "Europe/Berlin"


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


def _format_int(value: Any) -> str:
    number = int(round(_safe_float(value)))
    return f"{number:,}".replace(",", " ")


def _format_money(value: Any) -> str:
    amount = _safe_float(value)
    rounded = int(round(amount))
    return f"{rounded:,}".replace(",", " ") + " ₽"


def _format_pct(value: Any) -> str:
    return f"{_safe_float(value):.1f} %"


def _format_ktr(value: Any) -> str:
    return f"{_safe_float(value):.2f}"


def _confidence_ru(value: str) -> str:
    mapping = {
        "high": "высокая",
        "medium": "средняя",
        "low": "низкая",
    }
    return mapping.get(str(value or "").strip().lower(), str(value or "низкая"))


def _compact_sku_list(items: List[str], limit: int = 8) -> str:
    clean = [str(x).strip() for x in items if str(x).strip()]
    if not clean:
        return "—"
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
        "unassigned_costs_detected",
        "decision_memory_updated",
        "decision_outcomes_evaluated",
        "no_decisions_ready_for_outcome",
        "sales_report_missing",
        "ads_report_missing",
        "stocks_report_missing",
        "input_files_missing",
        "low_total_profit",
        "profit_concentration_high",
        "wb_token_missing",
        "wb_api_empty",
        "wb_api_zero_sales_rows",
        "wb_api_financial_degraded",
        "financial_data_missing",
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
            f"Отфильтрованы невалидные SKU-строки: {number}."
            if number is not None
            else "Невалидные SKU-строки отфильтрованы."
        ),
        "unassigned_costs_detected": "Часть расходов не привязана к SKU и учтена отдельно.",
        "decision_memory_updated": (
            f"Память решений AI обновлена: добавлено {number} записей."
            if number is not None
            else "Память решений AI обновлена."
        ),
        "decision_outcomes_evaluated": (
            f"Выполнена оценка результатов решений: {number}."
            if number is not None
            else "Выполнена оценка результатов прошлых решений."
        ),
        "no_decisions_ready_for_outcome": "Пока нет решений, готовых к оценке результата.",
        "sales_report_missing": "Не найден валидный отчет продаж.",
        "ads_report_missing": "Не найден валидный рекламный отчет.",
        "stocks_report_missing": "Не найден валидный отчет остатков.",
        "input_files_missing": "Во входной папке нет локальных отчетов.",
        "low_total_profit": "Суммарная прибыль по SKU неположительная.",
        "profit_concentration_high": "Концентрация прибыли в одном SKU слишком высокая.",
        "wb_token_missing": "Отсутствует WB токен для внешнего источника.",
        "wb_api_zero_sales_rows": "WB API вернул 0 строк продаж за выбранный период.",
        "wb_api_financial_degraded": "Финансовые данные WB API не получены, использован деградированный режим.",
        "financial_data_missing": "Данные о продажах не получены.",
        "territorial_distribution_built": (
            f"Рассчитано территориальное распределение для {number} SKU."
            if number is not None
            else "Рассчитано территориальное распределение SKU."
        ),
        "insufficient_warehouse_data": "Недостаточно данных по складам для полного территориального анализа.",
        "high_ktr_detected": (
            f"Обнаружен высокий KTR у {number} SKU."
            if number is not None
            else "Обнаружены SKU с высоким KTR."
        ),
    }
    base = mapping.get(code, text or "Предупреждение системы.")
    if code == "profit_concentration_high" and text:
        return text
    return base


def _build_key_insights(
    facts: Dict[str, Any],
    health_summary: Dict[str, Any],
    outcomes_payload: Dict[str, Any],
    decision_rows_added: int,
) -> List[str]:
    insights: List[str] = []
    profit_summary = facts.get("profit_contribution_summary", {}) if isinstance(facts, dict) else {}
    p1_count = int((profit_summary or {}).get("p1_count", 0) or 0)
    if p1_count > 0:
        insights.append(f"{p1_count} SKU формируют основную прибыль бизнеса (P1).")

    liquidate = int((health_summary or {}).get("LIQUIDATE", 0) or 0)
    if liquidate > 0:
        insights.append(f"{liquidate} SKU находится в зоне ликвидации.")

    data_quality = facts.get("data_quality", {}) if isinstance(facts, dict) else {}
    invalid_rows = int((data_quality or {}).get("invalid_sku_rows", 0) or 0)
    if invalid_rows > 0:
        insights.append(f"{invalid_rows} строк расходов не привязаны к валидному SKU.")

    memory_summary = facts.get("decision_memory_summary", {}) if isinstance(facts, dict) else {}
    total_logged = int((memory_summary or {}).get("total_logged", 0) or 0)
    if total_logged > 0:
        insights.append(f"В памяти AI уже накоплено {total_logged} решений.")
    if decision_rows_added > 0:
        insights.append(f"В текущем запуске добавлено {decision_rows_added} новых решений в память.")

    evaluated = int((outcomes_payload or {}).get("evaluated", 0) or 0)
    if evaluated > 0:
        results = outcomes_payload.get("results", {}) if isinstance(outcomes_payload, dict) else {}
        success = int((results or {}).get("success", 0) or 0)
        neutral = int((results or {}).get("neutral", 0) or 0)
        fail = int((results or {}).get("fail", 0) or 0)
        insights.append(f"Оценка решений: успешных {success}, нейтральных {neutral}, неудачных {fail}.")

    if not insights:
        insights.append("Ключевые показатели рассчитаны без критичных отклонений.")
    return insights[:5]


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


def _mask_email_targets(raw_value: str) -> str:
    parts = [item.strip() for item in re.split(r"[;,]", str(raw_value or "")) if item.strip()]
    if not parts:
        return ""
    return ", ".join(_mask_email_address(item) for item in parts)


def _send_daily_report_email(seller_id: str, run_date: str, report_pdf_path: str) -> str:
    email_to_raw = str(os.getenv("EMAIL_TO", "")).strip()
    email_to_masked = _mask_email_targets(email_to_raw)
    smtp_user = str(os.getenv("YANDEX_SMTP_USER", "")).strip()
    smtp_pass = str(os.getenv("YANDEX_SMTP_APP_PASS", "")).strip()
    attachment_exists = os.path.isfile(report_pdf_path)

    print(f"[mail] email_to={email_to_masked or '<empty>'}")
    print(f"[mail] smtp_user_exists={str(bool(smtp_user)).lower()}")
    print(f"[mail] attachment_exists={str(attachment_exists).lower()}")
    print("[mail] send_started")

    try:
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

        subject = f"WB AI Agent v3 daily report: {seller_id} ({run_date})"
        body = (
            f"WB AI Agent v3 daily report for seller {seller_id} on {run_date}.\n\n"
            "See attached report.pdf."
        )
        send_email_with_pdf(subject=subject, body=body, pdf_path=report_pdf_path)
        print("[mail] send_success")
        return email_to_masked
    except Exception as exc:
        print(f"[mail] send_failed: {exc}")
        raise


def _apply_email_result(
    job: Dict[str, Any],
    *,
    attempted: bool,
    sent: bool,
    email_to: str,
    error: str | None,
) -> Dict[str, Any]:
    job["email_attempted"] = attempted
    job["email_sent"] = sent
    job["email_to"] = email_to
    job["email_error"] = error

    if attempted and not sent and str(job.get("status") or "") == "success":
        job["status"] = "partial_success"
        job["error"] = error or "Email sending failed"
    return job


def _run_daily_for_seller(repo_root: str, seller_id: str, run_date: str) -> Dict[str, Any]:
    cabinet_root(repo_root, seller_id, create=True)
    reports_dir(repo_root, seller_id, create=True)
    seller_input_dir = input_dir(repo_root, seller_id, create=True)
    out_dir = artifacts_dir(repo_root, seller_id, create=True)
    cfg = load_seller_config(repo_root, seller_id)

    started_at = _utc_now_iso()
    seller_name = str(cfg.get("seller_name") or seller_id)

    token = str(os.getenv("WB_API_TOKEN", "")).strip()
    discovered_files: Dict[str, List[str]] = {"sales": [], "ads": [], "stocks": [], "unknown": []}
    input_debug: Dict[str, Any] = {}
    api_debug: Dict[str, Any] = {}
    warnings: List[Dict[str, Any]] = []
    sales_rows: List[Dict[str, Any]] = []
    ads_rows: List[Dict[str, Any]] = []
    stocks_rows: List[Dict[str, Any]] = []
    api_sales_rows: List[Dict[str, Any]] = []
    api_orders_rows: List[Dict[str, Any]] = []
    api_realization_rows: List[Dict[str, Any]] = []
    api_ads_rows: List[Dict[str, Any]] = []
    api_stocks_rows: List[Dict[str, Any]] = []
    local_financial_fallback_used = False

    if token:
        source_mode = "wb_api"
        from .wb_client import WBClient

        report_timezone = _resolve_report_timezone(cfg)
        period = _resolve_wb_period(run_date, report_timezone)
        date_from = str(period.get("date_from") or run_date)
        date_to = str(period.get("date_to") or run_date)
        print(
            f"[wb] period_resolved run_date={run_date} timezone={period.get('timezone')} "
            f"date_from={date_from} date_to={date_to} shifted_to_previous_day={period.get('shifted_to_previous_day')}"
        )

        client = WBClient(token)
        api_realization_rows = client.fetch_realization(date_from=date_from, date_to=date_to)
        api_sales_rows = client.fetch_sales(date_from=date_from, date_to=date_to)
        api_orders_rows = client.fetch_orders(date_from=date_from, date_to=date_to)
        api_ads_rows = client.fetch_ads(date_from=date_from, date_to=date_to)
        api_stocks_rows = client.fetch_stocks()
        ads_rows = list(api_ads_rows)
        stocks_rows = list(api_stocks_rows)

        sales_rows = list(api_realization_rows) if api_realization_rows else _merge_financial_rows(api_sales_rows, api_orders_rows)

        if not api_sales_rows and not api_realization_rows:
            warnings.append(
                {
                    "code": "wb_api_zero_sales_rows",
                    "message": "WB API returned zero sales rows for selected period",
                }
            )

        if not sales_rows:
            local_bundle = load_local_reports(seller_input_dir)
            discovered_files = local_bundle.get("files", discovered_files)
            local_sales_rows = list(local_bundle.get("sales_rows", []))
            local_ads_rows = list(local_bundle.get("ads_rows", []))
            local_stocks_rows = list(local_bundle.get("stocks_rows", []))
            local_warnings = list(local_bundle.get("warnings", []))

            if local_sales_rows:
                sales_rows = local_sales_rows
                local_financial_fallback_used = True
                warnings.append(
                    {
                        "code": "wb_local_sales_fallback_used",
                        "message": "WB API sales data is empty; local sales files were used as fallback.",
                    }
                )
            if not ads_rows and local_ads_rows:
                ads_rows = local_ads_rows
                warnings.append(
                    {
                        "code": "wb_local_ads_fallback_used",
                        "message": "WB API ads data is empty; local ads files were used as fallback.",
                    }
                )
            if not stocks_rows and local_stocks_rows:
                stocks_rows = local_stocks_rows
                warnings.append(
                    {
                        "code": "wb_local_stocks_fallback_used",
                        "message": "WB API stocks data is empty; local stocks files were used as fallback.",
                    }
                )
            warnings.extend(local_warnings)

        if not sales_rows:
            warnings.append(
                {
                    "code": "financial_data_missing",
                    "message": "данные о продажах не получены",
                }
            )

        api_debug = {
            "sales_rows": len(api_sales_rows),
            "orders_rows": len(api_orders_rows),
            "realization_rows": len(api_realization_rows),
            "ads_rows": len(api_ads_rows),
            "stocks_rows": len(api_stocks_rows),
            "date_from": date_from,
            "date_to": date_to,
            "run_date_requested": run_date,
            "timezone": str(period.get("timezone") or report_timezone),
            "shifted_to_previous_day": bool(period.get("shifted_to_previous_day")),
            "local_financial_fallback_used": local_financial_fallback_used,
        }
        input_debug = {
            "source_mode": source_mode,
            "loaded_rows": {
                "sales": len(sales_rows),
                "ads": len(ads_rows),
                "stocks": len(stocks_rows),
            },
            "api_debug": api_debug,
        }
        if not sales_rows and not ads_rows and not stocks_rows:
            warnings.append(
                {
                    "code": "wb_api_empty",
                    "message": "WB API returned no rows",
                }
            )
    else:
        source_mode = "local_reports"
        local_bundle = load_local_reports(seller_input_dir)
        discovered_files = local_bundle.get("files", discovered_files)
        input_debug = local_bundle.get("debug", {})
        warnings = list(local_bundle.get("warnings", []))
        sales_rows = list(local_bundle.get("sales_rows", []))
        ads_rows = list(local_bundle.get("ads_rows", []))
        stocks_rows = list(local_bundle.get("stocks_rows", []))
        api_debug = {
            "sales_rows": 0,
            "orders_rows": 0,
            "realization_rows": 0,
            "ads_rows": 0,
            "stocks_rows": 0,
            "date_from": run_date,
            "date_to": run_date,
        }

    if not isinstance(input_debug, dict):
        input_debug = {}
    if "api_debug" not in input_debug:
        input_debug["api_debug"] = api_debug

    metrics = build_metrics_from_reports(sales_rows, ads_rows, stocks_rows)
    metrics_data_quality = metrics.get("data_quality", {}) if isinstance(metrics, dict) else {}
    invalid_rows = int(metrics_data_quality.get("invalid_sku_rows", 0) or 0)
    if invalid_rows > 0:
        warnings.append(
            {
                "code": "invalid_sku_filtered",
                "message": f"Filtered invalid SKU rows: {invalid_rows}",
            }
        )
    if bool(metrics_data_quality.get("unassigned_costs_present", False)):
        warnings.append(
            {
                "code": "unassigned_costs_detected",
                "message": "Part of costs is not assigned to SKU and stored in unassigned_costs.",
            }
        )
    api_financial_empty = bool(token and not api_realization_rows and not api_sales_rows and not api_orders_rows)
    financial_data_missing_flag = len(sales_rows) == 0
    financial_data_degraded_flag = False
    if financial_data_missing_flag:
        if not any(str(item.get("code") or "") == "financial_data_missing" for item in warnings if isinstance(item, dict)):
            warnings.append(
                {
                    "code": "financial_data_missing",
                    "message": "данные о продажах не получены",
                }
            )
        financial_data_degraded_flag = True
    elif api_financial_empty:
        warnings.append(
            {
                "code": "wb_api_financial_degraded",
                "message": "WB API financial datasets are empty; local fallback data was used.",
            }
        )
        financial_data_degraded_flag = True

    facts = build_facts_from_reports(
        seller_id=seller_id,
        run_date=run_date,
        seller_name=seller_name,
        metrics=metrics,
        discovered_files=discovered_files,
        warnings=warnings,
        source_mode=source_mode,
    )
    facts["source_mode"] = source_mode
    facts["api_debug"] = api_debug
    if isinstance(facts.get("data_quality"), dict):
        facts["data_quality"]["financial_status"] = "degraded" if financial_data_degraded_flag else "ok"

    confidence = str(facts.get("data_confidence", "low"))
    input_summary = facts.get("input_summary", {}) if isinstance(facts, dict) else {}
    data_quality = facts.get("data_quality", {}) if isinstance(facts, dict) else {}
    unassigned_costs = metrics.get("unassigned_costs", {}) if isinstance(metrics, dict) else {}

    sku_metrics = _extract_sku_metrics(metrics)
    abc_rows = compute_abc(sku_metrics)
    abc_summary = {"A": 0, "B": 0, "C": 0}
    for row in abc_rows:
        cls = str(row.get("abc_class", ""))
        if cls in abc_summary:
            abc_summary[cls] += 1

    profit_contribution = build_profit_contribution(metrics if isinstance(metrics, dict) else {})
    p1_rows = profit_contribution.get("p1", []) if isinstance(profit_contribution, dict) else []
    p2_rows = profit_contribution.get("p2", []) if isinstance(profit_contribution, dict) else []
    p3_rows = profit_contribution.get("p3", []) if isinstance(profit_contribution, dict) else []
    top_profit_rows = profit_contribution.get("top_profit_skus", []) if isinstance(profit_contribution, dict) else []
    profit_meta = profit_contribution.get("meta", {}) if isinstance(profit_contribution, dict) else {}
    total_profit = float(profit_meta.get("total_profit", 0.0) or 0.0)

    if total_profit <= 0:
        warnings.append(
            {
                "code": "low_total_profit",
                "message": "Total SKU profit is non-positive; profit contribution shares set to 0.",
            }
        )
    if isinstance(top_profit_rows, list) and top_profit_rows:
        top_share = float((top_profit_rows[0] or {}).get("profit_share", 0.0) or 0.0)
        if top_share > 0.5:
            warnings.append(
                {
                    "code": "profit_concentration_high",
                    "message": f"Top SKU contributes {round(top_share, 4)} of total profit.",
                }
            )

    facts["profit_contribution_summary"] = {
        "p1_count": len(p1_rows) if isinstance(p1_rows, list) else 0,
        "p2_count": len(p2_rows) if isinstance(p2_rows, list) else 0,
        "p3_count": len(p3_rows) if isinstance(p3_rows, list) else 0,
        "top_profit_skus": [
            str(item.get("sku"))
            for item in (top_profit_rows if isinstance(top_profit_rows, list) else [])
            if isinstance(item, dict) and str(item.get("sku") or "").strip()
        ][:5],
    }

    territorial_input: Dict[str, Any] = dict(metrics if isinstance(metrics, dict) else {})
    territorial_input["sales_rows"] = sales_rows
    territorial_input["stocks_rows"] = stocks_rows
    territorial_distribution = build_territorial_distribution(
        territorial_input,
        stocks_raw=stocks_rows,
        seller_id=seller_id,
        run_date=run_date,
    )
    territorial_summary = (
        territorial_distribution.get("summary", {}) if isinstance(territorial_distribution, dict) else {}
    )
    if not isinstance(territorial_summary, dict):
        territorial_summary = {}
    sku_total = int(territorial_summary.get("sku_total", territorial_summary.get("sku_analyzed", 0)) or 0)
    sku_with_ktr = int(
        territorial_summary.get(
            "sku_with_ktr",
            int(territorial_summary.get("balanced_count", 0) or 0)
            + int(territorial_summary.get("moderate_mismatch_count", 0) or 0)
            + int(territorial_summary.get("misallocated_count", 0) or 0),
        )
        or 0
    )
    insufficient_distribution_data_count = int(
        territorial_summary.get("insufficient_distribution_data_count", territorial_summary.get("insufficient_data_count", 0))
        or 0
    )
    no_stock_data_count = int(territorial_summary.get("no_stock_data_count", 0) or 0)
    insufficient_total_count = int(
        territorial_summary.get("insufficient_total_count", territorial_summary.get("insufficient_data_count", 0)) or 0
    )
    facts["territorial_distribution_summary"] = {
        "sku_total": sku_total,
        "sku_with_ktr": sku_with_ktr,
        "balanced_count": int(territorial_summary.get("balanced_count", 0) or 0),
        "moderate_mismatch_count": int(territorial_summary.get("moderate_mismatch_count", 0) or 0),
        "misallocated_count": int(territorial_summary.get("misallocated_count", 0) or 0),
        "insufficient_distribution_data_count": insufficient_distribution_data_count,
        "no_stock_data_count": no_stock_data_count,
        "insufficient_total_count": insufficient_total_count,
        "avg_ktr": float(territorial_summary.get("avg_ktr", 0.0) or 0.0),
        "top_misaligned_skus": (
            [
                str(value)
                for value in territorial_summary.get("top_misaligned_skus", [])
                if str(value or "").strip()
            ][:5]
            if isinstance(territorial_summary.get("top_misaligned_skus"), list)
            else []
        ),
    }

    warnings.append(
        {
            "code": "territorial_distribution_built",
            "message": f"Territorial distribution built for {sku_with_ktr} SKU with KTR",
        }
    )
    if insufficient_total_count > 0:
        warnings.append(
            {
                "code": "insufficient_warehouse_data",
                "message": "Insufficient warehouse-level data for full territorial analysis",
            }
        )
    high_ktr_count = int(territorial_summary.get("misallocated_count", 0) or 0)
    if high_ktr_count > 0:
        warnings.append(
            {
                "code": "high_ktr_detected",
                "message": f"High KTR detected for {high_ktr_count} SKU",
            }
        )

    write_json(os.path.join(out_dir, "metrics.json"), metrics)
    write_json(os.path.join(out_dir, "abc_analysis.json"), abc_rows)
    save_profit_contribution(os.path.join(out_dir, "profit_contribution.json"), profit_contribution)
    save_territorial_distribution(Path(out_dir) / "territorial_distribution.json", territorial_distribution)

    logistics_ktr = build_logistics_ktr(seller_id=seller_id, run_date=run_date, repo_root=repo_root)
    logistics_summary = logistics_ktr.get("summary", {}) if isinstance(logistics_ktr, dict) else {}
    if not isinstance(logistics_summary, dict):
        logistics_summary = {}
    facts["logistics_ktr_summary"] = {
        "sku_total": int(logistics_summary.get("sku_total", 0) or 0),
        "sku_with_ktr": int(logistics_summary.get("sku_with_ktr", 0) or 0),
        "efficient_count": int(logistics_summary.get("efficient_count", 0) or 0),
        "acceptable_count": int(logistics_summary.get("acceptable_count", 0) or 0),
        "inefficient_count": int(logistics_summary.get("inefficient_count", 0) or 0),
        "critical_count": int(logistics_summary.get("critical_count", 0) or 0),
        "low_confidence_count": int(logistics_summary.get("low_confidence_count", 0) or 0),
        "avg_ktr": float(logistics_summary.get("avg_ktr", 0.0) or 0.0),
        "avg_locality_score": float(logistics_summary.get("avg_locality_score", 0.0) or 0.0),
        "top_critical_skus": (
            [
                str(value)
                for value in logistics_summary.get("top_critical_skus", [])
                if str(value or "").strip()
            ][:5]
            if isinstance(logistics_summary.get("top_critical_skus"), list)
            else []
        ),
    }

    health_payload = compute_sku_health(facts, metrics)
    health_summary = health_payload.get("summary", {}) if isinstance(health_payload, dict) else {}
    decisions_payload = build_decisions(metrics, abc_rows, health_payload, territorial_distribution, logistics_ktr)
    decisions_summary = decisions_payload.get("summary", {}) if isinstance(decisions_payload, dict) else {}
    growth_simulation = simulate_growth(metrics if isinstance(metrics, dict) else {})
    opportunity_scores = compute_opportunity_scores(
        metrics if isinstance(metrics, dict) else {},
        abc_rows if isinstance(abc_rows, list) else [],
        health_payload if isinstance(health_payload, dict) else {},
    )
    director_strategy = build_strategy_plan(
        metrics if isinstance(metrics, dict) else {},
        abc_rows if isinstance(abc_rows, list) else [],
        health_payload if isinstance(health_payload, dict) else {},
        territorial_distribution if isinstance(territorial_distribution, dict) else {},
        logistics_ktr if isinstance(logistics_ktr, dict) else {},
        opportunity_scores if isinstance(opportunity_scores, dict) else {},
        growth_simulation if isinstance(growth_simulation, dict) else {},
    )

    job = {
        "seller_id": seller_id,
        "mode": "daily",
        "run_date": run_date,
        "status": "partial_success" if financial_data_missing_flag else "success",
        "started_at": started_at,
        "finished_at": _utc_now_iso(),
        "error": "данные о продажах не получены" if financial_data_missing_flag else None,
        "source_mode": source_mode,
        "artifacts_dir": out_dir,
        "input_debug": input_debug,
        "api_debug": api_debug,
        "data_quality": "degraded" if financial_data_degraded_flag else "ok",
        "artifacts": [
            "job.json",
            "facts.json",
            "metrics.json",
            "warnings.json",
            "abc_analysis.json",
            "profit_contribution.json",
            "territorial_distribution.json",
            "logistics_ktr.json",
            "health_score.json",
            "decisions.json",
            "growth_simulation.json",
            "opportunity_scores.json",
            "director_strategy.json",
            "memory/decision_memory.jsonl",
            f"memory/outcomes/{run_date}_outcomes.json",
            f"history/daily/{run_date}/",
            "history/history_index.json",
            "report_meta.json",
            "report.pdf",
        ],
    }

    write_json(os.path.join(out_dir, "health_score.json"), health_payload)
    write_json(os.path.join(out_dir, "decisions.json"), decisions_payload)
    write_json(os.path.join(out_dir, "growth_simulation.json"), growth_simulation)
    write_json(os.path.join(out_dir, "opportunity_scores.json"), opportunity_scores)
    write_json(os.path.join(out_dir, "director_strategy.json"), director_strategy)

    decision_rows_added = log_decisions(
        seller_id=seller_id,
        run_date=run_date,
        metrics=metrics if isinstance(metrics, dict) else {},
        decisions=decisions_payload if isinstance(decisions_payload, dict) else {},
        artifacts_dir=Path(out_dir),
    )
    if decision_rows_added > 0:
        warnings.append(
            {
                "code": "decision_memory_updated",
                "message": f"Decision memory updated: added {decision_rows_added} records.",
            }
        )
    job["decision_memory_added"] = decision_rows_added

    memory_dir = Path(out_dir).parent / "memory"
    outcomes_payload = evaluate_decision_outcomes(
        seller_id=seller_id,
        run_date=run_date,
        artifacts_dir=Path(out_dir),
        memory_dir=memory_dir,
    )
    outcomes_file = save_outcomes(
        seller_id=seller_id,
        run_date=run_date,
        outcomes=outcomes_payload,
        memory_dir=memory_dir,
    )
    outcomes_evaluated = int(outcomes_payload.get("evaluated", 0) or 0)
    if outcomes_evaluated > 0:
        warnings.append(
            {
                "code": "decision_outcomes_evaluated",
                "message": f"Decision outcomes evaluated: {outcomes_evaluated}",
            }
        )
    else:
        warnings.append(
            {
                "code": "no_decisions_ready_for_outcome",
                "message": "No decisions are ready for outcome evaluation yet",
            }
        )

    decision_memory_summary = outcomes_payload.get("decision_memory_summary", {})
    if not isinstance(decision_memory_summary, dict):
        decision_memory_summary = {}
    facts["decision_memory_summary"] = {
        "total_logged": int(decision_memory_summary.get("total_logged", 0) or 0),
        "pending": int(decision_memory_summary.get("pending", 0) or 0),
        "success": int(decision_memory_summary.get("success", 0) or 0),
        "fail": int(decision_memory_summary.get("fail", 0) or 0),
        "neutral": int(decision_memory_summary.get("neutral", 0) or 0),
    }
    job["decision_outcomes_evaluated"] = outcomes_evaluated
    job["decision_outcomes_file"] = str(outcomes_file)

    write_json(os.path.join(out_dir, "facts.json"), facts)
    write_json(os.path.join(out_dir, "warnings.json"), warnings)
    totals = metrics.get("totals", {}) if isinstance(metrics, dict) else {}
    profit_rows = _top_profit_rows(
        profit_contribution=profit_contribution if isinstance(profit_contribution, dict) else {},
        sku_metrics=sku_metrics,
        abc_rows=abc_rows,
    )
    key_insights = _build_key_insights(
        facts=facts,
        health_summary=health_summary if isinstance(health_summary, dict) else {},
        outcomes_payload=outcomes_payload if isinstance(outcomes_payload, dict) else {},
        decision_rows_added=decision_rows_added,
    )

    page_1: List[str] = [
        "# WB AI Agent — Отчет по кабинету",
        f"### Кабинет: {seller_id}",
        f"### Дата отчета: {run_date}",
        f"### Уверенность данных: {_confidence_ru(confidence)}",
        "",
        "## КЛЮЧЕВЫЕ KPI",
        "Показатель | Значение",
        f"Выручка | {_format_money(totals.get('revenue', 0.0))}",
        f"Прибыль | {_format_money(totals.get('profit', 0.0))}",
        f"Количество SKU | {_format_int(len(sku_metrics))}",
        f"Выкупы / Заказы | {_format_int(totals.get('buys', 0))} / {_format_int(totals.get('orders', 0))}",
        f"Расходы на рекламу | {_format_money(totals.get('ads_spend', 0.0))}",
        "",
        "## КЛЮЧЕВЫЕ ВЫВОДЫ",
    ]
    page_1.extend(f"- {line}" for line in key_insights)
    balanced_count = int(territorial_summary.get("balanced_count", 0) or 0)
    moderate_count = int(territorial_summary.get("moderate_mismatch_count", 0) or 0)
    misallocated_count = int(territorial_summary.get("misallocated_count", 0) or 0)
    analyzed_with_ktr = int(
        territorial_summary.get("sku_with_ktr", balanced_count + moderate_count + misallocated_count) or 0
    )
    top_misaligned_pdf = territorial_summary.get("top_misaligned_skus", [])
    if not isinstance(top_misaligned_pdf, list):
        top_misaligned_pdf = []
    top_misaligned_pdf = [str(x).strip() for x in top_misaligned_pdf if str(x).strip()]
    territorial_items = territorial_distribution.get("skus", []) if isinstance(territorial_distribution, dict) else []
    if not isinstance(territorial_items, list) and isinstance(territorial_distribution, dict):
        territorial_items = territorial_distribution.get("items", [])
    if not isinstance(territorial_items, list):
        territorial_items = []
    confidence_by_sku: Dict[str, str] = {}
    for item in territorial_items:
        if not isinstance(item, dict):
            continue
        sku = str(item.get("sku") or "").strip()
        if not sku:
            continue
        confidence_by_sku[sku] = str(item.get("confidence") or "").strip().lower()
    top_misaligned_confident = [sku for sku in top_misaligned_pdf if confidence_by_sku.get(sku) != "low"]
    excluded_low_conf_count = len([sku for sku in top_misaligned_pdf if confidence_by_sku.get(sku) == "low"])
    low_conf_ktr_count = sum(
        1
        for item in territorial_items
        if isinstance(item, dict)
        and _safe_float(item.get("ktr")) > 0
        and str(item.get("confidence") or "").strip().lower() == "low"
    )
    top_misaligned_text = _compact_sku_list(top_misaligned_confident, limit=3)

    page_1.extend(["", "## ТЕРРИТОРИАЛЬНОЕ РАСПРЕДЕЛЕНИЕ"])
    if analyzed_with_ktr <= 0:
        page_1.append("- Недостаточно данных для анализа территориального распределения")
    else:
        page_1.append(f"- Средний КТР по кабинету: {_format_ktr(territorial_summary.get('avg_ktr', 0.0))}")
        page_1.append(f"- Хорошо распределены: {_format_int(balanced_count)} SKU")
        page_1.append(f"- Есть перекос: {_format_int(moderate_count + misallocated_count)} SKU")
        if top_misaligned_confident:
            page_1.append(f"- Наибольший перекос (confidence medium/high): {top_misaligned_text}")
        elif top_misaligned_pdf:
            page_1.append("- Наибольший перекос: только low-confidence SKU (total_buys < 3)")
        else:
            page_1.append("- Наибольший перекос: —")
        if excluded_low_conf_count > 0:
            page_1.append(f"- Исключено low-confidence SKU из топа: {_format_int(excluded_low_conf_count)}")
        if low_conf_ktr_count > 0:
            page_1.append(
                f"- Low-confidence KTR (total_buys < 3): {_format_int(low_conf_ktr_count)} SKU, интерпретировать осторожно"
            )

    logistics_top_critical = logistics_summary.get("top_critical_skus", []) if isinstance(logistics_summary, dict) else []
    if not isinstance(logistics_top_critical, list):
        logistics_top_critical = []
    logistics_top_critical = [str(x).strip() for x in logistics_top_critical if str(x).strip()]
    logistics_sku_total = int(logistics_summary.get("sku_total", 0) or 0) if isinstance(logistics_summary, dict) else 0
    if logistics_sku_total > 0:
        page_1.extend(["", "## LOGISTICS KTR"])
        page_1.append(f"- Critical SKU: {_format_int(logistics_summary.get('critical_count', 0))}")
        page_1.append(f"- Inefficient SKU: {_format_int(logistics_summary.get('inefficient_count', 0))}")
        page_1.append(f"- Average locality score: {_format_ktr(logistics_summary.get('avg_locality_score', 0.0))}")
        if logistics_top_critical:
            page_1.append(f"- Top critical SKU: {_compact_sku_list(logistics_top_critical, limit=5)}")
        else:
            page_1.append("- Top critical SKU: —")

    page_1.extend(["", "## ТОП SKU ПО ПРИБЫЛИ", "SKU | Прибыль | Маржа | Класс прибыли | ABC"])
    if profit_rows:
        for row in profit_rows[:5]:
            page_1.append(
                f"{row.get('sku', 'n/a')} | "
                f"{_format_money(row.get('profit', 0.0))} | "
                f"{_format_pct(row.get('margin_pct', 0.0))} | "
                f"{str(row.get('profit_class', '-') or '-')} | "
                f"{str(row.get('abc_class', '-') or '-')}"
            )
    else:
        page_1.append("Нет данных по SKU.")

    decision_groups: Dict[str, List[Dict[str, Any]]] = {}
    if isinstance(decisions_summary, dict):
        for key in ("scale", "fix", "watch", "liquidate"):
            rows = decisions_summary.get(key, [])
            decision_groups[key] = [x for x in rows if isinstance(x, dict)] if isinstance(rows, list) else []
    else:
        decision_groups = {"scale": [], "fix": [], "watch": [], "liquidate": []}

    status_labels = {
        "scale": "МАСШТАБИРОВАТЬ (SCALE)",
        "fix": "ИСПРАВИТЬ (FIX)",
        "watch": "НАБЛЮДАТЬ (WATCH)",
        "liquidate": "ЛИКВИДИРОВАТЬ (LIQUIDATE)",
    }

    page_2: List[str] = [
        "# СТАТУС SKU И РЕШЕНИЯ AI",
        "## СТАТУС SKU",
        f"- {status_labels['scale']}: {_format_int(len(decision_groups['scale']))} — "
        f"{_compact_sku_list([str(x.get('sku') or '').strip() for x in decision_groups['scale']])}",
        f"- {status_labels['fix']}: {_format_int(len(decision_groups['fix']))} — "
        f"{_compact_sku_list([str(x.get('sku') or '').strip() for x in decision_groups['fix']])}",
        f"- {status_labels['watch']}: {_format_int(len(decision_groups['watch']))} — "
        f"{_compact_sku_list([str(x.get('sku') or '').strip() for x in decision_groups['watch']])}",
        f"- {status_labels['liquidate']}: {_format_int(len(decision_groups['liquidate']))} — "
        f"{_compact_sku_list([str(x.get('sku') or '').strip() for x in decision_groups['liquidate']])}",
        "",
        "## РЕШЕНИЯ AI",
    ]

    def _append_decision_group(page: List[str], group_key: str) -> None:
        page.append(f"### {status_labels[group_key]}")
        rows = decision_groups.get(group_key, [])
        if not rows:
            page.append("- Нет SKU в этой группе.")
            page.append("")
            return
        for row in rows:
            sku = str(row.get("sku") or "n/a")
            action_text = str(row.get("action") or "").strip() or "Решение не задано"
            page.append(f"- SKU {sku} — прибыль {_format_money(row.get('profit', 0.0))} — {action_text.lower()}")
        page.append("")

    _append_decision_group(page_2, "scale")
    _append_decision_group(page_2, "fix")
    _append_decision_group(page_2, "watch")
    _append_decision_group(page_2, "liquidate")

    director_strategy_payload = director_strategy if isinstance(director_strategy, dict) else {}
    director_groups_raw = director_strategy_payload.get("strategy", {})
    if not isinstance(director_groups_raw, dict):
        director_groups_raw = {}
    director_tasks_raw = director_strategy_payload.get("tasks", [])
    if not isinstance(director_tasks_raw, list):
        director_tasks_raw = []

    director_groups: Dict[str, List[str]] = {}
    for key in ("scale", "fix", "watch", "liquidate"):
        raw_rows = director_groups_raw.get(key, [])
        if isinstance(raw_rows, list):
            director_groups[key] = [str(item).strip() for item in raw_rows if str(item).strip()]
        else:
            director_groups[key] = []

    task_by_sku: Dict[str, str] = {}
    for row in director_tasks_raw:
        if not isinstance(row, dict):
            continue
        sku = str(row.get("sku") or "").strip()
        task = str(row.get("task") or "").strip()
        if not sku or not task:
            continue
        task_by_sku.setdefault(sku, task)

    director_default_actions = {
        "scale": "increase_ads",
        "fix": "improve_listing",
        "watch": "monitor",
        "liquidate": "discount_or_remove",
    }

    page_2.extend(["## СТРАТЕГИЯ AI ДИРЕКТОРА"])
    for key in ("scale", "fix", "watch", "liquidate"):
        page_2.append(f"### {status_labels[key]}")
        rows = director_groups.get(key, [])
        if not rows:
            page_2.append("- Нет SKU в этой группе.")
            continue
        default_task = director_default_actions.get(key, "")
        for sku in rows[:10]:
            task = task_by_sku.get(sku) or default_task
            page_2.append(f"- SKU {sku} -> {task}")
    rebalance_rows = [
        row
        for row in director_tasks_raw
        if isinstance(row, dict) and str(row.get("task") or "").strip() == "rebalance_stock"
    ]
    if rebalance_rows:
        page_2.append("### ЛОГИСТИЧЕСКАЯ БАЛАНСИРОВКА")
        for row in rebalance_rows[:10]:
            sku = str(row.get("sku") or "").strip()
            if sku:
                page_2.append(f"- SKU {sku} -> rebalance_stock")

    memory_summary = facts.get("decision_memory_summary", {}) if isinstance(facts, dict) else {}
    important_warnings = _important_warnings(warnings)

    page_3: List[str] = [
        "# ОБУЧЕНИЕ AI И КАЧЕСТВО ДАННЫХ",
        "## ПАМЯТЬ РЕШЕНИЙ AI",
        "Показатель | Значение",
        f"Всего решений | {_format_int(memory_summary.get('total_logged', 0))}",
        f"Ожидают оценки | {_format_int(memory_summary.get('pending', 0))}",
        f"Успешных | {_format_int(memory_summary.get('success', 0))}",
        f"Неудачных | {_format_int(memory_summary.get('fail', 0))}",
        f"Нейтральных | {_format_int(memory_summary.get('neutral', 0))}",
    ]
    if outcomes_evaluated > 0:
        outcome_results = outcomes_payload.get("results", {}) if isinstance(outcomes_payload, dict) else {}
        page_3.append(
            f"- AI оценил {_format_int(outcomes_evaluated)} прошлых решений: "
            f"{_format_int(outcome_results.get('success', 0))} успешных, "
            f"{_format_int(outcome_results.get('neutral', 0))} нейтральных, "
            f"{_format_int(outcome_results.get('fail', 0))} неудачных."
        )

    page_3.extend(
        [
            "",
            "## КАЧЕСТВО ДАННЫХ",
            "Показатель | Значение",
            f"Валидные SKU | {_format_int(data_quality.get('valid_sku_count', 0))}",
            f"Невалидные строки | {_format_int(data_quality.get('invalid_sku_rows', 0))}",
            f"Расходы без SKU | {'Да' if bool(data_quality.get('unassigned_costs_present', False)) else 'Нет'}",
        ]
    )
    if bool(data_quality.get("unassigned_costs_present", False)):
        page_3.append("- Часть расходов не привязана к SKU и учтена отдельно.")

    page_3.extend(["", "## ПРЕДУПРЕЖДЕНИЯ СИСТЕМЫ"])
    if important_warnings:
        for item in important_warnings:
            code = str(item.get("code") or "")
            message = _warning_message_ru(code, str(item.get("message") or ""))
            page_3.append(f"- {message}")
    else:
        page_3.append("- Важных предупреждений нет.")

    report_pages: List[List[str]] = [page_1, page_2, page_3]
    pdf_lines: List[str] = []
    for idx, page in enumerate(report_pages):
        if idx > 0:
            pdf_lines.append("\f")
        pdf_lines.extend(page)

    font_info = write_text_pdf(os.path.join(out_dir, "report.pdf"), pdf_lines)
    job["pdf_font"] = {
        "family": font_info.get("family", ""),
        "regular": font_info.get("regular", ""),
        "bold": font_info.get("bold", ""),
    }
    report_meta: Dict[str, Any] = {
        "pdf_path": os.path.join(out_dir, "report.pdf"),
        "font": job["pdf_font"],
        "pages": int(str(font_info.get("pages", "1"))),
    }
    report_meta["page_previews"] = [
        {"page": page_idx + 1, "lines": page[:30]} for page_idx, page in enumerate(report_pages)
    ]

    write_json(os.path.join(out_dir, "report_meta.json"), report_meta)
    history_dir = Path(out_dir).parent / "history"
    history_snapshot = save_daily_history_snapshot(
        seller_id=seller_id,
        run_date=run_date,
        artifacts_dir=Path(out_dir),
        history_dir=history_dir,
    )
    history_summary = history_snapshot.get("history_summary", {}) if isinstance(history_snapshot, dict) else {}
    if not isinstance(history_summary, dict):
        history_summary = {}

    facts["history_summary"] = {
        "snapshots_count": int(history_summary.get("snapshots_count", 0) or 0),
        "latest_snapshot_date": str(history_summary.get("latest_snapshot_date") or run_date),
    }

    warnings.append(
        {
            "code": "history_snapshot_saved",
            "message": f"History snapshot saved for {run_date}",
        }
    )
    write_json(os.path.join(out_dir, "facts.json"), facts)
    write_json(os.path.join(out_dir, "warnings.json"), warnings)

    history_snapshot_final = save_daily_history_snapshot(
        seller_id=seller_id,
        run_date=run_date,
        artifacts_dir=Path(out_dir),
        history_dir=history_dir,
    )
    job["history_snapshot"] = {
        "date": run_date,
        "path": str((history_snapshot_final or {}).get("snapshot_path", "")),
        "files": (history_snapshot_final or {}).get("files", []),
    }
    job["warnings"] = [item for item in warnings if isinstance(item, dict)]
    write_json(os.path.join(out_dir, "job.json"), job)

    return job


def _failed_run_result(seller_id: str, run_date: str, mode: str, error: str) -> Dict[str, Any]:
    return {
        "seller_id": seller_id,
        "mode": mode,
        "run_date": run_date,
        "status": "failed",
        "error": error,
    }


def _batch_summary(run_date: str, results: List[Dict[str, Any]]) -> Dict[str, Any]:
    success_count = sum(1 for row in results if str(row.get("status") or "") == "success")
    partial_success_count = sum(1 for row in results if str(row.get("status") or "") == "partial_success")
    failed_count = sum(
        1 for row in results if str(row.get("status") or "") not in {"success", "partial_success"}
    )
    return {
        "run_date": run_date,
        "total_sellers": len(results),
        "success_count": success_count,
        "partial_success_count": partial_success_count,
        "failed_count": failed_count,
        "results": results,
    }


def _save_batch_summary(repo_root: str, summary: Dict[str, Any]) -> str:
    cabinets_dir = Path(repo_root) / "cabinets"
    batch_path = cabinets_dir / "_batch" / "batch_run_summary.json"
    write_json(str(batch_path), summary)
    return str(batch_path)


def _resolve_seller_repo_root(repo_root: str, seller_id: str) -> str:
    discovered = discover_sellers(repo_root)
    if seller_id in discovered:
        return repo_root
    if seller_id == _FALLBACK_SELLER_ID:
        allow_fallback = str(os.getenv(_ALLOW_FALLBACK_ENV, "")).strip() == "1"
        if allow_fallback:
            print(
                f"[warn] fallback seller '{_FALLBACK_SELLER_ID}' enabled via {_ALLOW_FALLBACK_ENV}=1; "
                "using debug fallback cabinet paths."
            )
            return repo_root
        if discovered:
            raise ValueError(
                f"Refusing fallback seller '{_FALLBACK_SELLER_ID}' because real sellers exist: {', '.join(discovered)}. "
                f"Set {_ALLOW_FALLBACK_ENV}=1 to force debug fallback."
            )
        print(
            f"[warn] using fallback seller '{_FALLBACK_SELLER_ID}' because no real sellers were discovered in "
            f"{Path(repo_root) / 'cabinets'}."
        )
        return repo_root

    if discovered:
        raise FileNotFoundError(f"Seller '{seller_id}' not found. Discovered sellers: {', '.join(discovered)}")

    print(
        f"[warn] seller '{seller_id}' not discovered; running in bootstrap mode because no sellers exist in "
        f"{Path(repo_root) / 'cabinets'}."
    )
    return repo_root


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


def run_for_seller(seller_id: str, run_date: str | None = None, repo_root: str | None = None) -> Dict[str, Any]:
    resolved_repo_root = repo_root or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    resolved_run_date = run_date or _default_date()
    try:
        seller_repo_root = _resolve_seller_repo_root(resolved_repo_root, seller_id)
        print(f"[{seller_id}] pipeline started")
        _debug_seller_paths(seller_repo_root, seller_id)
        result = _run_daily_for_seller(seller_repo_root, seller_id, resolved_run_date)
        if str(result.get("status") or "") in {"success", "partial_success"}:
            report_pdf_path = os.path.join(str(result.get("artifacts_dir") or ""), "report.pdf")
            email_to_masked = _mask_email_targets(str(os.getenv("EMAIL_TO", "")).strip())
            try:
                email_to_masked = _send_daily_report_email(seller_id, resolved_run_date, report_pdf_path)
                result = _apply_email_result(
                    result,
                    attempted=True,
                    sent=True,
                    email_to=email_to_masked,
                    error=None,
                )
            except Exception as exc:
                result = _apply_email_result(
                    result,
                    attempted=True,
                    sent=False,
                    email_to=email_to_masked,
                    error=str(exc),
                )

            job_path = os.path.join(str(result.get("artifacts_dir") or ""), "job.json")
            if str(result.get("artifacts_dir") or "").strip():
                write_json(job_path, result)

        status = str(result.get("status") or "")
        if status == "success":
            print(f"[{seller_id}] pipeline finished successfully")
        elif status == "partial_success":
            print(
                f"[{seller_id}] pipeline finished with partial_success: "
                f"{result.get('error') or result.get('email_error')}"
            )
        else:
            print(f"[{seller_id}] pipeline failed: {result.get('error')}")
        return result
    except Exception as exc:
        print(f"[{seller_id}] pipeline failed: {exc}")
        return _failed_run_result(seller_id, resolved_run_date, mode="daily", error=str(exc))


def run_for_all_sellers(run_date: str | None = None, repo_root: str | None = None) -> Dict[str, Any]:
    resolved_repo_root = repo_root or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    resolved_run_date = run_date or _default_date()
    sellers = discover_sellers(resolved_repo_root)
    print(f"[batch] discovered {len(sellers)} sellers")
    if sellers:
        print(f"[batch] discovered sellers: {' '.join(sellers)}")
    else:
        print("[warn] no valid seller cabinets found")

    results: List[Dict[str, Any]] = []
    for current_seller in sellers:
        results.append(run_for_seller(current_seller, run_date=resolved_run_date, repo_root=resolved_repo_root))

    summary = _batch_summary(resolved_run_date, results)
    summary["batch_summary_path"] = _save_batch_summary(resolved_repo_root, summary)
    print("[batch] completed")
    print(f"success: {summary['success_count']}")
    print(f"partial_success: {summary['partial_success_count']}")
    print(f"failed: {summary['failed_count']}")
    return summary


def run_daily_batch(repo_root: str, seller_id: str | None, run_date: str) -> Dict[str, Any]:
    if seller_id:
        print(f"[batch] explicit seller: {seller_id}")
        result = run_for_seller(seller_id, run_date=run_date, repo_root=repo_root)
        summary = _batch_summary(run_date, [result])
        print("[batch] completed")
        print(f"success: {summary['success_count']}")
        print(f"partial_success: {summary['partial_success_count']}")
        print(f"failed: {summary['failed_count']}")
        return summary
    return run_for_all_sellers(run_date=run_date, repo_root=repo_root)


def _run_daily(repo_root: str, seller_id: str | None, run_date: str) -> List[Dict[str, Any]]:
    if seller_id:
        return [run_for_seller(seller_id, run_date=run_date, repo_root=repo_root)]
    batch = run_for_all_sellers(run_date=run_date, repo_root=repo_root)
    return [row for row in batch.get("results", []) if isinstance(row, dict)]


def _run_weekly_for_seller(repo_root: str, seller_id: str, run_date: str) -> Dict[str, Any]:
    cabinet_root(repo_root, seller_id, create=True)
    out_dir = artifacts_dir(repo_root, seller_id, create=True)
    history_dir = Path(repo_root) / "cabinets" / seller_id / "history"

    started_at = _utc_now_iso()
    weekly_data = build_weekly_intelligence(
        seller_id=seller_id,
        history_dir=history_dir,
        run_date=run_date,
    )
    weekly_path = save_weekly_intelligence(
        seller_id=seller_id,
        artifacts_dir=Path(out_dir),
        data=weekly_data,
    )
    trend_data = build_trend_anomalies(
        seller_id=seller_id,
        run_date=run_date,
        history_dir=history_dir,
    )
    trend_path = save_trend_anomalies(
        artifacts_dir=Path(out_dir),
        data=trend_data,
    )

    snapshots_used = int(weekly_data.get("snapshots_used", 0) or 0)
    anomaly_snapshots_used = int(trend_data.get("snapshots_used", 0) or 0)
    warnings: List[Dict[str, Any]] = [
        {
            "code": "weekly_intelligence_built",
            "message": f"Weekly intelligence built from {snapshots_used} snapshots",
        },
        {
            "code": "trend_anomalies_built",
            "message": f"Trend anomalies built from {anomaly_snapshots_used} snapshots",
        }
    ]
    if snapshots_used < 7:
        warnings.append(
            {
                "code": "insufficient_history_for_full_weekly",
                "message": f"Only {snapshots_used} snapshots available; full 7-day analysis is limited",
            }
        )
    if anomaly_snapshots_used < 3:
        warnings.append(
            {
                "code": "insufficient_history_for_anomaly_detection",
                "message": f"Only {anomaly_snapshots_used} snapshots available; anomaly detection is limited",
            }
        )

    kpi_trends = weekly_data.get("kpi_trends", {}) if isinstance(weekly_data, dict) else {}
    if not isinstance(kpi_trends, dict):
        kpi_trends = {}
    anomaly_summary = trend_data.get("summary", {}) if isinstance(trend_data, dict) else {}
    if not isinstance(anomaly_summary, dict):
        anomaly_summary = {}

    weekly_facts = {
        "seller_id": seller_id,
        "run_date": run_date,
        "window_days": int(weekly_data.get("window_days", 7) or 7),
        "snapshots_used": snapshots_used,
        "weekly_summary": {
            "revenue_delta_pct": (kpi_trends.get("revenue") or {}).get("delta_pct"),
            "profit_delta_pct": (kpi_trends.get("profit") or {}).get("delta_pct"),
            "buyouts_delta_pct": (kpi_trends.get("buyouts") or {}).get("delta_pct"),
        },
        "anomaly_summary": {
            "total_anomalies": int(anomaly_summary.get("total_anomalies", 0) or 0),
            "high": int(anomaly_summary.get("high", 0) or 0),
            "medium": int(anomaly_summary.get("medium", 0) or 0),
            "low": int(anomaly_summary.get("low", 0) or 0),
        },
    }

    write_json(os.path.join(out_dir, "weekly_facts.json"), weekly_facts)
    write_json(os.path.join(out_dir, "warnings.json"), warnings)

    sku_trends = weekly_data.get("sku_trends", {}) if isinstance(weekly_data, dict) else {}
    if not isinstance(sku_trends, dict):
        sku_trends = {}
    growing = sku_trends.get("growing", [])
    declining = sku_trends.get("declining", [])
    if not isinstance(growing, list):
        growing = []
    if not isinstance(declining, list):
        declining = []

    weekly_pdf_lines: List[str] = [
        "# НЕДЕЛЬНЫЙ ОТЧЕТ",
        f"### Кабинет: {seller_id}",
        f"### Дата: {run_date}",
        f"### Период анализа: {weekly_data.get('window_days', 7)} дней",
        f"### Использовано snapshot: {snapshots_used}",
        "",
        "## ТЕНДЕНЦИИ KPI",
        "KPI | Начало | Текущее | Изменение | Изменение %",
    ]

    weekly_kpi_labels = {
        "revenue": "Выручка",
        "profit": "Прибыль",
        "buyouts": "Выкупы",
        "ads_spend": "Реклама",
        "sku_count": "SKU",
    }
    for key in ("revenue", "profit", "buyouts", "ads_spend", "sku_count"):
        row = kpi_trends.get(key, {})
        if not isinstance(row, dict):
            row = {}
        weekly_pdf_lines.append(
            f"{weekly_kpi_labels.get(key, key)} | {row.get('start', 0)} | {row.get('current', 0)} | {row.get('delta', 0)} | {row.get('delta_pct', None)}"
        )

    weekly_pdf_lines.extend(["", "## РАСТУЩИЕ SKU"])
    if growing:
        for item in growing[:10]:
            if not isinstance(item, dict):
                continue
            weekly_pdf_lines.append(
                f"- SKU {item.get('sku', 'н/д')} | изменение прибыли {item.get('profit_delta', 0)}"
            )
    else:
        weekly_pdf_lines.append("- нет")

    weekly_pdf_lines.extend(["", "## СНИЖАЮЩИЕСЯ SKU"])
    if declining:
        for item in declining[:10]:
            if not isinstance(item, dict):
                continue
            weekly_pdf_lines.append(
                f"- SKU {item.get('sku', 'н/д')} | изменение прибыли {item.get('profit_delta', 0)}"
            )
    else:
        weekly_pdf_lines.append("- нет")

    weekly_pdf_lines.extend(["", "## НЕДЕЛЬНЫЕ ВЫВОДЫ AI"])
    insights = weekly_data.get("insights", []) if isinstance(weekly_data, dict) else []
    if isinstance(insights, list) and insights:
        for insight in insights[:8]:
            weekly_pdf_lines.append(f"- {insight}")
    else:
        weekly_pdf_lines.append("- Недостаточно данных для недельных выводов.")

    kpi_anomalies = trend_data.get("kpi_anomalies", []) if isinstance(trend_data, dict) else []
    sku_anomalies = trend_data.get("sku_anomalies", []) if isinstance(trend_data, dict) else []
    if not isinstance(kpi_anomalies, list):
        kpi_anomalies = []
    if not isinstance(sku_anomalies, list):
        sku_anomalies = []
    combined_anomalies = [x for x in (kpi_anomalies + sku_anomalies) if isinstance(x, dict)]
    severity_order = {"high": 0, "medium": 1, "low": 2}
    combined_anomalies.sort(
        key=lambda x: (
            severity_order.get(str(x.get("severity") or "").lower(), 3),
            str(x.get("metric") or x.get("sku") or ""),
            str(x.get("type") or ""),
        )
    )

    weekly_pdf_lines.extend(["", "## АНОМАЛИИ И РИСКИ"])
    if not combined_anomalies:
        weekly_pdf_lines.append("- Значимых аномалий не обнаружено")
    else:
        for severity in ("high", "medium", "low"):
            rows = [x for x in combined_anomalies if str(x.get("severity") or "").lower() == severity]
            if not rows:
                continue
            for row in rows:
                level = severity.upper()
                message = str(row.get("message") or "Обнаружена аномалия.")
                sku = str(row.get("sku") or "").strip()
                if sku:
                    weekly_pdf_lines.append(f"- [{level}] SKU {sku}: {message}")
                else:
                    weekly_pdf_lines.append(f"- [{level}] {message}")

    write_text_pdf(os.path.join(out_dir, "weekly_report.pdf"), weekly_pdf_lines)

    job = {
        "seller_id": seller_id,
        "mode": "weekly",
        "run_date": run_date,
        "status": "success",
        "started_at": started_at,
        "finished_at": _utc_now_iso(),
        "error": None,
        "artifacts_dir": out_dir,
        "artifacts": [
            "job.json",
            "weekly_intelligence.json",
            "trend_anomalies.json",
            "weekly_facts.json",
            "warnings.json",
            "weekly_report.pdf",
        ],
        "weekly_intelligence_path": str(weekly_path),
        "trend_anomalies_path": str(trend_path),
        "snapshots_used": snapshots_used,
    }
    write_json(os.path.join(out_dir, "job.json"), job)
    return job


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
    p_daily.add_argument("--seller", default=None, help="seller_id, РµСЃР»Рё РЅРµ Р·Р°РґР°РЅ вЂ” Р·Р°РїСѓСЃС‚РёС‚ РїРѕ РІСЃРµРј cabinets/*")
    p_daily.add_argument("--date", default=_default_date(), help="YYYY-MM-DD")

    p_weekly = sub.add_parser("weekly", help="Run weekly intelligence from history snapshots")
    p_weekly.add_argument("--seller", default=None, help="seller_id, если не задан — запустит по всем cabinets/*")
    p_weekly.add_argument("--date", default=_default_date(), help="YYYY-MM-DD")

    p_audit = sub.add_parser("audit", help="Run audit pipeline (Excel input)")
    p_audit.add_argument("--seller", required=True, help="seller_id")
    p_audit.add_argument("--input", required=True, help="Path to Excel file")
    p_audit.add_argument("--date", default=_default_date(), help="YYYY-MM-DD")

    args = parser.parse_args()
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    if args.cmd == "daily":
        results = _run_daily(repo_root=repo_root, seller_id=args.seller, run_date=args.date)
    elif args.cmd == "weekly":
        results = _run_weekly(repo_root=repo_root, seller_id=args.seller, run_date=args.date)
    else:
        results = run_audit(repo_root=repo_root, seller_id=args.seller, run_date=args.date, audit_input=args.input)

    ok = sum(1 for r in results if r.get("status") == "success")
    partial = sum(1 for r in results if r.get("status") == "partial_success")
    fail = sum(1 for r in results if r.get("status") not in {"success", "partial_success"})
    print(f"v3 finished: success={ok} partial_success={partial} failed={fail}")
    for r in results:
        print(f"- {r.get('seller_id')} {r.get('mode')} {r.get('run_date')} => {r.get('status')}")


if __name__ == "__main__":
    main()
