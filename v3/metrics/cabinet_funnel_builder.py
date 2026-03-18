from __future__ import annotations

from typing import Any, Dict

from .sales_funnel_assembler import assemble_sales_funnel


def _extract_funnel_xlsx_payload(metrics: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(metrics, dict):
        return {}

    candidates = [
        metrics.get("funnel_xlsx"),
        metrics.get("funnel_report_xlsx"),
        metrics.get("funnel_report"),
        metrics.get("local_funnel"),
        metrics.get("wb_funnel_xlsx"),
    ]
    input_debug = metrics.get("input_debug", {})
    if isinstance(input_debug, dict):
        candidates.extend(
            [
                input_debug.get("funnel_xlsx"),
                input_debug.get("funnel_report"),
                input_debug.get("local_funnel"),
            ]
        )

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if isinstance(candidate.get("cabinet_totals"), dict):
            return candidate
        if any(key in candidate for key in ("views", "add_to_cart", "orders", "buyouts")):
            return {
                "cabinet_totals": {
                    "views": candidate.get("views"),
                    "add_to_cart": candidate.get("add_to_cart"),
                    "orders": candidate.get("orders"),
                    "buyouts": candidate.get("buyouts"),
                    "orders_amount": candidate.get("orders_amount"),
                    "buyouts_amount": candidate.get("buyouts_amount"),
                },
                "sku_rows": candidate.get("sku_rows") if isinstance(candidate.get("sku_rows"), list) else [],
            }
    return {}


def build_cabinet_funnel_core(
    *,
    run_date: str,
    metrics: Dict[str, Any],
    ads_diagnostics: Dict[str, Any],
) -> Dict[str, Any]:
    safe_metrics = metrics if isinstance(metrics, dict) else {}
    funnel_xlsx_payload = _extract_funnel_xlsx_payload(safe_metrics)
    return assemble_sales_funnel(
        run_date=run_date,
        metrics=safe_metrics,
        ads_diagnostics=ads_diagnostics if isinstance(ads_diagnostics, dict) else {},
        funnel_xlsx_payload=funnel_xlsx_payload if isinstance(funnel_xlsx_payload, dict) else {},
    )
