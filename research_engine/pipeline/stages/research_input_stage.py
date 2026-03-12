from pathlib import Path

from research_engine.builders import ResearchJobBuilder
from research_engine.config import ResearchEngineSettings, ResearchInputLoader
from research_engine.domain.contracts import ResearchContext
from research_engine.domain.models import ResearchInput


class ResearchInputStage:
    def __init__(
        self,
        settings: ResearchEngineSettings,
        scenario_path: Path | None = None,
        input_loader: ResearchInputLoader | None = None,
        job_builder: ResearchJobBuilder | None = None,
    ):
        self.settings = settings
        self.scenario_path = Path(scenario_path) if scenario_path else settings.default_scenario_path
        self.input_loader = input_loader or ResearchInputLoader()
        self.job_builder = job_builder or ResearchJobBuilder()

    def run(self, context: ResearchContext) -> ResearchContext:
        input_data = context.input_data
        if input_data is None:
            input_data = self.input_loader.load(context.scenario_path or self.scenario_path)
        else:
            self.input_loader.validate(input_data)

        if not isinstance(input_data, ResearchInput):
            raise TypeError("ResearchInputStage expects context.input_data to be a ResearchInput instance.")

        context.input_data = input_data
        context.job = self.job_builder.build_job(input_data)
        return context
