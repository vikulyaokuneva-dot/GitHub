"""Seller/cabinet configuration contracts for orchestration layer.

This layer must stay free from KPI/business logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SellerConfig:
    seller_id: str
    display_name: str
    cabinet_id: str | None = None
    cabinet_name: str | None = None
    is_enabled: bool = True
    mode_overrides: dict[str, Any] = field(default_factory=dict)
    feature_overrides: dict[str, bool] = field(default_factory=dict)
    output_subdir: str | None = None
    input_subdir: str | None = None
    tags: list[str] = field(default_factory=list)
    notes: str | None = None


_SELLERS: tuple[SellerConfig, ...] = (
    SellerConfig(
        seller_id="seller_001",
        display_name="Seller 001",
        cabinet_id="cabinet_001",
        cabinet_name="Main Cabinet",
        is_enabled=True,
        output_subdir="seller_001",
        input_subdir="seller_001",
        feature_overrides={},
        mode_overrides={},
        tags=["default"],
    ),
)


def list_sellers(include_disabled: bool = False) -> list[SellerConfig]:
    if include_disabled:
        return list(_SELLERS)
    return [seller for seller in _SELLERS if seller.is_enabled]


def get_seller_config(seller_id: str) -> SellerConfig:
    target = str(seller_id or "").strip()
    if not target:
        raise ValueError("seller_id is required")
    for seller in _SELLERS:
        if seller.seller_id == target:
            return seller
    raise KeyError(f"Unknown seller_id: {target}")


def resolve_enabled_sellers(seller_ids: list[str] | None = None) -> list[SellerConfig]:
    if not seller_ids:
        return list_sellers(include_disabled=False)

    resolved: list[SellerConfig] = []
    for seller_id in seller_ids:
        config = get_seller_config(str(seller_id))
        if config.is_enabled:
            resolved.append(config)
    return resolved


__all__ = [
    "SellerConfig",
    "list_sellers",
    "get_seller_config",
    "resolve_enabled_sellers",
]

