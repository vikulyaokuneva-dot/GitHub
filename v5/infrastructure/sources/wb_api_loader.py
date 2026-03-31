"""WB API data loader – loads data from Wildberries API"""

import asyncio
import logging
from datetime import date, timedelta
from typing import Optional

import aiohttp

from ...domain import RawDataBundle, CabinetContext
from ..wb_api_client import AsyncWBClient
from .base import DataSource
from .parsers import (
    AdsParser,
    OrdersParser,
    MarginsParser,
    ReturnsParser,
    RatingsParser,
)

logger = logging.getLogger(__name__)


class WBAPILoader(DataSource):
    """
    Loads data from Wildberries API.
    
    Combines multiple WB endpoints:
    - /adv/v3/fullstats - ads performance (views, clicks, spend)
    - /api/analytics/v3/sales-funnel/products - orders & conversions
    - /api/v5/supplier/reportDetailByPeriod - detailed orders, returns, margins
    - /api/v1/supplier/stocks - stock info
    
    Maps all data to RawDataBundle format.
    """
    
    def __init__(self, timeout: int = 60):
        """
        Initialize WB API loader.
        
        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
    
    async def load_data(
        self,
        cabinet_ctx: CabinetContext,
        target_date: date
    ) -> RawDataBundle:
        """
        Load data from WB API for a specific date.
        
        Args:
            cabinet_ctx: Cabinet context with API credentials (cabinet.api_key)
            target_date: Date to load data for (ISO format)
            
        Returns:
            RawDataBundle with source="api"
            
        Raises:
            ValueError: If API key not configured
            RuntimeError: If API calls fail after retries
        """
        
        # Validate API credentials
        if not cabinet_ctx.cabinet.api_key:
            raise ValueError(f"Cabinet {cabinet_ctx.cabinet.id} has no API key configured")
        
        logger.info(
            f"Loading data from WB API for {cabinet_ctx.cabinet.id} on {target_date}"
        )
        
        # Initialize async client
        client = AsyncWBClient(
            api_key=cabinet_ctx.cabinet.api_key,
            timeout=self.timeout
        )
        
        # Prepare ISO date strings (WB uses YYYY-MM-DD)
        date_from = target_date.isoformat()
        date_to = target_date.isoformat()
        
        # Fetch all data in parallel using aiohttp session
        async with aiohttp.ClientSession() as session:
            try:
                # Parallel fetches to speed up data loading
                (ads_stats, ad_ids), funnel_data, realization_data, stocks_data = \
                    await asyncio.gather(
                        client.fetch_ads_stats(session, date_from, date_to),
                        client.fetch_sales_funnel(session, date_from, date_to),
                        client.fetch_realization_report(session, date_from, date_to),
                        client.fetch_stocks(session, date_from),
                        return_exceptions=False
                    )
                
            except Exception as e:
                logger.error(f"Failed to fetch data from WB API: {e}")
                raise RuntimeError(f"WB API fetch failed: {e}") from e
        
        # Parse API responses into domain contracts
        logger.info("Parsing WB API responses...")
        
        ads_data = AdsParser.parse_ads_stats(ads_stats, target_date)
        
        # Parse orders from both sources (combine for completeness)
        orders_from_funnel = OrdersParser.parse_orders_from_funnel(funnel_data, target_date)
        orders_from_real = OrdersParser.parse_orders_from_realization(realization_data, target_date)
        
        # Prefer detailed realization data, fallback to funnel
        orders_data = orders_from_real if orders_from_real else orders_from_funnel
        logger.info(f"Using {len(orders_data)} orders from {'realization' if orders_from_real else 'funnel'}")
        
        # Parse margins, returns, ratings from realization report
        margins_data = MarginsParser.parse_margins_from_realization(realization_data, target_date)
        returns_data = ReturnsParser.parse_returns(realization_data, target_date)
        ratings_data = RatingsParser.parse_ratings({}, target_date)  # TODO: fetch product ratings
        
        # Log what we loaded
        logger.info(
            f"Loaded from WB API: "
            f"{len(ads_data)} ads, "
            f"{len(orders_data)} orders, "
            f"{len(margins_data)} margins, "
            f"{len(returns_data)} returns, "
            f"{len(ratings_data)} ratings"
        )
        
        # Bundle everything into RawDataBundle
        bundle = RawDataBundle(
            cabinet_id=cabinet_ctx.cabinet.id,
            period_date=target_date,
            source="api",
            ads=ads_data,
            orders=orders_data,
            margins=margins_data,
            returns=returns_data,
            ratings=ratings_data,
        )
        
        return bundle
