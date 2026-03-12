from datetime import datetime, timezone

from research_engine.domain.models import ResearchInput, ResearchResult, ScoredNiche


class ResearchSummaryBuilder:
    @staticmethod
    def build_input_summary(input_data: ResearchInput) -> dict[str, object]:
        return {
            "scenario_name": input_data.scenario_name,
            "budget_total": input_data.budget_total,
            "target_price_min": input_data.target_price_min,
            "target_price_max": input_data.target_price_max,
            "target_margin_pct": input_data.target_margin_pct,
            "preferred_categories": input_data.preferred_categories,
            "excluded_categories": input_data.excluded_categories,
            "max_competition_level": input_data.max_competition_level,
            "notes": input_data.notes,
        }

    @staticmethod
    def build_result(
        input_data: ResearchInput,
        scored_niches: list[ScoredNiche],
        shortlist_size: int,
        warnings: list[str],
        artifact_paths: dict[str, str],
    ) -> ResearchResult:
        shortlist = scored_niches[:shortlist_size]
        return ResearchResult(
            generated_at=datetime.now(timezone.utc),
            input_summary=ResearchSummaryBuilder.build_input_summary(input_data),
            candidates_count=len(scored_niches),
            shortlisted_count=len(shortlist),
            shortlist=shortlist,
            warnings=warnings,
            artifact_paths=artifact_paths,
        )
