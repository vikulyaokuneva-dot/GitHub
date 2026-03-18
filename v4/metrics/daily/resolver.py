"""Daily metrics resolver from financial section.

Input: FinancialMetricsSection.
Output: DailyMetricsSection (financial subset).
Does not compute independent KPI formulas.
"""

from __future__ import annotations

from ...core.contracts import DailyMetricsSection, FinancialMetricsSection


def build_daily_metrics_from_financial(
    financial_section: FinancialMetricsSection | None,
) -> DailyMetricsSection | None:
    if financial_section is None:
        return None

    return DailyMetricsSection(
        orders_count=financial_section.orders_count,
        sales_count=financial_section.sales_count,
        returns_count=financial_section.returns_count,
        orders_amount=financial_section.orders_amount,
        sales_amount=financial_section.sales_amount,
    )


def build(payload: FinancialMetricsSection | None = None) -> DailyMetricsSection | None:
    """Back-compat alias for stage-1 naming."""

    return build_daily_metrics_from_financial(payload)
