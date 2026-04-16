"""
Tests for FinanceNormalizer (PHASE 2).
"""

import pytest
from v3.financial.finance_normalizer import FinanceNormalizer
from v3.financial.models import FinanceAPISource, FinancialRow


class TestFinanceNormalizer:
    """Test financial row normalization from both API formats."""

    def test_normalize_new_api_rows(self):
        """Test normalizing rows from new finance API."""
        normalizer = FinanceNormalizer()
        
        # Simulate new API response format
        raw_rows = [
            {
                "date": "2026-04-15",
                "nmId": 12345,
                "quantity": 5,
                "ppvzForPay": 1000.0,
                "ppvzSalesCommission": 100.0,
                "deliveryRub": 50.0,
                "storageFee": 20.0,
                "penaltyAmount": 0.0,
                "deduction": 5.0,
                "tax": 120.0,
            }
        ]
        
        normalized = normalizer.normalize_rows(raw_rows, FinanceAPISource.NEW_FINANCE_API)
        
        assert len(normalized) == 1
        row = normalized[0]
        assert row.date == "2026-04-15"
        assert row.sku == 12345
        assert row.quantity == 5
        assert row.revenue == 1000.0
        assert row.wb_commission == 100.0
        assert row.logistics == 50.0
        assert row.api_source == FinanceAPISource.NEW_FINANCE_API

    def test_normalize_legacy_api_rows(self):
        """Test normalizing rows from legacy API."""
        normalizer = FinanceNormalizer()
        
        # Simulate legacy API response format (different field names)
        raw_rows = [
            {
                "sale_dt": "2026-04-15",
                "article": 12345,
                "qty": 5,
                "sum": 1000.0,
                "commission": 100.0,
                "delivery_rub": 50.0,
                "storage_fee": 20.0,
                "penalty": 0.0,
                "acquiringFee": 5.0,
                "ndfl": 120.0,
            }
        ]
        
        normalized = normalizer.normalize_rows(raw_rows, FinanceAPISource.LEGACY_SUPPLIER_API)
        
        assert len(normalized) == 1
        row = normalized[0]
        assert row.date == "2026-04-15"
        assert row.sku == 12345
        assert row.quantity == 5
        assert row.revenue == 1000.0
        assert row.wb_commission == 100.0
        assert row.api_source == FinanceAPISource.LEGACY_SUPPLIER_API

    def test_normalize_missing_required_fields(self):
        """Test handling of missing required fields."""
        normalizer = FinanceNormalizer()
        
        # Row missing date
        raw_rows = [
            {
                "nmId": 12345,
                "quantity": 5,
                "ppvzForPay": 1000.0,
            }
        ]
        
        normalized = normalizer.normalize_rows(raw_rows, FinanceAPISource.NEW_FINANCE_API)
        
        assert len(normalized) == 0
        assert "date" in normalizer.missing_required_fields

    def test_normalize_string_money_parsing(self):
        """Test safe parsing of money fields from strings."""
        normalizer = FinanceNormalizer()
        
        raw_rows = [
            {
                "date": "2026-04-15",
                "nmId": 12345,
                "quantity": "5",
                "ppvzForPay": "1000.50",  # String
                "ppvzSalesCommission": "100,00",  # European format
                "deliveryRub": 50.0,
                "storageFee": 20.0,
                "penaltyAmount": 0,
                "deduction": 5.0,
                "tax": 120.0,
            }
        ]
        
        normalized = normalizer.normalize_rows(raw_rows, FinanceAPISource.NEW_FINANCE_API)
        
        assert len(normalized) == 1
        row = normalized[0]
        assert row.revenue == 1000.50
        assert row.wb_commission == 100.0  # Parsed from string
        assert row.quantity == 5

    def test_normalize_empty_rows(self):
        """Test handling of empty row list."""
        normalizer = FinanceNormalizer()
        
        normalized = normalizer.normalize_rows([], FinanceAPISource.NEW_FINANCE_API)
        
        assert len(normalized) == 0

    def test_normalize_multiple_rows(self):
        """Test normalizing multiple rows."""
        normalizer = FinanceNormalizer()
        
        raw_rows = [
            {
                "date": "2026-04-15",
                "nmId": 12345,
                "quantity": 5,
                "ppvzForPay": 1000.0,
                "ppvzSalesCommission": 100.0,
                "deliveryRub": 50.0,
                "storageFee": 20.0,
                "penaltyAmount": 0.0,
                "deduction": 5.0,
                "tax": 120.0,
            },
            {
                "date": "2026-04-15",
                "nmId": 67890,
                "quantity": 10,
                "ppvzForPay": 2000.0,
                "ppvzSalesCommission": 200.0,
                "deliveryRub": 100.0,
                "storageFee": 40.0,
                "penaltyAmount": 0.0,
                "deduction": 10.0,
                "tax": 240.0,
            }
        ]
        
        normalized = normalizer.normalize_rows(raw_rows, FinanceAPISource.NEW_FINANCE_API)
        
        assert len(normalized) == 2
        assert normalized[0].sku == 12345
        assert normalized[1].sku == 67890

    def test_normalize_date_formats(self):
        """Test parsing different date formats."""
        normalizer = FinanceNormalizer()
        
        test_cases = [
            {"date": "2026-04-15", "expected": "2026-04-15"},
            {"date": "15.04.2026", "expected": "2026-04-15"},
            {"date": "15/04/2026", "expected": "2026-04-15"},
            {"date": "20260415", "expected": "2026-04-15"},
        ]
        
        for test_case in test_cases:
            normalizer = FinanceNormalizer()
            raw_rows = [
                {
                    "date": test_case["date"],
                    "nmId": 12345,
                    "quantity": 5,
                    "ppvzForPay": 1000.0,
                    "ppvzSalesCommission": 100.0,
                    "deliveryRub": 50.0,
                    "storageFee": 20.0,
                    "penaltyAmount": 0.0,
                    "deduction": 5.0,
                    "tax": 120.0,
                }
            ]
            
            normalized = normalizer.normalize_rows(raw_rows, FinanceAPISource.NEW_FINANCE_API)
            assert len(normalized) == 1
            assert normalized[0].date == test_case["expected"]

    def test_normalize_field_mapping_tracked(self):
        """Test that field mappings are tracked."""
        normalizer = FinanceNormalizer()
        
        raw_rows = [
            {
                "date": "2026-04-15",
                "nmId": 12345,
                "quantity": 5,
                "ppvzForPay": 1000.0,
                "ppvzSalesCommission": 100.0,
                "deliveryRub": 50.0,
                "storageFee": 20.0,
                "penaltyAmount": 0.0,
                "deduction": 5.0,
                "tax": 120.0,
            }
        ]
        
        normalized = normalizer.normalize_rows(raw_rows, FinanceAPISource.NEW_FINANCE_API)
        
        row = normalized[0]
        mapping = row.source_field_mapping
        assert mapping["date"] == "date"
        assert mapping["sku"] == "nmId"
        assert mapping["revenue"] == "ppvzForPay"

    def test_normalize_zero_values_handled(self):
        """Test that zero values are preserved."""
        normalizer = FinanceNormalizer()
        
        raw_rows = [
            {
                "date": "2026-04-15",
                "nmId": 12345,
                "quantity": 0,
                "ppvzForPay": 0.0,
                "ppvzSalesCommission": 0.0,
                "deliveryRub": 0.0,
                "storageFee": 0.0,
                "penaltyAmount": 0.0,
                "deduction": 0.0,
                "tax": 0.0,
            }
        ]
        
        normalized = normalizer.normalize_rows(raw_rows, FinanceAPISource.NEW_FINANCE_API)
        
        assert len(normalized) == 1
        row = normalized[0]
        assert row.quantity == 0
        assert row.revenue == 0.0
        assert row.wb_commission == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
