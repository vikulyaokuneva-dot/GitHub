"""
Parsers to transform WB API responses into domain contracts.

Each parser converts raw API response to a specific Raw*Data class.
"""

import logging
from datetime import date, datetime
from typing import Any, Dict, Optional

from domain.contracts import (
    RawAdsData,
    RawOrdersData,
    RawMarginsData,
    RawReturnsData,
    RawRatingsData,
)

logger = logging.getLogger(__name__)


class AdsParser:
    """Parse WB ads stats into RawAdsData"""
    
    @staticmethod
    def parse_ads_stats(
        ads_stats: list[Dict[str, Any]],
        target_date: date
    ) -> list[RawAdsData]:
        """
        Parse ads statistics from /adv/v3/fullstats endpoint.
        
        Args:
            ads_stats: Response from fetch_ads_stats()
            target_date: Date for this data
            
        Returns:
            List of RawAdsData
        """
        result = []
        
        for stat in ads_stats:
            if not isinstance(stat, dict):
                continue
            
            try:
                # Extract basic ad info
                ad_id = str(stat.get("advertId") or stat.get("id") or "")
                if not ad_id:
                    logger.warning("Ad stat missing advertId")
                    continue
                
                # Map WB field names to our contracts
                # WB returns: statistic -> [list of per-date stats]
                stats_list = stat.get("statistic", [])
                
                # Aggregate stats for target date
                views = 0
                clicks = 0
                spend = 0.0
                
                for s in stats_list:
                    if not isinstance(s, dict):
                        continue
                    
                    # Check if this stat is for target date
                    stat_date_str = s.get("date", "")
                    if stat_date_str:
                        try:
                            stat_date = datetime.fromisoformat(stat_date_str).date()
                            if stat_date != target_date:
                                continue
                        except (ValueError, TypeError):
                            pass
                    
                    views += int(s.get("shows") or s.get("views") or 0)
                    clicks += int(s.get("clicks") or 0)
                    spend += float(s.get("spend") or 0.0)
                
                # Get ad name and SKUs
                name = stat.get("advertName") or stat.get("name") or f"Ad {ad_id}"
                sku_ids = []
                
                # WB provides articlesWb (SKU IDs) in some responses
                articles = stat.get("articlesWb", [])
                if articles:
                    for art in articles:
                        if isinstance(art, dict):
                            sku_id = str(art.get("nmId") or art.get("id") or "")
                        else:
                            sku_id = str(art)
                        
                        if sku_id:
                            sku_ids.append(sku_id)
                
                # Get budget (daily budget usually in campaign info)
                budget_daily = float(stat.get("budget") or stat.get("dailyBudget") or 0.0)
                
                # Get status
                status = stat.get("status") or "active"
                
                raw_ad = RawAdsData(
                    ad_id=ad_id,
                    name=name,
                    sku_ids=sku_ids,
                    budget_daily=budget_daily,
                    status=status,
                    views=views,
                    clicks=clicks,
                    spend=spend,
                    date=target_date,
                )
                
                result.append(raw_ad)
                
            except Exception as e:
                logger.error(f"Failed to parse ad stat: {e}")
                continue
        
        logger.info(f"Parsed {len(result)} ads")
        return result


