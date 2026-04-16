from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List

from ..domain.event_model import build_event_date_model
from .daily_stage_support import sync_from_entry


def _safe_float_metric(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _sum_metric(rows: List[Dict[str, Any]], keys: tuple[str, ...]) -> float | None:
    total = 0.0
    found = False
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in keys:
            value = _safe_float_metric(row.get(key))
            if value is None:
                continue
            total += value
            found = True
            break
    if not found:
        return None
    return round(total, 2)


def _api_probe_metrics(
    *,
    api_orders_rows: List[Dict[str, Any]],
    api_sales_rows: List[Dict[str, Any]],
    api_realization_rows: List[Dict[str, Any]],
    api_ads_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    orders_count = len([row for row in api_orders_rows if isinstance(row, dict)]) or None
    orders_amount = _sum_metric(api_orders_rows, ("price", "revenue", "totalPrice", "finishedPrice"))
    buyouts = len([row for row in api_sales_rows if isinstance(row, dict)]) or None
    if buyouts is None:
        buyouts = len([row for row in api_realization_rows if isinstance(row, dict)]) or None
    views = _sum_metric(api_ads_rows, ("impressions", "views", "shows"))
    add_to_cart = _sum_metric(api_ads_rows, ("add_to_cart", "addToCart", "cart_count", "atbs"))
    ads_spend = _sum_metric(api_ads_rows, ("ads_spend", "spend", "cost", "sum"))
    return {
        "orders_count": orders_count,
        "orders_amount": orders_amount,
        "buyouts": buyouts,
        "views": views,
        "add_to_cart": add_to_cart,
        "ads_spend": ads_spend,
    }


def _log_api_probe_metrics(metrics: Dict[str, Any]) -> None:
    if not isinstance(metrics, dict):
        metrics = {}

    def _as_text(key: str) -> str:
        value = metrics.get(key)
        if value is None:
            return "missing"
        if key in {"orders_count", "buyouts", "views", "add_to_cart"}:
            return str(int(round(float(value))))
        return f"{float(value):.2f}"

    print(
        "[wb] api_probe "
        f"orders_count={_as_text('orders_count')} "
        f"orders_amount={_as_text('orders_amount')} "
        f"buyouts={_as_text('buyouts')} "
        f"views={_as_text('views')} "
        f"add_to_cart={_as_text('add_to_cart')} "
        f"ads_spend={_as_text('ads_spend')}"
    )
    if any(metrics.get(key) is None for key in ("orders_count", "orders_amount", "buyouts", "views", "add_to_cart", "ads_spend")):
        print("API DATA MISSING")


def _resolve_funnel_contour_source(
    *,
    local_funnel_found: bool,
    api_ads_rows: List[Dict[str, Any]],
    api_orders_rows: List[Dict[str, Any]],
    api_sales_rows: List[Dict[str, Any]],
) -> str:
    if bool(local_funnel_found):
        return "local_report"
    if bool(api_ads_rows) or bool(api_orders_rows) or bool(api_sales_rows):
        return "api"
    return "missing"


def _parse_iso_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _load_realization_with_lag(
    *,
    client: Any,
    date_from: str,
    date_to: str,
    max_lag_days: int,
    loader: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    safe_lag = max(int(max_lag_days or 0), 0)
    parsed_from = _parse_iso_date(date_from)
    parsed_to = _parse_iso_date(date_to) or parsed_from
    if parsed_from is None or parsed_to is None:
        bundle = loader(client, date_from=date_from, date_to=date_to)
        return {
            "bundle": bundle if isinstance(bundle, dict) else {"rows": [], "api_debug": {}},
            "attempts": [bundle.get("api_debug", {})] if isinstance(bundle, dict) and isinstance(bundle.get("api_debug"), dict) else [],
            "target_date": str(date_to or date_from),
            "actual_source_date": str(date_to or date_from),
            "fallback_used": False,
            "fallback_lag_days": 0,
        }

    target_date = parsed_to.isoformat()
    selected_bundle: Dict[str, Any] = {}
    attempts: List[Dict[str, Any]] = []
    selected_source_date = target_date
    selected_lag_days = 0
    bundle_last: Dict[str, Any] = {}

    for lag in range(0, safe_lag + 1):
        attempt_from = (parsed_from - timedelta(days=lag)).isoformat()
        attempt_to = (parsed_to - timedelta(days=lag)).isoformat()
        bundle = loader(client, date_from=attempt_from, date_to=attempt_to)
        bundle_last = bundle if isinstance(bundle, dict) else {"rows": [], "api_debug": {}}
        attempt_debug = bundle_last.get("api_debug", {})
        if not isinstance(attempt_debug, dict):
            attempt_debug = {}
        attempt_payload = dict(attempt_debug)
        attempt_payload["realization_lag_days"] = lag
        attempt_payload["realization_attempt_date_from"] = attempt_from
        attempt_payload["realization_attempt_date_to"] = attempt_to
        attempt_payload["realization_target_date"] = target_date
        attempts.append(attempt_payload)

        rows = bundle_last.get("rows", [])
        if isinstance(rows, list) and rows:
            selected_bundle = bundle_last
            selected_source_date = attempt_to
            selected_lag_days = lag
            break

    if not selected_bundle:
        selected_bundle = bundle_last if isinstance(bundle_last, dict) else {"rows": [], "api_debug": {}}
        selected_source_date = target_date
        selected_lag_days = 0

    selected_rows = selected_bundle.get("rows", [])
    has_selected_rows = isinstance(selected_rows, list) and len(selected_rows) > 0
    return {
        "bundle": selected_bundle,
        "attempts": attempts,
        "target_date": target_date,
        "actual_source_date": selected_source_date if has_selected_rows else None,
        "fallback_used": bool(has_selected_rows and selected_lag_days > 0),
        "fallback_lag_days": int(selected_lag_days if has_selected_rows else 0),
    }


def run_daily_input_stage(repo_root: str, seller_id: str, run_date: str) -> Dict[str, Any]:
    sync_from_entry(globals())

    cabinet_root(repo_root, seller_id, create=True)
    seller_input_dir = input_dir(repo_root, seller_id, create=True)
    out_dir = artifacts_dir(repo_root, seller_id, create=True)
    cfg = load_seller_config(repo_root, seller_id)

    started_at = _utc_now_iso()
    seller_name = str(cfg.get("seller_name") or seller_id)

    warnings_collector = WarningsCollector()
    token = str(os.environ.get("WB_API_TOKEN", "")).strip()
    ci_flag = str(os.environ.get("GITHUB_ACTIONS") or os.environ.get("CI") or "").strip().lower()
    if ci_flag in {"1", "true", "yes"} and not token:
        print("WB API token not configured in environment")
        warnings_collector.add_warning("wb_token_missing", "WB API token not configured in environment")

    discovered_files: Dict[str, List[str]] = {
        "sales": [],
        "ads": [],
        "stocks": [],
        "funnel": [],
        "supplier_goods": [],
        "unknown": [],
    }
    input_debug: Dict[str, Any] = {}
    api_debug: Dict[str, Any] = {}
    sales_rows: List[Dict[str, Any]] = []
    ads_rows: List[Dict[str, Any]] = []
    stocks_rows: List[Dict[str, Any]] = []
    api_sales_rows: List[Dict[str, Any]] = []
    api_orders_rows: List[Dict[str, Any]] = []
    api_realization_rows: List[Dict[str, Any]] = []
    api_ads_rows: List[Dict[str, Any]] = []
    api_stocks_rows: List[Dict[str, Any]] = []
    local_financial_fallback_used = False
    local_input_debug: Dict[str, Any] = {}
    event_date_model: Dict[str, Any] = {}
    ads_loaded_from_file = False
    ads_source_file = ""
    ads_rows_count = 0
    ads_attribution_quality = "unknown"
    local_bundle = load_local_reports(seller_input_dir)
    if isinstance(local_bundle.get("files"), dict):
        discovered_files = dict(local_bundle.get("files") or discovered_files)
    local_input_debug = local_bundle.get("debug", {}) if isinstance(local_bundle.get("debug"), dict) else {}
    local_sales_rows = list(local_bundle.get("sales_rows", []))
    local_ads_rows = list(local_bundle.get("ads_rows", []))
    local_stocks_rows = list(local_bundle.get("stocks_rows", []))
    local_warnings = list(local_bundle.get("warnings", [])) if isinstance(local_bundle.get("warnings"), list) else []

    supplier_goods_daily = load_supplier_goods_daily_kpi(seller_input_dir)
    local_input_files_detected = int(local_input_debug.get("input_files_detected", 0) or 0)
    local_funnel_found = bool(local_input_debug.get("funnel_report_detected", False))
    local_funnel_source_file = str(local_input_debug.get("funnel_source_file") or "")
    local_archive_scan = (
        local_input_debug.get("archive_scan", {})
        if isinstance(local_input_debug.get("archive_scan"), dict)
        else {}
    )

    print(
        "[input] local_scan "
        f"input_files_detected={local_input_files_detected} "
        f"supplier_goods_found={str(bool(supplier_goods_daily.get('found', False))).lower()} "
        f"funnel_found={str(local_funnel_found).lower()} "
        f"archives_unpacked={int(local_archive_scan.get('unpacked_files_count', 0) or 0)}"
    )
    if local_archive_scan.get("archive_errors"):
        warnings_collector.add_warning(
            "input_archive_extract_error",
            "Archive extraction errors: "
            + "; ".join(str(item) for item in list(local_archive_scan.get("archive_errors", []))[:5]),
        )
    api_probe = _api_probe_metrics(
        api_orders_rows=api_orders_rows,
        api_sales_rows=api_sales_rows,
        api_realization_rows=api_realization_rows,
        api_ads_rows=api_ads_rows,
    )

    if token:
        source_mode = "wb_api"
        from ..api.wb_client import WBApiClient
        from ..ingestion.api_orders_loader import load_orders_from_api
        from ..ingestion.api_realization_loader import load_realization_from_api
        from ..ingestion.api_sales_loader import load_sales_from_api
        from ..ingestion.api_stocks_loader import load_stocks_from_api
        from ..wb_client import WBClient as LegacyAdsClient
        from ..financial.finance_loader import FinanceLoader

        report_timezone = _resolve_report_timezone(cfg)
        period = _resolve_wb_period(run_date, report_timezone)
        date_from = str(period.get("date_from") or run_date)
        date_to = str(period.get("date_to") or run_date)
        print(
            "[date] "
            f"requested_date={run_date} "
            f"resolved_date={date_from} "
            f"timezone={period.get('timezone')} "
            f"shifted_to_previous_day={str(bool(period.get('shifted_to_previous_day'))).lower()} "
            "resolution_source=wb_api_period"
        )

        api_endpoint_debug: List[Dict[str, Any]] = []
        client = WBApiClient(token)

        try:
            max_finance_lag_days = max(int(os.environ.get("WB_MAX_FINANCE_LAG_DAYS", "3") or 3), 0)
        except Exception:
            max_finance_lag_days = 3
        realization_attempt = _load_realization_with_lag(
            client=client,
            date_from=date_from,
            date_to=date_to,
            max_lag_days=max_finance_lag_days,
            loader=load_realization_from_api,
        )
        realization_bundle = realization_attempt.get("bundle", {})
        if not isinstance(realization_bundle, dict):
            realization_bundle = {"rows": [], "api_debug": {}}
        api_realization_rows = list(realization_bundle.get("rows", []))
        realization_loader_debug = realization_bundle.get("api_debug", {})
        if not isinstance(realization_loader_debug, dict):
            realization_loader_debug = {}
        realization_attempt_debug = realization_attempt.get("attempts", [])
        if isinstance(realization_attempt_debug, list):
            api_endpoint_debug.extend(
                [dict(item) for item in realization_attempt_debug if isinstance(item, dict)]
            )
        realization_target_date = str(realization_attempt.get("target_date") or date_to or date_from)
        realization_actual_source_date = realization_attempt.get("actual_source_date")
        if realization_actual_source_date is not None:
            realization_actual_source_date = str(realization_actual_source_date)
        realization_fallback_used = bool(realization_attempt.get("fallback_used", False))
        realization_fallback_lag_days = int(realization_attempt.get("fallback_lag_days", 0) or 0)
        
        # PHASE 3: Load FinancialSnapshot as SSOT
        financial_snapshot = None
        try:
            finance_loader = FinanceLoader(client)
            load_result = finance_loader.load(date_from, date_to)
            from ..financial.snapshot_builder import build_financial_snapshot_from_loader
            financial_snapshot = build_financial_snapshot_from_loader(
                target_date=date_from,
                load_result=load_result,
                actual_date=realization_actual_source_date or date_from,
            )
        except Exception as e:
            print(f"[phase3] FinancialSnapshot loading failed: {str(e)}")
            financial_snapshot = None
        
        if realization_fallback_used and realization_actual_source_date:
            warnings_collector.add_warning(
                "wb_api_realization_lag_fallback_used",
                "WB realization data loaded with lag fallback from "
                f"{realization_actual_source_date} (target {realization_target_date}, lag {realization_fallback_lag_days} days).",
            )

        sales_bundle = load_sales_from_api(client, date_from=date_from, date_to=date_to)
        api_sales_rows = list(sales_bundle.get("rows", []))
        sales_debug = sales_bundle.get("api_debug", {})
        if isinstance(sales_debug, dict):
            api_endpoint_debug.append(sales_debug)

        orders_bundle = load_orders_from_api(client, date_from=date_from, date_to=date_to)
        api_orders_rows = list(orders_bundle.get("rows", []))
        orders_debug = orders_bundle.get("api_debug", {})
        if isinstance(orders_debug, dict):
            api_endpoint_debug.append(orders_debug)

        try:
            stocks_date_from = (datetime.strptime(date_from, "%Y-%m-%d").date() - timedelta(days=30)).isoformat()
        except Exception:
            stocks_date_from = date_from
        stocks_bundle = load_stocks_from_api(client, date_from=stocks_date_from, date_to=date_to)
        api_stocks_rows = list(stocks_bundle.get("rows", []))
        stocks_debug = stocks_bundle.get("api_debug", {})
        if isinstance(stocks_debug, dict):
            api_endpoint_debug.append(stocks_debug)

        try:
            legacy_ads_client = LegacyAdsClient(token)
            api_ads_rows = legacy_ads_client.fetch_ads(date_from=date_from, date_to=date_to)
            api_endpoint_debug.append(
                {
                    "endpoint": "ads_legacy",
                    "success": True,
                    "fail": False,
                    "rows_loaded": len(api_ads_rows),
                    "date_from": date_from,
                    "date_to": date_to,
                    "error_text": "",
                    "status_code": 200,
                    "attempts": 1,
                }
            )
        except Exception as exc:
            api_ads_rows = []
            api_endpoint_debug.append(
                {
                    "endpoint": "ads_legacy",
                    "success": False,
                    "fail": True,
                    "rows_loaded": 0,
                    "date_from": date_from,
                    "date_to": date_to,
                    "error_text": str(exc),
                    "status_code": None,
                    "attempts": 1,
                }
            )

        endpoint_status: Dict[str, Dict[str, bool]] = {}
        for item in api_endpoint_debug:
            if not isinstance(item, dict):
                continue
            endpoint_name = str(item.get("endpoint") or "").strip()
            if not endpoint_name:
                continue
            state = endpoint_status.setdefault(endpoint_name, {"success": False, "fail": False})
            if bool(item.get("success", False)):
                state["success"] = True
            if not bool(item.get("success", False)):
                state["fail"] = True
        failed_endpoints = [
            endpoint_name
            for endpoint_name, state in endpoint_status.items()
            if bool(state.get("fail", False)) and not bool(state.get("success", False))
        ]
        if failed_endpoints:
            warnings_collector.add_warning(
                "wb_api_endpoint_failed",
                "WB API endpoint failed: " + ", ".join(failed_endpoints),
            )

        ads_rows = list(api_ads_rows)
        stocks_rows = list(api_stocks_rows)

        # orders/sales API rows are commerce-only and must not be used as financial contour.
        sales_rows = list(api_realization_rows)

        if not api_sales_rows and not api_realization_rows:
            warnings_collector.add_warning(
                "wb_api_zero_sales_rows",
                "WB API returned zero sales rows for selected period",
            )
        elif api_sales_rows and not api_realization_rows:
            warnings_collector.add_warning(
                "wb_api_realization_missing",
                "WB API sales rows are present, but realization rows are empty; financial contour is not confirmed.",
            )

        local_financial_report_found = bool(local_sales_rows) or bool(supplier_goods_daily.get("found", False))
        if local_sales_rows:
            sales_rows = list(local_sales_rows)
            local_financial_fallback_used = True
            warnings_collector.add_warning(
                "wb_local_sales_fallback_used",
                "Local WB detailed report was selected as primary financial source.",
            )
        elif local_financial_report_found:
            local_financial_fallback_used = True
            warnings_collector.add_warning(
                "wb_local_financial_kpi_detected",
                "Local WB detailed KPI report detected and used for financial fallback.",
            )

        need_local_ads = not ads_rows
        need_local_stocks = not stocks_rows
        if need_local_ads:
            if local_ads_rows:
                ads_rows = list(local_ads_rows)
                ads_loaded_from_file = bool(local_input_debug.get("ads_loaded_from_file", len(local_ads_rows) > 0))
                ads_source_file = str(local_input_debug.get("ads_source_file") or "")
                warnings_collector.add_warning(
                    "wb_local_ads_fallback_used",
                    "WB API ads data is empty; local ads files were used as fallback.",
                )
            elif bool(local_input_debug.get("ads_file_detected", False)):
                warnings_collector.add_warning(
                    "ads_file_detected_but_not_parsed",
                    f"Ads file detected but not parsed: {str(local_input_debug.get('ads_source_file') or 'local_input')}",
                )
        if need_local_stocks and local_stocks_rows:
            stocks_rows = list(local_stocks_rows)
            warnings_collector.add_warning(
                "wb_local_stocks_fallback_used",
                "WB API stocks data is empty; local stocks files were used as fallback.",
            )

        if local_financial_fallback_used or local_funnel_found or need_local_ads or need_local_stocks:
            warnings_collector.extend_warnings(local_warnings)

        if not sales_rows and not local_financial_report_found:
            warnings_collector.add_warning(
                "financial_data_missing",
                "Financial contour is missing: no realization rows and no local financial fallback.",
            )

        api_probe = _api_probe_metrics(
            api_orders_rows=api_orders_rows,
            api_sales_rows=api_sales_rows,
            api_realization_rows=api_realization_rows,
            api_ads_rows=api_ads_rows,
        )
        _log_api_probe_metrics(api_probe)

        source_mode = "local_reports_fallback" if (local_financial_fallback_used or local_funnel_found) else "wb_api"
        financial_contour_source = (
            "local_report"
            if local_financial_fallback_used
            else (
                "api.realization_fallback"
                if (api_realization_rows and realization_fallback_used)
                else ("api.realization" if api_realization_rows else "missing")
            )
        )
        funnel_contour_source = _resolve_funnel_contour_source(
            local_funnel_found=bool(local_funnel_found),
            api_ads_rows=api_ads_rows if isinstance(api_ads_rows, list) else [],
            api_orders_rows=api_orders_rows if isinstance(api_orders_rows, list) else [],
            api_sales_rows=api_sales_rows if isinstance(api_sales_rows, list) else [],
        )
        funnel_upper_available = bool(api_ads_rows)
        funnel_lower_available = bool(api_orders_rows or api_sales_rows)

        api_debug = {
            "sales_rows": len(api_sales_rows),
            "orders_rows": len(api_orders_rows),
            "realization_rows": len(api_realization_rows),
            "financial_rows": len(sales_rows),
            "ads_rows": len(api_ads_rows),
            "stocks_rows": len(api_stocks_rows),
            "endpoints": api_endpoint_debug,
            "date_from": date_from,
            "date_to": date_to,
            "run_date_requested": run_date,
            "timezone": str(period.get("timezone") or report_timezone),
            "shifted_to_previous_day": bool(period.get("shifted_to_previous_day")),
            "input_files_detected": int(local_input_files_detected),
            "local_financial_fallback_used": local_financial_fallback_used,
            "financial_contour_source": financial_contour_source,
            "funnel_source": funnel_contour_source,
            "funnel_upper_available": funnel_upper_available,
            "funnel_lower_available": funnel_lower_available,
            "funnel_degradation_mode": (
                "upper_funnel_unavailable_from_api" if (funnel_lower_available and not funnel_upper_available) else "none"
            ),
            "supplier_goods_daily_found": bool(supplier_goods_daily.get("found", False)),
            "local_funnel_report_found": bool(local_funnel_found),
            "local_funnel_source_file": local_funnel_source_file,
            "archive_scan": local_archive_scan if isinstance(local_archive_scan, dict) else {},
            "probe_metrics": api_probe,
            "realization_target_date": realization_target_date,
            "realization_actual_source_date": realization_actual_source_date,
            "realization_fallback_used": realization_fallback_used,
            "realization_fallback_lag_days": realization_fallback_lag_days,
            "finance_api_mode": str(realization_loader_debug.get("finance_api_mode") or "unknown"),
            "finance_endpoint_used": str(realization_loader_debug.get("finance_endpoint_used") or ""),
            "finance_report_ids": (
                list(realization_loader_debug.get("finance_report_ids", []))
                if isinstance(realization_loader_debug.get("finance_report_ids"), list)
                else []
            ),
            "finance_requested_fields_count": int(realization_loader_debug.get("finance_requested_fields_count", 0) or 0),
            "finance_mapping_diagnostics": (
                dict(realization_loader_debug.get("finance_mapping_diagnostics", {}))
                if isinstance(realization_loader_debug.get("finance_mapping_diagnostics"), dict)
                else {}
            ),
            "finance_fallback_used": bool(realization_loader_debug.get("finance_fallback_used", False)),
            "finance_fallback_reason": str(realization_loader_debug.get("finance_fallback_reason") or ""),
            "finance_primary_endpoint_attempted": str(realization_loader_debug.get("finance_primary_endpoint_attempted") or ""),
            "finance_primary_status_code": realization_loader_debug.get("finance_primary_status_code"),
            "finance_primary_error_text": str(realization_loader_debug.get("finance_primary_error_text") or ""),
        }
        print(
            "[wb] rows_loaded "
            f"orders_rows={len(api_orders_rows)} buyouts_rows={len(api_sales_rows)} "
            f"financial_rows={len(sales_rows)} ads_rows={len(api_ads_rows)}"
        )
        print(
            "[input] primary_sources "
            f"financial={financial_contour_source} "
            f"funnel={funnel_contour_source} "
            f"ads={'local_report' if ads_loaded_from_file else ('api' if len(api_ads_rows) > 0 else 'missing')}"
        )
        event_date_model = build_event_date_model(
            run_date=run_date,
            api_debug=api_debug,
            timezone=str(period.get("timezone") or report_timezone),
        )
        input_debug = {
            "source_mode": source_mode,
            "loaded_rows": {
                "sales": len(sales_rows),
                "ads": len(ads_rows),
                "stocks": len(stocks_rows),
            },
            "api_debug": api_debug,
        }
        if isinstance(local_input_debug, dict) and local_input_debug:
            for key in (
                "input_files_detected",
                "archive_scan",
                "supplier_goods_candidates",
                "funnel_candidates",
                "funnel_report_detected",
                "funnel_source_file",
                "ads_file_candidates_found",
                "ads_file_detected",
                "ads_source_file",
                "ads_sheet_found",
                "ads_columns_detected",
                "ads_rows_raw",
                "ads_rows_usable",
                "ads_loader_error",
                "ads_loaded_from_file",
            ):
                if key in local_input_debug:
                    input_debug[key] = local_input_debug.get(key)
        if not sales_rows and not ads_rows and not stocks_rows:
            warnings_collector.add_warning("wb_api_empty", "WB API returned no rows")
    else:
        source_mode = "local_reports"
        warnings_collector.extend_warnings(local_warnings)
        sales_rows = list(local_sales_rows)
        ads_rows = list(local_ads_rows)
        stocks_rows = list(local_stocks_rows)
        local_financial_fallback_used = bool(len(local_sales_rows) > 0 or bool(supplier_goods_daily.get("found", False)))
        if isinstance(local_input_debug, dict):
            input_debug = dict(local_input_debug)
            ads_loaded_from_file = bool(input_debug.get("ads_loaded_from_file", len(ads_rows) > 0))
            ads_source_file = str(input_debug.get("ads_source_file") or "")
        api_debug = {
            "sales_rows": 0,
            "orders_rows": 0,
            "realization_rows": 0,
            "financial_rows": len(sales_rows),
            "ads_rows": 0,
            "stocks_rows": 0,
            "endpoints": [],
            "date_from": run_date,
            "date_to": run_date,
            "run_date_requested": run_date,
            "timezone": _resolve_report_timezone(cfg),
            "shifted_to_previous_day": False,
            "input_files_detected": int(local_input_files_detected),
            "local_financial_fallback_used": bool(local_financial_fallback_used),
            "financial_contour_source": "local_report" if local_financial_fallback_used else "missing",
            "funnel_source": "local_report" if local_funnel_found else "missing",
            "supplier_goods_daily_found": bool(supplier_goods_daily.get("found", False)),
            "local_funnel_report_found": bool(local_funnel_found),
            "local_funnel_source_file": local_funnel_source_file,
            "archive_scan": local_archive_scan if isinstance(local_archive_scan, dict) else {},
            "probe_metrics": api_probe,
            "realization_target_date": run_date,
            "realization_actual_source_date": None,
            "realization_fallback_used": False,
            "realization_fallback_lag_days": 0,
            "finance_api_mode": "unknown",
            "finance_endpoint_used": "",
            "finance_report_ids": [],
            "finance_requested_fields_count": 0,
            "finance_mapping_diagnostics": {},
            "finance_fallback_used": False,
            "finance_fallback_reason": "",
            "finance_primary_endpoint_attempted": "",
            "finance_primary_status_code": None,
            "finance_primary_error_text": "",
        }
        _log_api_probe_metrics(api_probe)
        print(
            "[date] "
            f"requested_date={run_date} "
            f"resolved_date={run_date} "
            f"timezone={api_debug.get('timezone')} "
            "shifted_to_previous_day=false "
            "resolution_source=local_reports"
        )
        print(
            "[wb] rows_loaded "
            "orders_rows=0 buyouts_rows=0 "
            f"financial_rows={len(sales_rows)} ads_rows=0"
        )
        print(
            "[input] primary_sources "
            f"financial={api_debug.get('financial_contour_source')} "
            f"funnel={api_debug.get('funnel_source')} "
            f"ads={'local_report' if ads_loaded_from_file else 'missing'}"
        )
        event_date_model = build_event_date_model(
            run_date=run_date,
            api_debug=api_debug,
            timezone=str(api_debug.get("timezone") or "Europe/Moscow"),
        )

    input_debug_bundle = build_input_debug(
        source_mode=source_mode,
        input_debug=input_debug if isinstance(input_debug, dict) else {},
        local_input_debug=local_input_debug if isinstance(local_input_debug, dict) else {},
        discovered_files=discovered_files if isinstance(discovered_files, dict) else {},
        api_debug=api_debug if isinstance(api_debug, dict) else {},
        supplier_goods_daily=supplier_goods_daily if isinstance(supplier_goods_daily, dict) else {"found": False},
        sales_rows_count=len(sales_rows),
        ads_rows=ads_rows if isinstance(ads_rows, list) else [],
        ads_rows_count=len(ads_rows),
        stocks_rows_count=len(stocks_rows),
        ads_loaded_from_file=bool(ads_loaded_from_file),
        ads_source_file=str(ads_source_file or ""),
    )
    input_debug = input_debug_bundle.get("input_debug", {}) if isinstance(input_debug_bundle, dict) else {}
    if not isinstance(input_debug, dict):
        input_debug = {}
    input_debug_warning_additions = (
        input_debug_bundle.get("warnings_additions", [])
        if isinstance(input_debug_bundle, dict) and isinstance(input_debug_bundle.get("warnings_additions"), list)
        else []
    )
    warnings_collector.extend_warnings(input_debug_warning_additions)

    input_debug["input_files_detected"] = int(input_debug.get("input_files_detected", local_input_files_detected) or 0)
    input_debug["supplier_goods_daily"] = (
        supplier_goods_daily if isinstance(supplier_goods_daily, dict) else {"found": False}
    )

    data_mode = "api" if (source_mode == "wb_api" and not bool(local_financial_fallback_used)) else "raw_reports_fallback"
    non_api_mode = not (data_mode == "api")
    input_debug["data_mode"] = data_mode
    input_debug["non_api_mode"] = non_api_mode
    ads_rows_count = len(ads_rows)
    print(
        "[pipeline] data_mode "
        f"mode={data_mode} source_mode={source_mode} "
        f"local_financial_fallback_used={str(bool(local_financial_fallback_used)).lower()}"
    )

    return {
        "repo_root": repo_root,
        "seller_id": seller_id,
        "run_date": run_date,
        "seller_input_dir": seller_input_dir,
        "out_dir": out_dir,
        "cfg": cfg,
        "started_at": started_at,
        "seller_name": seller_name,
        "token": token,
        "source_mode": source_mode,
        "data_mode": data_mode,
        "non_api_mode": non_api_mode,
        "warnings_collector": warnings_collector,
        "discovered_files": discovered_files,
        "input_debug": input_debug,
        "api_debug": api_debug,
        "event_date_model": event_date_model,
        "financial_snapshot": financial_snapshot,  # PHASE 3: NEW - Unified financial data SSOT
        "sales_rows": sales_rows,
        "ads_rows": ads_rows,
        "stocks_rows": stocks_rows,
        "api_sales_rows": api_sales_rows,
        "api_orders_rows": api_orders_rows,
        "api_realization_rows": api_realization_rows,
        "api_ads_rows": api_ads_rows,
        "api_stocks_rows": api_stocks_rows,
        "local_financial_fallback_used": local_financial_fallback_used,
        "local_input_debug": local_input_debug,
        "ads_loaded_from_file": ads_loaded_from_file,
        "ads_source_file": ads_source_file,
        "ads_rows_count": ads_rows_count,
        "ads_attribution_quality": ads_attribution_quality,
        "supplier_goods_daily": supplier_goods_daily,
    }

