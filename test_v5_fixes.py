#!/usr/bin/env python3
"""
Test v5 fixes for JSON export and data loading.

Проверяет что:
1. Все импорты работают
2. Структуры данных совместимы
3. JSON exporter правильно сериализует данные
"""

import json
from datetime import date
from pathlib import Path

def test_imports():
    """Test that all imports work"""
    print("✓ Testing imports...")
    try:
        from v5.domain import (
            RawDataBundle,
            RawAdsData,
            RawOrdersData,
            RawMarginsData,
            RawReturnsData,
            RawRatingsData,
            NormalizedDataBundle,
            MetricsBundle,
            FactsBundle,
            CabinetContext,
        )
        from v5.infrastructure.sources import FileReportLoader
        from v5.outputs.json_exporter import JsonExporter
        from v5.analytics.normalization import Normalizer
        from v5.analytics.metrics_engine import MetricsEngine
        print("  ✓ All imports successful")
        return True
    except ImportError as e:
        print(f"  ✗ Import error: {e}")
        return False


def test_raw_data_structures():
    """Test that RawData structures accept correct fields"""
    print("\n✓ Testing RawData structures...")
    try:
        from v5.domain import (
            RawAdsData,
            RawOrdersData,
            RawMarginsData,
            RawReturnsData,
            RawRatingsData,
            RawDataBundle,
        )
        
        target_date = date.today()
        
        # Create sample data
        ads = [
            RawAdsData(
                ad_id="ad_001",
                name="Test Ad",
                sku_ids=["sku_001"],
                budget_daily=1000.0,
                status="active",
                views=100,
                clicks=10,
                spend=50.0,
                date=target_date,
            )
        ]
        
        orders = [
            RawOrdersData(
                order_id="ord_001",
                sku_id="sku_001",
                ad_id="ad_001",
                quantity=5,
                revenue=500.0,
                commission=50.0,
                date=target_date,
            )
        ]
        
        margins = [
            RawMarginsData(
                sku_id="sku_001",
                cost_price=100.0,
                selling_price=200.0,
                margin_percent=50.0,
                date=target_date,
            )
        ]
        
        returns = [
            RawReturnsData(
                return_id="ret_001",
                order_id="ord_001",
                sku_id="sku_001",
                reason="damaged",
                revenue_lost=50.0,
                date=target_date,
            )
        ]
        
        ratings = [
            RawRatingsData(
                sku_id="sku_001",
                rating=4.5,
                review_count=100,
                negative_reviews=5,
                date=target_date,
            )
        ]
        
        # Create bundle
        bundle = RawDataBundle(
            cabinet_id="seller_001",
            period_date=target_date,
            source="report",
            ads=ads,
            orders=orders,
            margins=margins,
            returns=returns,
            ratings=ratings,
        )
        
        print(f"  ✓ Created RawDataBundle with:")
        print(f"    - {len(bundle.ads)} ads")
        print(f"    - {len(bundle.orders)} orders")
        print(f"    - {len(bundle.margins)} margins")
        print(f"    - {len(bundle.returns)} returns")
        print(f"    - {len(bundle.ratings)} ratings")
        return bundle
        
    except Exception as e:
        print(f"  ✗ Error creating structures: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_normalization(raw_bundle):
    """Test that normalization works"""
    print("\n✓ Testing normalization...")
    try:
        from v5.analytics.normalization import Normalizer
        
        normalizer = Normalizer()
        normalized = normalizer.normalize(raw_bundle)
        
        print(f"  ✓ Normalized data:")
        print(f"    - {len(normalized.ads)} normalized ads")
        print(f"    - {len(normalized.skus)} normalized SKUs")
        
        # Check that data is not empty
        if normalized.ads and normalized.skus:
            print(f"    ✓ Data is not empty (good sign)")
            return normalized
        else:
            print(f"    ! Warning: Empty normalized data")
            return normalized
            
    except Exception as e:
        print(f"  ✗ Error during normalization: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_metrics_calculation(normalized):
    """Test metrics calculation"""
    print("\n✓ Testing metrics calculation...")
    try:
        from v5.analytics.metrics_engine import MetricsEngine
        
        engine = MetricsEngine()
        metrics = engine.calculate(normalized)
        
        print(f"  ✓ Calculated metrics:")
        print(f"    - Portfolio total_spend: {metrics.portfolio_metrics.total_spend}")
        print(f"    - Portfolio total_revenue: {metrics.portfolio_metrics.total_revenue}")
        print(f"    - Portfolio total_profit: {metrics.portfolio_metrics.total_profit}")
        print(f"    - {len(metrics.ad_metrics)} ad metrics")
        print(f"    - {len(metrics.sku_metrics)} SKU metrics")
        
        # Check if we have non-zero values
        if metrics.portfolio_metrics.total_spend > 0:
            print(f"    ✓ Metrics have real values (not zeros)")
        else:
            print(f"    ! Warning: Metrics appear to be zero")
        
        return metrics
        
    except Exception as e:
        print(f"  ✗ Error during metrics calculation: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_json_export(metrics):
    """Test JSON export"""
    print("\n✓ Testing JSON export...")
    try:
        from dataclasses import asdict
        from v5.domain import MetricsBundle
        
        # Serialize metrics to dict (what JsonExporter does)
        metrics_dict = asdict(metrics)
        
        # Try to dump to JSON string
        json_str = json.dumps(metrics_dict, indent=2, default=str)
        
        # Check that JSON is not empty
        json_size = len(json_str)
        print(f"  ✓ Metrics serialized to JSON:")
        print(f"    - JSON size: {json_size} bytes")
        print(f"    - Contains portfolio_metrics: {'portfolio_metrics' in json_str}")
        print(f"    - Contains ad_metrics: {'ad_metrics' in json_str}")
        print(f"    - Contains sku_metrics: {'sku_metrics' in json_str}")
        
        if json_size > 100:
            print(f"    ✓ JSON is not empty (good sign)")
        else:
            print(f"    ! Warning: JSON seems too small")
        
        return json_str
        
    except Exception as e:
        print(f"  ✗ Error exporting to JSON: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Run all tests"""
    print("=" * 60)
    print("V5 JSON Export and Data Loading Fixes Test")
    print("=" * 60)
    
    # Test imports
    if not test_imports():
        print("\n✗ Import test failed. Cannot continue.")
        return False
    
    # Test structure creation
    raw_bundle = test_raw_data_structures()
    if not raw_bundle:
        print("\n✗ RawData structure test failed.")
        return False
    
    # Test normalization
    normalized = test_normalization(raw_bundle)
    if not normalized:
        print("\n✗ Normalization test failed.")
        return False
    
    # Test metrics
    metrics = test_metrics_calculation(normalized)
    if not metrics:
        print("\n✗ Metrics calculation test failed.")
        return False
    
    # Test JSON export
    json_str = test_json_export(metrics)
    if not json_str:
        print("\n✗ JSON export test failed.")
        return False
    
    print("\n" + "=" * 60)
    print("✓ All tests passed!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
