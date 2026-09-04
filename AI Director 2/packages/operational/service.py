"""Pure aggregation for operational source facts."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from packages.data.canonical import (
    CanonicalOperationalOrder,
    CanonicalOperationalSale,
    CanonicalSalesFunnelProduct,
    CanonicalStockSnapshot,
)
from packages.wb_core.contracts import TenantAccountScope

from .contracts import OperationalDailyReadModel, OperationalMetricValue, OperationalReadStatus

OperationalFact = (
    CanonicalOperationalOrder | CanonicalOperationalSale | CanonicalStockSnapshot | CanonicalSalesFunnelProduct
)


def _source_key(fact: OperationalFact) -> tuple[str, int]:
    metadata = getattr(fact, "source_metadata")
    return metadata.source_object_id, metadata.source_record_index


def _aggregate(values: tuple[Decimal | int | None, ...]) -> OperationalMetricValue:
    if not values:
        return OperationalMetricValue(value=None, status=OperationalReadStatus.MISSING, source_record_count=0)
    usable = tuple(Decimal(value) for value in values if value is not None)
    if not usable:
        return OperationalMetricValue(value=None, status=OperationalReadStatus.MISSING, source_record_count=len(values))
    status = OperationalReadStatus.COMPLETE if len(usable) == len(values) else OperationalReadStatus.PARTIAL
    return OperationalMetricValue(value=sum(usable, Decimal("0")), status=status, source_record_count=len(values))


def _require_scope_and_date(*, facts: tuple[OperationalFact, ...]) -> tuple[TenantAccountScope, date]:
    if not facts:
        raise ValueError("at least one operational fact is required")
    first = facts[0]
    scope = first.source_metadata.scope
    operational_date = first.operational_date
    for fact in facts[1:]:
        if fact.source_metadata.scope != scope:
            raise ValueError("operational inputs must belong to exactly one tenant/account scope")
        if fact.operational_date != operational_date:
            raise ValueError("operational inputs must belong to exactly one operational_date")
    return scope, operational_date


def build_operational_daily_read_model(
    *,
    orders: Iterable[CanonicalOperationalOrder] = (),
    sales: Iterable[CanonicalOperationalSale] = (),
    stock_snapshots: Iterable[CanonicalStockSnapshot] = (),
    funnel_products: Iterable[CanonicalSalesFunnelProduct] = (),
) -> OperationalDailyReadModel:
    """Build a source-owned operational daily view without finance or COGS inference."""

    ordered_orders = tuple(sorted(orders, key=_source_key))
    ordered_sales = tuple(sorted(sales, key=_source_key))
    ordered_stocks = tuple(sorted(stock_snapshots, key=_source_key))
    ordered_funnel = tuple(sorted(funnel_products, key=_source_key))
    all_facts: tuple[OperationalFact, ...] = (*ordered_orders, *ordered_sales, *ordered_stocks, *ordered_funnel)
    scope, operational_date = _require_scope_and_date(facts=all_facts)
    return OperationalDailyReadModel(
        scope=scope,
        operational_date=operational_date,
        orders=ordered_orders,
        sales=ordered_sales,
        stock_snapshots=ordered_stocks,
        funnel_products=ordered_funnel,
        order_quantity=_aggregate(tuple(fact.quantity for fact in ordered_orders)),
        sales_quantity=_aggregate(tuple(fact.quantity for fact in ordered_sales)),
        available_stock_quantity=_aggregate(tuple(fact.available_quantity for fact in ordered_stocks)),
        funnel_open_count=_aggregate(tuple(fact.source_open_count for fact in ordered_funnel)),
        funnel_cart_count=_aggregate(tuple(fact.source_cart_count for fact in ordered_funnel)),
        funnel_order_count=_aggregate(tuple(fact.quantity for fact in ordered_funnel)),
        cohort_buyout_count=_aggregate(tuple(fact.buyout_count for fact in ordered_funnel)),
        cohort_buyout_sum=_aggregate(tuple(fact.buyout_sum for fact in ordered_funnel)),
    )


def build_empty_operational_daily_read_model(
    *, scope: TenantAccountScope, operational_date: date
) -> OperationalDailyReadModel:
    """Represent an empty endpoint set without manufacturing operational zeroes."""

    return OperationalDailyReadModel(
        scope=scope,
        operational_date=operational_date,
        order_quantity=_aggregate(()),
        sales_quantity=_aggregate(()),
        available_stock_quantity=_aggregate(()),
        funnel_open_count=_aggregate(()),
        funnel_cart_count=_aggregate(()),
        funnel_order_count=_aggregate(()),
        cohort_buyout_count=_aggregate(()),
        cohort_buyout_sum=_aggregate(()),
    )
