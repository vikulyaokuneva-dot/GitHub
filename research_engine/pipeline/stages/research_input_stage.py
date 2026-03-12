from research_engine.builders import ResearchJobBuilder
from research_engine.domain.contracts import ResearchContext
from research_engine.domain.models import ResearchInput


class ResearchInputStage:
    def __init__(self, job_builder: ResearchJobBuilder | None = None):
        self.job_builder = job_builder or ResearchJobBuilder()

    def run(self, context: ResearchContext) -> ResearchContext:
        input_data = context.input_data or self.job_builder.build_default_input()
        if not isinstance(input_data, ResearchInput):
            raise TypeError("ResearchInputStage expects context.input_data to be a ResearchInput instance.")
        context.input_data = input_data
        context.job = self.job_builder.build_job(input_data)
        return context
