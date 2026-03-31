"""Data normalization – convert raw data to unified format"""

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
        # TODO: Implement normalization
        # 1. Validate raw data
        # 2. Transform RawAdsData → NormalizedAds
        # 3. Transform RawOrdersData → NormalizedSKU
        # 4. Calculate basic metrics (CTR, spend per impression, etc.)
        # 5. Handle edge cases (division by 0, missing data, etc.)
        # 6. Return NormalizedDataBundle
        
        raise NotImplementedError("Normalizer.normalize() not yet implemented")
