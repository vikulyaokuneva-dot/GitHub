"""Contracts for the Stage 10 operational read model."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from packages.data.canonical import (
    CanonicalOperationalOrder,
    CanonicalOperationalSale,
    CanonicalSalesFunnelProduct,
    CanonicalStockSnapshot,
)
from packages.wb_core.contracts import TenantAccountScope

OperationalFact = (
    CanonicalOperationalOrder | CanonicalOperationalSale | CanonicalStockSnapshot | CanonicalSalesFunnelProduct
)


class OperationalReadStatus(StrEnum):
    """Availability state of an operational metric without silently using zero."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    MISSING = "missing"


class OperationalMetricValue(BaseModel):
    """A source-owned operational aggregate with an explicit missing state."""

    model_config = ConfigDict(frozen=True)

    value: Decimal | None = None
    status: OperationalReadStatus
    source_record_count: int = Field(ge=0)

    @model_validator(mode="after")
    def require_value_to_match_status(self) -> OperationalMetricValue:
        if self.status == OperationalReadStatus.MISSING and self.value is not None:
            raise ValueError("missing operational metric must not have a value")
        if self.status != OperationalReadStatus.MISSING and self.value is None:
            raise ValueError("available operational metric must have a value")
        return self


class OperationalDailyReadModel(BaseModel):
    """Deterministic daily operational view; it contains no financial components."""

    model_config = ConfigDict(frozen=True)

    scope: TenantAccountScope
    operational_date: date
    orders: tuple[CanonicalOperationalOrder, ...] = ()
    sales: tuple[CanonicalOperationalSale, ...] = ()
    stock_snapshots: tuple[CanonicalStockSnapshot, ...] = ()
    funnel_products: tuple[CanonicalSalesFunnelProduct, ...] = ()
    order_quantity: OperationalMetricValue
    sales_quantity: OperationalMetricValue
    available_stock_quantity: OperationalMetricValue
    funnel_open_count: OperationalMetricValue
    funnel_cart_count: OperationalMetricValue
    funnel_order_count: OperationalMetricValue
    cohort_buyout_count: OperationalMetricValue
    cohort_buyout_sum: OperationalMetricValue

    @model_validator(mode="after")
    def require_single_scope_and_day(self) -> OperationalDailyReadModel:
        facts: tuple[OperationalFact, ...] = (*self.orders, *self.sales, *self.stock_snapshots, *self.funnel_products)
        for fact in facts:
            if fact.source_metadata.scope != self.scope:
                raise ValueError("operational facts must belong to the model tenant/account scope")
            if fact.operational_date != self.operational_date:
                raise ValueError("operational facts must belong to the model operational_date")
        return self
