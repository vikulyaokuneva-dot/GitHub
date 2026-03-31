"""Facts and insights builder"""

from domain import (
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
        # TODO: Implement facts generation
        # 1. Compare current metrics with historical data
        # 2. Detect opportunities (high ROAS, low CPC)
        # 3. Detect risks (declining CTR, rising CPC)
        # 4. Detect anomalies (check config thresholds)
        # 5. Identify trends (growth/decline over time)
        # 6. Return FactsBundle
        
        raise NotImplementedError("FactsBuilder.build() not yet implemented")
