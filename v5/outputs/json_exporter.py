"""JSON exporter – serialize bundles to JSON"""

import json
from pathlib import Path
from datetime import date
from dataclasses import asdict

from ..domain import MetricsBundle, FactsBundle, CabinetContext


class JsonExporter:
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
        outputs_dir = self.cabinet_ctx.cabinet_path / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        
        json_path = outputs_dir / f"metrics_analysis_{target_date}.json"
        
        try:
            # Convert metrics bundle to dictionary
            metrics_dict = asdict(metrics)
            
            # Write to JSON file with proper formatting
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(metrics_dict, f, indent=2, ensure_ascii=False, default=str)
            
            return json_path
        except Exception as e:
            print(f"Error exporting metrics: {e}")
            raise
    
    def export_facts(self, facts: FactsBundle, target_date: date) -> Path:
        """
        Export facts to JSON.
        
        Args:
            facts: Facts bundle
            target_date: Date of facts
            
        Returns:
            Path to JSON file
        """
        outputs_dir = self.cabinet_ctx.cabinet_path / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        
        json_path = outputs_dir / f"decisions_{target_date}.json"
        
        try:
            # Convert facts bundle to dictionary
            facts_dict = asdict(facts)
            
            # Write to JSON file with proper formatting
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(facts_dict, f, indent=2, ensure_ascii=False, default=str)
            
            return json_path
        except Exception as e:
            print(f"Error exporting facts: {e}")
            raise
