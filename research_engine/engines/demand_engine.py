from research_engine.domain.models import DemandSnapshot, NicheCandidate


class DemandEngine:
    def evaluate(self, candidate: NicheCandidate) -> DemandSnapshot:
        monthly_searches = 2000 + len(candidate.keyword) * 180
        growth_pct = 4.0 + (len(candidate.title) % 6) * 1.5
        demand_score = min(100.0, monthly_searches / 70.0 + growth_pct * 2.5)
        return DemandSnapshot(
            niche_id=candidate.niche_id,
            monthly_searches=monthly_searches,
            growth_pct=round(growth_pct, 2),
            demand_score=round(demand_score, 2),
        )
