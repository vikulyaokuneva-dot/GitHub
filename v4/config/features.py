"""Feature policy helpers for runtime orchestration.

Feature resolution is deterministic and does not affect KPI calculations.
"""

from __future__ import annotations

from typing import Any, Mapping

from .sellers import SellerConfig


FEATURE_DEFAULTS: dict[str, bool] = {
    "enable_delivery": False,
    "enable_pdf_render": False,
    "enable_email_preview": False,
    "enable_health_section": True,
    "enable_audit_mode": True,
    "enable_multi_cabinet_runs": True,
    "enable_v4_production": False,
    "enable_legacy_production": True,
    "enable_production_fallback_to_legacy": False,
    "enable_cli_production_override": False,
    "enable_shadow_mode": False,
    "enable_comparison": True,
    "enable_shadow_persistence": True,
}


def _coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "on"}


def _mode_from_context(run_context: Any) -> str:
    if run_context is None:
        return ""
    if isinstance(run_context, Mapping):
        mode = run_context.get("mode")
    else:
        mode = getattr(run_context, "mode", None)
    if hasattr(mode, "value"):
        return str(mode.value).strip().lower()
    return str(mode or "").strip().lower()


def resolve_feature_flags(
    *,
    run_context: Any = None,
    seller_config: SellerConfig | None = None,
    run_overrides: Mapping[str, object] | None = None,
) -> dict[str, bool]:
    resolved = dict(FEATURE_DEFAULTS)

    if seller_config is not None:
        for key, value in seller_config.feature_overrides.items():
            if key in resolved:
                resolved[key] = _coerce_bool(value)

    if run_overrides:
        for key, value in run_overrides.items():
            if key in resolved:
                resolved[key] = _coerce_bool(value)

    mode_text = _mode_from_context(run_context)
    if mode_text == "audit_file_mode" and not resolved["enable_audit_mode"]:
        resolved["enable_audit_mode"] = False

    return resolved


def is_feature_enabled(
    feature_name: str,
    *,
    run_context: Any = None,
    seller_config: SellerConfig | None = None,
    run_overrides: Mapping[str, object] | None = None,
) -> bool:
    flags = resolve_feature_flags(
        run_context=run_context,
        seller_config=seller_config,
        run_overrides=run_overrides,
    )
    return bool(flags.get(feature_name, False))


__all__ = ["FEATURE_DEFAULTS", "resolve_feature_flags", "is_feature_enabled"]
