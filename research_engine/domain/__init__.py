"""Domain models and contracts for research_engine."""

from .contracts import CandidateSnapshots, ResearchContext, ResearchStage
from .enums import CandidateStatus
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

__all__ = [
    "CandidateSnapshots",
    "CandidateStatus",
    "CompetitionSnapshot",
    "DemandSnapshot",
    "NicheCandidate",
    "ResearchContext",
    "ResearchInput",
    "ResearchJob",
    "ResearchResult",
    "ResearchStage",
    "RiskSnapshot",
    "ScoredNiche",
    "UnitEconomicsSnapshot",
]
