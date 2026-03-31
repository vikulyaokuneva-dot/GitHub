"""WB API data loader – loads data from Wildberries API"""

import asyncio
from datetime import date
from typing import Optional

from domain import RawDataBundle, CabinetContext
from .base import DataSource


class WBAPILoader(DataSource):
    """Loads data from Wildberries API (like v2)"""
    
    def __init__(self):
        """Initialize WB API loader"""
        pass
    
    async def load_data(
        self,
        cabinet_ctx: CabinetContext,
        target_date: date
    ) -> RawDataBundle:
        """
        Load data from WB API.
        
        Fetches:
          - Ads performance
          - Orders
          - Returns
          - Margins
          - Ratings
        
        Args:
            cabinet_ctx: Cabinet context with API credentials
            target_date: Date to fetch data for
            
        Returns:
            RawDataBundle with source="api"
        """
        # TODO: Implement WB API calls
        # 1. Fetch ads data from API
        # 2. Fetch orders from API
        # 3. Fetch margins/returns/ratings from API
        # 4. Handle rate limiting and pagination
        # 5. Return RawDataBundle
        
        raise NotImplementedError("WBAPILoader.load_data() not yet implemented")
