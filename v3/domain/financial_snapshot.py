"""
Financial Snapshot Contract - Isolated Financial Layer

This module defines the single source of truth for all financial data
in the daily pipeline. It separates operational KPI from financial metrics
and enforces explicit status/completeness semantics.

CORE PRINCIPLES:
1. Operational contour (orders/buyouts) is independent from financial contour
2. Financial snapshot always declares target_date, actual_date, and status
3. Lagged financial data are NOT interpreted as operational day summary
4. All legacy fallback paths are explicit in source and diagnostics
5. Downstream reads ONLY from this contract, not from scattered sources
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class FinancialStatus(str, Enum):
    """Status of financial data completeness and freshness."""
    FULL = "full"  # All required fields present, dates aligned
    LAGGED = "lagged"  # Valid data but from past date (fallback active)
    PARTIAL = "partial"  # Some components missing (is_partial=True)
    MISSING = "missing"  # No financial data at all
    UNKNOWN = "unknown"  # Status cannot be determined


class AlignmentStatus(str, Enum):
    """Date alignment between operational and financial contours."""
    ALIGNED = "aligned"  # actual_date == target_date
    LAGGED_FALLBACK = "lagged_fallback"  # using legacy endpoint, dates may differ
    MISSING = "missing"  # no financial data to align


class DataSource(str, Enum):
    """Where financial data originated."""
    FINANCE_API_NEW = "finance_api_new"  # /api/finance/v1/sales-reports/detailed
    LEGACY_ENDPOINT = "legacy_endpoint"  # /api/v5/supplier/reportDetailByPeriod
    MISSING = "missing"  # no data loaded


@dataclass
class ComponentStatus:
    """Track individual financial component availability."""
    revenue: bool = False
    cost_price: bool = False
    wb_commission: bool = False
    logistics: bool = False
    storage: bool = False
    penalties: bool = False
    deductions: bool = False
    loyalty_program: bool = False
    other_adjustments: bool = False
    tax: bool = False
    gross_profit: bool = False
    net_profit: bool = False
    margin_pct: bool = False
    profitability_pct: bool = False

    def available_count(self) -> int:
        """Count of available components."""
        return sum(1 for v in asdict(self).values() if v)

    def total_count(self) -> int:
        """Total tracked components."""
        return len(asdict(self))


@dataclass
class FinancialDiagnostics:
    """Diagnostics about financial data load and transformation."""
    rows_loaded: int = 0
    rows_with_errors: int = 0
    matched_fields: set[str] = field(default_factory=set)
    unmapped_fields: set[str] = field(default_factory=set)
    missing_required_fields: set[str] = field(default_factory=set)
    money_string_fields_parsed: set[str] = field(default_factory=set)
    parse_errors_count: int = 0
    deprecated_fields_seen: set[str] = field(default_factory=set)
    source_mode_counts: Dict[str, int] = field(default_factory=dict)
    finance_fallback_used: bool = False
    fallback_reason: str = ""
    api_error_message: str = ""
    raw_payload_sample: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, handling non-serializable fields."""
        return {
            "rows_loaded": self.rows_loaded,
            "rows_with_errors": self.rows_with_errors,
            "matched_fields": list(self.matched_fields),
            "unmapped_fields": list(self.unmapped_fields),
            "missing_required_fields": list(self.missing_required_fields),
            "money_string_fields_parsed": list(self.money_string_fields_parsed),
            "parse_errors_count": self.parse_errors_count,
            "deprecated_fields_seen": list(self.deprecated_fields_seen),
            "source_mode_counts": self.source_mode_counts,
            "finance_fallback_used": self.finance_fallback_used,
            "fallback_reason": self.fallback_reason,
            "api_error_message": self.api_error_message,
        }


@dataclass
class FinancialAlignment:
    """Describes how operational and financial dates relate."""
    date_aligned: bool = False  # target_date == actual_date
    alignment_status: AlignmentStatus = AlignmentStatus.MISSING
    target_date: str = ""  # requested operational date
    actual_date: str = ""  # date of actual financial data
    days_lag: int = 0  # how many days behind (0 = aligned)
    reason: str = ""  # explanation if not aligned


