"""Cabinet registry helpers.

Registry is a thin lookup layer and must not contain pipeline/KPI logic.
"""

from __future__ import annotations

from dataclasses import replace

from ..config.sellers import SellerConfig, list_sellers


_DEFAULT_REGISTRY: list[SellerConfig] = list_sellers(include_disabled=True)
_REGISTRY: list[SellerConfig] = list(_DEFAULT_REGISTRY)


def register_seller_configs(configs: list[SellerConfig]) -> None:
    global _REGISTRY
    _REGISTRY = [replace(config) for config in configs]


def reset_registry() -> None:
    register_seller_configs(_DEFAULT_REGISTRY)


def load_seller_configs(include_disabled: bool = True) -> list[SellerConfig]:
    if include_disabled:
        return list(_REGISTRY)
    return [config for config in _REGISTRY if config.is_enabled]


def get_enabled_cabinets() -> list[SellerConfig]:
    return load_seller_configs(include_disabled=False)


def validate_seller_id(seller_id: str) -> bool:
    target = str(seller_id or "").strip()
    if not target:
        return False
    return any(config.seller_id == target for config in _REGISTRY)


def get_cabinet_by_seller(seller_id: str) -> SellerConfig | None:
    target = str(seller_id or "").strip()
    if not target:
        return None
    for config in _REGISTRY:
        if config.seller_id == target:
            return config
    return None


def _normalize_seller_ids(seller_ids: list[str] | str | None) -> list[str]:
    if seller_ids is None:
        return []
    if isinstance(seller_ids, str):
        parts = [part.strip() for part in seller_ids.split(",")]
        return [part for part in parts if part]
    normalized: list[str] = []
    for value in seller_ids:
        text = str(value or "").strip()
        if text:
            normalized.append(text)
    return normalized


def resolve_single_or_multiple_sellers(
    *,
    seller_id: str | None = None,
    seller_ids: list[str] | str | None = None,
    include_disabled: bool = False,
) -> list[SellerConfig]:
    requested_ids = _normalize_seller_ids(seller_ids)
    if seller_id and str(seller_id).strip():
        requested_ids = [str(seller_id).strip()]

    if not requested_ids:
        return load_seller_configs(include_disabled=include_disabled)

    resolved: list[SellerConfig] = []
    missing: list[str] = []
    for requested in requested_ids:
        config = get_cabinet_by_seller(requested)
        if config is None:
            missing.append(requested)
            continue
        if not include_disabled and not config.is_enabled:
            continue
        resolved.append(config)

    if missing:
        raise KeyError(f"Unknown seller_ids: {missing}")

    return resolved


__all__ = [
    "register_seller_configs",
    "reset_registry",
    "load_seller_configs",
    "get_enabled_cabinets",
    "get_cabinet_by_seller",
    "validate_seller_id",
    "resolve_single_or_multiple_sellers",
]

