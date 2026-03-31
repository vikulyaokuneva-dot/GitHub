"""
Cabinet and context models.

Handles cabinet configuration and isolation.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Cabinet:
    """Cabinet information"""
    id: str  # e.g., "seller_001"
    name: str  # e.g., "ООО Рога и копыта"
    api_key: str  # WB API key
    wb_seller_id: str  # Seller ID from WB
    
    # Optional
    email: Optional[str] = None
    phone: Optional[str] = None


@dataclass
class CabinetConfig:
    """Cabinet-specific configuration"""
    # Thresholds
    anomaly_ctr_change_percent: float = 20.0  # Alert if CTR changes > 20%
    anomaly_cpc_change_percent: float = 15.0  # Alert if CPC changes > 15%
    
    # Opportunity detection
    min_roas_opportunity: float = 1.5  # Opportunity if ROAS > 1.5
    min_orders_daily: int = 5  # Only analyze if daily orders >= 5
    
    # Reports
    report_include_details: bool = True
    report_format: list[str] = None  # ["pdf", "excel", "json"]
    
    def __post_init__(self):
        if self.report_format is None:
            self.report_format = ["pdf", "json"]


@dataclass
class CabinetContext:
    """Runtime context for a cabinet processing session"""
    cabinet: Cabinet
    config: CabinetConfig
    
    # Paths
    cabinet_root: Path  # d:/cabinets/seller_001/
    
    # Computed paths
    @property
    def data_root(self) -> Path:
        return self.cabinet_root / "data"
    
    @property
    def raw_data_dir(self) -> Path:
        return self.data_root / "raw"
    
    @property
    def normalized_data_dir(self) -> Path:
        return self.data_root / "normalized"
    
    @property
    def metrics_dir(self) -> Path:
        return self.data_root / "metrics"
    
    @property
    def facts_dir(self) -> Path:
        return self.data_root / "facts"
    
    @property
    def reports_dir(self) -> Path:
        return self.cabinet_root / "reports"
    
    @property
    def inputs_dir(self) -> Path:
        """Input folder for uploaded reports"""
        return self.cabinet_root / "input"
    
    @property
    def state_file(self) -> Path:
        """Processing state file"""
        return self.cabinet_root / ".state.json"
