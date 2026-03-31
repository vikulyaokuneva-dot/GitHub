"""File report loader – loads data from uploaded Excel/CSV reports"""

from datetime import date
from pathlib import Path

from domain import RawDataBundle, CabinetContext
from .base import DataSource


class FileReportLoader(DataSource):
    """Loads data from Excel/CSV reports (like v3)"""
    
    async def load_data(
        self,
        cabinet_ctx: CabinetContext,
        target_date: date
    ) -> RawDataBundle:
        """
        Load data from uploaded report files.
        
        Looks for files in cabinet_ctx.inputs_dir:
          - ads_report_{date}.xlsx
          - orders_report_{date}.xlsx
          - margins_report_{date}.xlsx
          - etc.
        
        Args:
            cabinet_ctx: Cabinet context with paths
            target_date: Date to load reports for
            
        Returns:
            RawDataBundle with source="report"
        """
        # TODO: Implement file parsing
        # 1. Find report files for target_date in inputs_dir
        # 2. Parse Excel/CSV files
        # 3. Extract ads, orders, margins, etc.
        # 4. Validate data
        # 5. Return RawDataBundle
        
        raise NotImplementedError("FileReportLoader.load_data() not yet implemented")
