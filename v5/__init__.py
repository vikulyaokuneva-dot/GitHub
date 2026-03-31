"""
WB Analytics v5 – Unified Data Platform
Production-ready analytics for Wildberries sellers.

Modes:
  - daily: Pull data from WB API
  - audit: Process uploaded reports files
  
Both modes produce unified analytics and recommendations.
"""

__version__ = "5.0.0"
__author__ = "Your Name"

from .domain.contracts import (
    RawDataBundle,
    NormalizedDataBundle,
    MetricsBundle,
    FactsBundle,
)
from .domain.cabinet import Cabinet, CabinetContext

__all__ = [
    "RawDataBundle",
    "NormalizedDataBundle",
    "MetricsBundle",
    "FactsBundle",
    "Cabinet",
    "CabinetContext",
]
