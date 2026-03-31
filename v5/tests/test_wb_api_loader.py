"""
Tests for WBAPILoader and related parsers.

Run with: pytest v5/tests/test_wb_api_loader.py -v
"""

import pytest
from datetime import date
from unittest.mock import Mock, AsyncMock, patch
import asyncio

from domain.contracts import (
    RawDataBundle,
    RawAdsData,
    RawOrdersData,
    RawMarginsData,
)
from domain.cabinet import Cabinet, CabinetConfig, CabinetContext
from infrastructure.sources.wb_api_loader import WBAPILoader
from infrastructure.sources.parsers import (
    AdsParser,
    OrdersParser,
    MarginsParser,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def test_cabinet() -> Cabinet:
    """Create test cabinet"""
    return Cabinet(
        id="test_seller_001",
        name="Test Seller",
        api_key="test_api_key_12345",
        wb_seller_id="12345"
    )


@pytest.fixture
def test_cabinet_ctx(test_cabinet, tmp_path) -> CabinetContext:
    """Create test cabinet context"""
    return CabinetContext(
        cabinet=test_cabinet,
        config=CabinetConfig(),
        cabinet_root=tmp_path / "test_seller_001"
    )


@pytest.fixture
def test_date() -> date:
    """Test date"""
    return date(2024, 1, 15)


@pytest.fixture
def mock_ads_stats() -> list[dict]:
    """Mock ads stats response from WB API"""
    return [
        {
            "advertId": 123,
            "advertName": "Test Ad 1",
            "status": "active",
            "budget": 1000.0,
            "articlesWb": [
                {"nmId": 456789, "id": 456789},
                {"nmId": 456790, "id": 456790},
            ],
            "statistic": [
                {
                    "date": "2024-01-15T00:00:00",
                    "shows": 1000,
                    "clicks": 50,
                    "spend": 500.25,
                }
            ]
        },
        {
            "advertId": 124,
            "advertName": "Test Ad 2",
            "status": "paused",
            "budget": 500.0,
            "articlesWb": [],
            "statistic": [
                {
                    "date": "2024-01-15T00:00:00",
                    "shows": 2000,
                    "clicks": 100,
                    "spend": 1000.50,
                }
            ]
        }
    ]


@pytest.fixture
def mock_realization_data() -> list[dict]:
    """Mock realization report response"""
    return [
        {
            "rrdId": 1001,
            "nmId": 456789,
            "date": "2024-01-15",
            "quantity": 2,
            "saleSum": 5000.00,
            "commission": 500.00,
            "price": 2500.00,
            "costPrice": 1500.00,
            "status": "продажа",
        },
        {
            "rrdId": 1002,
            "nmId": 456790,
            "date": "2024-01-15",
            "quantity": 1,
            "saleSum": 3000.00,
            "commission": 300.00,
            "price": 3000.00,
            "costPrice": 1800.00,
            "status": "продажа",
        },
        {
            "rrdId": 1003,
            "nmId": 456789,
            "date": "2024-01-15",
            "quantity": 1,
            "saleSum": 5000.00,
            "commission": 500.00,
            "price": 2500.00,
            "costPrice": 1500.00,
            "status": "возврат",
            "reasonReturn": "Damaged",
        }
    ]


@pytest.fixture
def mock_funnel_data() -> dict:
    """Mock sales funnel response"""
    return {
        "data": {
            "products": [
                {
                    "nmId": 456789,
                    "title": "Test Product 1",
                    "imprCount": 5000,
                    "addToCartCount": 200,
                    "orderCount": 50,
                    "revenue": 250000.00,
                    "commission": 25000.00,
                    "rating": 4.5,
                    "feedbackCount": 100,
                }
            ]
        }
    }


# =============================================================================
# Parser Tests
# =============================================================================

class TestAdsParser:
    """Tests for AdsParser"""
    
    def test_parse_ads_stats(self, mock_ads_stats, test_date):
        """Test parsing ads stats"""
        result = AdsParser.parse_ads_stats(mock_ads_stats, test_date)
        
        assert len(result) == 2
        assert result[0].ad_id == "123"
        assert result[0].name == "Test Ad 1"
        assert result[0].views == 1000
        assert result[0].clicks == 50
        assert result[0].spend == 500.25
        assert len(result[0].sku_ids) == 2
        assert "456789" in result[0].sku_ids
        
        assert result[1].ad_id == "124"
        assert result[1].status == "paused"
    
    def test_parse_ads_stats_ignores_wrong_dates(self, test_date):
        """Test that parser ignores stats from other dates"""
        wrong_date_stats = [
            {
                "advertId": 100,
                "advertName": "Ad",
                "statistic": [
                    {
                        "date": "2024-01-20T00:00:00",  # Different date
                        "shows": 1000,
                        "clicks": 50,
                        "spend": 500.0,
                    }
                ]
            }
        ]
        
        result = AdsParser.parse_ads_stats(wrong_date_stats, test_date)
        
        # Should still create ad, but with 0 stats since no matching date
        assert len(result) == 1
        assert result[0].views == 0
        assert result[0].clicks == 0


class TestOrdersParser:
    """Tests for OrdersParser"""
    
    def test_parse_orders_from_realization(self, mock_realization_data, test_date):
        """Test parsing orders from realization report"""
        result = OrdersParser.parse_orders_from_realization(mock_realization_data, test_date)
        
        # Should get 2 orders (not the return)
        assert len(result) == 2
        
        assert result[0].sku_id == "456789"
        assert result[0].quantity == 2
        assert result[0].revenue == 5000.00
        assert result[0].commission == 500.00
        
        assert result[1].sku_id == "456790"
        assert result[1].quantity == 1
    
    def test_parse_orders_filters_by_date(self, test_date):
        """Test that orders are filtered by date"""
        wrong_date_data = [
            {
                "rrdId": 1001,
                "nmId": 456789,
                "date": "2024-01-20",  # Different date
                "quantity": 1,
                "saleSum": 1000.00,
                "commission": 100.00,
                "status": "продажа",
            }
        ]
        
        result = OrdersParser.parse_orders_from_realization(wrong_date_data, test_date)
        
        # Should be empty since date doesn't match
        assert len(result) == 0


class TestMarginsParser:
    """Tests for MarginsParser"""
    
    def test_parse_margins(self, mock_realization_data, test_date):
        """Test parsing margins"""
        result = MarginsParser.parse_margins_from_realization(mock_realization_data, test_date)
        
        # Should get 2 unique margins (ignores returns)
        assert len(result) == 2
        
        assert result[0].sku_id == "456789"
        assert result[0].cost_price == 1500.00
        assert result[0].selling_price == 2500.00
        assert abs(result[0].margin_percent - 40.0) < 0.01  # (2500-1500)/2500 * 100
        
        assert result[1].sku_id == "456790"
    
    def test_parse_margins_skips_invalid(self, test_date):
        """Test that invalid margin records are skipped"""
        invalid_data = [
            {
                "rrdId": 1001,
                "nmId": 456789,
                "date": "2024-01-15",
                "status": "продажа",
                "price": 0,  # Invalid
                "costPrice": 1000.00,
            },
            {
                "rrdId": 1002,
                "nmId": 456790,
                "date": "2024-01-15",
                "status": "продажа",
                "price": 2000.00,
                "costPrice": 0,  # Invalid
            }
        ]
        
        result = MarginsParser.parse_margins_from_realization(invalid_data, test_date)
        
        assert len(result) == 0


# =============================================================================
# WBAPILoader Tests
# =============================================================================

class TestWBAPILoader:
    """Tests for WBAPILoader"""
    
    def test_missing_api_key_raises_error(self, test_cabinet_ctx):
        """Test that missing API key raises ValueError"""
        test_cabinet_ctx.cabinet.api_key = ""
        loader = WBAPILoader()
        
        with pytest.raises(ValueError, match="no API key"):
            asyncio.run(loader.load_data(test_cabinet_ctx, date.today()))
    
    @pytest.mark.asyncio
    async def test_load_data_returns_raw_bundle(
        self,
        test_cabinet_ctx,
        test_date,
        mock_ads_stats,
        mock_realization_data,
        mock_funnel_data,
    ):
        """Test that load_data returns valid RawDataBundle"""
        
        loader = WBAPILoader()
        
        # Mock the async client
        with patch('infrastructure.sources.wb_api_loader.AsyncWBClient') as MockClient, \
             patch('infrastructure.sources.wb_api_loader.aiohttp.ClientSession'):
            
            mock_client = MockClient.return_value
            mock_client.fetch_ads_stats = AsyncMock(
                return_value=(mock_ads_stats, [123, 124])
            )
            mock_client.fetch_sales_funnel = AsyncMock(
                return_value=mock_funnel_data
            )
            mock_client.fetch_realization_report = AsyncMock(
                return_value=mock_realization_data
            )
            mock_client.fetch_stocks = AsyncMock(return_value=[])
            
            result = await loader.load_data(test_cabinet_ctx, test_date)
        
        # Validate result structure
        assert isinstance(result, RawDataBundle)
        assert result.cabinet_id == "test_seller_001"
        assert result.period_date == test_date
        assert result.source == "api"
        
        # Validate data is loaded
        assert len(result.ads) > 0
        assert len(result.orders) > 0
        assert len(result.margins) > 0
        
        # Check specific values
        assert result.ads[0].ad_id == "123"
        assert result.ads[0].views == 1000
        assert result.ads[0].clicks == 50


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests"""
    
    @pytest.mark.asyncio
    async def test_full_pipeline(
        self,
        test_cabinet_ctx,
        test_date,
        mock_ads_stats,
        mock_realization_data,
        mock_funnel_data,
    ):
        """Test full data loading and parsing pipeline"""
        
        loader = WBAPILoader()
        
        with patch('infrastructure.sources.wb_api_loader.AsyncWBClient') as MockClient, \
             patch('infrastructure.sources.wb_api_loader.aiohttp.ClientSession'):
            
            mock_client = MockClient.return_value
            mock_client.fetch_ads_stats = AsyncMock(
                return_value=(mock_ads_stats, [123, 124])
            )
            mock_client.fetch_sales_funnel = AsyncMock(
                return_value=mock_funnel_data
            )
            mock_client.fetch_realization_report = AsyncMock(
                return_value=mock_realization_data
            )
            mock_client.fetch_stocks = AsyncMock(return_value=[])
            
            bundle = await loader.load_data(test_cabinet_ctx, test_date)
        
        # Verify we can access all data types
        assert bundle.cabinet_id
        assert bundle.ads
        assert bundle.orders
        assert bundle.margins
        assert bundle.returns  # Should have at least 1 return
        
        # Verify data quality
        for ad in bundle.ads:
            assert ad.ad_id
            assert ad.date == test_date
        
        for order in bundle.orders:
            assert order.sku_id
            assert order.revenue >= 0
            assert order.date == test_date
        
        for margin in bundle.margins:
            assert margin.sku_id
            assert margin.selling_price > 0
            assert margin.date == test_date


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
