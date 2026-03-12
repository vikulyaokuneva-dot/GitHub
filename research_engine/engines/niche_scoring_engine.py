from research_engine.domain.models import (
    CompetitionSnapshot,
    DemandSnapshot,
    RiskSnapshot,
    UnitEconomicsSnapshot,
)


class NicheScoringEngine:
    def calculate_final_score(
        self,
        demand: DemandSnapshot,
        competition: CompetitionSnapshot,
        economics: UnitEconomicsSnapshot,
        risk: RiskSnapshot,
    ) -> float:
        final_score = (
            demand.demand_score * 0.35
            + competition.competition_score * 0.25
            + economics.economics_score * 0.25
            + risk.risk_score * 0.15
        )
        return round(final_score, 2)
