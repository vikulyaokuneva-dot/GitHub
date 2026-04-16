"""
Tests for FinancialSnapshot integration with FinanceLoader (PHASE 2).
"""

import pytest
from v3.financial.snapshot_builder import build_financial_snapshot_from_loader
from v3.financial.models import (
    FinancialRow,
    FinancialLoadResult,
    LoadStatus,
    FinanceAPISource,
)
from v3.domain.financial_snapshot import FinancialStatus, AlignmentStatus


class TestSnapshotLoaderIntegration:
    """Test building FinancialSnapshot from loader results."""

    def test_snapshot_from_successful_load(self):
        """Test building snapshot from successful loader result."""
        # Create normalized rows
        rows = [
            FinancialRow(
                date="2026-04-15",
                sku=12345,
                quantity=5,
                revenue=1000.0,
                wb_commission=100.0,
                logistics=50.0,
                storage=20.0,
                penalties=0.0,
                deductions=5.0,
                tax=120.0,
                cost_price=500.0,
                api_source=FinanceAPISource.NEW_FINANCE_API,
            ),
            FinancialRow(
                date="2026-04-15",
                sku=67890,
                quantity=10,
                revenue=2000.0,
                wb_commission=200.0,
                logistics=100.0,
                storage=40.0,
                penalties=0.0,
                deductions=10.0,
                tax=240.0,
                cost_price=1000.0,
                api_source=FinanceAPISource.NEW_FINANCE_API,
            ),
        ]
        
        load_result = FinancialLoadResult(
            status=LoadStatus.SUCCESS,
            rows=rows,
            api_source=FinanceAPISource.NEW_FINANCE_API,
            rows_attempted=2,
            rows_parsed=2,
        )
        
        snapshot = build_financial_snapshot_from_loader(
            target_date="2026-04-15",
            load_result=load_result,
            actual_date="2026-04-15",
        )
        
        assert snapshot.status == FinancialStatus.FULL
        assert snapshot.is_aligned()
        assert snapshot.components.revenue == 3000.0
        assert snapshot.components.cost_price == 1500.0
        assert snapshot.components.wb_commission == 300.0
        assert snapshot.rows_loaded == 2

    def test_snapshot_from_lagged_load(self):
        """Test building snapshot from lagged financial data."""
        rows = [
            FinancialRow(
                date="2026-04-14",  # Previous day
                sku=12345,
                quantity=5,
                revenue=1000.0,
                wb_commission=100.0,
                logistics=50.0,
                storage=20.0,
                penalties=0.0,
                deductions=5.0,
                tax=120.0,
                cost_price=500.0,
                api_source=FinanceAPISource.LEGACY_SUPPLIER_API,
            )
        ]
        
        load_result = FinancialLoadResult(
            status=LoadStatus.FALLBACK_USED,
            rows=rows,
            api_source=FinanceAPISource.LEGACY_SUPPLIER_API,
            rows_attempted=1,
            rows_parsed=1,
            fallback_reason="New API failed",
        )
        
        snapshot = build_financial_snapshot_from_loader(
            target_date="2026-04-15",
            load_result=load_result,
            actual_date="2026-04-14",  # Previous day
        )
        
        assert snapshot.status == FinancialStatus.LAGGED
        assert not snapshot.is_aligned()
        assert snapshot.alignment.days_lag == 1
        assert snapshot.alignment.reason == "Data lagged by 1 day(s)"

    def test_snapshot_from_empty_result(self):
        """Test building snapshot when loader returns no rows."""
        load_result = FinancialLoadResult(
            status=LoadStatus.BOTH_FAILED,
            rows=[],
            api_source=FinanceAPISource.MISSING,
        )
        
        snapshot = build_financial_snapshot_from_loader(
            target_date="2026-04-15",
            load_result=load_result,
            actual_date="2026-04-15",
        )
        
        assert snapshot.is_missing()
        assert snapshot.status == FinancialStatus.MISSING

    def test_snapshot_profit_calculations(self):
        """Test profit calculations in snapshot."""
        rows = [
            FinancialRow(
                date="2026-04-15",
                sku=12345,
                quantity=5,
                revenue=1000.0,
                wb_commission=100.0,
                logistics=50.0,
                storage=20.0,
                penalties=10.0,
                deductions=5.0,
                tax=120.0,
                cost_price=400.0,
                api_source=FinanceAPISource.NEW_FINANCE_API,
            )
        ]
        
        load_result = FinancialLoadResult(
            status=LoadStatus.SUCCESS,
            rows=rows,
            api_source=FinanceAPISource.NEW_FINANCE_API,
            rows_attempted=1,
            rows_parsed=1,
        )
        
        snapshot = build_financial_snapshot_from_loader(
            target_date="2026-04-15",
            load_result=load_result,
            actual_date="2026-04-15",
        )
        
        # gross_profit = revenue - cost_price - commission
        # = 1000 - 400 - 100 = 500
        assert snapshot.components.gross_profit == 500.0
        
        # net_profit = revenue - cost_price - commission - logistics - storage - penalties - deductions
        # = 1000 - 400 - 100 - 50 - 20 - 10 - 5 = 415
        assert snapshot.components.net_profit == 415.0
        
        # margin_pct = (net_profit / revenue) * 100 = (415 / 1000) * 100 = 41.5
        assert snapshot.components.margin_pct == 41.5

    def test_snapshot_multiple_sku_aggregation(self):
        """Test aggregation of multiple SKUs in snapshot."""
        rows = [
            FinancialRow(
                date="2026-04-15",
                sku=12345,
                quantity=5,
                revenue=1000.0,
                wb_commission=100.0,
                logistics=50.0,
                storage=20.0,
                penalties=0.0,
                deductions=5.0,
                tax=120.0,
                cost_price=500.0,
                api_source=FinanceAPISource.NEW_FINANCE_API,
            ),
            FinancialRow(
                date="2026-04-15",
                sku=67890,
                quantity=10,
                revenue=2000.0,
                wb_commission=200.0,
                logistics=100.0,
                storage=40.0,
                penalties=10.0,
                deductions=10.0,
                tax=240.0,
                cost_price=1000.0,
                api_source=FinanceAPISource.NEW_FINANCE_API,
            ),
        ]
        
        load_result = FinancialLoadResult(
            status=LoadStatus.SUCCESS,
            rows=rows,
            api_source=FinanceAPISource.NEW_FINANCE_API,
            rows_attempted=2,
            rows_parsed=2,
        )
        
        snapshot = build_financial_snapshot_from_loader(
            target_date="2026-04-15",
            load_result=load_result,
            actual_date="2026-04-15",
        )
        
        # Sum across SKUs
        assert snapshot.components.revenue == 3000.0
        assert snapshot.components.wb_commission == 300.0
        assert snapshot.components.logistics == 150.0
        assert snapshot.components.storage == 60.0
        assert snapshot.components.cost_price == 1500.0

    def test_snapshot_tracks_source(self):
        """Test that snapshot tracks API source correctly."""
        rows = [
            FinancialRow(
                date="2026-04-15",
                sku=12345,
                quantity=5,
                revenue=1000.0,
                wb_commission=100.0,
                logistics=50.0,
                storage=20.0,
                penalties=0.0,
                deductions=5.0,
                tax=120.0,
                cost_price=500.0,
                api_source=FinanceAPISource.NEW_FINANCE_API,
            )
        ]
        
        load_result = FinancialLoadResult(
            status=LoadStatus.SUCCESS,
            rows=rows,
            api_source=FinanceAPISource.NEW_FINANCE_API,
        )
        
        snapshot = build_financial_snapshot_from_loader(
            target_date="2026-04-15",
            load_result=load_result,
            actual_date="2026-04-15",
        )
        
        assert snapshot.source.value == "finance_api_new"
        assert snapshot.source_endpoint == "/api/finance/v1/sales-reports/detailed"

    def test_snapshot_tracks_fallback(self):
        """Test that snapshot tracks when fallback was used."""
        rows = [
            FinancialRow(
                date="2026-04-15",
                sku=12345,
                quantity=5,
                revenue=1000.0,
                wb_commission=100.0,
                logistics=50.0,
                storage=20.0,
                penalties=0.0,
                deductions=5.0,
                tax=120.0,
                cost_price=500.0,
                api_source=FinanceAPISource.LEGACY_SUPPLIER_API,
            )
        ]
        
        load_result = FinancialLoadResult(
            status=LoadStatus.FALLBACK_USED,
            rows=rows,
            api_source=FinanceAPISource.LEGACY_SUPPLIER_API,
            fallback_reason="New API returned no data",
        )
        
        snapshot = build_financial_snapshot_from_loader(
            target_date="2026-04-15",
            load_result=load_result,
            actual_date="2026-04-15",
        )
        
        assert snapshot.diagnostics.finance_fallback_used
        assert "no data" in snapshot.diagnostics.fallback_reason.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
