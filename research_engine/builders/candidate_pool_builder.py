from datetime import datetime, timezone

from research_engine.domain.models import CandidatePool, NicheRecord, ResearchInput, SubjectCandidate


class CandidatePoolBuilder:
    COMPETITION_RANK = {"low": 1, "medium": 2, "high": 3}

    def build(self, research_input: ResearchInput, niches: list[NicheRecord]) -> CandidatePool:
        preferred = {value.strip().lower() for value in research_input.preferred_categories}
        excluded = {value.strip().lower() for value in research_input.excluded_categories}
        max_competition_rank = self._competition_rank(research_input.max_competition_level)

        all_candidates: list[SubjectCandidate] = []
        filtered_candidates: list[SubjectCandidate] = []
        warnings: list[str] = []

        for niche in niches:
            candidate = self._build_candidate(niche, research_input, preferred, excluded)
            all_candidates.append(candidate)

            current_rank = self._competition_rank(candidate.competition_level)
            if not candidate.fit_price_range:
                candidate.status = "filtered_out_price"
                continue
            if not candidate.fit_category:
                candidate.status = "filtered_out_category"
                continue
            if current_rank > max_competition_rank:
                candidate.status = "filtered_out_competition"
                continue
            candidate.status = "filtered_in"
            filtered_candidates.append(candidate)

        if not filtered_candidates:
            warnings.append("No candidates matched scenario filters.")

        return CandidatePool(
            generated_at=datetime.now(timezone.utc),
            scenario_name=research_input.scenario_name,
            total_candidates=len(all_candidates),
            filtered_candidates=len(filtered_candidates),
            candidates=filtered_candidates,
            warnings=warnings,
        )

    def _build_candidate(
        self,
        niche: NicheRecord,
        research_input: ResearchInput,
        preferred: set[str],
        excluded: set[str],
    ) -> SubjectCandidate:
        category_normalized = niche.category.lower()
        fit_price_range = research_input.target_price_min <= niche.avg_price <= research_input.target_price_max
        fit_budget = niche.avg_price * 50 <= research_input.budget_total
        fit_category = category_normalized not in excluded and (
            not preferred or category_normalized in preferred
        )
        competition_level = self._competition_level(niche.competition_index)
        estimated_demand = self._demand_level(niche.monthly_orders)

        return SubjectCandidate(
            candidate_id=f"{niche.niche_id}-subject",
            subject_name=niche.title,
            niche_id=niche.niche_id,
            category=niche.category,
            subgroup=niche.subgroup,
            avg_price=niche.avg_price,
            estimated_demand=estimated_demand,
            competition_level=competition_level,
            fit_price_range=fit_price_range,
            fit_budget=fit_budget,
            fit_category=fit_category,
            notes=f"growth_rate={niche.growth_rate}%, seasonality={niche.seasonality}",
            status="new",
        )

    def _demand_level(self, monthly_orders: int) -> str:
        if monthly_orders >= 9000:
            return "high"
        if monthly_orders >= 5000:
            return "medium"
        return "low"

    def _competition_level(self, competition_index: float) -> str:
        if competition_index < 0.35:
            return "low"
        if competition_index < 0.7:
            return "medium"
        return "high"

    def _competition_rank(self, level: str) -> int:
        return self.COMPETITION_RANK.get(level.lower(), self.COMPETITION_RANK["high"])
