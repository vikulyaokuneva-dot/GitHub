from research_engine.domain.models import CompetitionSnapshot, NicheCandidate


class CompetitionEngine:
    def evaluate(self, candidate: NicheCandidate) -> CompetitionSnapshot:
        competitor_count = 20 + len(candidate.category) * 4 + len(candidate.keyword) % 9
        concentration_index = min(1.0, 0.35 + (competitor_count / 140.0))
        competition_score = max(0.0, 100.0 - competitor_count * 1.4 - concentration_index * 25.0)
        return CompetitionSnapshot(
            niche_id=candidate.niche_id,
            competitor_count=competitor_count,
            concentration_index=round(concentration_index, 2),
            competition_score=round(competition_score, 2),
        )
