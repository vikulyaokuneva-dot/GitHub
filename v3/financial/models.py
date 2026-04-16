"""
Financial data models for normalized rows and loader results.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from enum import Enum


class FinanceAPISource(str, Enum):
    """Which API endpoint supplied the data."""
    NEW_FINANCE_API = "new_finance_api"  # /api/finance/v1/sales-reports/detailed
    LEGACY_SUPPLIER_API = "legacy_supplier_api"  # /api/v5/supplier/reportDetailByPeriod
    MISSING = "missing"


class LoadStatus(str, Enum):
    """Status of API load attempt."""
    SUCCESS = "success"
    FALLBACK_USED = "fallback_used"
    BOTH_FAILED = "both_failed"
    MISSING = "missing"


@dataclass
class FinancialRow:
    """Single normalized financial row from either API."""
    date: str  # YYYY-MM-DD
    sku: int  # article number
    quantity: int
    revenue: float  # seller payout / gross revenue
    wb_commission: float
    logistics: float
    storage: float
    penalties: float
    deductions: float
    tax: float
    cost_price: float  # COGS (если доступна)
    
    # Metadata
    source_field_mapping: Dict[str, str] = field(default_factory=dict)  # какие поля откуда
    api_source: FinanceAPISource = FinanceAPISource.MISSING
    original_row: Optional[Dict[str, Any]] = None  # для debug

    def to_dict(self) -> Dict[str, Any]:
        """Export as dict."""
        return asdict(self)


@dataclass
class FinancialLoadResult:
    """Result of loading financial data from API."""
    status: LoadStatus
    rows: List[FinancialRow] = field(default_factory=list)
    api_source: FinanceAPISource = FinanceAPISource.MISSING
    
    # Diagnostics
    rows_attempted: int = 0
    rows_parsed: int = 0
    rows_with_errors: int = 0
    
    error_message: str = ""  # if load failed
    fallback_reason: str = ""  # why fallback was used
    
    parse_errors: List[str] = field(default_factory=list)
    unmapped_fields: set = field(default_factory=set)
    missing_required_fields: set = field(default_factory=set)
    
    # Timing
    duration_seconds: float = 0.0

    def is_success(self) -> bool:
        """True if any data was loaded."""
        return self.status in (LoadStatus.SUCCESS, LoadStatus.FALLBACK_USED)

    def to_dict(self) -> Dict[str, Any]:
        """Export as dict."""
        data = asdict(self)
        # Convert sets to lists for JSON serialization
        data["unmapped_fields"] = list(self.unmapped_fields)
        data["missing_required_fields"] = list(self.missing_required_fields)
        # Convert rows
        data["rows"] = [row.to_dict() if hasattr(row, 'to_dict') else row for row in self.rows]
        return data
