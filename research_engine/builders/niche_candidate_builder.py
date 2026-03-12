from research_engine.domain.models import NicheCandidate, ResearchInput


class NicheCandidateBuilder:
    @staticmethod
    def build_seed_candidates(input_data: ResearchInput) -> list[NicheCandidate]:
        mid_price = (input_data.target_price_min + input_data.target_price_max) / 2.0
        return [
            NicheCandidate(
                niche_id="niche-001",
                title="Compact organizer set",
                keyword="organizer set",
                category="home",
                avg_price=mid_price * 0.9,
            ),
            NicheCandidate(
                niche_id="niche-002",
                title="Silicone feeding kit",
                keyword="feeding kit",
                category="kids",
                avg_price=mid_price * 0.8,
            ),
            NicheCandidate(
                niche_id="niche-003",
                title="Hair styling brush",
                keyword="hair styling brush",
                category="beauty",
                avg_price=mid_price * 1.1,
            ),
            NicheCandidate(
                niche_id="niche-004",
                title="Travel bottle set",
                keyword="travel bottles",
                category="beauty",
                avg_price=mid_price * 0.7,
            ),
            NicheCandidate(
                niche_id="niche-005",
                title="Drawer divider blocks",
                keyword="drawer divider",
                category="home",
                avg_price=mid_price * 0.95,
            ),
        ]
