from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .models import (
    CompetitionSnapshot,
    DemandSnapshot,
    NicheCandidate,
    ResearchInput,
    ResearchJob,
    ResearchResult,
    RiskSnapshot,
    ScoredNiche,
    UnitEconomicsSnapshot,
)


@dataclass
class CandidateSnapshots:
    demand: DemandSnapshot
    competition: CompetitionSnapshot
    economics: UnitEconomicsSnapshot
    risk: RiskSnapshot


@dataclass
class ResearchContext:
    input_data: ResearchInput | None = None
    scenario_path: Path | None = None
    job: ResearchJob | None = None
    candidates: list[NicheCandidate] = field(default_factory=list)
    snapshots_by_niche: dict[str, CandidateSnapshots] = field(default_factory=dict)
    scored_niches: list[ScoredNiche] = field(default_factory=list)
    result: ResearchResult | None = None
    warnings: list[str] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)


class ResearchStage(Protocol):
    def run(self, context: ResearchContext) -> ResearchContext:
        """Process current context and return the updated context."""
