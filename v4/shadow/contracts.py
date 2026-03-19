"""Contracts for v4 shadow-mode orchestration/comparison."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ShadowDifference:
    metric: str
    v4_value: Any
    legacy_value: Any
    severity: str = "low"
    note: str | None = None


@dataclass
class ShadowComparison:
    differences: list[ShadowDifference] = field(default_factory=list)
    severity: str = "low"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "differences": [
                {
                    "metric": item.metric,
                    "v4_value": item.v4_value,
                    "legacy_value": item.legacy_value,
                    "severity": item.severity,
                    "note": item.note,
                }
                for item in self.differences
            ],
            "severity": self.severity,
            "notes": list(self.notes),
        }


@dataclass
class ShadowRunDiagnostics:
    run_v4: bool
    run_legacy: bool
    output_root: str
    output_labels: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_v4": bool(self.run_v4),
            "run_legacy": bool(self.run_legacy),
            "output_root": self.output_root,
            "output_labels": dict(self.output_labels),
            "warnings": list(self.warnings),
        }


__all__ = ["ShadowDifference", "ShadowComparison", "ShadowRunDiagnostics"]

