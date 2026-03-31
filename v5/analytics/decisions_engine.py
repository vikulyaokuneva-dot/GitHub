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
        # Basic implementation - convert facts to recommendations
        # TODO: Full implementation with more sophisticated rules
        
        recommendations = []
        
        # Example: Create recommendation for each fact
        for fact in facts.facts:
            rec = Recommendation(
                id=f"rec_{fact.type.value}_{len(recommendations)}",
                title=f"Action: {fact.title}",
                description=fact.description,
                priority=fact.severity,
                recommendation_type=fact.type.value,
                action="investigate",
                impact_area=fact.impact_area
            )
            recommendations.append(rec)
        
        return recommendations
