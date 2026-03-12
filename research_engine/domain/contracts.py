from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .models import (
    CandidatePool,
    NicheRecord,
    ResearchInput,
    ResearchJob,
    ResearchResult,
)


@dataclass
class ResearchContext:
    input_data: ResearchInput | None = None
    scenario_path: Path | None = None
    job: ResearchJob | None = None
    niche_universe: list[NicheRecord] = field(default_factory=list)
    candidate_pool: CandidatePool | None = None
    result: ResearchResult | None = None
    warnings: list[str] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)


class ResearchStage(Protocol):
    def run(self, context: ResearchContext) -> ResearchContext:
        """Process current context and return the updated context."""
