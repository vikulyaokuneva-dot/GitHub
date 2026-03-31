"""Data source abstract base class"""

from abc import ABC, abstractmethod
from datetime import date

from domain import RawDataBundle, CabinetContext


class DataSource(ABC):
    """Abstract base class for data sources"""
    
    @abstractmethod
    async def load_data(
        self,
        cabinet_ctx: CabinetContext,
        target_date: date
    ) -> RawDataBundle:
        """
        Load raw data from source.
        
        Args:
            cabinet_ctx: Cabinet context with config
            target_date: Date to load data for
            
        Returns:
            RawDataBundle with source marked appropriately
        """
        pass
