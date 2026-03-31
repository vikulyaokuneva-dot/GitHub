"""File report loader – loads data from uploaded Excel/CSV reports"""

import logging
from datetime import date
from pathlib import Path
from typing import List, Optional
import zipfile

import pandas as pd

from domain import RawDataBundle, CabinetContext, RawAdsData, RawOrdersData, RawMarginsData, RawReturnsData
from .base import DataSource


logger = logging.getLogger(__name__)


class FileReportLoader(DataSource):
    """Loads data from Excel/CSV reports (audit mode)"""
    
    # Isolated audit input structure: v5/audit/input/{report_type}/
    AUDIT_INPUT_DIRS = {
        "ads": "ads",              # ads_stats, full_stats
        "orders": "finance",       # report_detail_by_period
        "margins": "finance",      # margin_report
        "funnel": "funnel",        # sales_funnel, product_stats
        "warehouse": "warehouse"   # stocks, warehouse_info
    }
    
    async def load_data(
        self,
        cabinet_ctx: CabinetContext,
        target_date: date
    ) -> RawDataBundle:
        """
        Load data from v5/audit/input/{report_type}/ directories.
        
        Structure (isolated from v2/v3):
          v5/audit/input/
          ├── ads/               → AdsParser
          ├── finance/           → OrdersParser + MarginsParser
          ├── funnel/            → FunnelParser
          └── warehouse/         → WarehouseParser
        
        Args:
            cabinet_ctx: Cabinet context with paths
            target_date: Date to load reports for
            
        Returns:
            RawDataBundle with source="report"
        """
        logger.info(f"Loading audit reports for {cabinet_ctx.cabinet.id} ({target_date})")
        
        # Load each report type from its isolated directory
        ads_list = await self._load_ads_reports(cabinet_ctx, target_date)
        orders_list = await self._load_orders_reports(cabinet_ctx, target_date)
        margins_list = await self._load_margins_reports(cabinet_ctx, target_date)
        returns_list = await self._load_returns_reports(cabinet_ctx, target_date)
        
        bundle = RawDataBundle(
            source="report",
            cabinet_id=cabinet_ctx.cabinet.id,
            date=target_date,
            ads=ads_list,
            orders=orders_list,
            margins=margins_list,
            returns=returns_list
        )
        
        logger.info(f"Loaded {len(ads_list)} ads, {len(orders_list)} orders, {len(margins_list)} margins")
        return bundle
    
    async def _load_ads_reports(self, ctx: CabinetContext, target_date: date) -> List[RawAdsData]:
        """Load ads reports from v5/audit/input/ads/"""
        input_dir = self._get_input_dir("ads")
        
        results = []
        for csv_file in input_dir.glob("*.csv"):
            try:
                df = pd.read_csv(csv_file)
                # Parse using AdsParser logic
                ads_records = self._parse_ads_csv(df, ctx.cabinet.id)
                results.extend(ads_records)
                logger.info(f"Loaded {len(ads_records)} ads from {csv_file.name}")
            except Exception as e:
                logger.error(f"Error loading {csv_file.name}: {e}")
        
        return results
    
    async def _load_orders_reports(self, ctx: CabinetContext, target_date: date) -> List[RawOrdersData]:
        """Load orders reports from v5/audit/input/finance/"""
        input_dir = self._get_input_dir("orders")
        
        results = []
        for csv_file in input_dir.glob("*report_detail*.csv"):
            try:
                df = pd.read_csv(csv_file)
                orders_records = self._parse_orders_csv(df, ctx.cabinet.id)
                results.extend(orders_records)
                logger.info(f"Loaded {len(orders_records)} orders from {csv_file.name}")
            except Exception as e:
                logger.error(f"Error loading {csv_file.name}: {e}")
        
        return results
    
    async def _load_margins_reports(self, ctx: CabinetContext, target_date: date) -> List[RawMarginsData]:
        """Load margins reports from v5/audit/input/finance/"""
        input_dir = self._get_input_dir("margins")
        
        results = []
        for xlsx_file in input_dir.glob("*margin*.xlsx"):
            try:
                df = pd.read_excel(xlsx_file)
                margins_records = self._parse_margins_excel(df, ctx.cabinet.id)
                results.extend(margins_records)
                logger.info(f"Loaded {len(margins_records)} margins from {xlsx_file.name}")
            except Exception as e:
                logger.error(f"Error loading {xlsx_file.name}: {e}")
        
        return results
    
    async def _load_returns_reports(self, ctx: CabinetContext, target_date: date) -> List[RawReturnsData]:
        """Load returns reports from v5/audit/input/finance/"""
        input_dir = self._get_input_dir("orders")
        
        results = []
        for csv_file in input_dir.glob("*returns*.csv"):
            try:
                df = pd.read_csv(csv_file)
                returns_records = self._parse_returns_csv(df, ctx.cabinet.id)
                results.extend(returns_records)
                logger.info(f"Loaded {len(returns_records)} returns from {csv_file.name}")
            except Exception as e:
                logger.error(f"Error loading {csv_file.name}: {e}")
        
        return results
    
    def _get_input_dir(self, report_type: str) -> Path:
        """Get isolated audit input directory for report type."""
        dir_name = self.AUDIT_INPUT_DIRS.get(report_type, report_type)
        base = Path.cwd() / "v5" / "audit" / "input" / dir_name
        
        if not base.exists():
            base.mkdir(parents=True, exist_ok=True)
            logger.warning(f"Created missing audit input dir: {base}")
        
        return base
    
    def _parse_ads_csv(self, df: pd.DataFrame, cabinet_id: str) -> List[RawAdsData]:
        """Parse ads CSV (from v3 AdsParser)"""
        results = []
        for _, row in df.iterrows():
            try:
                record = RawAdsData(
                    cabinet_id=cabinet_id,
                    sku=int(row.get("sku", 0)) or int(row.get("nmId", 0)),
                    views=int(row.get("views", 0)),
                    clicks=int(row.get("clicks", 0)),
                    spend=float(row.get("spend", 0) or 0),
                    ctr=float(row.get("ctr", 0) or 0),
                    cpc=float(row.get("cpc", 0) or 0),
                    date=pd.to_datetime(row.get("date", "today")).date()
                )
                results.append(record)
            except Exception as e:
                logger.warning(f"Skipped invalid ads row: {e}")
        
        return results
    
    def _parse_orders_csv(self, df: pd.DataFrame, cabinet_id: str) -> List[RawOrdersData]:
        """Parse orders CSV (from v3 OrdersParser)"""
        results = []
        for _, row in df.iterrows():
            try:
                record = RawOrdersData(
                    cabinet_id=cabinet_id,
                    order_id=str(row.get("order_id", 0)),
                    sku=int(row.get("sku", 0)),
                    quantity=int(row.get("quantity", 1)),
                    revenue=float(row.get("revenue", 0) or 0),
                    commission_percent=float(row.get("commission_percent", 0) or 0),
                    date=pd.to_datetime(row.get("date", "today")).date()
                )
                results.append(record)
            except Exception as e:
                logger.warning(f"Skipped invalid order row: {e}")
        
        return results
    
    def _parse_margins_excel(self, df: pd.DataFrame, cabinet_id: str) -> List[RawMarginsData]:
        """Parse margins Excel (from v3 MarginsParser)"""
        results = []
        for _, row in df.iterrows():
            try:
                cost = float(row.get("cost_price", 0) or 0)
                if cost <= 0:
                    continue  # Skip invalid records
                
                record = RawMarginsData(
                    cabinet_id=cabinet_id,
                    sku=int(row.get("sku", 0)),
                    cost_price=cost,
                    selling_price=float(row.get("selling_price", 0) or 0),
                    margin_percent=float(row.get("margin_percent", 0) or 0),
                    date=pd.to_datetime(row.get("date", "today")).date()
                )
                results.append(record)
            except Exception as e:
                logger.warning(f"Skipped invalid margin row: {e}")
        
        return results
    
    def _parse_returns_csv(self, df: pd.DataFrame, cabinet_id: str) -> List[RawReturnsData]:
        """Parse returns CSV (from v3 ReturnsParser)"""
        results = []
        for _, row in df.iterrows():
            try:
                record = RawReturnsData(
                    cabinet_id=cabinet_id,
                    sku=int(row.get("sku", 0)),
                    reason=str(row.get("reason", "unknown")),
                    lost_revenue=float(row.get("lost_revenue", 0) or 0),
                    quantity=int(row.get("quantity", 1)),
                    date=pd.to_datetime(row.get("date", "today")).date()
                )
                results.append(record)
            except Exception as e:
                logger.warning(f"Skipped invalid return row: {e}")
        
        return results
