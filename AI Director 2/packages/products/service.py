"""Adapters from explicit Product Economics inputs to Finance contracts."""

from __future__ import annotations

from datetime import date

from packages.finance.contracts import (
    CogsAllocationInput,
    FinancialComponent,
    FinancialComponentInput,
)

from .contracts import DirectPeriodCogsInput, ProductCostProfile


def to_financial_component(input_value: DirectPeriodCogsInput) -> FinancialComponentInput:
    """Convert supplied period COGS only; no order, sale, or buyout data is read."""

    return FinancialComponentInput(
        component=FinancialComponent.COGS,
        state=input_value.state,
        amount=input_value.amount,
        source=input_value.source,
        source_record_id=input_value.source_record_id,
        source_endpoint=input_value.source_endpoint,
        operational_date=input_value.operational_date,
    )


def to_cogs_allocation(
    profile: ProductCostProfile,
    *,
    quantity: int,
    operational_date: date,
) -> CogsAllocationInput:
    """Declare one seller unit cost against an authoritative realized quantity.

    The multiplication ``unit COGS × quantity`` stays the Finance Kernel's job;
    this adapter only carries the two inputs and their provenance.  A caller
    without an authoritative positive quantity must not call it at all, so an
    unknown cost can never degrade into zero COGS.
    """

    return CogsAllocationInput(
        nm_id=profile.nm_id,
        quantity=quantity,
        state=profile.state,
        unit_cogs=profile.unit_cogs,
        packaging_per_unit=profile.packaging_per_unit,
        source=profile.source,
        source_record_id=profile.source_record_id,
        effective_date=operational_date,
    )
