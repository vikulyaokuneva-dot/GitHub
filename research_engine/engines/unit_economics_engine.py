from research_engine.domain.models import NicheCandidate, ResearchInput, UnitEconomicsSnapshot


class UnitEconomicsEngine:
    def evaluate(self, candidate: NicheCandidate, input_data: ResearchInput) -> UnitEconomicsSnapshot:
        estimated_cogs = candidate.avg_price * 0.52
        estimated_margin_pct = ((candidate.avg_price - estimated_cogs) / candidate.avg_price) * 100.0
        margin_gap = abs(estimated_margin_pct - input_data.target_margin_pct)
        economics_score = max(0.0, 100.0 - margin_gap * 3.2)
        return UnitEconomicsSnapshot(
            niche_id=candidate.niche_id,
            estimated_cogs=round(estimated_cogs, 2),
            estimated_margin_pct=round(estimated_margin_pct, 2),
            economics_score=round(economics_score, 2),
        )
