"""Contracts for controlled production switch and rollback diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ProductionMode(str, Enum):
    LEGACY = "legacy"
    V4 = "v4"
    SHADOW = "shadow"


@dataclass(frozen=True)
class ProductionSwitchDecision:
    selected_mode: ProductionMode
    reason: str
    source_of_decision: str
    rollback_allowed: bool
    notes: list[str] = field(default_factory=list)


@dataclass
class ProductionRunDiagnostics:
    selected_mode: str
    effective_runner: str
    seller_id: str
    run_date: str | None
    output_dir_label: str | None
    warnings: list[str] = field(default_factory=list)
    rollback_hint: str | None = None
    shadow_reference: str | None = None
    switch_reason: str | None = None
    source_of_decision: str | None = None
    rollback_happened: bool = False
    fallback_used: bool = False
    notes: list[str] = field(default_factory=list)
    feature_flags: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_mode": self.selected_mode,
            "effective_runner": self.effective_runner,
            "seller_id": self.seller_id,
            "run_date": self.run_date,
            "output_dir_label": self.output_dir_label,
            "warnings": list(self.warnings),
            "rollback_hint": self.rollback_hint,
            "shadow_reference": self.shadow_reference,
            "switch_reason": self.switch_reason,
            "source_of_decision": self.source_of_decision,
            "rollback_happened": bool(self.rollback_happened),
            "fallback_used": bool(self.fallback_used),
            "notes": list(self.notes),
            "feature_flags": dict(self.feature_flags),
        }


__all__ = ["ProductionMode", "ProductionSwitchDecision", "ProductionRunDiagnostics"]

