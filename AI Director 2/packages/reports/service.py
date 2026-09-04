"""Assemble report payloads solely from domain read models."""

from __future__ import annotations

from decimal import Decimal

from packages.advertising.contracts import AdvertisingReadModel
from packages.finance.contracts import FinancialResult
from packages.operational.contracts import OperationalDailyReadModel

from .contracts import ReportMetric, ReportPayload


def _metric(*, key: str, owner: str, value: Decimal | None, status: str) -> ReportMetric:
    return ReportMetric(key=key, owner=owner, value=value, status=status)


def build_report_payload(
    *,
    operational: OperationalDailyReadModel,
    financial: FinancialResult | None = None,
    advertising: AdvertisingReadModel | None = None,
    diagnostics: tuple[str, ...] = (),
) -> ReportPayload:
    """Project declared domain values into a renderer input without calculating them."""

    if financial is not None and (financial.scope != operational.scope or financial.operational_date != operational.operational_date):
        raise ValueError("financial result scope/date must match operational report context")
    metrics = [
        _metric(key="orders", owner="operational", value=operational.order_quantity.value, status=operational.order_quantity.status),
        _metric(key="sales", owner="operational", value=operational.sales_quantity.value, status=operational.sales_quantity.status),
        _metric(key="available_stock", owner="operational", value=operational.available_stock_quantity.value, status=operational.available_stock_quantity.status),
        _metric(key="funnel_opens", owner="operational", value=operational.funnel_open_count.value, status=operational.funnel_open_count.status),
        _metric(key="funnel_carts", owner="operational", value=operational.funnel_cart_count.value, status=operational.funnel_cart_count.status),
        _metric(key="funnel_orders", owner="operational", value=operational.funnel_order_count.value, status=operational.funnel_order_count.status),
        _metric(key="cohort_buyouts", owner="operational", value=operational.cohort_buyout_count.value, status=operational.cohort_buyout_count.status),
        _metric(key="cohort_buyout_sum", owner="operational", value=operational.cohort_buyout_sum.value, status=operational.cohort_buyout_sum.status),
    ]
    if financial is not None:
        metrics.extend(
            (
                _metric(key="net_profit", owner="finance", value=financial.net_profit, status=financial.status),
                _metric(key="profit_margin", owner="finance", value=financial.profit_margin, status=financial.status),
            )
        )
        for trace in financial.component_traces:
            # A component the kernel did not include must not appear as a P&L
            # amount: a reader summing the printed lines would get a total the
            # kernel never produced. Its status and diagnostic carry the fact.
            metrics.append(
                _metric(
                    key=trace.component.value,
                    owner="finance",
                    value=trace.amount if trace.included else None,
                    status=trace.status,
                )
            )
    if advertising is not None:
        for total in advertising.scope_totals:
            metrics.append(
                _metric(
                    key=f"advertising_{total.attribution_scope.value}",
                    owner="advertising",
                    value=total.spend,
                    status="available" if total.spend is not None else "missing",
                )
            )
    return ReportPayload(
        operational_date=operational.operational_date,
        operational=operational,
        financial=financial,
        advertising=advertising,
        metrics=tuple(metrics),
        diagnostics=tuple(diagnostics),
    )
