"""Rollback policy helpers for controlled production switch."""

from __future__ import annotations

from .contracts import ProductionMode


def can_rollback(
    *,
    selected_mode: ProductionMode,
    runner_failed: bool,
    fallback_allowed: bool,
    operator_forced_mode: bool = False,
) -> bool:
    if selected_mode == ProductionMode.LEGACY:
        return False
    if not runner_failed:
        return False
    if operator_forced_mode and not fallback_allowed:
        return False
    return bool(fallback_allowed)


def get_rollback_mode(selected_mode: ProductionMode) -> ProductionMode:
    if selected_mode in {ProductionMode.V4, ProductionMode.SHADOW}:
        return ProductionMode.LEGACY
    return ProductionMode.LEGACY


def build_rollback_note(
    *,
    selected_mode: ProductionMode,
    rollback_mode: ProductionMode,
    reason: str,
    fallback_allowed: bool,
) -> str:
    return (
        f"rollback: {selected_mode.value} -> {rollback_mode.value}; "
        f"fallback_allowed={str(bool(fallback_allowed)).lower()}; reason={reason}"
    )


__all__ = ["can_rollback", "get_rollback_mode", "build_rollback_note"]

