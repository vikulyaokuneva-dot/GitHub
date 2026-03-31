"""Cabinet storage – persistence layer for bundles"""

import json
from datetime import date
from pathlib import Path
from dataclasses import asdict

from domain import (
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
    
    # Raw data
    def save_raw(self, bundle: RawDataBundle) -> None:
        """Save raw data bundle"""
        # TODO: Implement JSON serialization
        pass
    
    def load_raw(self, target_date: date) -> RawDataBundle | None:
        """Load raw data bundle from storage"""
        # TODO: Implement loading
        pass
    
    # Normalized data
    def save_normalized(self, bundle: NormalizedDataBundle) -> None:
        """Save normalized data bundle"""
        # TODO: Implement
        pass
    
    def load_normalized(self, target_date: date) -> NormalizedDataBundle | None:
        """Load normalized data bundle"""
        # TODO: Implement
        pass
    
    # Metrics
    def save_metrics(self, bundle: MetricsBundle) -> None:
        """Save metrics bundle"""
        # TODO: Implement
        pass
    
    def load_metrics(self, target_date: date) -> MetricsBundle | None:
        """Load metrics bundle"""
        # TODO: Implement
        pass
    
    # Facts
    def save_facts(self, bundle: FactsBundle) -> None:
        """Save facts bundle"""
        # TODO: Implement
        pass
    
    def load_facts(self, target_date: date) -> FactsBundle | None:
        """Load facts bundle"""
        # TODO: Implement
        pass
