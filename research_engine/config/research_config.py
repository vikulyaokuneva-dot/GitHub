from dataclasses import dataclass


@dataclass(frozen=True)
class ResearchConfig:
    shortlist_size: int = 3
    min_candidates_required: int = 3
    default_currency: str = "RUB"