@dataclass
class FinancialComponents:
    """All financial metrics as floats (ready for calculations)."""
    seller_payout: float = 0.0
    revenue: float = 0.0
    gross_revenue: float = 0.0
    wb_commission: float = 0.0
    logistics: float = 0.0
    storage: float = 0.0
    penalties: float = 0.0
    deductions: float = 0.0
    loyalty_program: float = 0.0
    other_adjustments: float = 0.0
    tax: float = 0.0
    cost_price: float = 0.0
    gross_profit: float = 0.0
    net_profit: float = 0.0
    margin_pct: float = 0.0
    profitability_pct: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        """Export as dictionary."""
        return asdict(self)


@dataclass
class FinancialSnapshot:
    """
    Single source of truth for financial data in the daily pipeline.
    
    This contract is immutable and explicit about:
    - which date the financials apply to (target_date)
    - which date the data actually came from (actual_date)
    - whether data is complete, partial, lagged, or missing
    - which API endpoint was used (with fallback tracking)
    
    Downstream consumers read ONLY from this snapshot.
    """

    # Date semantics
    target_date: str  # requested operational date (YYYY-MM-DD)
    actual_date: str  # date of actual financial data (YYYY-MM-DD)

    # Status and source
    status: FinancialStatus = FinancialStatus.MISSING
    source: DataSource = DataSource.MISSING
    source_endpoint: str = ""  # which API returned data

    # Data counts
    rows_loaded: int = 0

    # Date alignment
    alignment: FinancialAlignment = field(default_factory=FinancialAlignment)

    # Financial metrics
    components: FinancialComponents = field(default_factory=FinancialComponents)

    # Component availability
    component_status: ComponentStatus = field(default_factory=ComponentStatus)

    # Overall completeness
    completeness_pct: float = 0.0  # 0-100: percent of available components

    # Diagnostics
    diagnostics: FinancialDiagnostics = field(default_factory=FinancialDiagnostics)

    def is_aligned(self) -> bool:
        """True if actual_date == target_date."""
        return self.alignment.date_aligned

    def is_complete(self) -> bool:
        """True if status is FULL and no missing components."""
        return self.status == FinancialStatus.FULL and self.completeness_pct >= 100.0

    def is_lagged(self) -> bool:
        """True if data is valid but from a past date."""
        return self.status == FinancialStatus.LAGGED

    def is_partial(self) -> bool:
        """True if some components are missing."""
        return self.status == FinancialStatus.PARTIAL

    def is_missing(self) -> bool:
        """True if no financial data at all."""
        return self.status == FinancialStatus.MISSING

    def to_dict(self) -> Dict[str, Any]:
        """Export as dictionary for serialization."""
        return {
            "target_date": self.target_date,
            "actual_date": self.actual_date,
            "status": self.status.value,
            "source": self.source.value,
            "source_endpoint": self.source_endpoint,
            "rows_loaded": self.rows_loaded,
            "alignment": {
                "date_aligned": self.alignment.date_aligned,
                "alignment_status": self.alignment.alignment_status.value,
                "target_date": self.alignment.target_date,
                "actual_date": self.alignment.actual_date,
                "days_lag": self.alignment.days_lag,
                "reason": self.alignment.reason,
            },
            "components": self.components.to_dict(),
            "component_status": asdict(self.component_status),
            "completeness_pct": self.completeness_pct,
            "diagnostics": self.diagnostics.to_dict(),
        }


def make_missing_snapshot(target_date: str) -> FinancialSnapshot:
    """Create a missing-status snapshot for when no data could be loaded."""
    return FinancialSnapshot(
        target_date=target_date,
        actual_date="",
        status=FinancialStatus.MISSING,
        source=DataSource.MISSING,
        alignment=FinancialAlignment(
            date_aligned=False,
            alignment_status=AlignmentStatus.MISSING,
            target_date=target_date,
            actual_date="",
            reason="No financial data loaded",
        ),
    )
