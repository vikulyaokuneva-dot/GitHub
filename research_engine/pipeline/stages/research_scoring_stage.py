from research_engine.domain.contracts import ResearchContext


class ResearchScoringStage:
    def __init__(self) -> None:
        pass

    def run(self, context: ResearchContext) -> ResearchContext:
        if context.candidate_pool is None:
            context.warnings.append("Candidate pool is missing before scoring stage.")
        return context
