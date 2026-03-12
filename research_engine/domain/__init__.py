"""Domain models and contracts for research_engine."""

from .contracts import ResearchContext, ResearchStage
from .enums import CandidateStatus
from .models import (
    CandidatePool,
    CompetitionSnapshot,
    DemandSnapshot,
    NicheRecord,
    NicheCandidate,
    ResearchInput,
    ResearchJob,
    ResearchResult,
    RiskSnapshot,
    ScoredNiche,
    SubjectCandidate,
    UnitEconomicsSnapshot,
)

__all__ = [
    "CandidatePool",
    "CandidateStatus",
    "CompetitionSnapshot",
    "DemandSnapshot",
    "NicheRecord",
    "NicheCandidate",
    "ResearchContext",
    "ResearchInput",
    "ResearchJob",
    "ResearchResult",
    "ResearchStage",
    "RiskSnapshot",
    "ScoredNiche",
    "SubjectCandidate",
    "UnitEconomicsSnapshot",
]
