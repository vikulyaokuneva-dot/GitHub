"""Production switch diagnostics builders."""

from __future__ import annotations

from typing import Any

from ..cabinets.paths import path_label
from .contracts import ProductionRunDiagnostics, ProductionSwitchDecision


def build_production_diagnostics(
    *,
    switch_decision: ProductionSwitchDecision,
    seller_id: str,
    run_date: str | None,
    output_dir: str | None,
    effective_runner: str,
    warnings: list[str] | None = None,
    rollback_happened: bool = False,
    fallback_used: bool = False,
    rollback_hint: str | None = None,
    shadow_reference: str | None = None,
    notes: list[str] | None = None,
    feature_flags: dict[str, bool] | None = None,
) -> dict[str, Any]:
    diagnostics = ProductionRunDiagnostics(
        selected_mode=switch_decision.selected_mode.value,
        effective_runner=effective_runner,
        seller_id=str(seller_id),
        run_date=str(run_date) if run_date is not None else None,
        output_dir_label=path_label(output_dir),
        warnings=list(warnings or []),
        rollback_hint=rollback_hint,
        shadow_reference=shadow_reference,
        switch_reason=switch_decision.reason,
        source_of_decision=switch_decision.source_of_decision,
        rollback_happened=bool(rollback_happened),
        fallback_used=bool(fallback_used),
        notes=list(notes or list(switch_decision.notes)),
        feature_flags=dict(feature_flags or {}),
    )
    return diagnostics.to_dict()


def build_switch_summary(production_diagnostics: dict[str, Any]) -> dict[str, Any]:
    payload = dict(production_diagnostics or {})
    return {
        "selected_mode": payload.get("selected_mode"),
        "effective_runner": payload.get("effective_runner"),
        "seller_id": payload.get("seller_id"),
        "run_date": payload.get("run_date"),
        "output_dir_label": payload.get("output_dir_label"),
        "rollback_happened": bool(payload.get("rollback_happened", False)),
        "fallback_used": bool(payload.get("fallback_used", False)),
        "warnings_count": len(payload.get("warnings", [])) if isinstance(payload.get("warnings"), list) else 0,
    }


__all__ = ["build_production_diagnostics", "build_switch_summary"]

