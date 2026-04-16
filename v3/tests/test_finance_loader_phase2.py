"""
Tests for FinanceLoader (PHASE 2).
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from v3.financial.finance_loader import FinanceLoader
from v3.financial.models import LoadStatus, FinanceAPISource


class TestFinanceLoader:
    """Test unified finance loader with fallback logic."""

    def test_load_new_api_success(self):
        """Test successful load from new API."""
        # Mock client
        mock_client = Mock()
        mock_client.get = Mock(return_value={
            "data": [
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
        })
        
        loader = FinanceLoader(mock_client)
        result = loader.load("2026-04-15")
        
        # Debug: Print result status
        if result.status != LoadStatus.SUCCESS:
            print(f"Expected SUCCESS, got {result.status}")
            print(f"Error: {result.error_message}")
            print(f"Rows attempted: {result.rows_attempted}")
            print(f"Rows parsed: {result.rows_parsed}")
        
        assert result.status == LoadStatus.SUCCESS, f"Status was {result.status}, error: {result.error_message}"
        assert result.api_source == FinanceAPISource.NEW_FINANCE_API
        assert len(result.rows) == 1
        assert result.rows[0].sku == 12345

    def test_load_new_api_fails_fallback_succeeds(self):
        """Test fallback to legacy API when new API fails."""
        mock_client = Mock()
        
        # First call (new API) returns empty
        # Second call (legacy API) returns data
        mock_client.get = Mock(side_effect=[
            {},  # New API returns empty
            {
                "data": [
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
            }
        ])
        
        loader = FinanceLoader(mock_client)
        result = loader.load("2026-04-15")
        
        assert result.status == LoadStatus.FALLBACK_USED
        assert result.api_source == FinanceAPISource.LEGACY_SUPPLIER_API
        assert len(result.rows) == 1
        assert result.rows[0].sku == 12345
        assert "api" in result.fallback_reason.lower()

    def test_load_both_apis_fail(self):
        """Test when both new and legacy APIs fail."""
        mock_client = Mock()
        mock_client.get = Mock(side_effect=Exception("Connection error"))
        
        loader = FinanceLoader(mock_client)
        result = loader.load("2026-04-15")
        
        assert result.status == LoadStatus.BOTH_FAILED
        assert result.api_source == FinanceAPISource.MISSING
        assert len(result.rows) == 0
        assert "failed" in result.error_message.lower()

    def test_load_date_range(self):
        """Test loading data for date range."""
        mock_client = Mock()
        mock_client.get = Mock(return_value={
            "data": [
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
        })
        
        loader = FinanceLoader(mock_client)
        result = loader.load("2026-04-15", "2026-04-16")
        
        assert result.status == LoadStatus.SUCCESS
        
        # Verify API was called with correct params
        call_args = mock_client.get.call_args_list[0]
        assert call_args[0][0] == "/api/finance/v1/sales-reports/detailed"
        assert call_args[1]["params"]["dateFrom"] == "2026-04-15"
        assert call_args[1]["params"]["dateTo"] == "2026-04-16"

    def test_load_extracts_rows_from_different_structures(self):
        """Test extracting rows from various API response structures."""
        test_cases = [
            # Structure 1: {data: [...]}
            {"data": [{"date": "2026-04-15", "nmId": 1, "quantity": 1, "ppvzForPay": 100.0,
                       "ppvzSalesCommission": 10.0, "deliveryRub": 5.0, "storageFee": 2.0,
                       "penaltyAmount": 0.0, "deduction": 0.0, "tax": 10.0}]},
            
            # Structure 2: {rows: [...]}
            {"rows": [{"date": "2026-04-15", "nmId": 1, "quantity": 1, "ppvzForPay": 100.0,
                       "ppvzSalesCommission": 10.0, "deliveryRub": 5.0, "storageFee": 2.0,
                       "penaltyAmount": 0.0, "deduction": 0.0, "tax": 10.0}]},
            
            # Structure 3: Direct list
            [{"date": "2026-04-15", "nmId": 1, "quantity": 1, "ppvzForPay": 100.0,
              "ppvzSalesCommission": 10.0, "deliveryRub": 5.0, "storageFee": 2.0,
              "penaltyAmount": 0.0, "deduction": 0.0, "tax": 10.0}],
        ]
        
        for response_structure in test_cases:
            mock_client = Mock()
            mock_client.get = Mock(return_value=response_structure)
            
            loader = FinanceLoader(mock_client)
            result = loader.load("2026-04-15")
            
            assert result.status == LoadStatus.SUCCESS
            assert len(result.rows) == 1
            assert result.rows[0].sku == 1

    def test_load_tracks_parse_diagnostics(self):
        """Test that parse diagnostics are tracked."""
        mock_client = Mock()
        mock_client.get = Mock(return_value={
            "data": [
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
        })
        
        loader = FinanceLoader(mock_client)
        result = loader.load("2026-04-15")
        
        assert result.rows_attempted == 1
        assert result.rows_parsed == 1
        assert result.rows_with_errors == 0

    def test_load_with_parsing_errors(self):
        """Test that rows with parsing errors are tracked."""
        mock_client = Mock()
        mock_client.get = Mock(return_value={
            "data": [
                # Valid row
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
                # Invalid row (missing nmId)
                {
                    "date": "2026-04-15",
                    "quantity": 5,
                    "ppvzForPay": 1000.0,
                    "ppvzSalesCommission": 100.0,
                },
            ]
        })
        
        loader = FinanceLoader(mock_client)
        result = loader.load("2026-04-15")
        
        assert result.status == LoadStatus.SUCCESS
        assert result.rows_attempted == 2
        assert result.rows_parsed == 1
        assert result.rows_with_errors == 1

    def test_load_empty_response_handled(self):
        """Test handling of empty response."""
        mock_client = Mock()
        mock_client.get = Mock(return_value=None)
        
        loader = FinanceLoader(mock_client)
        result = loader.load("2026-04-15")
        
        assert result.status == LoadStatus.BOTH_FAILED
        assert len(result.rows) == 0

    def test_load_duration_tracked(self):
        """Test that load duration is tracked."""
        mock_client = Mock()
        mock_client.get = Mock(return_value={
            "data": [
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
        })
        
        loader = FinanceLoader(mock_client)
        result = loader.load("2026-04-15")
        
        assert result.duration_seconds >= 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
