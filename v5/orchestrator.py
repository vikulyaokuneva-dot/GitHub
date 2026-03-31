"""Orchestrator – main execution pipeline"""

from datetime import date
from pathlib import Path
from typing import Union

from .domain import CabinetContext, Cabinet, CabinetConfig, RunMode, ProcessingResult, ProcessingStatus
from .infrastructure.sources import WBAPILoader, FileReportLoader
from .infrastructure.storage import CabinetStorage
from .analytics.normalization import Normalizer
from .analytics.metrics_engine import MetricsEngine
from .analytics.facts_builder import FactsBuilder
from .analytics.decisions_engine import DecisionsEngine
from .outputs.report_generator import ReportGenerator


class Orchestrator:
    """Main execution orchestrator"""
    
    def __init__(self, config: Union[CabinetConfig, str] = ""):
        if isinstance(config, str):
            self.config_root = Path(config)
            self.config = CabinetConfig()
        else:
            self.config = config
            self.config_root = Path("cabinets")
        
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
          6. DecisionsEngine.generate_recommendations() → Recommendations
          7. ReportGenerator.generate_pdf() → PDF
          8. CabinetStorage.save_*() → Persistence
        
        Args:
            cabinet_id: Cabinet ID (e.g. "seller_001")
            
        Returns:
            ProcessingResult with status
        """
        try:
            # 1. Load cabinet config
            cabinet_path = Path(self.config_root) / "cabinets" / cabinet_id
            cabinet_path.mkdir(parents=True, exist_ok=True)
            
            # Create Cabinet instance (simplified - in production load from config)
            cabinet = Cabinet(
                id=cabinet_id,
                name=f"Cabinet {cabinet_id}",
                api_key="",  # Will be loaded from env in production
                wb_seller_id=cabinet_id
            )
            
            # Create context
            config = CabinetConfig()
            ctx = CabinetContext(cabinet, config, cabinet_path)
            
            # 2. Load data with WBAPILoader
            api_loader = WBAPILoader()
            raw_bundle = await api_loader.load_data(ctx, date.today())
            
            # 3. Normalize
            normalized = self.normalizer.normalize(raw_bundle)
            
            # 4. Calculate metrics
            metrics = self.metrics_engine.calculate(normalized)
            
            # 5. Build facts
            facts_builder = FactsBuilder(config)
            facts = facts_builder.build(normalized, metrics)
            
            # 6. Generate decisions
            decisions_engine = DecisionsEngine(config)
            decisions = decisions_engine.generate_recommendations(facts)
            
            # 7. Generate reports
            report_gen = ReportGenerator(ctx)
            pdf_path = report_gen.generate_pdf(metrics, facts)
            
            # 8. Save all bundles
            storage = CabinetStorage(ctx)
            storage.save_raw(raw_bundle)
            storage.save_normalized(normalized)
            storage.save_metrics(metrics)
            storage.save_facts(facts)
            
            return ProcessingResult(
                status=ProcessingStatus.SUCCESS,
                cabinet_id=cabinet_id,
                run_date=date.today(),
                mode="daily",
                message=f"Successfully processed {cabinet_id}"
            )
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return ProcessingResult(
                status=ProcessingStatus.FAILED,
                cabinet_id=cabinet_id,
                run_date=date.today(),
                mode="daily",
                message=f"Error processing {cabinet_id}: {str(e)}",
                errors=[str(e)]
            )
    
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
        try:
            # 1. Load cabinet config
            cabinet_path = Path(self.config_root) / "cabinets" / cabinet_id
            cabinet_path.mkdir(parents=True, exist_ok=True)
            
            # Create Cabinet instance (simplified - in production load from config)
            cabinet = Cabinet(
                id=cabinet_id,
                name=f"Cabinet {cabinet_id}",
                api_key="",  # Not needed for audit mode
                wb_seller_id=cabinet_id
            )
            
            # Create context
            config = CabinetConfig()
            ctx = CabinetContext(cabinet, config, cabinet_path)
            
            # 2. Load data with FileReportLoader (instead of API)
            file_loader = FileReportLoader()
            raw_bundle = await file_loader.load_data(ctx, target_date)
            
            # 3. Normalize
            normalized = self.normalizer.normalize(raw_bundle)
            
            # 4. Calculate metrics
            metrics = self.metrics_engine.calculate(normalized)
            
            # 5. Build facts
            facts_builder = FactsBuilder(config)
            facts = facts_builder.build(normalized, metrics)
            
            # 6. Generate decisions
            decisions_engine = DecisionsEngine(config)
            decisions = decisions_engine.generate_recommendations(facts)
            
            # 7. Generate reports
            report_gen = ReportGenerator(ctx)
            pdf_path = report_gen.generate_pdf(metrics, facts)
            
            # 8. Save all bundles
            storage = CabinetStorage(ctx)
            storage.save_raw(raw_bundle)
            storage.save_normalized(normalized)
            storage.save_metrics(metrics)
            storage.save_facts(facts)
            
            return ProcessingResult(
                status=ProcessingStatus.SUCCESS,
                cabinet_id=cabinet_id,
                run_date=target_date,
                mode="audit",
                message=f"Successfully audited {cabinet_id} for {target_date}"
            )
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return ProcessingResult(
                status=ProcessingStatus.FAILED,
                cabinet_id=cabinet_id,
                run_date=target_date,
                mode="audit",
                message=f"Error auditing {cabinet_id}: {str(e)}",
                errors=[str(e)]
            )
    
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
