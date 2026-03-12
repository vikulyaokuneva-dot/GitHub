from research_engine.config import ResearchConfig
from research_engine.domain.enums import CandidateStatus
from research_engine.domain.models import ScoredNiche
from research_engine.domain.contracts import ResearchContext
from research_engine.engines import NicheScoringEngine


class ResearchScoringStage:
    def __init__(
        self,
        config: ResearchConfig,
        scoring_engine: NicheScoringEngine | None = None,
    ):
        self.config = config
        self.scoring_engine = scoring_engine or NicheScoringEngine()

    def run(self, context: ResearchContext) -> ResearchContext:
        scored_niches: list[ScoredNiche] = []

        for candidate in context.candidates:
            snapshots = context.snapshots_by_niche.get(candidate.niche_id)
            if snapshots is None:
                context.warnings.append(f"Missing snapshots for {candidate.niche_id}.")
                continue

            final_score = self.scoring_engine.calculate_final_score(
                demand=snapshots.demand,
                competition=snapshots.competition,
                economics=snapshots.economics,
                risk=snapshots.risk,
            )

            candidate.demand_score = snapshots.demand.demand_score
            candidate.competition_score = snapshots.competition.competition_score
            candidate.economics_score = snapshots.economics.economics_score
            candidate.risk_score = snapshots.risk.risk_score
            candidate.final_score = final_score
            candidate.status = CandidateStatus.ANALYZED

            scored_niches.append(
                ScoredNiche(
                    candidate=candidate,
                    demand_snapshot=snapshots.demand,
                    competition_snapshot=snapshots.competition,
                    unit_economics_snapshot=snapshots.economics,
                    risk_snapshot=snapshots.risk,
                    final_score=final_score,
                )
            )

        scored_niches.sort(key=lambda item: item.final_score, reverse=True)
        for scored in scored_niches[: self.config.shortlist_size]:
            scored.candidate.status = CandidateStatus.SHORTLISTED

        if len(scored_niches) < self.config.min_candidates_required:
            context.warnings.append("Candidates count is below configured minimum.")

        context.scored_niches = scored_niches
        return context
