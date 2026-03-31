"""
Async wrapper around WB API client.

Provides async interface to Wildberries API with retry logic and rate limiting.
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional
from datetime import date

import aiohttp

logger = logging.getLogger(__name__)


class AsyncWBClient:
    """Async WB API client with retry and rate limiting"""
    
    def __init__(self, api_key: str, timeout: int = 60):
        """
        Initialize async WB client.
        
        Args:
            api_key: WB API token (from Cabinet)
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.timeout = timeout
        
        # WB API endpoints
        self.analytics_url = "https://seller-analytics-api.wildberries.ru"
        self.advert_url = "https://advert-api.wildberries.ru"
        self.statistics_url = "https://statistics-api.wildberries.ru"
        
        # Rate limiting
        self.min_request_interval = 0.2  # Min seconds between requests
        self.last_request_time = 0.0
        
    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": self.api_key,
            "Content-Type": "application/json",
        }
    
    async def _respect_rate_limit(self):
        """Respect rate limiting between requests"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            await asyncio.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()
    
    async def _get_with_retry(
        self,
        session: aiohttp.ClientSession,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        max_retries: int = 5
    ) -> Any:
        """GET with exponential backoff retry logic"""
        last_error = None
        
        for attempt in range(1, max_retries + 1):
            try:
                await self._respect_rate_limit()
                
                async with session.get(
                    url,
                    headers=self._headers(),
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        logger.debug(f"GET {url} → 200 OK")
                        return data
                    
                    if resp.status == 204:
                        logger.debug(f"GET {url} → 204 No Content")
                        return None
                    
                    if resp.status == 403:
                        logger.warning(f"GET {url} → 403 Forbidden (access restricted)")
                        return None
                    
                    if resp.status in (429, 500, 502, 503, 504):
                        text = await resp.text()
                        last_error = f"HTTP {resp.status}: {text[:200]}"
                        sleep_time = 2 ** attempt
                        logger.warning(
                            f"GET {url} → {resp.status}, retrying in {sleep_time}s "
                            f"(attempt {attempt}/{max_retries})"
                        )
                        await asyncio.sleep(sleep_time)
                        continue
                    
                    text = await resp.text()
                    raise RuntimeError(f"WB API error {resp.status}: {text}")
                    
            except asyncio.TimeoutError:
                last_error = f"Timeout after {self.timeout}s"
                sleep_time = 2 ** attempt
                logger.warning(f"Timeout {url}, retrying in {sleep_time}s (attempt {attempt}/{max_retries})")
                await asyncio.sleep(sleep_time)
                
            except Exception as e:
                last_error = str(e)
                sleep_time = 2 ** attempt
                logger.warning(f"Error {url}: {last_error}, retrying in {sleep_time}s (attempt {attempt}/{max_retries})")
                await asyncio.sleep(sleep_time)
        
        raise RuntimeError(f"WB API failed after {max_retries} retries: {last_error}")
    
    async def _post_with_retry(
        self,
        session: aiohttp.ClientSession,
        url: str,
        body: Dict[str, Any],
        max_retries: int = 5
    ) -> Any:
        """POST with exponential backoff retry logic"""
        last_error = None
        
        for attempt in range(1, max_retries + 1):
            try:
                await self._respect_rate_limit()
                
                async with session.post(
                    url,
                    headers=self._headers(),
                    json=body,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        logger.debug(f"POST {url} → 200 OK")
                        return data
                    
                    if resp.status == 204:
                        logger.debug(f"POST {url} → 204 No Content")
                        return None
                    
                    if resp.status == 403:
                        logger.warning(f"POST {url} → 403 Forbidden")
                        return None
                    
                    if resp.status in (429, 500, 502, 503, 504):
                        text = await resp.text()
                        last_error = f"HTTP {resp.status}: {text[:200]}"
                        sleep_time = 2 ** attempt
                        logger.warning(f"POST {url} → {resp.status}, retrying in {sleep_time}s")
                        await asyncio.sleep(sleep_time)
                        continue
                    
                    text = await resp.text()
                    raise RuntimeError(f"WB API error {resp.status}: {text}")
                    
            except asyncio.TimeoutError:
                last_error = f"Timeout after {self.timeout}s"
                sleep_time = 2 ** attempt
                logger.warning(f"Timeout {url}, retrying in {sleep_time}s")
                await asyncio.sleep(sleep_time)
                
            except Exception as e:
                last_error = str(e)
                sleep_time = 2 ** attempt
                logger.warning(f"Error {url}: {last_error}, retrying in {sleep_time}s")
                await asyncio.sleep(sleep_time)
        
        raise RuntimeError(f"WB API failed after {max_retries} retries: {last_error}")
    
    # =========================================================================
    # PUBLIC API METHODS
    # =========================================================================
    
    async def fetch_ads_stats(
        self,
        session: aiohttp.ClientSession,
        date_from: str,
        date_to: str
    ) -> tuple[list[Dict[str, Any]], list[int]]:
        """
        Fetch ads statistics and return (stats, ad_ids).
        
        Args:
            session: aiohttp ClientSession
            date_from: ISO date "2024-01-01"
            date_to: ISO date "2024-01-31"
            
        Returns:
            Tuple of (list of stats dicts, list of ad_ids)
        """
        # Step 1: Get list of adverts
        adverts = await self._get_with_retry(
            session,
            f"{self.advert_url}/api/advert/v2/adverts",
            params={}
        )
        
        # Extract ad IDs
        ad_ids = []
        if adverts:
            items = []
            if isinstance(adverts, dict):
                if isinstance(adverts.get("adverts"), list):
                    items = adverts.get("adverts")
                else:
                    for v in adverts.values():
                        if isinstance(v, list):
                            items.extend(v)
            elif isinstance(adverts, list):
                items = adverts
            
            for item in items:
                if not isinstance(item, dict):
                    continue
                ad_id = item.get("advertId") or item.get("id")
                if ad_id:
                    try:
                        ad_ids.append(int(ad_id))
                    except (ValueError, TypeError):
                        pass
        
        ad_ids = sorted(set(ad_ids))
        logger.info(f"Found {len(ad_ids)} ads")
        
        if not ad_ids:
            return [], []
        
        # Step 2: Fetch stats for ad chunks
        all_stats = []
        chunk_size = 50
        
        for i in range(0, len(ad_ids), chunk_size):
            chunk = ad_ids[i:i + chunk_size]
            stats = await self._get_with_retry(
                session,
                f"{self.advert_url}/adv/v3/fullstats",
                params={
                    "ids": ",".join(map(str, chunk)),
                    "beginDate": date_from,
                    "endDate": date_to,
                }
            )
            
            if stats:
                if isinstance(stats, list):
                    all_stats.extend(stats)
                else:
                    all_stats.append(stats)
        
        return all_stats, ad_ids
    
    async def fetch_sales_funnel(
        self,
        session: aiohttp.ClientSession,
        date_from: str,
        date_to: str
    ) -> Dict[str, Any]:
        """
        Fetch sales funnel (orders, conversions).
        
        Returns data needed for Orders analytics.
        """
        body = {
            "selectedPeriod": {"start": date_from, "end": date_to},
            "nmIds": [],
            "brandNames": [],
            "subjectIds": [],
            "tagIds": [],
            "skipDeletedNm": True,
            "limit": 1000,
            "offset": 0,
        }
        
        return await self._post_with_retry(
            session,
            f"{self.analytics_url}/api/analytics/v3/sales-funnel/products",
            body
        ) or {}
    
    async def fetch_realization_report(
        self,
        session: aiohttp.ClientSession,
        date_from: str,
        date_to: str
    ) -> list[Dict[str, Any]]:
        """
        Fetch realization report (orders, returns, margins).
        
        Contains detailed order info: revenue, commission, returns, etc.
        """
        return await self._get_with_retry(
            session,
            f"{self.statistics_url}/api/v5/supplier/reportDetailByPeriod",
            params={
                "dateFrom": date_from,
                "dateTo": date_to,
                "limit": 100000,
                "rrdid": 0,
            }
        ) or []
    
    async def fetch_stocks(
        self,
        session: aiohttp.ClientSession,
        date_from: str
    ) -> list[Dict[str, Any]]:
        """
        Fetch current stocks (for cost price analysis).
        """
        return await self._get_with_retry(
            session,
            f"{self.statistics_url}/api/v1/supplier/stocks",
            params={"dateFrom": date_from}
        ) or []
    
    async def fetch_product_info(
        self,
        session: aiohttp.ClientSession,
        sku_ids: list[int]
    ) -> Dict[int, Dict[str, Any]]:
        """
        Fetch product info (prices, ratings, reviews).
        
        Args:
            session: aiohttp session
            sku_ids: List of SKU IDs to fetch
            
        Returns:
            Dict {sku_id: product_info}
        """
        # NOTE: This is a simplified version.
        # Real implementation would use WB product catalog API or similar
        return {}
