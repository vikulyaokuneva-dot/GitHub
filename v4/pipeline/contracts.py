"""Pipeline-level contracts.

Input: stage outputs from the orchestrated daily pipeline.
Output: typed run result between entrypoint and callers.
Does not contain KPI business logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core.contracts import DecisionsBundle, FactsBundle, MetricsBundle, RunContext


@dataclass
class PipelineRunResult:
    """Internal final contract of the orchestrated pipeline."""

    run_context: RunContext
    diagnostics: dict[str, Any] = field(default_factory=dict)
    metrics_bundle: MetricsBundle | None = None
    facts_bundle: FactsBundle | None = None
    decisions_bundle: DecisionsBundle | None = None
    outputs: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Compatibility dict representation requested by runtime callers."""

        return {
            "run_context": self.run_context,
            "diagnostics": dict(self.diagnostics),
            "metrics": self.metrics_bundle,
            "facts": self.facts_bundle,
            "decisions": self.decisions_bundle,
            "outputs": self.outputs,
            "warnings": list(self.warnings),
        }


@dataclass
class MultiCabinetRunResult:
    """Batch orchestration result for multi-cabinet runs."""

    mode: str
    requested_seller_ids: list[str] = field(default_factory=list)
    succeeded_sellers: list[str] = field(default_factory=list)
    partial_sellers: list[str] = field(default_factory=list)
    failed_sellers: list[str] = field(default_factory=list)
    output_dirs: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    results: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "requested_seller_ids": list(self.requested_seller_ids),
            "succeeded_sellers": list(self.succeeded_sellers),
            "partial_sellers": list(self.partial_sellers),
            "failed_sellers": list(self.failed_sellers),
            "output_dirs": dict(self.output_dirs),
            "warnings": list(self.warnings),
            "results": dict(self.results),
        }