class OrdersParser:
    """Parse WB sales funnel and realization report into RawOrdersData"""
    
    @staticmethod
    def parse_orders_from_funnel(
        funnel: Dict[str, Any],
        target_date: date
    ) -> list[RawOrdersData]:
        """
        Parse orders from sales-funnel/products endpoint.
        
        This gives conversion data but less detail. Better for trend data.
        """
        result = []
        
        data = funnel.get("data", {})
        products = data.get("products", [])
        
        for product in products:
            if not isinstance(product, dict):
                continue
            
            sku_id = str(product.get("nmId") or product.get("id") or "")
            if not sku_id:
                continue
            
            # Funnel has: impressions, adds_to_cart, orders, revenue, etc.
            order_count = int(product.get("orders") or product.get("orderCount") or 0)
            revenue = float(product.get("revenue") or product.get("orderSum") or 0.0)
            commission = float(product.get("commission") or 0.0)
            
            # We don't have individual orders from funnel, only aggregates
            # Create synthetic order records
            if order_count > 0:
                avg_quantity = max(1, order_count // max(1, order_count))
                avg_revenue = revenue / max(1, order_count)
                avg_commission = commission / max(1, order_count)
                
                for i in range(order_count):
                    order = RawOrdersData(
                        order_id=f"{sku_id}_funnel_{i}",
                        sku_id=sku_id,
                        ad_id=None,  # Funnel doesn't track ad attribution
                        quantity=avg_quantity,
                        revenue=avg_revenue,
                        commission=avg_commission,
                        date=target_date,
                    )
                    result.append(order)
        
        logger.info(f"Parsed {len(result)} orders from funnel")
        return result
    
    @staticmethod
    def parse_orders_from_realization(
        realization: list[Dict[str, Any]],
        target_date: date
    ) -> list[RawOrdersData]:
        """
        Parse detailed orders from reportDetailByPeriod endpoint.
        
        This gives per-order detail: date, sku, quantity, revenue, etc.
        """
        result = []
        
        for record in realization:
            if not isinstance(record, dict):
                continue
            
            try:
                # Filter by date
                record_date_str = record.get("date") or record.get("reportDate") or ""
                if record_date_str:
                    try:
                        record_date = datetime.fromisoformat(record_date_str).date()
                        if record_date != target_date:
                            continue
                    except (ValueError, TypeError):
                        pass
                
                # Extract order info
                # NOTE: WB realization report is complex and varies
                # Typical fields: rrd_id, supplier_sku, nm_id, order_dt, sale_dt, etc.
                
                sku_id = str(record.get("nmId") or record.get("nm_id") or "")
                if not sku_id:
                    continue
                
                order_id = str(record.get("rrdId") or record.get("orderId") or f"{sku_id}_{target_date}")
                quantity = int(record.get("quantity") or record.get("cnt") or 1)
                revenue = float(record.get("saleSum") or record.get("orderSum") or 0.0)
                commission = float(record.get("commission") or 0.0)
                
                # Try to get ad_id if available (not always present)
                ad_id = record.get("campaignId") or record.get("advertId")
                if ad_id:
                    ad_id = str(ad_id)
                
                order = RawOrdersData(
                    order_id=order_id,
                    sku_id=sku_id,
                    ad_id=ad_id,
                    quantity=quantity,
                    revenue=revenue,
                    commission=commission,
                    date=target_date,
                )
                
                result.append(order)
                
            except Exception as e:
                logger.error(f"Failed to parse order record: {e}")
                continue
        
        logger.info(f"Parsed {len(result)} orders from realization")
        return result


class MarginsParser:
    """Parse margins/cost data from various sources"""
    
    @staticmethod
    def parse_margins_from_realization(
        realization: list[Dict[str, Any]],
        target_date: date
    ) -> list[RawMarginsData]:
        """
        Extract margin data from realization report.
        
        Wildberries includes cost_price, selling_price, margins in the report.
        """
        result = []
        seen_skus = set()
        
        for record in realization:
            if not isinstance(record, dict):
                continue
            
            try:
                # Filter by date
                record_date_str = record.get("date") or record.get("reportDate") or ""
                if record_date_str:
                    try:
                        record_date = datetime.fromisoformat(record_date_str).date()
                        if record_date != target_date:
                            continue
                    except (ValueError, TypeError):
                        pass
                
                sku_id = str(record.get("nmId") or record.get("nm_id") or "")
                if not sku_id or sku_id in seen_skus:
                    continue
                
                # Get costs
                cost_price = float(record.get("costPrice") or record.get("cost") or 0.0)
                selling_price = float(record.get("price") or record.get("salePrice") or 0.0)
                
                if cost_price <= 0 or selling_price <= 0:
                    continue
                
                margin = selling_price - cost_price
                margin_percent = (margin / selling_price * 100) if selling_price > 0 else 0.0
                
                margin_data = RawMarginsData(
                    sku_id=sku_id,
                    cost_price=cost_price,
                    selling_price=selling_price,
                    margin_percent=margin_percent,
                    date=target_date,
                )
                
                result.append(margin_data)
                seen_skus.add(sku_id)
                
            except Exception as e:
                logger.error(f"Failed to parse margin record: {e}")
                continue
        
        logger.info(f"Parsed {len(result)} margins")
        return result


class ReturnsParser:
    """Parse returns data from realization report"""
    
    @staticmethod
    def parse_returns(
        realization: list[Dict[str, Any]],
        target_date: date
    ) -> list[RawReturnsData]:
        """
        Extract return information from realization report.
        
        WB tracks returns with return_id, reason, revenue lost.
        """
        result = []
        
        for record in realization:
            if not isinstance(record, dict):
                continue
            
            try:
                # Check if this is a return record
                # WB marks returns with status="возврат" or similar
                status = record.get("status") or ""
                if "возврат" not in status.lower() and "return" not in status.lower():
                    continue
                
                # Filter by date
                record_date_str = record.get("date") or record.get("reportDate") or ""
                if record_date_str:
                    try:
                        record_date = datetime.fromisoformat(record_date_str).date()
                        if record_date != target_date:
                            continue
                    except (ValueError, TypeError):
                        pass
                
                # Extract return info
                return_id = str(record.get("rrdId") or record.get("returnId") or "")
                order_id = str(record.get("orderId") or "")
                sku_id = str(record.get("nmId") or record.get("nm_id") or "")
                
                if not sku_id:
                    continue
                
                reason = record.get("reasonReturn") or record.get("reason") or "unknown"
                revenue_lost = float(record.get("saleSum") or record.get("orderSum") or 0.0)
                
                return_data = RawReturnsData(
                    return_id=return_id or f"{order_id}_return",
                    order_id=order_id,
                    sku_id=sku_id,
                    reason=reason,
                    revenue_lost=revenue_lost,
                    date=target_date,
                )
                
                result.append(return_data)
                
            except Exception as e:
                logger.error(f"Failed to parse return record: {e}")
                continue
        
        logger.info(f"Parsed {len(result)} returns")
        return result


class RatingsParser:
    """Parse product ratings and review data"""
    
    @staticmethod
    def parse_ratings(
        products_info: Dict[int, Dict[str, Any]],
        target_date: date
    ) -> list[RawRatingsData]:
        """
        Extract ratings from product info.
        
        Args:
            products_info: Dict {sku_id: product_info} from API
            target_date: Date for this data
        """
        result = []
        
        for sku_id, info in products_info.items():
            if not isinstance(info, dict):
                continue
            
            try:
                rating = float(info.get("rating") or 0.0)
                review_count = int(info.get("reviewCount") or info.get("feedbackCount") or 0)
                negative_reviews = int(info.get("negativeReviews") or 0)
                
                rating_data = RawRatingsData(
                    sku_id=str(sku_id),
                    rating=rating,
                    review_count=review_count,
                    negative_reviews=negative_reviews,
                    date=target_date,
                )
                
                result.append(rating_data)
                
            except Exception as e:
                logger.error(f"Failed to parse rating for SKU {sku_id}: {e}")
                continue
        
        logger.info(f"Parsed {len(result)} ratings")
        return result
