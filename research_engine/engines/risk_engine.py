from research_engine.domain.models import NicheCandidate, ResearchInput, RiskSnapshot


class RiskEngine:
    def evaluate(self, candidate: NicheCandidate, input_data: ResearchInput) -> RiskSnapshot:
        base_return_rate = 6.0 + (len(candidate.keyword) % 5)
        category_penalty = 2.0 if candidate.category in input_data.excluded_categories else 0.0
        return_rate_pct = base_return_rate + category_penalty
        compliance_risk_level = "high" if return_rate_pct >= 10 else "medium" if return_rate_pct >= 8 else "low"
        risk_score = max(0.0, 100.0 - return_rate_pct * 8.5)
        return RiskSnapshot(
            niche_id=candidate.niche_id,
            return_rate_pct=round(return_rate_pct, 2),
            compliance_risk_level=compliance_risk_level,
            risk_score=round(risk_score, 2),
        )
