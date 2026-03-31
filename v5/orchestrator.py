"""Orchestrator – main execution pipeline"""

from datetime import date

from .domain import CabinetContext, Cabinet, CabinetConfig, RunMode, ProcessingResult
from .infrastructure.sources import WBAPILoader, FileReportLoader
from .infrastructure.storage import CabinetStorage
from .analytics.normalization import Normalizer
from .analytics.metrics_engine import MetricsEngine
from .analytics.facts_builder import FactsBuilder
from .analytics.decisions_engine import DecisionsEngine
from .outputs.report_generator import ReportGenerator


class Orchestrator:
    """Main execution orchestrator"""
    
    def __init__(self, config_root: str = ""):
        self.config_root = config_root
        self.normalizer = Normalizer()
        self.metrics_engine = MetricsEngine()
    
    async def run_daily(self, cabinet_id: str) -> ProcessingResult:
        """
        Run daily API pull mode.
        
        Pipeline:
          1. Load Cabinet config
          2. WBAPILoader.load_data() → RawDataBundle
          3. Normalizer.normalize() → NormalizedDataBundle
          4. MetricsEngine.calculate() → MetricsBundle
          5. FactsBuilder.build() → FactsBundle
          6. DecisionsEngine.generate() → Recommendations
          7. ReportGenerator.generate() → PDF/Excel
          8. CabinetStorage.save_all()
        
        Args:
            cabinet_id: Cabinet ID (e.g. "seller_001")
            
        Returns:
            ProcessingResult with status
        """
        # TODO: Implement daily pipeline
        # 1. Load cabinet config
        # 2. Create WBAPILoader
        # 3. Load data → Normalize → Calculate → Build facts → Generate reports
        # 4. Save all bundles
        # 5. Return ProcessingResult
        
        raise NotImplementedError("Orchestrator.run_daily() not yet implemented")
    
    async def run_audit(self, cabinet_id: str, target_date: date) -> ProcessingResult:
        """
        Run report audit mode.
        
        Pipeline (same as daily, but with FileReportLoader):
          1. FileReportLoader.load_data() → RawDataBundle
          2. [rest is identical to run_daily]
        
        Args:
            cabinet_id: Cabinet ID
            target_date: Date to audit
            
        Returns:
            ProcessingResult with status
        """
        # TODO: Implement audit pipeline
        # Same as run_daily, but use FileReportLoader instead of WBAPILoader
        
        raise NotImplementedError("Orchestrator.run_audit() not yet implemented")
    
    async def show_analytics(self, cabinet_id: str) -> None:
        """
        Display analytics summary for a cabinet.
        
        Args:
            cabinet_id: Cabinet ID
        """
        # TODO: Implement analytics display
        # 1. Load latest metrics and facts
        # 2. Display summary in console
        
        raise NotImplementedError("Orchestrator.show_analytics() not yet implemented")
