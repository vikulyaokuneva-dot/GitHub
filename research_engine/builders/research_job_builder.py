from datetime import datetime, timezone
from uuid import uuid4

from research_engine.domain.models import ResearchInput, ResearchJob


class ResearchJobBuilder:
    @staticmethod
    def build_job(input_data: ResearchInput) -> ResearchJob:
        return ResearchJob(
            job_id=f"research-{uuid4().hex[:10]}",
            scenario_name=input_data.scenario_name,
            created_at=datetime.now(timezone.utc),
            input_summary={
                "scenario_name": input_data.scenario_name,
                "budget_total": input_data.budget_total,
                "target_price_min": input_data.target_price_min,
                "target_price_max": input_data.target_price_max,
                "target_margin_pct": input_data.target_margin_pct,
                "preferred_categories": input_data.preferred_categories,
                "excluded_categories": input_data.excluded_categories,
                "max_competition_level": input_data.max_competition_level,
            },
        )
