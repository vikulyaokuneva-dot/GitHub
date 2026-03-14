from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping

from .ads_aggregation import aggregate_ads_by_query, aggregate_ads_by_sku
from .ads_data_loader import load_ads_efficiency_sources
from .models import AdvertisingEfficiencyOutput, AdvertisingSignal
from .portfolio_ads_summary import build_portfolio_ads_summary
from .query_ads_performance import build_query_ads_performance
from .signals import build_ads_signals
from .sku_ads_performance import build_sku_ads_performance

DEFAULT_ADVERTISING_EFFICIENCY_CONFIG: Dict[str, Any] = {
    "enable_advertising_efficiency_engine": True,
    "min_orders_for_confidence": 3,
    "min_query_clicks_for_confidence": 5,
    "high_romi_threshold_pct": 40.0,
    "budget_leak_spend_threshold": 1000.0,
}


def _as_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _resolve_config(cfg: Mapping[str, Any] | None) -> Dict[str, Any]:
    resolved = dict(DEFAULT_ADVERTISING_EFFICIENCY_CONFIG)
    if not isinstance(cfg, Mapping):
        return resolved

    section = cfg.get("advertising_efficiency")
    if isinstance(section, Mapping):
        for key in resolved.keys():
            if key in section:
                resolved[key] = section.get(key)

    for key in resolved.keys():
        if key in cfg:
            resolved[key] = cfg.get(key)

    resolved["enable_advertising_efficiency_engine"] = bool(
        resolved.get("enable_advertising_efficiency_engine", True)
    )
    resolved["min_orders_for_confidence"] = int(max(1.0, _as_float(resolved.get("min_orders_for_confidence", 3))))
    resolved["min_query_clicks_for_confidence"] = int(
        max(1.0, _as_float(resolved.get("min_query_clicks_for_confidence", 5)))
    )
    resolved["high_romi_threshold_pct"] = float(_as_float(resolved.get("high_romi_threshold_pct", 40.0)))
    resolved["budget_leak_spend_threshold"] = float(
        _as_float(resolved.get("budget_leak_spend_threshold", 1000.0))
    )
    return resolved


def _analysis_mode(*, ads_data_present: bool, orders_available: bool, buyouts_confirmed: bool) -> str:
    if not ads_data_present:
        return "disabled"
    if orders_available and buyouts_confirmed:
        return "full"
    return "preview"


