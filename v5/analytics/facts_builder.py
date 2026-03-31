"""Facts and insights builder"""

from ..domain import (
    NormalizedDataBundle,
    MetricsBundle,
    FactsBundle,
    Fact,
    FactType,
    CabinetConfig,
)


class FactsBuilder:
    """Generates insights and facts from metrics"""
    
    def __init__(self, config: CabinetConfig):
        self.config = config
    
    def build(
        self,
        normalized: NormalizedDataBundle,
        metrics: MetricsBundle,
        historical_metrics: list[MetricsBundle] | None = None
    ) -> FactsBundle:
        """
        Generate facts and insights.
        
        Detects:
          - OPPORTUNITY: High ROAS, low CPC
          - RISK: Declining CTR, rising CPC
          - ANOMALY: Unexpected changes in data
          - TREND: Long-term patterns
        
        Args:
            normalized: Normalized data
            metrics: Calculated metrics
            historical_metrics: Previous metrics (last 30 days)
            
        Returns:
            FactsBundle with facts and recommendations
        """
        # Basic implementation - return empty bundle with defaults
        # TODO: Full implementation with actual facts generation
        
        facts = []
        
        # Example: Basic anomaly detection (can be extended later)
        if metrics.portfolio_metrics.get("ctr", 0) == 0:
            facts.append(Fact(
                type=FactType.ANOMALY,
                title="No clicks detected",
                description="Portfolio has no clicks today",
                severity=1,
                impact_area="general"
            ))
        
        return FactsBundle(
            date=metrics.date,
            facts=facts,
            total_facts=len(facts),
            opportunities_count=0,
            risks_count=0,
            anomalies_count=len([f for f in facts if f.type == FactType.ANOMALY]),
            metadata={"generated": True}
        )
