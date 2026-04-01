"""Cabinet storage – persistence layer for bundles"""

import json
from datetime import date
from pathlib import Path
from dataclasses import asdict

from ...domain import (
    RawDataBundle,
    NormalizedDataBundle,
    MetricsBundle,
    FactsBundle,
    CabinetContext,
)


class CabinetStorage:
    """Handles storage and retrieval of processing bundles"""
    
    def __init__(self, cabinet_ctx: CabinetContext):
        self.cabinet_ctx = cabinet_ctx
        self.data_dir = cabinet_ctx.cabinet_path / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_filename(self, bundle_type: str, target_date: date | None = None) -> Path:
        """Get filename for a bundle"""
        if target_date is None:
            target_date = date.today()
        return self.data_dir / f"{bundle_type}_{target_date}.json"
    
    # Raw data
    def save_raw(self, bundle: RawDataBundle) -> None:
        """Save raw data bundle"""
        filename = self._get_filename("raw", bundle.period_date)
        try:
            data = asdict(bundle)
            filename.write_text(json.dumps(data, indent=2, default=str))
        except Exception as e:
            print(f"Error saving raw data: {e}")
    
    def load_raw(self, target_date: date) -> RawDataBundle | None:
        """Load raw data bundle from storage"""
        filename = self._get_filename("raw", target_date)
        try:
            if filename.exists():
                data = json.loads(filename.read_text())
                # TODO: Deserialize properly to RawDataBundle
                return None
        except Exception as e:
            print(f"Error loading raw data: {e}")
        return None
    
    # Normalized data
    def save_normalized(self, bundle: NormalizedDataBundle) -> None:
        """Save normalized data bundle"""
        filename = self._get_filename("normalized", bundle.period_date)
        try:
            data = asdict(bundle)
            filename.write_text(json.dumps(data, indent=2, default=str))
        except Exception as e:
            print(f"Error saving normalized data: {e}")
    
    def load_normalized(self, target_date: date) -> NormalizedDataBundle | None:
        """Load normalized data bundle"""
        filename = self._get_filename("normalized", target_date)
        try:
            if filename.exists():
                data = json.loads(filename.read_text())
                # TODO: Deserialize properly to NormalizedDataBundle
                return None
        except Exception as e:
            print(f"Error loading normalized data: {e}")
        return None
    
    # Metrics
    def save_metrics(self, bundle: MetricsBundle) -> None:
        """Save metrics bundle"""
        filename = self._get_filename("metrics", bundle.period_date)
        try:
            data = asdict(bundle)
            filename.write_text(json.dumps(data, indent=2, default=str))
        except Exception as e:
            print(f"Error saving metrics: {e}")
    
    def load_metrics(self, target_date: date) -> MetricsBundle | None:
        """Load metrics bundle"""
        filename = self._get_filename("metrics", target_date)
        try:
            if filename.exists():
                data = json.loads(filename.read_text())
                # TODO: Deserialize properly to MetricsBundle
                return None
        except Exception as e:
            print(f"Error loading metrics: {e}")
        return None
    
    # Facts
    def save_facts(self, bundle: FactsBundle) -> None:
        """Save facts bundle"""
        filename = self._get_filename("facts", bundle.period_date)
        try:
            data = asdict(bundle)
            filename.write_text(json.dumps(data, indent=2, default=str))
        except Exception as e:
            print(f"Error saving facts: {e}")
    
    def load_facts(self, target_date: date) -> FactsBundle | None:
        """Load facts bundle"""
        filename = self._get_filename("facts", target_date)
        try:
            if filename.exists():
                data = json.loads(filename.read_text())
                # TODO: Deserialize properly to FactsBundle
                return None
        except Exception as e:
            print(f"Error loading facts: {e}")
        return None
