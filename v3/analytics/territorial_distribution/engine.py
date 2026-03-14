from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping

from .coefficients import resolve_effective_date, resolve_threshold
from .irp_calculator import estimate_irp_penalty, is_effective_date_applied, resolve_average_retail_price
from .localization_calculator import build_localization_rows
from .models import DistributionEngineOutput, SkuDistributionMetrics
from .signals import build_distribution_signals

DEFAULT_DISTRIBUTION_CONFIG: Dict[str, Any] = {
    "enable_territorial_distribution_engine": True,
    "wb_irp_effective_date": "2026-03-23",
    "distribution_profit_leak_threshold": 5000.0,
    "localization_watch_threshold": 60.0,
    "localization_weak_threshold": 40.0,
    "localization_critical_threshold": 20.0,
    "min_orders_for_confidence": 3.0,
    "min_orders_for_actionable": 5.0,
    "min_portfolio_coverage_pct": 40.0,
    "min_demand_coverage_pct": 50.0,
    "min_stock_coverage_pct": 40.0,
    "max_unknown_share_pct": 60.0,
}

_STATE_LABELS_RU = {
    "no_orders": "нет заказов",
    "strong": "распределение хорошее",
    "watch": "зона наблюдения",
    "weak": "слабая локализация",
    "critical": "критично низкая локализация",
    "insufficient_data": "недостаточно данных",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _extract_sku_metrics_index(metrics: Any) -> Dict[str, Dict[str, Any]]:
    if not isinstance(metrics, dict):
        return {}
    rows = metrics.get("sku_metrics")
    if not isinstance(rows, list):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        sku = str(row.get("sku") or "").strip().lower()
        if sku:
            out[sku] = row
    return out


def _resolve_config(cfg: Mapping[str, Any] | None) -> Dict[str, Any]:
    resolved = dict(DEFAULT_DISTRIBUTION_CONFIG)
    if not isinstance(cfg, Mapping):
        return resolved

    section = cfg.get("territorial_distribution")
    if isinstance(section, Mapping):
        for key in resolved.keys():
            if key in section:
                resolved[key] = section.get(key)

    for key in resolved.keys():
        if key in cfg:
            resolved[key] = cfg.get(key)

    resolved["enable_territorial_distribution_engine"] = bool(
        resolved.get("enable_territorial_distribution_engine", True)
    )
    resolved["wb_irp_effective_date"] = resolve_effective_date(resolved.get("wb_irp_effective_date"))

    for key in (
        "distribution_profit_leak_threshold",
        "localization_watch_threshold",
        "localization_weak_threshold",
        "localization_critical_threshold",
        "min_orders_for_confidence",
        "min_orders_for_actionable",
        "min_portfolio_coverage_pct",
        "min_demand_coverage_pct",
        "min_stock_coverage_pct",
        "max_unknown_share_pct",
    ):
        resolved[key] = resolve_threshold(resolved.get(key), DEFAULT_DISTRIBUTION_CONFIG[key])

    return resolved


def _distribution_state(localization_share: float | None, total_orders: float, cfg: Mapping[str, Any]) -> str:
    if total_orders <= 0:
        return "no_orders"
    if localization_share is None:
        return "insufficient_data"

    watch = float(cfg.get("localization_watch_threshold", 60.0))
    weak = float(cfg.get("localization_weak_threshold", 40.0))
    critical = float(cfg.get("localization_critical_threshold", 20.0))

    if localization_share >= watch:
        return "strong"
    if localization_share >= weak:
        return "watch"
    if localization_share >= critical:
        return "weak"
    return "critical"


def _legacy_status_from_state(state: str) -> str:
    if state == "strong":
        return "balanced"
    if state == "watch":
        return "moderate_mismatch"
    if state in {"weak", "critical"}:
        return "misallocated"
    if state == "no_orders":
        return "no_demand_data"
    return "insufficient_distribution_data"


def _confidence_level(*, coverage_pct: float, demand_coverage_pct: float, stock_coverage_pct: float, full_share_pct: float, suppressed_due_to_data_quality: bool) -> str:
    if suppressed_due_to_data_quality:
        return "low"
    if coverage_pct >= 80 and demand_coverage_pct >= 80 and stock_coverage_pct >= 70 and full_share_pct >= 60:
        return "high"
    if coverage_pct >= 55 and demand_coverage_pct >= 55 and stock_coverage_pct >= 45 and full_share_pct >= 35:
        return "medium"
    return "low"


def _summary(items: List[Dict[str, Any]], cfg: Mapping[str, Any], sku_attribution_status: str) -> Dict[str, Any]:
    total_skus = len(items)
    known_rows = [
        row
        for row in items
        if isinstance(row, dict) and row.get("localization_share") is not None and _as_float(row.get("total_orders")) > 0
    ]
    actionable_rows = [
        row
        for row in items
        if isinstance(row, dict)
        and str(row.get("analysis_mode") or "").strip().lower() == "full"
        and str(row.get("recommendation_status") or "").strip().lower() == "actionable"
    ]

    known_localization_skus = len(known_rows)
    unknown_localization_skus = max(0, total_skus - known_localization_skus)
    coverage_pct = round(known_localization_skus / total_skus * 100.0, 2) if total_skus > 0 else 0.0
    demand_coverage_pct = round(sum(1 for row in items if bool(row.get("demand_geography_available", False))) / total_skus * 100.0, 2) if total_skus > 0 else 0.0
    stock_coverage_pct = round(sum(1 for row in items if bool(row.get("stock_geography_available", False))) / total_skus * 100.0, 2) if total_skus > 0 else 0.0

    full_analysis_skus = sum(1 for row in items if str(row.get("analysis_mode") or "") == "full")
    preview_analysis_skus = sum(1 for row in items if str(row.get("analysis_mode") or "") == "preview")
    disabled_analysis_skus = sum(1 for row in items if str(row.get("analysis_mode") or "") == "disabled")
    full_share_pct = round(full_analysis_skus / total_skus * 100.0, 2) if total_skus > 0 else 0.0
    unknown_share_pct = round(unknown_localization_skus / total_skus * 100.0, 2) if total_skus > 0 else 100.0

    suppression_reasons: List[str] = []
    if str(sku_attribution_status or "ok").strip().lower() == "broken":
        suppression_reasons.append("sku_attribution_broken")
    if coverage_pct < _as_float(cfg.get("min_portfolio_coverage_pct", 40.0)):
        suppression_reasons.append("low_localization_coverage")
    if demand_coverage_pct < _as_float(cfg.get("min_demand_coverage_pct", 50.0)):
        suppression_reasons.append("low_demand_geography_coverage")
    if stock_coverage_pct < _as_float(cfg.get("min_stock_coverage_pct", 40.0)):
        suppression_reasons.append("low_stock_geography_coverage")
    if unknown_share_pct > _as_float(cfg.get("max_unknown_share_pct", 60.0)):
        suppression_reasons.append("too_many_unknown_skus")

    suppressed_due_to_data_quality = bool(suppression_reasons)
    confidence_level = _confidence_level(
        coverage_pct=coverage_pct,
        demand_coverage_pct=demand_coverage_pct,
        stock_coverage_pct=stock_coverage_pct,
        full_share_pct=full_share_pct,
        suppressed_due_to_data_quality=suppressed_due_to_data_quality,
    )

    if coverage_pct <= 0:
        analysis_mode = "disabled"
    elif suppressed_due_to_data_quality or confidence_level == "low":
        analysis_mode = "preview"
    else:
        analysis_mode = "full"

    recommendation_status = "actionable" if analysis_mode == "full" else ("watch" if analysis_mode == "preview" else "blocked_by_data")
    total_orders_known = sum(_as_float(row.get("total_orders")) for row in known_rows)
    weighted_localization_sum = sum(_as_float(row.get("localization_share")) * _as_float(row.get("total_orders")) for row in known_rows)
    weighted_localization = round(weighted_localization_sum / total_orders_known, 4) if total_orders_known > 0 else None

    skus_with_irp_penalty = sum(1 for row in actionable_rows if _as_float(row.get("estimated_irp_penalty_total")) > 0)
    below_60 = sum(1 for row in known_rows if _as_float(row.get("localization_share")) < 60.0 and _as_float(row.get("total_orders")) > 0)
    below_40 = sum(1 for row in known_rows if _as_float(row.get("localization_share")) < 40.0 and _as_float(row.get("total_orders")) > 0)
    below_20 = sum(1 for row in known_rows if _as_float(row.get("localization_share")) < 20.0 and _as_float(row.get("total_orders")) > 0)

    aggregate_penalty = round(sum(_as_float(row.get("estimated_irp_penalty_total")) for row in actionable_rows), 2)

    ktr_values = [_as_float(row.get("ktr")) for row in known_rows if row.get("ktr") is not None]
    avg_ktr = round(sum(ktr_values) / len(ktr_values), 4) if ktr_values else None

    state_counts = {
        "no_orders": sum(1 for row in items if str(row.get("distribution_state") or "") == "no_orders"),
        "strong": sum(1 for row in items if str(row.get("distribution_state") or "") == "strong"),
        "watch": sum(1 for row in items if str(row.get("distribution_state") or "") == "watch"),
        "weak": sum(1 for row in items if str(row.get("distribution_state") or "") == "weak"),
        "critical": sum(1 for row in items if str(row.get("distribution_state") or "") == "critical"),
        "insufficient_data": sum(1 for row in items if str(row.get("distribution_state") or "") == "insufficient_data"),
    }

    top_worst_localization = [
        {
            "sku": str(row.get("sku") or ""),
            "localization_share": row.get("localization_share"),
            "total_orders": row.get("total_orders"),
            "analysis_mode": row.get("analysis_mode"),
            "recommendation_status": row.get("recommendation_status"),
        }
        for row in sorted(known_rows, key=lambda r: (_as_float(r.get("localization_share")), -_as_float(r.get("total_orders"))))
    ][:10]

    top_irp_penalty = [
        {
            "sku": str(row.get("sku") or ""),
            "estimated_irp_penalty_total": row.get("estimated_irp_penalty_total"),
            "localization_share": row.get("localization_share"),
            "analysis_mode": row.get("analysis_mode"),
        }
        for row in sorted(actionable_rows, key=lambda r: (_as_float(r.get("estimated_irp_penalty_total")), str(r.get("sku") or "")), reverse=True)
        if _as_float(row.get("estimated_irp_penalty_total")) > 0
    ][:10]

    if weighted_localization is None or suppressed_due_to_data_quality:
        portfolio_risk = "unknown"
    elif weighted_localization < _as_float(cfg.get("localization_critical_threshold", 20.0)):
        portfolio_risk = "high"
    elif weighted_localization < _as_float(cfg.get("localization_weak_threshold", 40.0)) or (total_skus > 0 and (below_60 / total_skus) >= 0.5):
        portfolio_risk = "elevated"
    else:
        portfolio_risk = "low"

    return {
        "total_skus_analyzed": total_skus,
        "skus_with_irp_penalty": skus_with_irp_penalty,
        "skus_below_60_localization": below_60,
        "skus_below_40_localization": below_40,
        "skus_critical_below_20_localization": below_20,
        "aggregate_estimated_irp_penalty_total": aggregate_penalty,
        "weighted_average_localization_share": weighted_localization,
        "distribution_efficiency_score": round(max(0.0, min(100.0, _as_float(weighted_localization))), 2) if weighted_localization is not None else 0.0,
        "distribution_state_counts": state_counts,
        "top_weak_localization_skus": top_worst_localization,
        "top_irp_penalty_skus": top_irp_penalty,
        "sku_total": total_skus,
        "sku_with_ktr": len([row for row in items if row.get("ktr") is not None]),
        "balanced_count": state_counts["strong"],
        "moderate_mismatch_count": state_counts["watch"],
        "misallocated_count": state_counts["weak"] + state_counts["critical"],
        "insufficient_distribution_data_count": state_counts["insufficient_data"] + state_counts["no_orders"],
        "no_stock_data_count": sum(1 for row in items if not bool(row.get("stock_geography_available", False))),
        "insufficient_total_count": state_counts["insufficient_data"] + state_counts["no_orders"],
        "avg_ktr": avg_ktr,
        "top_misaligned_skus": [str(item.get("sku") or "") for item in top_worst_localization[:5] if str(item.get("sku") or "").strip()],
        "coverage_pct": coverage_pct,
        "demand_coverage_pct": demand_coverage_pct,
        "stock_coverage_pct": stock_coverage_pct,
        "unknown_localization_skus": unknown_localization_skus,
        "known_localization_skus": known_localization_skus,
        "unknown_share_pct": unknown_share_pct,
        "confidence_level": confidence_level,
        "suppressed_due_to_data_quality": suppressed_due_to_data_quality,
        "suppression_reasons": suppression_reasons,
        "analysis_mode": analysis_mode,
        "data_quality_status": "ok" if analysis_mode == "full" else ("low_confidence" if analysis_mode == "preview" else "insufficient_data"),
        "recommendation_status": recommendation_status,
        "portfolio_territorial_risk": portfolio_risk,
        "full_analysis_skus": full_analysis_skus,
        "preview_analysis_skus": preview_analysis_skus,
        "disabled_analysis_skus": disabled_analysis_skus,
    }


def build_territorial_distribution(
    metrics: Dict[str, Any],
    stocks_raw: Dict[str, Any] | List[Dict[str, Any]] | None = None,
    seller_id: str | None = None,
    run_date: str | None = None,
    config: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    cfg = _resolve_config(config)
    safe_metrics = metrics if isinstance(metrics, dict) else {}
    safe_data_quality = safe_metrics.get("data_quality", {}) if isinstance(safe_metrics.get("data_quality"), dict) else {}

    resolved_seller_id = str(seller_id or safe_metrics.get("seller_id") or "").strip()
    resolved_run_date = str(run_date or safe_metrics.get("run_date") or "").strip()
    sku_attribution_status = str(safe_data_quality.get("sku_attribution_status") or "ok").strip().lower()

    if not bool(cfg.get("enable_territorial_distribution_engine", True)):
        payload = DistributionEngineOutput(
            seller_id=resolved_seller_id,
            report_date=resolved_run_date,
            status="disabled",
            warnings=[{"code": "territorial_distribution_disabled", "message": "Territorial distribution engine is disabled by config."}],
            metadata={
                "engine": "territorial_distribution_engine",
                "version": "2.1",
                "seller_id": resolved_seller_id,
                "run_date": resolved_run_date,
                "generated_at": _utc_now_iso(),
                "wb_irp_effective_date": str(cfg.get("wb_irp_effective_date") or ""),
            },
            summary={
                "total_skus_analyzed": 0,
                "distribution_efficiency_score": 0.0,
                "aggregate_estimated_irp_penalty_total": 0.0,
                "analysis_mode": "disabled",
                "recommendation_status": "blocked_by_data",
                "suppressed_due_to_data_quality": True,
                "coverage_pct": 0.0,
                "confidence_level": "low",
            },
            signals=[],
            sku_metrics=[],
        )
        result = payload.to_dict()
        result.update({
            "analysis_mode": "disabled",
            "data_quality_status": "insufficient_data",
            "recommendation_status": "blocked_by_data",
            "suppressed_due_to_data_quality": True,
            "coverage_pct": 0.0,
            "confidence_level": "low",
        })
        return result

    localization_rows, warnings = build_localization_rows(
        safe_metrics,
        stocks_raw=stocks_raw,
        min_orders_for_confidence=int(_as_float(cfg.get("min_orders_for_confidence", 3.0))),
        min_orders_for_actionable=int(_as_float(cfg.get("min_orders_for_actionable", 5.0))),
        sku_attribution_status=sku_attribution_status,
    )
    sku_metrics_index = _extract_sku_metrics_index(safe_metrics)
    sku_items: List[SkuDistributionMetrics] = []
    effective_date = str(cfg.get("wb_irp_effective_date") or "2026-03-23")
    for row in localization_rows:
        sku = str(row.get("sku") or "").strip()
        if not sku:
            continue

        total_orders = max(0.0, _as_float(row.get("total_orders")))
        local_orders_raw = row.get("local_orders")
        local_orders = None if local_orders_raw is None else max(0.0, _as_float(local_orders_raw))
        localization_share_raw = row.get("localization_share")
        localization_share = round(float(localization_share_raw), 6) if localization_share_raw is not None else None

        metric_row = sku_metrics_index.get(sku.lower(), {})
        average_price, price_source, price_warning = resolve_average_retail_price(metric_row, total_orders=total_orders)

        if localization_share is None:
            irp = {
                "ktr": None,
                "krp": None,
                "irp_penalty_per_order": None,
                "estimated_irp_penalty_total": 0.0,
                "effective_date_applied": is_effective_date_applied(resolved_run_date, effective_date),
            }
        else:
            irp = estimate_irp_penalty(
                localization_share=localization_share,
                total_orders=total_orders,
                average_retail_price=average_price,
                report_date=resolved_run_date,
                effective_date=effective_date,
            )

        state = _distribution_state(localization_share, total_orders, cfg)

        notes: List[str] = []
        if price_warning:
            notes.append(str(price_warning))
        if not bool(irp.get("effective_date_applied", False)):
            notes.append("irp_effect_not_applied_yet")
        if localization_share is None:
            notes.append("localization_share_unknown")
        elif _as_float(localization_share) >= 60.0:
            notes.append("krp_zero_due_to_localization_60_plus")

        diagnostics = {
            "price_source": price_source,
            "local_orders_source": row.get("local_orders_source"),
            "distribution_gap": row.get("distribution_gap"),
            "locality_score": row.get("locality_score"),
            "demand_by_warehouse": row.get("demand_by_warehouse", {}),
            "stock_by_warehouse": row.get("stock_by_warehouse", {}),
            "demand_share_by_warehouse": row.get("demand_share_by_warehouse", {}),
            "stock_share_by_warehouse": row.get("stock_share_by_warehouse", {}),
            "dominant_demand_warehouses": row.get("dominant_demand_warehouses", []),
            "dominant_stock_warehouses": row.get("dominant_stock_warehouses", []),
            "reverse_logistics_modeling": "deferred_until_volume_fields_available",
            "valid_sku_attribution": bool(row.get("valid_sku_attribution", True)),
            "order_count_available": bool(row.get("order_count_available", False)),
            "demand_geography_available": bool(row.get("demand_geography_available", False)),
            "stock_geography_available": bool(row.get("stock_geography_available", False)),
            "minimum_sample_met": bool(row.get("minimum_sample_met", False)),
            "evidence_sources": row.get("evidence_sources", {}),
            "known_facts": row.get("known_facts", {}),
            "estimated_metrics": row.get("estimated_metrics", {}),
            "unavailable_metrics": row.get("unavailable_metrics", []),
            "suppressed_recommendations": row.get("suppressed_recommendations", []),
        }

        sku_items.append(
            SkuDistributionMetrics(
                sku=sku,
                total_orders=round(total_orders, 6),
                local_orders=(round(local_orders, 6) if local_orders is not None else None),
                localization_share=localization_share,
                ktr=(round(_as_float(irp.get("ktr")), 4) if irp.get("ktr") is not None else None),
                krp=(round(_as_float(irp.get("krp")), 6) if irp.get("krp") is not None else None),
                average_retail_price=(round(float(average_price), 4) if average_price is not None else None),
                irp_penalty_per_order=(round(_as_float(irp.get("irp_penalty_per_order")), 6) if irp.get("irp_penalty_per_order") is not None else None),
                estimated_irp_penalty_total=round(_as_float(irp.get("estimated_irp_penalty_total")), 6),
                distribution_state=state,
                distribution_state_label_ru=_STATE_LABELS_RU.get(state, state),
                effective_date_applied=bool(irp.get("effective_date_applied", False)),
                confidence=str(row.get("confidence") or "low"),
                analysis_mode=str(row.get("analysis_mode") or "disabled"),
                data_quality_status=str(row.get("data_quality_status") or "insufficient_data"),
                recommendation_status=str(row.get("recommendation_status") or "blocked_by_data"),
                diagnostics=diagnostics,
                notes=notes,
            )
        )

    items_dict: List[Dict[str, Any]] = []
    for item in sku_items:
        row = item.to_dict()
        row["status"] = _legacy_status_from_state(item.distribution_state)
        row["distribution_gap"] = row.get("diagnostics", {}).get("distribution_gap", row.get("distribution_gap"))
        row["demand_by_warehouse"] = row.get("diagnostics", {}).get("demand_by_warehouse", {}) or {}
        row["stock_by_warehouse"] = row.get("diagnostics", {}).get("stock_by_warehouse", {}) or {}
        row["demand_share_by_warehouse"] = row.get("diagnostics", {}).get("demand_share_by_warehouse", {}) or {}
        row["stock_share_by_warehouse"] = row.get("diagnostics", {}).get("stock_share_by_warehouse", {}) or {}
        row["dominant_demand_warehouses"] = row.get("diagnostics", {}).get("dominant_demand_warehouses") or sorted(
            [str(k) for k, v in row["demand_share_by_warehouse"].items() if _as_float(v) > 0.2],
            key=lambda k: -_as_float(row["demand_share_by_warehouse"].get(k)),
        )
        row["dominant_stock_warehouses"] = row.get("diagnostics", {}).get("dominant_stock_warehouses") or sorted(
            [str(k) for k, v in row["stock_share_by_warehouse"].items() if _as_float(v) > 0.2],
            key=lambda k: -_as_float(row["stock_share_by_warehouse"].get(k)),
        )
        row["locality_score"] = row.get("diagnostics", {}).get("locality_score")
        if row["locality_score"] is None:
            row["locality_score"] = round(
                sum(
                    min(_as_float(row["demand_share_by_warehouse"].get(k)), _as_float(row["stock_share_by_warehouse"].get(k)))
                    for k in set(row["demand_share_by_warehouse"]) | set(row["stock_share_by_warehouse"])
                ),
                6,
            )
        row["total_buys"] = int(round(_as_float(row.get("total_orders", 0.0))))
        row["total_stock"] = int(round(sum(_as_float(v) for v in row["stock_by_warehouse"].values())))
        row["low_sample_warning"] = str(row.get("confidence") or "").strip().lower() == "low"
        row["relocation_hint"] = (
            "priority_relocation"
            if row.get("distribution_state") in {"critical", "weak"} and row.get("recommendation_status") == "actionable"
            else ("monitor" if row.get("distribution_state") == "watch" else None)
        )
        row["valid_sku_attribution"] = bool(row.get("diagnostics", {}).get("valid_sku_attribution", True))
        row["order_count_available"] = bool(row.get("diagnostics", {}).get("order_count_available", False))
        row["demand_geography_available"] = bool(row.get("diagnostics", {}).get("demand_geography_available", False))
        row["stock_geography_available"] = bool(row.get("diagnostics", {}).get("stock_geography_available", False))
        row["minimum_sample_met"] = bool(row.get("diagnostics", {}).get("minimum_sample_met", False))
        row["evidence_sources"] = row.get("diagnostics", {}).get("evidence_sources", {})
        row["known_facts"] = row.get("diagnostics", {}).get("known_facts", {})
        row["estimated_metrics"] = row.get("diagnostics", {}).get("estimated_metrics", {})
        row["unavailable_metrics"] = row.get("diagnostics", {}).get("unavailable_metrics", [])
        row["suppressed_recommendations"] = row.get("diagnostics", {}).get("suppressed_recommendations", [])
        items_dict.append(row)

    summary = _summary(items_dict, cfg, sku_attribution_status)
    signals = build_distribution_signals(
        items_dict,
        summary,
        profit_leak_threshold=float(cfg.get("distribution_profit_leak_threshold", 5000.0)),
        weak_threshold=float(cfg.get("localization_weak_threshold", 40.0)),
        critical_threshold=float(cfg.get("localization_critical_threshold", 20.0)),
        min_orders_for_actionable=int(_as_float(cfg.get("min_orders_for_actionable", 5.0))),
    )

    if summary.get("suppressed_due_to_data_quality"):
        warnings = list(warnings) + [{
            "code": "territorial_distribution_suppressed_due_to_data_quality",
            "message": "Portfolio-level territorial conclusions downgraded due to low evidence coverage.",
        }]
    if not items_dict:
        status = "insufficient_data"
    elif str(summary.get("analysis_mode") or "preview") == "disabled":
        status = "insufficient_data"
    elif str(summary.get("analysis_mode") or "preview") == "preview":
        status = "partial"
    elif warnings:
        status = "partial"
    else:
        status = "ok"

    metadata = {
        "engine": "territorial_distribution_engine",
        "version": "2.1",
        "seller_id": resolved_seller_id,
        "run_date": resolved_run_date,
        "generated_at": _utc_now_iso(),
        "wb_irp_effective_date": effective_date,
        "source_artifacts": ["metrics.json"],
        "reverse_logistics": {
            "mode": "deferred",
            "details": "Volume-based reverse logistics can be added when liters/volume fields become available.",
        },
        "config": {
            "enable_territorial_distribution_engine": bool(cfg.get("enable_territorial_distribution_engine", True)),
            "distribution_profit_leak_threshold": float(cfg.get("distribution_profit_leak_threshold", 5000.0)),
            "localization_watch_threshold": float(cfg.get("localization_watch_threshold", 60.0)),
            "localization_weak_threshold": float(cfg.get("localization_weak_threshold", 40.0)),
            "localization_critical_threshold": float(cfg.get("localization_critical_threshold", 20.0)),
            "min_orders_for_confidence": int(_as_float(cfg.get("min_orders_for_confidence", 3.0))),
            "min_orders_for_actionable": int(_as_float(cfg.get("min_orders_for_actionable", 5.0))),
            "min_portfolio_coverage_pct": float(cfg.get("min_portfolio_coverage_pct", 40.0)),
            "min_demand_coverage_pct": float(cfg.get("min_demand_coverage_pct", 50.0)),
            "min_stock_coverage_pct": float(cfg.get("min_stock_coverage_pct", 40.0)),
            "max_unknown_share_pct": float(cfg.get("max_unknown_share_pct", 60.0)),
        },
    }

    payload = DistributionEngineOutput(
        seller_id=resolved_seller_id,
        report_date=resolved_run_date,
        status=status,
        warnings=list(warnings),
        metadata=metadata,
        summary=summary,
        signals=signals,
        sku_metrics=sku_items,
    ).to_dict()

    payload["aggregate_estimated_irp_penalty_total"] = summary.get("aggregate_estimated_irp_penalty_total", 0.0)
    payload["distribution_efficiency_score"] = summary.get("distribution_efficiency_score", 0.0)
    payload["analysis_mode"] = str(summary.get("analysis_mode") or "preview")
    payload["data_quality_status"] = str(summary.get("data_quality_status") or "insufficient_data")
    payload["recommendation_status"] = str(summary.get("recommendation_status") or "blocked_by_data")
    payload["coverage_pct"] = float(summary.get("coverage_pct", 0.0) or 0.0)
    payload["confidence_level"] = str(summary.get("confidence_level") or "low")
    payload["suppressed_due_to_data_quality"] = bool(summary.get("suppressed_due_to_data_quality", False))
    payload["evidence_sources"] = {
        "sku_attribution_status": sku_attribution_status,
        "demand_coverage_pct": summary.get("demand_coverage_pct", 0.0),
        "stock_coverage_pct": summary.get("stock_coverage_pct", 0.0),
        "known_localization_skus": summary.get("known_localization_skus", 0),
        "total_skus": summary.get("total_skus_analyzed", 0),
    }
    payload["suppressed_recommendations"] = (
        ["rebalance_stock", "relocate_inventory", "warehouse_redistribution"]
        if str(summary.get("recommendation_status") or "blocked_by_data") != "actionable"
        else []
    )

    return payload


def save_territorial_distribution(output_path: Path, data: Dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
