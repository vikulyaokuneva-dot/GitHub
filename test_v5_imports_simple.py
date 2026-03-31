#!/usr/bin/env python
"""Simple import test for v5"""

import sys
from pathlib import Path

# Add current dir to path
repo_root = Path(__file__).parent
sys.path.insert(0, str(repo_root))

print("[1/7] Testing v5.domain imports...")
try:
    from v5.domain import (
        Cabinet, CabinetContext, CabinetConfig,
        RawAdsData, RawOrdersData, RawMarginsData, RawReturnsData, RawRatingsData,
        RawDataBundle,
    )
    print("✓ v5.domain OK")
except Exception as e:
    print(f"✗ v5.domain FAILED: {e}")
    sys.exit(1)

print("[2/7] Testing v5.infrastructure imports...")
try:
    from v5.infrastructure import WBAPILoader, FileReportLoader, CabinetStorage
    print("✓ v5.infrastructure OK")
except Exception as e:
    print(f"✗ v5.infrastructure FAILED: {e}")
    sys.exit(1)

print("[3/7] Testing v5.analytics imports...")
try:
    from v5.analytics import Normalizer, MetricsEngine, FactsBuilder, DecisionsEngine
    print("✓ v5.analytics OK")
except Exception as e:
    print(f"✗ v5.analytics FAILED: {e}")
    sys.exit(1)

print("[4/7] Testing v5.outputs imports...")
try:
    from v5.outputs import ReportGenerator, JsonExporter
    print("✓ v5.outputs OK")
except Exception as e:
    print(f"✗ v5.outputs FAILED: {e}")
    sys.exit(1)

print("[5/7] Testing v5.memory imports...")
try:
    from v5.memory import StateManager
    print("✓ v5.memory OK")
except Exception as e:
    print(f"✗ v5.memory FAILED: {e}")
    sys.exit(1)

print("[6/7] Testing v5.orchestrator imports...")
try:
    from v5.orchestrator import Orchestrator
    print("✓ v5.orchestrator OK")
except Exception as e:
    print(f"✗ v5.orchestrator FAILED: {e}")
    sys.exit(1)

print("[7/7] Testing v5.entry imports...")
try:
    from v5.entry import main
    print("✓ v5.entry OK")
except Exception as e:
    print(f"✗ v5.entry FAILED: {e}")
    sys.exit(1)

print("\n✅ All imports successful!")
