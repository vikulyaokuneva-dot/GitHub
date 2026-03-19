"""Controlled production switch resolution and runner orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..cabinets.paths import path_label
from ..cabinets.registry import get_cabinet_by_seller
from ..config.features import resolve_feature_flags
from ..config.settings import get_settings
from ..pipeline.runners.daily_runner import run_daily_pipeline
from ..shadow.runner import run_shadow_daily
from .contracts import ProductionMode, ProductionSwitchDecision
from .diagnostics import build_production_diagnostics, build_switch_summary
from .rollback import build_rollback_note, can_rollback, get_rollback_mode


def _coerce_mode(value: object) -> ProductionMode | None:
    if value is None:
        return None
    if isinstance(value, ProductionMode):
        return value
    text = str(value).strip().lower()
    if not text:
        return None
    for mode in ProductionMode:
        if mode.value == text:
            return mode
    raise ValueError(f"Unsupported production mode: {value}")


def _run_legacy_daily(
    *,
    seller_id: str,
    run_date: str | None,
    output_dir: str | None,
) -> dict[str, Any]:
    from v3.entry import run_daily_batch  # type: ignore

    repo_root = str(Path(__file__).resolve().parents[2])
    return run_daily_batch(
        repo_root=repo_root,
        seller_id=str(seller_id).strip() or None,
        run_date=str(run_date).strip() if run_date else None,
    )


def is_v4_enabled_for_seller(
    seller_id: str,
    *,
    run_overrides: dict[str, object] | None = None,
) -> bool:
    seller_config = get_cabinet_by_seller(seller_id)
    flags = resolve_feature_flags(
        run_context={"mode": "daily_api_mode"},
        seller_config=seller_config,
        run_overrides=run_overrides or {},
    )
    return bool(flags.get("enable_v4_production", False))


def resolve_production_mode(
    *,
    seller_id: str,
    cli_mode: str | None = None,
    run_overrides: dict[str, object] | None = None,
) -> ProductionSwitchDecision:
    settings = get_settings()
    seller_config = get_cabinet_by_seller(seller_id)
    feature_flags = resolve_feature_flags(
        run_context={"mode": "daily_api_mode"},
        seller_config=seller_config,
        run_overrides=run_overrides or {},
    )

    notes: list[str] = []
    selected: ProductionMode | None = None
    source = "default"
    reason = "default safe mode"

    cli_requested = _coerce_mode(cli_mode)
    if cli_requested is not None:
        if feature_flags.get("enable_cli_production_override", False):
            selected = cli_requested
            source = "cli_override"
            reason = "explicit CLI production override"
            notes.append(f"cli requested mode={cli_requested.value}")
        else:
            notes.append("cli production override ignored: enable_cli_production_override=false")

    if selected is None and seller_config is not None:
        seller_mode = _coerce_mode(seller_config.mode_overrides.get("production_mode"))
        if seller_mode is not None:
            selected = seller_mode
            source = "seller_config"
            reason = "seller-level production mode override"
            notes.append(f"seller mode override={seller_mode.value}")

    if selected is None:
        global_mode = _coerce_mode(settings.production_default_mode)
        if global_mode is not None:
            selected = global_mode
            source = "global_config"
            reason = "global production default mode"
            notes.append(f"global default mode={global_mode.value}")

    if selected is None:
        selected = ProductionMode.LEGACY
        source = "default"
        reason = "safe fallback default"
        notes.append("fallback to legacy default")

    if selected == ProductionMode.V4 and not feature_flags.get("enable_v4_production", False):
        notes.append("v4 production requested but enable_v4_production=false; forcing legacy")
        selected = ProductionMode.LEGACY
        source = "feature_guard"
        reason = "v4 production disabled by feature flag"

    if selected == ProductionMode.LEGACY and not feature_flags.get("enable_legacy_production", True):
        notes.append("legacy mode disabled by feature flag; forcing v4")
        selected = ProductionMode.V4
        source = "feature_guard"
        reason = "legacy production disabled by feature flag"

    rollback_allowed = bool(feature_flags.get("enable_production_fallback_to_legacy", False))
    return ProductionSwitchDecision(
        selected_mode=selected,
        reason=reason,
        source_of_decision=source,
        rollback_allowed=rollback_allowed,
        notes=notes,
    )


def run_production_daily(
    *,
    seller_id: str,
    run_date: str | None,
    output_dir: str | None,
    cli_mode: str | None = None,
    allow_fallback_to_legacy: bool = False,
    dry_run: bool = False,
    run_overrides: dict[str, object] | None = None,
) -> dict[str, Any]:
    seller_text = str(seller_id).strip()
    if not seller_text:
        raise ValueError("seller_id is required")

    requested_overrides = dict(run_overrides or {})
    if allow_fallback_to_legacy:
        requested_overrides["enable_production_fallback_to_legacy"] = True

    decision = resolve_production_mode(
        seller_id=seller_text,
        cli_mode=cli_mode,
        run_overrides=requested_overrides,
    )

    seller_config = get_cabinet_by_seller(seller_text)
    feature_flags = resolve_feature_flags(
        run_context={"mode": "daily_api_mode"},
        seller_config=seller_config,
        run_overrides=requested_overrides,
    )

    warnings: list[str] = []
    rollback_happened = False
    fallback_used = False
    rollback_hint: str | None = None

    mode = decision.selected_mode
    if mode == ProductionMode.LEGACY:
        if dry_run:
            raise ValueError(
                "dry-run in legacy production mode is unsafe: use --production-mode v4 "
                "or run without production switch."
            )
        result = _run_legacy_daily(
            seller_id=seller_text,
            run_date=run_date,
            output_dir=output_dir,
        )
        diagnostics = build_production_diagnostics(
            switch_decision=decision,
            seller_id=seller_text,
            run_date=run_date,
            dry_run=dry_run,
            output_dir=output_dir,
            effective_runner="legacy_daily_batch",
            warnings=warnings,
            rollback_happened=False,
            fallback_used=False,
            rollback_hint="legacy is baseline rollback target",
            notes=["single-run production path uses legacy only"],
            feature_flags=feature_flags,
        )
        return {
            "run_result": result,
            "production": {
                "switch_decision": {
                    "selected_mode": decision.selected_mode.value,
                    "reason": decision.reason,
                    "source_of_decision": decision.source_of_decision,
                    "rollback_allowed": decision.rollback_allowed,
                    "notes": list(decision.notes),
                },
                "diagnostics": diagnostics,
                "summary": build_switch_summary(diagnostics),
            },
        }

    if mode == ProductionMode.SHADOW:
        shadow_output_root = output_dir or str(Path(".tmp") / f"v4_shadow_{seller_text}")
        shadow_result = run_shadow_daily(
            seller_id=seller_text,
            run_date=str(run_date or "").strip(),
            output_root=shadow_output_root,
            run_v4=True,
            run_legacy=not dry_run,
        )
        diagnostics = build_production_diagnostics(
            switch_decision=decision,
            seller_id=seller_text,
            run_date=run_date,
            dry_run=dry_run,
            output_dir=shadow_output_root,
            effective_runner="shadow_daily_runner",
            warnings=warnings,
            rollback_hint="shadow mode is read-only; use legacy for hard rollback",
            shadow_reference=str(path_label(shadow_output_root) or ""),
            notes=["shadow mode is observational and not a hard production switch"],
            feature_flags=feature_flags,
        )
        return {
            "run_result": shadow_result,
            "production": {
                "switch_decision": {
                    "selected_mode": decision.selected_mode.value,
                    "reason": decision.reason,
                    "source_of_decision": decision.source_of_decision,
                    "rollback_allowed": decision.rollback_allowed,
                    "notes": list(decision.notes),
                },
                "diagnostics": diagnostics,
                "summary": build_switch_summary(diagnostics),
            },
        }

    # mode == V4
    try:
        v4_result = run_daily_pipeline(
            run_context={
                "seller_id": seller_text,
                "run_date": run_date,
                "dry_run": bool(dry_run),
            },
            output_dir=output_dir,
        )
        diagnostics = build_production_diagnostics(
            switch_decision=decision,
            seller_id=seller_text,
            run_date=run_date,
            dry_run=dry_run,
            output_dir=output_dir,
            effective_runner="v4_daily_pipeline",
            warnings=warnings,
            rollback_hint="rollback target: legacy",
            notes=["single-run production path uses v4 only"],
            feature_flags=feature_flags,
        )
        return {
            "run_result": v4_result,
            "production": {
                "switch_decision": {
                    "selected_mode": decision.selected_mode.value,
                    "reason": decision.reason,
                    "source_of_decision": decision.source_of_decision,
                    "rollback_allowed": decision.rollback_allowed,
                    "notes": list(decision.notes),
                },
                "diagnostics": diagnostics,
                "summary": build_switch_summary(diagnostics),
            },
        }
    except Exception as exc:
        fallback_allowed = bool(
            allow_fallback_to_legacy
            and decision.rollback_allowed
            and feature_flags.get("enable_production_fallback_to_legacy", False)
        )
        rollback_possible = can_rollback(
            selected_mode=mode,
            runner_failed=True,
            fallback_allowed=fallback_allowed,
            operator_forced_mode=bool(_coerce_mode(cli_mode) is not None),
        )
        if not rollback_possible:
            note = build_rollback_note(
                selected_mode=mode,
                rollback_mode=get_rollback_mode(mode),
                reason=f"fallback denied: {exc}",
                fallback_allowed=fallback_allowed,
            )
            diagnostics = build_production_diagnostics(
                switch_decision=decision,
                seller_id=seller_text,
                run_date=run_date,
                dry_run=dry_run,
                output_dir=output_dir,
                effective_runner="v4_daily_pipeline",
                warnings=[str(exc)],
                rollback_happened=False,
                fallback_used=False,
                rollback_hint=note,
                notes=["v4 run failed and rollback was not allowed"],
                feature_flags=feature_flags,
            )
            raise RuntimeError(
                f"v4 production run failed without rollback: {exc}; diagnostics={diagnostics}"
            ) from exc

        rollback_mode = get_rollback_mode(mode)
        rollback_happened = True
        fallback_used = True
        rollback_hint = build_rollback_note(
            selected_mode=mode,
            rollback_mode=rollback_mode,
            reason=str(exc),
            fallback_allowed=fallback_allowed,
        )
        warnings.append(str(exc))
        legacy_result = _run_legacy_daily(
            seller_id=seller_text,
            run_date=run_date,
            output_dir=output_dir,
        )
        diagnostics = build_production_diagnostics(
            switch_decision=ProductionSwitchDecision(
                selected_mode=rollback_mode,
                reason="rollback fallback to legacy after v4 failure",
                source_of_decision="rollback_policy",
                rollback_allowed=decision.rollback_allowed,
                notes=list(decision.notes),
            ),
            seller_id=seller_text,
            run_date=run_date,
            dry_run=dry_run,
            output_dir=output_dir,
            effective_runner="legacy_daily_batch",
            warnings=warnings,
            rollback_happened=rollback_happened,
            fallback_used=fallback_used,
            rollback_hint=rollback_hint,
            notes=["explicit fallback to legacy executed after v4 failure"],
            feature_flags=feature_flags,
        )
        return {
            "run_result": legacy_result,
            "production": {
                "switch_decision": {
                    "selected_mode": decision.selected_mode.value,
                    "reason": decision.reason,
                    "source_of_decision": decision.source_of_decision,
                    "rollback_allowed": decision.rollback_allowed,
                    "notes": list(decision.notes),
                },
                "diagnostics": diagnostics,
                "summary": build_switch_summary(diagnostics),
            },
        }


__all__ = ["resolve_production_mode", "run_production_daily", "is_v4_enabled_for_seller"]
