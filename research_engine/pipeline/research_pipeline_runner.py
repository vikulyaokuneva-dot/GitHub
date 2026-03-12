from pathlib import Path

from research_engine.config import ResearchConfig, ResearchEngineSettings, get_settings
from research_engine.domain.contracts import ResearchContext
from research_engine.domain.models import ResearchInput, ResearchResult
from research_engine.pipeline.stages import (
    ResearchInputStage,
    ResearchMarketStage,
    ResearchOutputStage,
    ResearchScoringStage,
)


class ResearchPipelineRunner:
    def __init__(
        self,
        settings: ResearchEngineSettings | None = None,
        research_config: ResearchConfig | None = None,
        scenario_path: str | Path | None = None,
    ):
        self.settings = settings or get_settings()
        self.research_config = research_config or ResearchConfig()
        self.default_scenario_path = Path(scenario_path) if scenario_path else self.settings.default_scenario_path
        self.stages = [
            ResearchInputStage(settings=self.settings, scenario_path=self.default_scenario_path),
            ResearchMarketStage(),
            ResearchScoringStage(config=self.research_config),
            ResearchOutputStage(settings=self.settings, config=self.research_config),
        ]

    def run(
        self,
        research_input: ResearchInput | None = None,
        scenario_path: str | Path | None = None,
    ) -> ResearchResult:
        resolved_scenario = Path(scenario_path) if scenario_path else self.default_scenario_path
        context = ResearchContext(input_data=research_input, scenario_path=resolved_scenario)
        for stage in self.stages:
            context = stage.run(context)

        if context.result is None:
            raise RuntimeError("Pipeline finished without result.")
        return context.result
