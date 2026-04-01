"""Data normalization – convert raw data to unified format"""

from datetime import date
from collections import defaultdict
from ..domain import (
    RawDataBundle,
    RawAdsData,
    RawOrdersData,
    RawMarginsData,
    RawRatingsData,
    NormalizedDataBundle,
    NormalizedAds,
    NormalizedSKU,
    CabinetContext,
)


class Normalizer:
    """Transforms raw data into normalized format"""
    
    def normalize(self, raw: RawDataBundle) -> NormalizedDataBundle:
        """
        Convert RawDataBundle to NormalizedDataBundle.
        
        This transformation is independent of the source (API or report).
        Both API and file sources should produce equivalent results.
        
        Args:
            raw: Raw data bundle (source="api" or "report")
            
        Returns:
            NormalizedDataBundle with unified structure
        """
        # Transform ads
        normalized_ads = self._normalize_ads(raw.ads)
        
        # Transform SKUs (aggregate from orders, margins, ratings)
        normalized_skus = self._normalize_skus(
            raw.orders,
            raw.margins,
            raw.ratings,
            raw.returns
        )
        
        return NormalizedDataBundle(
            cabinet_id=raw.cabinet_id,
            period_date=raw.period_date,
            ads=normalized_ads,
            skus=normalized_skus
        )
    
    def _normalize_ads(self, raw_ads: list[RawAdsData]) -> list[NormalizedAds]:
        """Transform raw ads to normalized format"""
        normalized = []
        for ad in raw_ads:
            # Calculate CTR: clicks / views (impressions)
            ctr = (ad.clicks / ad.views * 100) if ad.views > 0 else 0.0
            
            # Calculate spend per impression
            spend_per_imp = (ad.spend / ad.views) if ad.views > 0 else 0.0
            
            normalized.append(NormalizedAds(
                ad_id=ad.ad_id,
                name=ad.name,
                sku_ids=ad.sku_ids,
                budget_daily=ad.budget_daily,
                status=ad.status,
                impressions=ad.views,
                clicks=ad.clicks,
                spend=ad.spend,
                ctr=ctr,
                spend_per_impression=spend_per_imp
            ))
        
        return normalized
    
    def _normalize_skus(
        self,
        raw_orders: list[RawOrdersData],
        raw_margins: list[RawMarginsData],
        raw_ratings: list[RawRatingsData],
        raw_returns: list = None
    ) -> list[NormalizedSKU]:
        """Transform raw SKU data to normalized format"""
        if raw_returns is None:
            raw_returns = []
        
        # Build SKU aggregates
        sku_data = defaultdict(lambda: {
            "orders": 0,
            "revenue": 0.0,
            "cost_price": 0.0,
            "margin_percent": 0.0,
            "profit": 0.0,
            "rating": 0.0,
            "review_count": 0,
            "return_rate": 0.0,
            "total_returns": 0
        })
        
        # Process orders
        for order in raw_orders:
            sku_id = order.sku_id
            sku_data[sku_id]["orders"] += order.quantity
            sku_data[sku_id]["revenue"] += order.revenue
        
        # Process margins
        for margin in raw_margins:
            sku_id = margin.sku_id
            sku_data[sku_id]["cost_price"] = margin.cost_price
            sku_data[sku_id]["margin_percent"] = margin.margin_percent
            
            # Calculate profit
            if sku_data[sku_id]["orders"] > 0:
                profit_per_unit = margin.selling_price - margin.cost_price
                sku_data[sku_id]["profit"] = profit_per_unit * sku_data[sku_id]["orders"]
        
        # Process ratings
        for rating in raw_ratings:
            sku_id = rating.sku_id
            sku_data[sku_id]["rating"] = rating.rating
            sku_data[sku_id]["review_count"] = rating.review_count
        
        # Calculate return rate
        for return_item in raw_returns:
            sku_id = return_item.sku_id
            sku_data[sku_id]["total_returns"] += 1
        
        # Build normalized SKU list
        normalized_skus = []
        for sku_id, data in sku_data.items():
            return_rate = (
                data["total_returns"] / data["orders"]
                if data["orders"] > 0 else 0.0
            )
            
            normalized_skus.append(NormalizedSKU(
                sku_id=sku_id,
                name=f"SKU {sku_id}",  # Will be populated from product database in future
                orders=data["orders"],
                revenue=data["revenue"],
                cost_price=data["cost_price"],
                margin_percent=data["margin_percent"],
                profit=data["profit"],
                rating=data["rating"],
                review_count=data["review_count"],
                return_rate=return_rate
            ))
        
        return normalized_skus
