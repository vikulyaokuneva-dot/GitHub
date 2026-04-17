"""
Financial Snapshot Builder

Isolates financial data assembly from the rest of the pipeline.
Responsible for:
1. Loading financial data (primary API or fallback)
2. Normalizing to unified format
3. Building FinancialSnapshot contract
4. Tracking status, alignment, and diagnostics

This layer sits between raw financial data and downstream consumers.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import re
from decimal import Decimal

from ..domain.financial_snapshot import (
    AlignmentStatus,
    ComponentStatus,
    DataSource,
    FinancialAlignment,
    FinancialComponents,
    FinancialDiagnostics,
    FinancialSnapshot,
    FinancialStatus,
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert value to float."""
    try:
        if value is None or value == "":
            return default
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, Decimal):
            return float(value)
        text = str(value).strip().replace(",", ".")
        return float(text) if text else default
    except (TypeError, ValueError):
        return default


class FinancialSnapshotBuilder:
    """Builds FinancialSnapshot from raw financial data."""

    def __init__(self, target_date: str):
        self.target_date = target_date
        self.diagnostics = FinancialDiagnostics()
        self.components = FinancialComponents()
        self.component_status = ComponentStatus()
        self.alignment = FinancialAlignment(
            target_date=target_date,
            actual_date="",
        )

    def load_from_daily_kpi(
        self,
        daily_kpi: Dict[str, Any],
        source: DataSource = DataSource.LEGACY_ENDPOINT,
        source_endpoint: str = "",
        actual_date: str = "",
    ) -> FinancialSnapshot:
        """
        Load financial data from current daily_kpi structure.
        This is the interim integration point for PHASE 1.
        """
        if not daily_kpi:
            return self._make_missing()

        # Extract financial components from daily_kpi
        self.components.revenue = _safe_float(daily_kpi.get("daily_revenue"))
        self.components.cost_price = _safe_float(daily_kpi.get("daily_cost_price"))
        self.components.wb_commission = _safe_float(daily_kpi.get("daily_wb_commission"))
        self.components.logistics = _safe_float(daily_kpi.get("daily_logistics"))
        self.components.storage = _safe_float(daily_kpi.get("daily_storage"))
        self.components.penalties = _safe_float(daily_kpi.get("daily_penalties"))
        self.components.deductions = _safe_float(daily_kpi.get("daily_deductions"))
        self.components.tax = _safe_float(daily_kpi.get("daily_tax"))
        self.components.gross_profit = _safe_float(daily_kpi.get("daily_gross_profit"))
        self.components.net_profit = _safe_float(daily_kpi.get("daily_net_profit"))
        self.components.margin_pct = _safe_float(daily_kpi.get("daily_margin_pct"))
        self.components.profitability_pct = _safe_float(daily_kpi.get("daily_profitability_pct"))
        self.components.seller_payout = _safe_float(daily_kpi.get("daily_seller_payout"))
        self.components.gross_revenue = _safe_float(daily_kpi.get("daily_gross_revenue"))

        # Track which components are available
        self._mark_available_components()

        # Set date and alignment
        actual_date = actual_date or self.target_date
        self.alignment.actual_date = actual_date
        self.alignment.date_aligned = actual_date == self.target_date
        self.alignment.days_lag = self._calc_days_lag(self.target_date, actual_date)

        # Determine completeness
        is_partial = bool(daily_kpi.get("is_partial", False))
        rows_loaded = daily_kpi.get("financial_rows_count", 0) or 0

        # Determine status
        if not rows_loaded:
            status = FinancialStatus.MISSING
            alignment_status = AlignmentStatus.MISSING
            reason = "No financial rows loaded"
        elif is_partial:
            status = FinancialStatus.PARTIAL
            alignment_status = (
                AlignmentStatus.ALIGNED
                if self.alignment.date_aligned
                else AlignmentStatus.LAGGED_FALLBACK
            )
            reason = "Partial financial data (some components missing)"
        elif not self.alignment.date_aligned:
            status = FinancialStatus.LAGGED
            alignment_status = AlignmentStatus.LAGGED_FALLBACK
            reason = f"Data lagged by {self.alignment.days_lag} day(s)"
        else:
            status = FinancialStatus.FULL
            alignment_status = AlignmentStatus.ALIGNED
            reason = "Full financial data, date aligned"

        self.alignment.alignment_status = alignment_status
        self.alignment.reason = reason

        # Detect if legacy fallback was used
        fallback_used = bool(daily_kpi.get("financial_fallback_used", False))
        if fallback_used:
            self.diagnostics.finance_fallback_used = True
            self.diagnostics.fallback_reason = daily_kpi.get("financial_fallback_reason", "")

        # Calculate completeness
        completeness = (
            self.component_status.available_count() / self.component_status.total_count() * 100
        )

        return FinancialSnapshot(
            target_date=self.target_date,
            actual_date=actual_date,
            status=status,
            source=source,
            source_endpoint=source_endpoint,
            rows_loaded=rows_loaded,
            alignment=self.alignment,
            components=self.components,
            component_status=self.component_status,
            completeness_pct=completeness,
            diagnostics=self.diagnostics,
        )

    def _mark_available_components(self) -> None:
        """Mark which components have non-zero values."""
        self.component_status.revenue = self.components.revenue > 0
        self.component_status.cost_price = self.components.cost_price > 0
        self.component_status.wb_commission = self.components.wb_commission > 0
        self.component_status.logistics = self.components.logistics > 0
        self.component_status.storage = self.components.storage > 0
        self.component_status.penalties = self.components.penalties > 0
        self.component_status.deductions = self.components.deductions > 0
        self.component_status.tax = self.components.tax > 0
        self.component_status.gross_profit = self.components.gross_profit > 0
        self.component_status.net_profit = self.components.net_profit > 0
        self.component_status.margin_pct = self.components.margin_pct > 0
        self.component_status.profitability_pct = self.components.profitability_pct > 0

    def _calc_days_lag(self, target_date: str, actual_date: str) -> int:
        """Calculate days between target and actual dates."""
        try:
            from datetime import datetime

            target = datetime.fromisoformat(target_date)
            actual = datetime.fromisoformat(actual_date)
            lag = (target - actual).days
            return max(0, lag)
        except Exception:
            return 0

    def load_from_normalized_rows(
        self,
        load_result: Any,  # FinancialLoadResult
        actual_date: str,
    ) -> FinancialSnapshot:
        """
        Load financial data from FinancialLoadResult (PHASE 2 - loader output).
        
        Args:
            load_result: FinancialLoadResult from FinanceLoader
            actual_date: The date these financials are for (YYYY-MM-DD)
        """
        # Import here to avoid circular imports
        from .models import FinanceAPISource, LoadStatus
        
        if not load_result or not load_result.is_success():
            return self._make_missing()

        # Aggregate normalized rows into financial components
        rows = load_result.rows if hasattr(load_result, 'rows') else []
        if not rows:
            return self._make_missing()

        # Sum across all rows per component
        total_revenue = 0.0
        total_cost_price = 0.0
        total_wb_commission = 0.0
        total_logistics = 0.0
        total_storage = 0.0
        total_penalties = 0.0
        total_deductions = 0.0
        total_tax = 0.0

        for row in rows:
            total_revenue += _safe_float(row.revenue if hasattr(row, 'revenue') else row.get('revenue'))
            total_cost_price += _safe_float(row.cost_price if hasattr(row, 'cost_price') else row.get('cost_price'))
            total_wb_commission += _safe_float(row.wb_commission if hasattr(row, 'wb_commission') else row.get('wb_commission'))
            total_logistics += _safe_float(row.logistics if hasattr(row, 'logistics') else row.get('logistics'))
            total_storage += _safe_float(row.storage if hasattr(row, 'storage') else row.get('storage'))
            total_penalties += _safe_float(row.penalties if hasattr(row, 'penalties') else row.get('penalties'))
            total_deductions += _safe_float(row.deductions if hasattr(row, 'deductions') else row.get('deductions'))
            total_tax += _safe_float(row.tax if hasattr(row, 'tax') else row.get('tax'))

        # Calculate derived metrics
        gross_profit = total_revenue - total_cost_price - total_wb_commission
        net_profit = total_revenue - total_cost_price - total_wb_commission - total_logistics - total_storage - total_penalties - total_deductions

        margin_pct = 0.0
        if total_revenue > 0.01:
            margin_pct = (net_profit / total_revenue) * 100.0

        profitability_pct = 0.0
        if total_cost_price > 0.01:
            profitability_pct = (net_profit / total_cost_price) * 100.0

        # Set components
        self.components.revenue = round(total_revenue, 2)
        self.components.cost_price = round(total_cost_price, 2)
        self.components.wb_commission = round(total_wb_commission, 2)
        self.components.logistics = round(total_logistics, 2)
        self.components.storage = round(total_storage, 2)
        self.components.penalties = round(total_penalties, 2)
        self.components.deductions = round(total_deductions, 2)
        self.components.tax = round(total_tax, 2)
        self.components.gross_profit = round(gross_profit, 2)
        self.components.net_profit = round(net_profit, 2)
        self.components.margin_pct = round(margin_pct, 2)
        self.components.profitability_pct = round(profitability_pct, 2)
        self.components.seller_payout = self.components.revenue

        # Mark available components
        self._mark_available_components()

        # Set alignment
        if not actual_date:
            actual_date = self.target_date

        self.alignment.actual_date = actual_date
        self.alignment.date_aligned = actual_date == self.target_date
        self.alignment.days_lag = self._calc_days_lag(self.target_date, actual_date)

        # Determine status
        api_source = load_result.api_source if hasattr(load_result, 'api_source') else FinanceAPISource.MISSING
        load_status = load_result.status if hasattr(load_result, 'status') else LoadStatus.MISSING

        status = FinancialStatus.FULL
        alignment_status = AlignmentStatus.ALIGNED
        reason = "Full financial data"

        if not self.alignment.date_aligned:
            status = FinancialStatus.LAGGED
            alignment_status = AlignmentStatus.LAGGED_FALLBACK
            reason = f"Data lagged by {self.alignment.days_lag} day(s)"

        # Map data source
        if api_source == FinanceAPISource.NEW_FINANCE_API:
            source = DataSource.FINANCE_API_NEW
            source_endpoint = "/api/finance/v1/sales-reports/detailed"
        elif api_source == FinanceAPISource.LEGACY_SUPPLIER_API:
            source = DataSource.LEGACY_ENDPOINT
            source_endpoint = "/api/v5/supplier/reportDetailByPeriod"
        else:
            source = DataSource.MISSING
            source_endpoint = ""

        self.alignment.alignment_status = alignment_status
        self.alignment.reason = reason

        # Track diagnostics
        if load_status == LoadStatus.FALLBACK_USED:
            self.diagnostics.finance_fallback_used = True
            self.diagnostics.fallback_reason = load_result.fallback_reason if hasattr(load_result, 'fallback_reason') else ""

        if hasattr(load_result, 'get_diagnostics'):
            diag_dict = load_result.get_diagnostics()
        else:
            diag_dict = {}

        # Merge diagnostics
        parse_errors = diag_dict.get('parse_errors', [])
        if parse_errors:
            self.diagnostics.parse_errors_count = len(parse_errors)

        unmapped = diag_dict.get('unmapped_fields', [])
        if unmapped:
            self.diagnostics.unmapped_fields = set(unmapped)

        missing = diag_dict.get('missing_required_fields', [])
        if missing:
            self.diagnostics.missing_required_fields = set(missing)

        money_parsed = diag_dict.get('money_string_fields_parsed', [])
        if money_parsed:
            self.diagnostics.money_string_fields_parsed = set(money_parsed)

        # Calculate completeness
        completeness = (
            self.component_status.available_count() / self.component_status.total_count() * 100
        )

        return FinancialSnapshot(
            target_date=self.target_date,
            actual_date=actual_date,
            status=status,
            source=source,
            source_endpoint=source_endpoint,
            rows_loaded=len(rows),
            alignment=self.alignment,
            components=self.components,
            component_status=self.component_status,
            completeness_pct=completeness,
            diagnostics=self.diagnostics,
        )

    def _make_missing(self) -> FinancialSnapshot:
        """Create missing-status snapshot."""
        self.alignment.alignment_status = AlignmentStatus.MISSING
        self.alignment.reason = "No financial data"
        return FinancialSnapshot(
            target_date=self.target_date,
            actual_date="",
            status=FinancialStatus.MISSING,
            source=DataSource.MISSING,
            alignment=self.alignment,
            components=self.components,
            component_status=self.component_status,
            completeness_pct=0.0,
            diagnostics=self.diagnostics,
        )


    def load_from_financial_kpi(
        self,
        financial_kpi: Dict[str, Any],
        event_date_model: Dict[str, Any],
        source: DataSource = DataSource.LEGACY_ENDPOINT,
    ) -> FinancialSnapshot:
        """
        Load financial data from financial_kpi structure (from kernel).
        This is used in PHASE 1 to bridge kernel output to FinancialSnapshot.
        """
        if not financial_kpi:
            return self._make_missing()

        # Extract from financial_kpi
        self.components.revenue = _safe_float(financial_kpi.get("revenue"))
        self.components.cost_price = _safe_float(financial_kpi.get("cost_price"))
        self.components.wb_commission = _safe_float(financial_kpi.get("wb_commission"))
        self.components.logistics = _safe_float(financial_kpi.get("logistics"))
        self.components.storage = _safe_float(financial_kpi.get("storage"))
        self.components.penalties = _safe_float(financial_kpi.get("penalties"))
        self.components.deductions = _safe_float(financial_kpi.get("deductions"))
        self.components.tax = _safe_float(financial_kpi.get("tax"))
        self.components.gross_profit = _safe_float(financial_kpi.get("gross_profit"))
        self.components.net_profit = _safe_float(financial_kpi.get("net_profit"))
        self.components.margin_pct = _safe_float(financial_kpi.get("margin_pct"))
        self.components.profitability_pct = _safe_float(financial_kpi.get("profitability_pct"))
        self.components.seller_payout = _safe_float(financial_kpi.get("seller_payout"))
        self.components.gross_revenue = _safe_float(financial_kpi.get("gross_revenue"))

        # Mark available components
        self._mark_available_components()

        # Get dates from event_date_model
        event_date_model = event_date_model or {}
        actual_date = str(event_date_model.get("financial_date") or self.target_date).strip()
        if not actual_date:
            actual_date = self.target_date

        self.alignment.actual_date = actual_date
        self.alignment.date_aligned = actual_date == self.target_date
        self.alignment.days_lag = self._calc_days_lag(self.target_date, actual_date)

        # Determine completeness and status
        is_partial = bool(financial_kpi.get("is_partial", False))
        confirmed = bool(financial_kpi.get("confirmed", False))
        financial_status_str = str(financial_kpi.get("financial_status", "unknown")).lower()
        financial_finality_status = str(financial_kpi.get("financial_finality_status", "")).strip().lower()
        financial_source = str(financial_kpi.get("financial_source", "")).strip().lower()
        if "." in financial_source:
            financial_source = financial_source.split(".")[-1]
        rows_value = financial_kpi.get(
            "kernel_rows_total",
            financial_kpi.get(
                "financial_rows_count",
                financial_kpi.get("rows_count", financial_kpi.get("financial_rows", 0)),
            ),
        )
        rows_loaded = _safe_float(rows_value) > 0
        contour_missing = bool(
            (not rows_loaded)
            or financial_source in {"missing", "unknown"}
            or financial_status_str == "missing"
            or financial_finality_status == "missing"
        )

        # Map financial status to FinancialStatus
        if contour_missing:
            status = FinancialStatus.MISSING
            alignment_status = AlignmentStatus.MISSING
            reason = "No financial data loaded"
        elif is_partial or financial_status_str in {"partial", "degraded"}:
            status = FinancialStatus.PARTIAL
            alignment_status = (
                AlignmentStatus.ALIGNED
                if self.alignment.date_aligned
                else AlignmentStatus.LAGGED_FALLBACK
            )
            reason = "Partial financial data"
        elif not self.alignment.date_aligned:
            status = FinancialStatus.LAGGED
            alignment_status = AlignmentStatus.LAGGED_FALLBACK
            reason = f"Data lagged by {self.alignment.days_lag} day(s)"
        else:
            status = FinancialStatus.FULL
            alignment_status = AlignmentStatus.ALIGNED
            reason = "Full financial data"

        self.alignment.alignment_status = alignment_status
        self.alignment.reason = reason

        # Calculate completeness
        completeness = (
            self.component_status.available_count() / self.component_status.total_count() * 100
        )

        return FinancialSnapshot(
            target_date=self.target_date,
            actual_date=actual_date,
            status=status,
            source=source,
            source_endpoint=financial_kpi.get("source_endpoint", ""),
            rows_loaded=int(_safe_float(financial_kpi.get("kernel_rows_total", 0))),
            alignment=self.alignment,
            components=self.components,
            component_status=self.component_status,
            completeness_pct=completeness,
            diagnostics=self.diagnostics,
        )


