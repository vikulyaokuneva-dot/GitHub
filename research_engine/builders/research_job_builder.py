from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

from research_engine.domain.models import ResearchInput, ResearchJob


class ResearchJobBuilder:
    @staticmethod
    def build_default_input() -> ResearchInput:
        return ResearchInput(
            budget_total=300000.0,
            target_price_min=900.0,
            target_price_max=3200.0,
            target_margin_pct=28.0,
            excluded_categories=["fragile"],
            preferred_categories=["home", "beauty", "kids"],
            notes="Default bootstrap input for local smoke runs.",
        )

    @staticmethod
    def build_job(input_data: ResearchInput) -> ResearchJob:
        return ResearchJob(
            job_id=f"research-{uuid4().hex[:10]}",
            created_at=datetime.now(timezone.utc),
            input_data=replace(input_data),
        )
