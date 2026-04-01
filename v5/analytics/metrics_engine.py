"""Metrics calculation engine"""

from datetime import date
from ..domain import (
    RawDataBundle,
    NormalizedDataBundle,
    MetricsBundle,
    AdMetrics,
    SKUMetrics,
    PortfolioMetrics,
    CabinetContext,
)
from .financial_summary import aggregate_financial_summary


class MetricsEngine:
    """Calculates KPI metrics from normalized data"""
    
    def calculate(
        self,
        normalized: NormalizedDataBundle,
        historical_metrics: dict | None = None,
        raw_bundle: RawDataBundle | None = None,
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
            raw_bundle: Optional raw bundle for finance-aware aggregation
            
        Returns:
            MetricsBundle with calculated metrics
        """
        # Calculate ad metrics
        ad_metrics = self._calculate_ad_metrics(normalized.ads)
        
        # Calculate SKU metrics
        sku_metrics = self._calculate_sku_metrics(normalized.skus)

        financial_summary = {}
        if raw_bundle is not None:
            loader_debug = {}
            if isinstance(raw_bundle.debug, dict):
                loader_debug = raw_bundle.debug.get("finance_loader") or {}
            financial_summary = aggregate_financial_summary(
                orders=raw_bundle.orders,
                margins=raw_bundle.margins,
                tax_rate=0.06,
                loader_debug=loader_debug if isinstance(loader_debug, dict) else {},
            )
        
        # Calculate portfolio metrics
        portfolio_metrics = self._calculate_portfolio_metrics(
            normalized.ads,
            normalized.skus,
            ad_metrics,
            sku_metrics,
            financial_summary=financial_summary,
        )
        
        return MetricsBundle(
            cabinet_id=normalized.cabinet_id,
            period_date=normalized.period_date,
            ad_metrics=ad_metrics,
            sku_metrics=sku_metrics,
            portfolio_metrics=portfolio_metrics,
            financial_summary=financial_summary,
        )
    
    def _calculate_ad_metrics(self, ads) -> list[AdMetrics]:
        """Calculate metrics for each ad"""
        metrics = []
        
        for ad in ads:
            # CTR: already calculated in normalization
            ctr = ad.ctr
            
            # CPC: Cost Per Click
            cpc = (ad.spend / ad.clicks) if ad.clicks > 0 else 0.0
            
            # TODO: ROAS requires revenue data linked to ads
            # For now, basic estimation
            roas = 0.0  # Will be calculated when linking ads to orders
            
            # Efficiency score (0-100)
            efficiency_score = self._calculate_efficiency_score(ctr, cpc)
            
            # Anomaly detection
            has_anomaly = False
            anomaly_severity = 0
            if ctr > 10:  # Very high CTR could be anomaly
                has_anomaly = True
                anomaly_severity = 3
            elif ctr < 0.1 and ad.clicks > 0:  # Very low CTR despite clicks
                has_anomaly = True
                anomaly_severity = 5
            
            metrics.append(AdMetrics(
                ad_id=ad.ad_id,
                ctr=ctr,
                cpc=cpc,
                roas=roas,
                efficiency_score=efficiency_score,
                has_anomaly=has_anomaly,
                anomaly_severity=anomaly_severity
            ))
        
        return metrics
    
    def _calculate_sku_metrics(self, skus) -> list[SKUMetrics]:
        """Calculate metrics for each SKU"""
        metrics = []
        
        for sku in skus:
            # Daily averages (assuming period is 1 day for now)
            daily_orders = float(sku.orders)
            daily_revenue = sku.revenue
            daily_profit = sku.profit
            
            # Growth rate (comparison with historical data)
            # TODO: Implement when we have historical data
            growth_rate = 0.0
            
            # Negative review rate
            negative_review_rate = 0.0  # Would need separate data on negative reviews
            
            metrics.append(SKUMetrics(
                sku_id=sku.sku_id,
                daily_orders=daily_orders,
                daily_revenue=daily_revenue,
                daily_profit=daily_profit,
                margin_percent=sku.margin_percent,
                growth_rate=growth_rate,
                rating=sku.rating,
                negative_review_rate=negative_review_rate
            ))
        
        return metrics
    
    def _calculate_portfolio_metrics(
        self,
        ads,
        skus,
        ad_metrics,
        sku_metrics,
        financial_summary: dict | None = None,
    ) -> PortfolioMetrics:
        """Calculate portfolio-level metrics"""
        # Portfolio totals
        total_spend = sum(ad.spend for ad in ads)
        total_revenue = sum(sku.revenue for sku in skus)
        total_profit = sum(sku.profit for sku in skus)

        fin = financial_summary if isinstance(financial_summary, dict) else {}
        if fin and int(fin.get("rows_count", 0) or 0) > 0:
            total_revenue = float(fin.get("gross_revenue", total_revenue) or total_revenue)
            total_profit = float(fin.get("profit", total_profit) or total_profit)
        
        # Aggregate order counts from SKU metrics
        daily_orders_count = sum(int(sku.orders) for sku in skus)
        daily_buyouts_count = daily_orders_count  # Assuming buyouts = orders for now
        if fin:
            daily_buyouts_count = int(fin.get("sales_qty", daily_buyouts_count) or daily_buyouts_count)
            daily_orders_count = int(fin.get("sales_qty", daily_orders_count) or daily_orders_count)
        
        # Portfolio averages
        total_clicks = sum(ad.clicks for ad in ads)
        total_impressions = sum(ad.impressions for ad in ads)
        
        # Average metrics
        avg_ctr = (
            (sum(ad.ctr for ad in ads) / len(ads))
            if ads else 0.0
        )
        
        avg_cpc = (
            (total_spend / total_clicks)
            if total_clicks > 0 else 0.0
        )
        
        avg_roas = (
            (total_revenue / total_spend)
            if total_spend > 0 else 0.0
        )
        
        # Efficiency score
        portfolio_efficiency_score = self._calculate_efficiency_score(
            avg_ctr,
            avg_cpc,
            is_portfolio=True
        )
        
        return PortfolioMetrics(
            total_spend=total_spend,
            total_revenue=total_revenue,
            total_profit=total_profit,
            avg_roas=avg_roas,
            avg_cpc=avg_cpc,
            avg_ctr=avg_ctr,
            portfolio_efficiency_score=portfolio_efficiency_score,
            daily_orders_count=daily_orders_count,
            daily_buyouts_count=daily_buyouts_count,
            orders_count_confirmed=True,  # Data from file source
            financial_summary=fin,
        )
    
    def _calculate_efficiency_score(
        self,
        ctr: float,
        cpc: float = 0.0,
        is_portfolio: bool = False
    ) -> float:
        """
        Calculate efficiency score (0-100).
        
        Higher CTR is better (max 5% = 100 points)
        Lower CPC is better (baseline varies by category)
        """
        # CTR component (0-50 points)
        ctr_score = min(50, (ctr / 5) * 50)  # Max 5% CTR = 50 points
        
        # CPC component (depends on context)
        # For now, simple baseline: 50 CPC = 50 points
        if cpc > 0:
            cpc_score = min(50, (50 / cpc) * 50)
        else:
            cpc_score = 50  # Full points if no spend
        
        return min(100, ctr_score + cpc_score)
