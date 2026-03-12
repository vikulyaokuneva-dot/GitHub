from research_engine.builders import NicheCandidateBuilder
from research_engine.domain.contracts import CandidateSnapshots, ResearchContext
from research_engine.engines import CompetitionEngine, DemandEngine, RiskEngine, UnitEconomicsEngine


class ResearchMarketStage:
    def __init__(
        self,
        candidate_builder: NicheCandidateBuilder | None = None,
        demand_engine: DemandEngine | None = None,
        competition_engine: CompetitionEngine | None = None,
        unit_economics_engine: UnitEconomicsEngine | None = None,
        risk_engine: RiskEngine | None = None,
    ):
        self.candidate_builder = candidate_builder or NicheCandidateBuilder()
        self.demand_engine = demand_engine or DemandEngine()
        self.competition_engine = competition_engine or CompetitionEngine()
        self.unit_economics_engine = unit_economics_engine or UnitEconomicsEngine()
        self.risk_engine = risk_engine or RiskEngine()

    def run(self, context: ResearchContext) -> ResearchContext:
        if context.input_data is None:
            raise ValueError("ResearchMarketStage requires input_data from previous stage.")

        candidates = self.candidate_builder.build_seed_candidates(context.input_data)
        context.candidates = candidates
        context.snapshots_by_niche = {}

        for candidate in candidates:
            context.snapshots_by_niche[candidate.niche_id] = CandidateSnapshots(
                demand=self.demand_engine.evaluate(candidate),
                competition=self.competition_engine.evaluate(candidate),
                economics=self.unit_economics_engine.evaluate(candidate, context.input_data),
                risk=self.risk_engine.evaluate(candidate, context.input_data),
            )

        return context