def build_advertising_efficiency(
    *,
    metrics: Dict[str, Any],
    ads_rows: List[Dict[str, Any]] | None,
    keyword_monitoring: Dict[str, Any] | None,
    daily_kpi: Dict[str, Any] | None,
    seller_id: str,
    run_date: str,
    config: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    cfg = _resolve_config(config)
    safe_daily_kpi = daily_kpi if isinstance(daily_kpi, dict) else {}
    warnings: List[Dict[str, Any]] = []

    if not bool(cfg.get("enable_advertising_efficiency_engine", True)):
        payload = AdvertisingEfficiencyOutput(
            seller_id=str(seller_id or ""),
            report_date=str(run_date or ""),
            status="disabled",
            analysis_mode="disabled",
            data_quality_status="disabled_by_config",
            warnings=[
                {
                    "code": "advertising_efficiency_disabled",
                    "message": "Advertising efficiency engine is disabled by configuration.",
                }
            ],
            summary={
                "analysis_mode": "disabled",
                "portfolio_ad_spend": 0.0,
                "portfolio_orders_from_ads": 0.0,
                "portfolio_buyouts_from_ads": 0.0,
                "portfolio_revenue_from_ads": 0.0,
                "portfolio_profit_from_ads": 0.0,
                "portfolio_ROMI": None,
                "portfolio_DRR": None,
                "portfolio_CPO": None,
                "top_profitable_queries": [],
                "top_unprofitable_queries": [],
                "high_potential_queries": [],
            },
            sku_performance=[],
            query_performance=[],
            signals=[],
        ).to_dict()
        payload["portfolio"] = dict(payload.get("summary", {}))
        payload["portfolio_ads_summary"] = dict(payload.get("summary", {}))
        payload["query_profitability"] = {
            "analysis_mode": "disabled",
            "status": "disabled",
            "items": [],
            "summary": {"query_count": 0},
        }
        payload["advertising_efficiency_summary"] = dict(payload.get("summary", {}))
        return payload

    source = load_ads_efficiency_sources(
        metrics=metrics if isinstance(metrics, dict) else {},
        ads_rows=ads_rows if isinstance(ads_rows, list) else [],
        keyword_monitoring=keyword_monitoring if isinstance(keyword_monitoring, dict) else {},
    )

    ads_rows_count = int(source.get("ads_rows_count", 0) or 0)
    query_rows_count = int(source.get("query_rows_count", 0) or 0)
    rows_spend = _as_float(source.get("rows_spend"))
    campaign_total_spend = _as_float(source.get("campaign_total_spend"))
    ads_data_present = bool(ads_rows_count > 0 or rows_spend > 0 or campaign_total_spend > 0)

    orders_confirmed = bool(safe_daily_kpi.get("orders_count_confirmed", False))
    buyouts_confirmed = bool(safe_daily_kpi.get("buyouts_count_confirmed", False))
    orders_available = bool(orders_confirmed or int(safe_daily_kpi.get("daily_orders_count", 0) or 0) > 0)

    analysis_mode = _analysis_mode(
        ads_data_present=ads_data_present,
        orders_available=orders_available,
        buyouts_confirmed=buyouts_confirmed,
    )

    if analysis_mode == "disabled":
        warnings.append(
            {
                "code": "advertising_efficiency_ads_missing",
                "message": "Advertising efficiency analysis is disabled because ads data is missing.",
            }
        )
    elif analysis_mode == "preview":
        warnings.append(
            {
                "code": "advertising_efficiency_preview",
                "message": "Advertising efficiency is preview-only: buyouts are not confirmed.",
            }
        )

    if query_rows_count <= 0:
        warnings.append(
            {
                "code": "advertising_efficiency_query_missing",
                "message": "Query-level advertising rows are missing; query analysis is limited.",
            }
        )

    if analysis_mode == "disabled":
        sku_rows: List[Dict[str, Any]] = []
        query_rows: List[Dict[str, Any]] = []
    else:
        sku_rows = build_sku_ads_performance(
            ads_by_sku=aggregate_ads_by_sku(source.get("sku_ads_rows", [])),
            sku_metrics_index=source.get("sku_metrics_index", {}),
            min_orders_for_confidence=int(cfg.get("min_orders_for_confidence", 3)),
        )

        query_rows = build_query_ads_performance(
            ads_by_query=aggregate_ads_by_query(source.get("query_rows", [])),
            sku_performance=sku_rows,
            min_clicks_for_confidence=int(cfg.get("min_query_clicks_for_confidence", 5)),
        )

    summary = build_portfolio_ads_summary(
        sku_rows=sku_rows,
        query_rows=query_rows,
        analysis_mode=analysis_mode,
        campaign_total_spend=campaign_total_spend,
    )

    signal_rows = build_ads_signals(
        analysis_mode=analysis_mode,
        summary=summary,
        sku_rows=sku_rows,
        query_rows=query_rows,
        high_romi_threshold_pct=float(cfg.get("high_romi_threshold_pct", 40.0)),
        budget_leak_spend_threshold=float(cfg.get("budget_leak_spend_threshold", 1000.0)),
    )

    status = "ok"
    data_quality_status = "ok"
    if analysis_mode == "disabled":
        status = "disabled"
        data_quality_status = "missing_ads_data"
    elif analysis_mode == "preview":
        status = "partial"
        data_quality_status = "partial_buyout_confirmation"

    payload = AdvertisingEfficiencyOutput(
        seller_id=str(seller_id or ""),
        report_date=str(run_date or ""),
        status=status,
        analysis_mode=analysis_mode,
        data_quality_status=data_quality_status,
        warnings=warnings,
        summary=summary,
        sku_performance=sku_rows,
        query_performance=query_rows,
        signals=[AdvertisingSignal(**row) for row in signal_rows],
    ).to_dict()

    payload["portfolio"] = dict(summary)
    payload["portfolio_ads_summary"] = dict(summary)
    payload["advertising_efficiency_summary"] = dict(summary)
    payload["query_profitability"] = {
        "analysis_mode": analysis_mode,
        "status": status,
        "summary": {
            "query_count": len(query_rows),
            "profitable": len(
                [row for row in query_rows if str(row.get("classification") or "") == "profitable"]
            ),
            "neutral": len([row for row in query_rows if str(row.get("classification") or "") == "neutral"]),
            "unprofitable": len(
                [row for row in query_rows if str(row.get("classification") or "") == "unprofitable"]
            ),
            "insufficient_data": len(
                [row for row in query_rows if str(row.get("classification") or "") == "insufficient_data"]
            ),
        },
        "items": query_rows,
    }
    payload["source"] = {
        "ads_rows_count": ads_rows_count,
        "query_rows_count": query_rows_count,
        "query_source": str(source.get("query_source") or "ads_rows"),
        "campaign_total_spend": round(campaign_total_spend, 2),
        "rows_spend": round(rows_spend, 2),
    }
    return payload


def save_advertising_efficiency(output_path: Path, data: Dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
