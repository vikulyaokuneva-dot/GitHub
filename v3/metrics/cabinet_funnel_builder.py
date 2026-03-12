from __future__ import annotations

from typing import Any, Dict

from .sales_funnel_assembler import assemble_sales_funnel


def build_cabinet_funnel_core(
    *,
    run_date: str,
    metrics: Dict[str, Any],
    ads_diagnostics: Dict[str, Any],
) -> Dict[str, Any]:
    return assemble_sales_funnel(
        run_date=run_date,
        metrics=metrics if isinstance(metrics, dict) else {},
        ads_diagnostics=ads_diagnostics if isinstance(ads_diagnostics, dict) else {},
    )
