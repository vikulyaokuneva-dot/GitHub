from datetime import datetime, timezone

from research_engine.domain.models import CandidatePool, ResearchInput, ResearchResult


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
        candidate_pool: CandidatePool | None,
        warnings: list[str],
        artifact_paths: dict[str, str],
    ) -> ResearchResult:
        total_candidates = candidate_pool.total_candidates if candidate_pool is not None else 0
        filtered_candidates = candidate_pool.filtered_candidates if candidate_pool is not None else 0
        return ResearchResult(
            generated_at=datetime.now(timezone.utc),
            input_summary=ResearchSummaryBuilder.build_input_summary(input_data),
            total_candidates=total_candidates,
            filtered_candidates=filtered_candidates,
            warnings=warnings,
            artifact_paths=artifact_paths,
        )
