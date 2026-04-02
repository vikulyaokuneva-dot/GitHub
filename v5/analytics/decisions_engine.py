"""Decisions and recommendations engine"""

from ..domain import FactsBundle, Recommendation, CabinetConfig


class DecisionsEngine:
    """Generates actionable recommendations from facts"""
    
    def __init__(self, config: CabinetConfig):
        self.config = config
    
    def generate_recommendations(self, facts: FactsBundle) -> list[Recommendation]:
        """
        Generate actionable recommendations.
        
        Examples:
          - "Increase budget for ad_123 (OPPORTUNITY: high ROAS)"
          - "Reduce bid for ad_456 (RISK: declining CTR)"
          - "Investigate ad_789 (ANOMALY detected)"
        
        Args:
            facts: Facts bundle with insights
            
        Returns:
            List of recommendations with priority
        """
        recommendations: list[Recommendation] = []

        for fact in facts.facts:
            action_type = "investigate"
            if fact.type.value == "opportunity":
                action_type = "scale"
            elif fact.type.value == "risk":
                action_type = "mitigate"
            elif fact.type.value == "anomaly":
                action_type = "investigate"
            elif fact.type.value == "trend":
                action_type = "monitor"

            recommendations.append(
                Recommendation(
                    title=f"Action: {fact.title}",
                    description=fact.description,
                    priority=max(1, min(10, int(fact.severity))),
                    action_type=action_type,
                )
            )

        return recommendations
