"""
Tests for Financial Snapshot contract and builder (PHASE 1).

Tests basic functionality of FinancialSnapshot isolation layer.
"""

import pytest
from datetime import datetime
from v3.domain.financial_snapshot import (
    FinancialSnapshot,
    FinancialStatus,
    AlignmentStatus,
    DataSource,
    FinancialComponents,
    ComponentStatus,
    make_missing_snapshot,
)
from v3.financial import build_financial_snapshot_from_kernel, FinancialSnapshotBuilder


class TestFinancialSnapshotContract:
    """Test FinancialSnapshot contract structure and semantics."""

    def test_aligned_snapshot(self):
        """Test snapshot with aligned dates."""
        snapshot = FinancialSnapshot(
            target_date="2026-04-15",
            actual_date="2026-04-15",
            status=FinancialStatus.FULL,
            source=DataSource.FINANCE_API_NEW,
            components=FinancialComponents(
                revenue=1000.0,
                cost_price=500.0,
                wb_commission=100.0,
                net_profit=200.0,
                margin_pct=20.0,
            ),
        )
        
        assert snapshot.is_aligned()
        assert snapshot.is_complete()
        assert not snapshot.is_lagged()
        assert snapshot.alignment.date_aligned
        assert snapshot.alignment.days_lag == 0

    def test_lagged_snapshot(self):
        """Test snapshot with lagged dates."""
        snapshot = FinancialSnapshot(
            target_date="2026-04-15",
            actual_date="2026-04-14",
            status=FinancialStatus.LAGGED,
            source=DataSource.LEGACY_ENDPOINT,
            components=FinancialComponents(revenue=1000.0),
        )
        
        assert not snapshot.is_aligned()
        assert snapshot.is_lagged()
        assert snapshot.alignment.days_lag == 1

    def test_partial_snapshot(self):
        """Test snapshot with partial data."""
        component_status = ComponentStatus()
        component_status.revenue = True
        component_status.cost_price = False  # Missing
        component_status.net_profit = False  # Missing
        
        snapshot = FinancialSnapshot(
            target_date="2026-04-15",
            actual_date="2026-04-15",
            status=FinancialStatus.PARTIAL,
            source=DataSource.LEGACY_ENDPOINT,
            components=FinancialComponents(revenue=1000.0),
            component_status=component_status,
            completeness_pct=33.3,
        )
        
        assert snapshot.is_partial()
        assert not snapshot.is_complete()
        assert snapshot.completeness_pct < 100.0

    def test_missing_snapshot(self):
        """Test missing snapshot."""
        snapshot = make_missing_snapshot("2026-04-15")
        
        assert snapshot.is_missing()
        assert not snapshot.is_aligned()
        assert snapshot.status == FinancialStatus.MISSING

    def test_snapshot_serialization(self):
        """Test snapshot can be serialized to dict."""
        snapshot = FinancialSnapshot(
            target_date="2026-04-15",
            actual_date="2026-04-15",
            status=FinancialStatus.FULL,
            source=DataSource.FINANCE_API_NEW,
        )
        
        data = snapshot.to_dict()
        
        assert data["target_date"] == "2026-04-15"
        assert data["status"] == "full"
        assert data["source"] == "finance_api_new"
        assert "components" in data
        assert "alignment" in data


class TestFinancialSnapshotBuilder:
    """Test FinancialSnapshotBuilder functionality."""

    def test_build_from_financial_kpi(self):
        """Test building snapshot from financial_kpi dict."""
        financial_kpi = {
            "revenue": 1000.0,
            "cost_price": 500.0,
            "wb_commission": 100.0,
            "net_profit": 200.0,
            "is_partial": False,
            "confirmed": True,
            "financial_status": "ok",
            "kernel_rows_total": 10,
        }
        event_date_model = {
            "financial_date": "2026-04-15",
        }
        
        snapshot = build_financial_snapshot_from_kernel(
            target_date="2026-04-15",
            financial_kpi=financial_kpi,
            event_date_model=event_date_model,
        )
        
        assert snapshot.target_date == "2026-04-15"
        assert snapshot.actual_date == "2026-04-15"
        assert snapshot.components.revenue == 1000.0
        assert snapshot.components.net_profit == 200.0
        assert snapshot.rows_loaded == 10

    def test_build_with_lagged_data(self):
        """Test building snapshot with lagged financial data."""
        financial_kpi = {
            "revenue": 1000.0,
            "is_partial": False,
            "confirmed": False,
            "financial_status": "partial",
        }
        event_date_model = {
            "financial_date": "2026-04-14",  # Previous day
        }
        
        snapshot = build_financial_snapshot_from_kernel(
            target_date="2026-04-15",
            financial_kpi=financial_kpi,
            event_date_model=event_date_model,
        )
        
        assert snapshot.actual_date == "2026-04-14"
        assert not snapshot.is_aligned()
        assert snapshot.status == FinancialStatus.LAGGED

    def test_build_missing_data(self):
        """Test building snapshot when no data available."""
        snapshot = build_financial_snapshot_from_kernel(
            target_date="2026-04-15",
            financial_kpi={},
            event_date_model={},
        )
        
        assert snapshot.is_missing()
        assert snapshot.status == FinancialStatus.MISSING


class TestFinancialSnapshotDownstreamParity:
    """Test that FinancialSnapshot can support downstream layers."""

    def test_snapshot_exports_financial_metrics(self):
        """Test snapshot exports all necessary financial metrics."""
        snapshot = FinancialSnapshot(
            target_date="2026-04-15",
            actual_date="2026-04-15",
            status=FinancialStatus.FULL,
            components=FinancialComponents(
                revenue=1000.0,
                cost_price=500.0,
                wb_commission=100.0,
                logistics=50.0,
                storage=20.0,
                penalties=10.0,
                deductions=5.0,
                net_profit=200.0,
                margin_pct=20.0,
            ),
        )
        
        # Downstream should be able to extract these
        assert snapshot.components.revenue > 0
        assert snapshot.components.net_profit > 0
        assert snapshot.components.margin_pct > 0

    def test_snapshot_alignment_visible_to_report(self):
        """Test that alignment status is visible for reporting."""
        snapshot_aligned = FinancialSnapshot(
            target_date="2026-04-15",
            actual_date="2026-04-15",
            status=FinancialStatus.FULL,
            alignment=None,  # Will use default
        )
        
        snapshot_lagged = FinancialSnapshot(
            target_date="2026-04-15",
            actual_date="2026-04-14",
            status=FinancialStatus.LAGGED,
        )
        
        # Report layer should be able to see alignment status
        assert snapshot_aligned.is_aligned()
        assert not snapshot_lagged.is_aligned()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
