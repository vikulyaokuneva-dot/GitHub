"""Pure advertising aggregation with scope-preserving attribution."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from packages.data.canonical import AdvertisingAttributionScope, CanonicalAdvertisingPerformance

from .contracts import AdvertisingReadModel, AdvertisingScopeTotals


def build_advertising_read_model(facts: Iterable[CanonicalAdvertisingPerformance]) -> AdvertisingReadModel:
    """Aggregate spend only at its source scope; only direct `nm_id` reaches SKU."""

    ordered = tuple(sorted(facts, key=lambda item: (item.source_metadata.source_object_id, item.source_metadata.source_record_index)))
    scopes: list[AdvertisingScopeTotals] = []
    direct_sku_spend: dict[str, Decimal | None] = {}
    for scope in AdvertisingAttributionScope:
        scoped = tuple(item for item in ordered if item.attribution_scope == scope)
        known = tuple(item.spend for item in scoped if item.spend is not None)
        scopes.append(
            AdvertisingScopeTotals(
                attribution_scope=scope,
                spend=sum(known, Decimal("0")) if known else None,
                source_record_count=len(scoped),
            )
        )
        if scope == AdvertisingAttributionScope.DIRECT_SKU:
            for item in scoped:
                assert item.nm_id is not None
                if item.spend is None:
                    direct_sku_spend[item.nm_id] = None
                elif item.nm_id not in direct_sku_spend:
                    direct_sku_spend[item.nm_id] = item.spend
                else:
                    existing_spend = direct_sku_spend[item.nm_id]
                    if existing_spend is not None:
                        direct_sku_spend[item.nm_id] = existing_spend + item.spend
    return AdvertisingReadModel(facts=ordered, scope_totals=tuple(scopes), direct_sku_spend=direct_sku_spend)
