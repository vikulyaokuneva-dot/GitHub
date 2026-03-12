from research_engine.builders import CandidatePoolBuilder
from research_engine.domain.contracts import ResearchContext
from research_engine.engines import NicheUniverseEngine


class ResearchMarketStage:
    def __init__(
        self,
        niche_universe_engine: NicheUniverseEngine | None = None,
        candidate_pool_builder: CandidatePoolBuilder | None = None,
    ):
        self.niche_universe_engine = niche_universe_engine or NicheUniverseEngine()
        self.candidate_pool_builder = candidate_pool_builder or CandidatePoolBuilder()

    def run(self, context: ResearchContext) -> ResearchContext:
        if context.input_data is None:
            raise ValueError("ResearchMarketStage requires input_data from previous stage.")

        context.niche_universe = self.niche_universe_engine.get_stub_universe()
        context.candidate_pool = self.candidate_pool_builder.build(
            research_input=context.input_data,
            niches=context.niche_universe,
        )
        context.warnings.extend(context.candidate_pool.warnings)

        return context
