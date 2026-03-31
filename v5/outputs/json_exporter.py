"""JSON exporter – serialize bundles to JSON"""

from pathlib import Path
from datetime import date

from ..domain import MetricsBundle, FactsBundle, CabinetContext


class JSONExporter:
    """Exports bundles to JSON for archival and analysis"""
    
    def __init__(self, cabinet_ctx: CabinetContext):
        self.cabinet_ctx = cabinet_ctx
    
    def export_metrics(self, metrics: MetricsBundle, target_date: date) -> Path:
        """
        Export metrics to JSON.
        
        Args:
            metrics: Metrics bundle
            target_date: Date of metrics
            
        Returns:
            Path to JSON file
        """
        # TODO: Implement JSON export
        pass
    
    def export_facts(self, facts: FactsBundle, target_date: date) -> Path:
        """
        Export facts to JSON.
        
        Args:
            facts: Facts bundle
            target_date: Date of facts
            
        Returns:
            Path to JSON file
        """
        # TODO: Implement JSON export
        pass
