"""
Unified financial data loader - tries new API first, falls back to legacy.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from datetime import datetime

from ..api.wb_client import WBApiClient
from .models import FinancialLoadResult, LoadStatus, FinanceAPISource
from .finance_normalizer import FinanceNormalizer


class FinanceLoader:
    """
    Loads financial data from WB API endpoints.
    
    Primary: /api/finance/v1/sales-reports/detailed (new)
    Fallback: /api/v5/supplier/reportDetailByPeriod (legacy)
    """

    def __init__(self, client: WBApiClient):
        self.client = client
        self.normalizer = FinanceNormalizer()

    def load(
        self,
        date_from: str,
        date_to: Optional[str] = None,
    ) -> FinancialLoadResult:
        """
        Load financial data for date range.
        
        Args:
            date_from: Start date (YYYY-MM-DD)
            date_to: End date (YYYY-MM-DD), defaults to date_from
            
        Returns:
            FinancialLoadResult with status, rows, and diagnostics
        """
        if not date_to:
            date_to = date_from

        start_time = time.time()

        # Try new API first
        result = self._try_new_api(date_from, date_to)
        if result.is_success():
            result.duration_seconds = time.time() - start_time
            return result

        # Fallback to legacy API
        result = self._try_legacy_api(date_from, date_to)
        if result.is_success():
            result.status = LoadStatus.FALLBACK_USED
            result.fallback_reason = "New API failed or returned no data"
            result.duration_seconds = time.time() - start_time
            return result

        # Both failed
        result = FinancialLoadResult(
            status=LoadStatus.BOTH_FAILED,
            api_source=FinanceAPISource.MISSING,
            error_message="Both new and legacy API failed to load financial data",
            duration_seconds=time.time() - start_time,
        )
        return result

    def _try_new_api(self, date_from: str, date_to: str) -> FinancialLoadResult:
        """Try loading from new finance API endpoint."""
        try:
            # /api/finance/v1/sales-reports/detailed?dateFrom=YYYY-MM-DD&dateTo=YYYY-MM-DD
            raw_result = self.client.get(
                "/api/finance/v1/sales-reports/detailed",
                params={"dateFrom": date_from, "dateTo": date_to},
                timeout=30,
            )

            if not raw_result:
                return FinancialLoadResult(
                    status=LoadStatus.MISSING,
                    error_message="New API returned empty response",
                )

            # Extract rows from response (structure depends on API version)
            rows = self._extract_rows_from_new_api(raw_result)
            if not rows:
                return FinancialLoadResult(
                    status=LoadStatus.MISSING,
                    error_message="New API returned no rows",
                )

            # Normalize rows
            normalized_rows = self.normalizer.normalize_rows(
                rows,
                api_source=FinanceAPISource.NEW_FINANCE_API,
            )

            return FinancialLoadResult(
                status=LoadStatus.SUCCESS,
                rows=normalized_rows,
                api_source=FinanceAPISource.NEW_FINANCE_API,
                rows_attempted=len(rows),
                rows_parsed=len(normalized_rows),
                rows_with_errors=len(rows) - len(normalized_rows),
                **self.normalizer.get_diagnostics(),
            )

        except Exception as e:
            return FinancialLoadResult(
                status=LoadStatus.MISSING,
                error_message=f"New API error: {str(e)}",
            )

    def _try_legacy_api(self, date_from: str, date_to: str) -> FinancialLoadResult:
        """Try loading from legacy supplier report endpoint."""
        try:
            # /api/v5/supplier/reportDetailByPeriod?dateFrom=YYYY-MM-DD&dateTo=YYYY-MM-DD
            raw_result = self.client.get(
                "/api/v5/supplier/reportDetailByPeriod",
                params={"dateFrom": date_from, "dateTo": date_to},
                timeout=30,
            )

            if not raw_result:
                return FinancialLoadResult(
                    status=LoadStatus.MISSING,
                    error_message="Legacy API returned empty response",
                )

            # Extract rows from response
            rows = self._extract_rows_from_legacy_api(raw_result)
            if not rows:
                return FinancialLoadResult(
                    status=LoadStatus.MISSING,
                    error_message="Legacy API returned no rows",
                )

            # Normalize rows
            normalized_rows = self.normalizer.normalize_rows(
                rows,
                api_source=FinanceAPISource.LEGACY_SUPPLIER_API,
            )

            return FinancialLoadResult(
                status=LoadStatus.SUCCESS,
                rows=normalized_rows,
                api_source=FinanceAPISource.LEGACY_SUPPLIER_API,
                rows_attempted=len(rows),
                rows_parsed=len(normalized_rows),
                rows_with_errors=len(rows) - len(normalized_rows),
                **self.normalizer.get_diagnostics(),
            )

        except Exception as e:
            return FinancialLoadResult(
                status=LoadStatus.MISSING,
                error_message=f"Legacy API error: {str(e)}",
            )

    def _extract_rows_from_new_api(self, response: Any) -> List[Dict[str, Any]]:
        """Extract financial rows from new API response."""
        if isinstance(response, dict):
            # Try various possible response structures
            if "data" in response:
                data = response["data"]
                if isinstance(data, list):
                    return data
                if isinstance(data, dict) and "rows" in data:
                    rows = data["rows"]
                    if isinstance(rows, list):
                        return rows
            if "rows" in response:
                rows = response["rows"]
                if isinstance(rows, list):
                    return rows

        if isinstance(response, list):
            return response

        return []

    def _extract_rows_from_legacy_api(self, response: Any) -> List[Dict[str, Any]]:
        """Extract financial rows from legacy API response."""
        if isinstance(response, dict):
            # Legacy API often has structure: {data: [{...}, {...}]}
            if "data" in response:
                data = response["data"]
                if isinstance(data, list):
                    return data
            # Or direct list
            if "rows" in response:
                rows = response["rows"]
                if isinstance(rows, list):
                    return rows

        if isinstance(response, list):
            return response

        return []
