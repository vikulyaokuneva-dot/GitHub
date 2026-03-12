from research_engine.builders import ResearchSummaryBuilder
from research_engine.config import ResearchConfig, ResearchEngineSettings
from research_engine.domain.contracts import ResearchContext
from research_engine.outputs import ArtifactWriter, ReportWriter


class ResearchOutputStage:
    def __init__(self, settings: ResearchEngineSettings, config: ResearchConfig):
        self.settings = settings
        self.config = config
        self.artifact_writer = ArtifactWriter(settings.artifacts_dir)
        self.report_writer = ReportWriter(settings.artifacts_dir)

    def run(self, context: ResearchContext) -> ResearchContext:
        if context.input_data is None:
            raise ValueError("ResearchOutputStage requires input_data from previous stages.")

        result = ResearchSummaryBuilder.build_result(
            input_data=context.input_data,
            candidate_pool=context.candidate_pool,
            warnings=context.warnings,
            artifact_paths=context.artifacts,
        )
        context.result = result

        context.artifacts = self.artifact_writer.write_research_artifacts(context)
        context.result.artifact_paths = context.artifacts
        context.artifacts["research_report"] = self.report_writer.write_text_report(context.result)
        return context
