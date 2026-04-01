"""Facts and insights builder"""

from datetime import date
from ..domain import (
    NormalizedDataBundle,
    MetricsBundle,
    FactsBundle,
    Fact,
    Recommendation,
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
        facts = []
        recommendations = []
        
        # === ANOMALY DETECTION ===
        
        # Check for zero metrics
        if metrics.portfolio_metrics.total_spend == 0:
            facts.append(Fact(
                type=FactType.ANOMALY,
                title="No ad spend detected",
                description="Portfolio has zero ad spend",
                severity=9,
                affected_ids=[]
            ))
            recommendations.append(Recommendation(
                title="Check ad campaigns",
                description="All campaigns appear to be paused or have zero budget",
                priority=10,
                action_type="review_campaigns"
            ))
        
        if metrics.portfolio_metrics.total_revenue == 0 and len(normalized.skus) > 0:
            facts.append(Fact(
                type=FactType.ANOMALY,
                title="No revenue detected",
                description="Portfolio has no revenue",
                severity=8,
                affected_ids=[]
            ))
        
        # === OPPORTUNITY DETECTION ===
        
        # High performing SKUs
        profitable_skus = [
            sku for sku in metrics.sku_metrics
            if sku.daily_profit > 0
        ]
        
        if profitable_skus:
            top_sku = max(profitable_skus, key=lambda s: s.daily_profit)
            if top_sku.daily_profit > 0:
                facts.append(Fact(
                    type=FactType.OPPORTUNITY,
                    title=f"Top performing SKU: {top_sku.sku_id}",
                    description=f"SKU {top_sku.sku_id} generated {top_sku.daily_profit:.2f} profit",
                    severity=1,
                    affected_ids=[top_sku.sku_id]
                ))
                recommendations.append(Recommendation(
                    title=f"Scale {top_sku.sku_id}",
                    description=f"Consider increasing budget for top-performing SKU to maximize profit",
                    priority=9,
                    action_type="increase_budget"
                ))
        
        # High efficiency ads
        efficient_ads = [
            ad for ad in metrics.ad_metrics
            if ad.efficiency_score > 75
        ]
        
        if efficient_ads:
            facts.append(Fact(
                type=FactType.OPPORTUNITY,
                title=f"{len(efficient_ads)} highly efficient ads",
                description=f"Found {len(efficient_ads)} ads with efficiency score > 75%",
                severity=2,
                affected_ids=[ad.ad_id for ad in efficient_ads]
            ))
        
        # === RISK DETECTION ===
        
        # Low CTR ads
        low_ctr_ads = [
            ad for ad in metrics.ad_metrics
            if 0 < ad.ctr < 0.5
        ]
        
        if low_ctr_ads:
            facts.append(Fact(
                type=FactType.RISK,
                title=f"{len(low_ctr_ads)} low CTR ads",
                description=f"{len(low_ctr_ads)} ads have CTR < 0.5%",
                severity=5,
                affected_ids=[ad.ad_id for ad in low_ctr_ads]
            ))
            recommendations.append(Recommendation(
                title="Optimize low-CTR ads",
                description="Review ad copy, targeting, and creative for low-CTR ads",
                priority=6,
                action_type="optimize_ad_copy"
            ))
        
        # High CPC
        high_cpc_ads = [
            ad for ad in metrics.ad_metrics
            if ad.cpc > 50  # Arbitrary threshold
        ]
        
        if high_cpc_ads:
            facts.append(Fact(
                type=FactType.RISK,
                title=f"{len(high_cpc_ads)} ads with high CPC",
                description=f"{len(high_cpc_ads)} ads have CPC > 50",
                severity=4,
                affected_ids=[ad.ad_id for ad in high_cpc_ads]
            ))
        
        # Low rating SKUs
        low_rating_skus = [
            sku for sku in metrics.sku_metrics
            if sku.rating > 0 and sku.rating < 4.0  # Assuming 5-star system
        ]
        
        if low_rating_skus:
            facts.append(Fact(
                type=FactType.RISK,
                title=f"{len(low_rating_skus)} low-rated SKUs",
                description=f"{len(low_rating_skus)} SKUs have rating < 4.0",
                severity=6,
                affected_ids=[sku.sku_id for sku in low_rating_skus]
            ))
            recommendations.append(Recommendation(
                title="Improve product quality",
                description="Address quality issues in low-rated products",
                priority=7,
                action_type="improve_quality"
            ))
        
        # === TREND DETECTION ===
        
        # High return rate
        high_return_skus = [
            sku for sku in metrics.sku_metrics
            if sku.negative_review_rate > 0.1  # > 10%
        ]
        
        if high_return_skus:
            facts.append(Fact(
                type=FactType.TREND,
                title=f"High return rate detected",
                description=f"{len(high_return_skus)} SKUs have elevated return rates",
                severity=6,
                affected_ids=[sku.sku_id for sku in high_return_skus]
            ))
        
        return FactsBundle(
            cabinet_id=normalized.cabinet_id,
            period_date=normalized.period_date,
            facts=facts,
            recommendations=recommendations
        )