def build_financial_snapshot(
    target_date: str,
    daily_kpi: Dict[str, Any],
    source: DataSource = DataSource.LEGACY_ENDPOINT,
) -> FinancialSnapshot:
    """
    Build FinancialSnapshot from current daily_kpi structure.
    This is the integration point for downstream to read financial data.
    """
    builder = FinancialSnapshotBuilder(target_date)
    actual_date = daily_kpi.get("financial_date") or target_date
    return builder.load_from_daily_kpi(
        daily_kpi,
        source=source,
        actual_date=actual_date,
    )


def build_financial_snapshot_from_kernel(
    target_date: str,
    financial_kpi: Dict[str, Any],
    event_date_model: Dict[str, Any],
    source: DataSource = DataSource.FINANCE_API_NEW,
) -> FinancialSnapshot:
    """
    Build FinancialSnapshot from financial_kpi (kernel output).
    This is PHASE 1 integration point for pipeline.
    """
    builder = FinancialSnapshotBuilder(target_date)
    return builder.load_from_financial_kpi(
        financial_kpi,
        event_date_model=event_date_model,
        source=source,
    )


def build_financial_snapshot_from_loader(
    target_date: str,
    load_result: Any,
    actual_date: str,
) -> FinancialSnapshot:
    """
    Build FinancialSnapshot from FinanceLoader result (PHASE 2).
    
    This is the new path that uses unified loader + normalizer.
    """
    builder = FinancialSnapshotBuilder(target_date)
    return builder.load_from_normalized_rows(load_result, actual_date)
