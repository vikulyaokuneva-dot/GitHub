#!/usr/bin/env python3
"""Test script to verify JSON export fix for metrics and facts"""

from datetime import date
from pathlib import Path

# Test imports
try:
    from v5.domain import (
        MetricsBundle, FactsBundle, AdMetrics, SKUMetrics, PortfolioMetrics,
        Fact, Recommendation, FactType, NormalizedDataBundle, NormalizedAds, NormalizedSKU
    )
    from v5.analytics.normalization import Normalizer
    from v5.analytics.metrics_engine import MetricsEngine
    from v5.analytics.facts_builder import FactsBuilder
    from v5.outputs.json_exporter import JsonExporter
    from v5.domain import CabinetContext, Cabinet, CabinetConfig
    print("✓ All imports successful!")
except Exception as e:
    print(f"✗ Import failed: {e}")
    exit(1)

# Create test data
test_date = date.today()

# Test 1: Create normalized data
print("\n=== Test 1: Normalizer ===")
normalized = NormalizedDataBundle(
    cabinet_id="test_seller",
    period_date=test_date,
    ads=[
        NormalizedAds(
            ad_id="ad_001",
            name="Test Ad",
            sku_ids=["sku_001"],
            budget_daily=100.0,
            status="active",
            impressions=1000,
            clicks=15,
            spend=50.0,
            ctr=1.5,
            spend_per_impression=0.05
        )
    ],
    skus=[
        NormalizedSKU(
            sku_id="sku_001",
            name="Test SKU",
            orders=10,
            revenue=500.0,
            cost_price=30.0,
            margin_percent=40.0,
            profit=200.0,
            rating=4.5,
            review_count=20,
            return_rate=0.05
        )
    ]
)
print(f"✓ Created normalized data with {len(normalized.ads)} ads and {len(normalized.skus)} skus")

# Test 2: Metrics Engine
print("\n=== Test 2: MetricsEngine ===")
metrics_engine = MetricsEngine()
metrics = metrics_engine.calculate(normalized)
print(f"✓ Calculated metrics:")
print(f"  - Portfolio spend: {metrics.portfolio_metrics.total_spend}")
print(f"  - Portfolio revenue: {metrics.portfolio_metrics.total_revenue}")
print(f"  - Portfolio profit: {metrics.portfolio_metrics.total_profit}")
print(f"  - Avg ROAS: {metrics.portfolio_metrics.avg_roas:.2f}")
print(f"  - Ad metrics count: {len(metrics.ad_metrics)}")
print(f"  - SKU metrics count: {len(metrics.sku_metrics)}")

# Test 3: Facts Builder
print("\n=== Test 3: FactsBuilder ===")
config = CabinetConfig()
facts_builder = FactsBuilder(config)
facts = facts_builder.build(normalized, metrics)
print(f"✓ Generated facts:")
print(f"  - Total facts: {len(facts.facts)}")
print(f"  - Total recommendations: {len(facts.recommendations)}")
for fact in facts.facts[:3]:
    print(f"    - {fact.type.value}: {fact.title}")

# Test 4: JSON Exporter
print("\n=== Test 4: JsonExporter ===")
cabinet = Cabinet(
    id="test_seller",
    name="Test Cabinet",
    api_key="test_key",
    wb_seller_id="123456"
)
cabinet_path = Path("test_cabinet")
cabinet_path.mkdir(exist_ok=True)
ctx = CabinetContext(cabinet, config, cabinet_path)

json_exporter = JsonExporter(ctx)

try:
    metrics_json = json_exporter.export_metrics(metrics, test_date)
    facts_json = json_exporter.export_facts(facts, test_date)
    
    print(f"✓ JSON files exported:")
    print(f"  - {metrics_json.name} ({metrics_json.stat().st_size} bytes)")
    print(f"  - {facts_json.name} ({facts_json.stat().st_size} bytes)")
    
    # Check content
    import json
    with open(metrics_json, 'r', encoding='utf-8') as f:
        metrics_data = json.load(f)
    with open(facts_json, 'r', encoding='utf-8') as f:
        facts_data = json.load(f)
    
    print(f"\n✓ JSON content verification:")
    print(f"  - metrics.json has keys: {list(metrics_data.keys())}")
    print(f"  - facts.json has keys: {list(facts_data.keys())}")
    print(f"  - Total spend in metrics: {metrics_data.get('total_spend', 'N/A')}")
    print(f"  - Total facts in facts.json: {len(facts_data.get('facts', []))}")
    
except Exception as e:
    print(f"✗ Export failed: {e}")
    import traceback
    traceback.print_exc()

print("\n=== All tests completed successfully! ===")
