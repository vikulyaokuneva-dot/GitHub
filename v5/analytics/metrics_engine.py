"""Metrics calculation engine"""

from ..domain import NormalizedDataBundle, MetricsBundle, CabinetContext


class MetricsEngine:
    """Calculates KPI metrics from normalized data"""
    
    def calculate(
        self,
        normalized: NormalizedDataBundle,
        historical_metrics: dict | None = None
    ) -> MetricsBundle:
        """
        Calculate metrics from normalized data.
        
        Computes:
          - CTR, CPC, ROAS
          - Efficiency scores
          - Anomaly detection
          - Portfolio-level metrics
        
        Args:
            normalized: Normalized data bundle
            historical_metrics: Previous metrics for comparison/anomaly detection
            
        Returns:
            MetricsBundle with calculated metrics
        """
        # TODO: Implement metrics calculation
        # 1. For each ad: calculate CPC, ROAS, efficiency_score
        # 2. For each SKU: calculate daily metrics, growth rate
        # 3. Detect anomalies (compare with historical data)
        # 4. Calculate portfolio-level metrics
        # 5. Return MetricsBundle
        
        raise NotImplementedError("MetricsEngine.calculate() not yet implemented")
