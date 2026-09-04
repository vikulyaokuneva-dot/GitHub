"""Advertising read contracts that prohibit invented SKU allocation."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from packages.data.canonical import AdvertisingAttributionScope, CanonicalAdvertisingPerformance


class AdvertisingScopeTotals(BaseModel):
    """A scope-preserving advertising aggregate."""

    model_config = ConfigDict(frozen=True)

    attribution_scope: AdvertisingAttributionScope
    spend: Decimal | None = None
    source_record_count: int = Field(ge=0)

    @model_validator(mode="after")
    def require_spend_for_nonempty_scope(self) -> AdvertisingScopeTotals:
        if self.source_record_count == 0 and self.spend is not None:
            raise ValueError("an empty advertising scope must not have spend")
        return self


class AdvertisingReadModel(BaseModel):
    """Production read model with only evidence-backed SKU attribution."""

    model_config = ConfigDict(frozen=True)

    facts: tuple[CanonicalAdvertisingPerformance, ...]
    scope_totals: tuple[AdvertisingScopeTotals, ...]
    direct_sku_spend: dict[str, Decimal | None]
