from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .enums import CandidateStatus


@dataclass
class ResearchInput:
    budget_total: float
    target_price_min: float
    target_price_max: float
    target_margin_pct: float
    excluded_categories: list[str] = field(default_factory=list)
    preferred_categories: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class ResearchJob:
    job_id: str
    created_at: datetime
    input_data: ResearchInput
    status: str = "created"


@dataclass
class NicheCandidate:
    niche_id: str
    title: str
    keyword: str
    category: str
    avg_price: float
    demand_score: float = 0.0
    competition_score: float = 0.0
    economics_score: float = 0.0
    risk_score: float = 0.0
    final_score: float = 0.0
    status: CandidateStatus = CandidateStatus.NEW


@dataclass
class DemandSnapshot:
    niche_id: str
    monthly_searches: int
    growth_pct: float
    demand_score: float


@dataclass
class CompetitionSnapshot:
    niche_id: str
    competitor_count: int
    concentration_index: float
    competition_score: float


@dataclass
class UnitEconomicsSnapshot:
    niche_id: str
    estimated_cogs: float
    estimated_margin_pct: float
    economics_score: float


@dataclass
class RiskSnapshot:
    niche_id: str
    return_rate_pct: float
    compliance_risk_level: str
    risk_score: float


@dataclass
class ScoredNiche:
    candidate: NicheCandidate
    demand_snapshot: DemandSnapshot
    competition_snapshot: CompetitionSnapshot
    unit_economics_snapshot: UnitEconomicsSnapshot
    risk_snapshot: RiskSnapshot
    final_score: float


@dataclass
class ResearchResult:
    generated_at: datetime
    input_summary: dict[str, Any]
    candidates_count: int
    shortlisted_count: int
    shortlist: list[ScoredNiche] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    artifact_paths: dict[str, str] = field(default_factory=dict)
