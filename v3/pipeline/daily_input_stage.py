from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Dict, List

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


def run_daily_input_stage(repo_root: str, seller_id: str, run_date: str) -> Dict[str, Any]:
    sync_from_entry(globals())

    cabinet_root(repo_root, seller_id, create=True)
    reports_dir(repo_root, seller_id, create=True)
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

    discovered_files: Dict[str, List[str]] = {"sales": [], "ads": [], "stocks": [], "unknown": []}
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
    supplier_goods_daily = load_supplier_goods_daily_kpi(seller_input_dir)
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

        report_timezone = _resolve_report_timezone(cfg)
        period = _resolve_wb_period(run_date, report_timezone)
        date_from = str(period.get("date_from") or run_date)
        date_to = str(period.get("date_to") or run_date)
        print(
            f"[wb] period_resolved run_date={run_date} timezone={period.get('timezone')} "
            f"date_from={date_from} date_to={date_to} shifted_to_previous_day={period.get('shifted_to_previous_day')}"
        )

        api_endpoint_debug: List[Dict[str, Any]] = []
        client = WBApiClient(token)

        realization_bundle = load_realization_from_api(client, date_from=date_from, date_to=date_to)
        api_realization_rows = list(realization_bundle.get("rows", []))
        realization_debug = realization_bundle.get("api_debug", {})
        if isinstance(realization_debug, dict):
            api_endpoint_debug.append(realization_debug)

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

        failed_endpoints = [
            str(item.get("endpoint") or "")
            for item in api_endpoint_debug
            if isinstance(item, dict) and not bool(item.get("success", False))
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

        need_local_sales = not sales_rows
        need_local_ads = not ads_rows
        need_local_stocks = not stocks_rows
        if need_local_sales or need_local_ads or need_local_stocks:
            local_bundle = load_local_reports(seller_input_dir)
            discovered_files = local_bundle.get("files", discovered_files)
            local_sales_rows = list(local_bundle.get("sales_rows", []))
            local_ads_rows = list(local_bundle.get("ads_rows", []))
            local_stocks_rows = list(local_bundle.get("stocks_rows", []))
            local_warnings = list(local_bundle.get("warnings", []))
            local_debug = local_bundle.get("debug", {}) if isinstance(local_bundle.get("debug"), dict) else {}
            if isinstance(local_debug, dict):
                local_input_debug = local_debug

            if need_local_sales and local_sales_rows:
                sales_rows = local_sales_rows
                local_financial_fallback_used = True
                warnings_collector.add_warning(
                    "wb_local_sales_fallback_used",
                    "WB API sales data is empty; local sales files were used as fallback.",
                )
            if need_local_ads:
                if local_ads_rows:
                    ads_rows = local_ads_rows
                    ads_loaded_from_file = bool(local_debug.get("ads_loaded_from_file", len(local_ads_rows) > 0))
                    ads_source_file = str(local_debug.get("ads_source_file") or "")
                    warnings_collector.add_warning(
                        "wb_local_ads_fallback_used",
                        "WB API ads data is empty; local ads files were used as fallback.",
                    )
                elif bool(local_debug.get("ads_file_detected", False)):
                    warnings_collector.add_warning(
                        "ads_file_detected_but_not_parsed",
                        f"Ads file detected but not parsed: {str(local_debug.get('ads_source_file') or 'local_input')}",
                    )
            if need_local_stocks and local_stocks_rows:
                stocks_rows = local_stocks_rows
                warnings_collector.add_warning(
                    "wb_local_stocks_fallback_used",
                    "WB API stocks data is empty; local stocks files were used as fallback.",
                )
            if need_local_sales:
                warnings_collector.extend_warnings(local_warnings)
            else:
                for item in local_warnings:
                    if not isinstance(item, dict):
                        continue
                    code = str(item.get("code") or "")
                    message = str(item.get("message") or "").lower()
                    include_ads = need_local_ads and (
                        code.startswith("ads_")
                        or "ads report" in message
                        or " ads " in f" {message} "
                    )
                    include_stocks = need_local_stocks and (
                        code.startswith("stocks_")
                        or "stocks report" in message
                        or " stocks " in f" {message} "
                    )
                    if include_ads or include_stocks:
                        warnings_collector.extend_warnings([item])

        if not sales_rows:
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
            "local_financial_fallback_used": local_financial_fallback_used,
            "financial_contour_source": (
                "api.realization"
                if api_realization_rows
                else ("local.sales_fallback" if local_financial_fallback_used else "missing")
            ),
            "probe_metrics": api_probe,
        }
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
        local_bundle = load_local_reports(seller_input_dir)
        discovered_files = local_bundle.get("files", discovered_files)
        input_debug = local_bundle.get("debug", {})
        warnings_collector.extend_warnings(
            list(local_bundle.get("warnings", [])) if isinstance(local_bundle.get("warnings"), list) else []
        )
        sales_rows = list(local_bundle.get("sales_rows", []))
        ads_rows = list(local_bundle.get("ads_rows", []))
        stocks_rows = list(local_bundle.get("stocks_rows", []))
        if isinstance(input_debug, dict):
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
            "local_financial_fallback_used": bool(len(sales_rows) > 0),
            "financial_contour_source": "local.report" if sales_rows else "missing",
            "probe_metrics": api_probe,
        }
        _log_api_probe_metrics(api_probe)
        event_date_model = build_event_date_model(
            run_date=run_date,
            api_debug=api_debug,
            timezone=str(api_debug.get("timezone") or "Europe/Berlin"),
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
        "warnings_collector": warnings_collector,
        "discovered_files": discovered_files,
        "input_debug": input_debug,
        "api_debug": api_debug,
        "event_date_model": event_date_model,
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
