"""Data normalization – convert raw data to unified format"""

from datetime import date
from ..domain import RawDataBundle, NormalizedDataBundle, CabinetContext


class Normalizer:
    """Transforms raw data into normalized format"""
    
    def normalize(self, raw: RawDataBundle) -> NormalizedDataBundle:
        """
        Convert RawDataBundle to NormalizedDataBundle.
        
        This transformation is independent of the source (API or report).
        Both API and file sources should produce equivalent results.
        
        Args:
            raw: Raw data bundle (source="api" or "report")
            
        Returns:
            NormalizedDataBundle with unified structure
        """
        # Basic implementation - just copy data with minimal transformation
        # TODO: Full implementation with proper transformations
        
        return NormalizedDataBundle(
            source=raw.source,
            date=raw.date or date.today(),
            ads=[],  # Will be transformed in future phases
            skus=[],  # Will be transformed in future phases
            metadata={"normalized": True}
        )
