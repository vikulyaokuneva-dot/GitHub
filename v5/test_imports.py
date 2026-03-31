#!/usr/bin/env python3
"""
Quick test to verify all imports work correctly.
Run: python -m v5.test_imports
"""

import sys
from pathlib import Path

def test_imports():
    """Test all critical imports"""
    
    print("[v5] Testing imports...")
    
    try:
        # Core imports
        print("  ✓ domain.contracts")
        from v5.domain.contracts import RawDataBundle, NormalizedDataBundle
        
        print("  ✓ domain.cabinet")
        from v5.domain.cabinet import Cabinet, CabinetContext, CabinetConfig
        
        print("  ✓ domain.enums")
        from v5.domain.enums import RunMode, DataSource, ProcessingPhase
        
        # Infrastructure imports
        print("  ✓ infrastructure.wb_api_client")
        from v5.infrastructure.wb_api_client import AsyncWBClient
        
        print("  ✓ infrastructure.sources")
        from v5.infrastructure.sources import WBAPILoader, FileReportLoader
        
        print("  ✓ infrastructure.storage")
        from v5.infrastructure.storage import CabinetStorage
        
        # Analytics imports
        print("  ✓ analytics.normalization")
        from v5.analytics.normalization import Normalizer
        
        print("  ✓ analytics.metrics_engine")
        from v5.analytics.metrics_engine import MetricsEngine
        
        print("  ✓ analytics.facts_builder")
        from v5.analytics.facts_builder import FactsBuilder
        
        # Orchestrator
        print("  ✓ orchestrator")
        from v5.orchestrator import Orchestrator
        
        # Config
        print("  ✓ config")
        from v5.config import get_config
        
        print("\n✅ All imports successful!")
        return True
        
    except Exception as e:
        print(f"\n❌ Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1)
