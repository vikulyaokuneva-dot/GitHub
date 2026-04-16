"""
Finance normalizer - converts both API formats to unified FinancialRow schema.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from .models import FinancialRow, FinanceAPISource


# Field alias mappings for both APIs
FIELD_ALIASES = {
    # Date fields
    "date": ("date", "sale_dt", "order_dt", "lastChangeDate", "create_dt", "dateFrom"),
    
    # SKU/Article
    "sku": ("nmId", "article", "sku", "product_id", "nm_id"),
    
    # Quantity
    "quantity": ("quantity", "qty", "Quantity", "product_quantity"),
    
    # Revenue/Payout fields
    "revenue": (
        "ppvzForPay", "seller_payout", "revenue", "retailAmount", 
        "sum", "amount", "paid_amount", "gross_revenue"
    ),
    
    # Commission fields
    "wb_commission": (
        "ppvzSalesCommission", "commission", "wb_commission", "commission_amount",
        "retailCommission", "commission_percent"
    ),
    
    # Logistics
    "logistics": (
        "deliveryRub", "delivery_rub", "logistics", "logistics_cost",
        "delivery_cost", "shipping"
    ),
    
    # Storage
    "storage": (
        "storageFee", "storage_fee", "storage", "warehouse_fee",
        "storage_cost"
    ),
    
    # Penalties
    "penalties": (
        "penaltyAmount", "penalty", "penalties", "fine",
        "penalty_amount"
    ),
    
    # Deductions
    "deductions": (
        "deduction", "deductions", "acquiringFee", "acquiring_fee",
        "fee", "adjustment"
    ),
    
    # Tax
    "tax": ("tax", "tax_amount", "ndfl", "tax_withheld"),
    
    # Cost price (COGS)
    "cost_price": ("cost_price", "cogs", "cost", "purchase_price"),
}


def _normalize_text(value: Any) -> str:
    """Safely convert to text."""
    if value is None:
        return ""
    text = str(value).strip()
    return text.replace("\u00a0", " ").replace(",", ".")


def _parse_date(value: Any) -> str:
    """Parse date to YYYY-MM-DD format."""
    if not value:
        return ""
    
    text = _normalize_text(value)
    if not text:
        return ""
    
    # Already YYYY-MM-DD?
    if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
        return text[:10]
    
    # Try parsing common formats
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y%m%d"):
        try:
            dt = datetime.strptime(text[:10], fmt)
            return dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            pass
    
    return text[:10] if len(text) >= 10 else ""


def _parse_decimal(value: Any) -> Tuple[float, bool]:
    """
    Parse value to float. Returns (value, was_parsed_from_string).
    """
    if value is None:
        return 0.0, False
    
    if isinstance(value, (int, float)):
        return float(value), False
    
    if isinstance(value, Decimal):
        return float(value), False
    
    text = _normalize_text(value)
    if not text:
        return 0.0, False
    
    try:
        dec = Decimal(text)
        rounded = float(dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        return rounded, True
    except (InvalidOperation, ValueError):
        return 0.0, False


def _pick_first_available(row: Dict[str, Any], aliases: Tuple[str, ...]) -> Tuple[Any, str]:
    """Get first non-empty value from aliases. Returns (value, used_key)."""
    for key in aliases:
        if key in row:
            val = row.get(key)
            text = _normalize_text(val)
            if text:
                return val, key
    return None, ""


class FinanceNormalizer:
    """Normalize financial rows from both API formats to unified schema."""

    def __init__(self):
        self.parse_errors: List[str] = []
        self.unmapped_fields: set = set()
        self.missing_required_fields: set = set()
        self.money_string_fields_parsed: set = set()

    def normalize_rows(
        self,
        rows: List[Dict[str, Any]],
        api_source: FinanceAPISource = FinanceAPISource.NEW_FINANCE_API,
    ) -> List[FinancialRow]:
        """Normalize list of rows from either API to unified FinancialRow schema."""
        normalized: List[FinancialRow] = []
        
        self.parse_errors.clear()
        self.unmapped_fields.clear()
        self.missing_required_fields.clear()
        self.money_string_fields_parsed.clear()

        if not rows:
            return normalized

        for row_dict in rows:
            if not isinstance(row_dict, dict):
                continue
            
            normalized_row = self._normalize_single_row(row_dict, api_source)
            if normalized_row:
                normalized.append(normalized_row)

        return normalized

    def _normalize_single_row(
        self,
        row: Dict[str, Any],
        api_source: FinanceAPISource,
    ) -> Optional[FinancialRow]:
        """Normalize single row from API response."""
        try:
            # Extract fields using aliases
            date, date_key = _pick_first_available(row, FIELD_ALIASES["date"])
            sku_val, sku_key = _pick_first_available(row, FIELD_ALIASES["sku"])
            qty_val, qty_key = _pick_first_available(row, FIELD_ALIASES["quantity"])
            revenue_val, revenue_key = _pick_first_available(row, FIELD_ALIASES["revenue"])
            commission_val, commission_key = _pick_first_available(row, FIELD_ALIASES["wb_commission"])
            logistics_val, logistics_key = _pick_first_available(row, FIELD_ALIASES["logistics"])
            storage_val, storage_key = _pick_first_available(row, FIELD_ALIASES["storage"])
            penalties_val, penalties_key = _pick_first_available(row, FIELD_ALIASES["penalties"])
            deductions_val, deductions_key = _pick_first_available(row, FIELD_ALIASES["deductions"])
            tax_val, tax_key = _pick_first_available(row, FIELD_ALIASES["tax"])
            cost_val, cost_key = _pick_first_available(row, FIELD_ALIASES["cost_price"])

            # Validate required fields
            parsed_date = _parse_date(date)
            if not parsed_date:
                self.missing_required_fields.add("date")
                return None

            try:
                sku_int = int(float(_normalize_text(sku_val or "")))
            except (ValueError, TypeError):
                self.missing_required_fields.add("sku")
                return None

            qty_float, qty_from_str = _parse_decimal(qty_val)
            qty_int = int(qty_float)

            # Parse money fields
            revenue_float, rev_from_str = _parse_decimal(revenue_val)
            commission_float, comm_from_str = _parse_decimal(commission_val)
            logistics_float, log_from_str = _parse_decimal(logistics_val)
            storage_float, stor_from_str = _parse_decimal(storage_val)
            penalties_float, pen_from_str = _parse_decimal(penalties_val)
            deductions_float, ded_from_str = _parse_decimal(deductions_val)
            tax_float, tax_from_str = _parse_decimal(tax_val)
            cost_float, cost_from_str = _parse_decimal(cost_val)

            # Track string fields that were parsed
            if rev_from_str:
                self.money_string_fields_parsed.add(revenue_key or "revenue")
            if comm_from_str:
                self.money_string_fields_parsed.add(commission_key or "wb_commission")
            if log_from_str:
                self.money_string_fields_parsed.add(logistics_key or "logistics")
            if stor_from_str:
                self.money_string_fields_parsed.add(storage_key or "storage")
            if pen_from_str:
                self.money_string_fields_parsed.add(penalties_key or "penalties")
            if ded_from_str:
                self.money_string_fields_parsed.add(deductions_key or "deductions")
            if tax_from_str:
                self.money_string_fields_parsed.add(tax_key or "tax")
            if cost_from_str:
                self.money_string_fields_parsed.add(cost_key or "cost_price")

            # Build field mapping for tracking
            field_mapping = {
                "date": date_key or "unknown",
                "sku": sku_key or "unknown",
                "quantity": qty_key or "unknown",
                "revenue": revenue_key or "unknown",
                "wb_commission": commission_key or "unknown",
                "logistics": logistics_key or "unknown",
                "storage": storage_key or "unknown",
                "penalties": penalties_key or "unknown",
                "deductions": deductions_key or "unknown",
                "tax": tax_key or "unknown",
                "cost_price": cost_key or "unknown",
            }

            return FinancialRow(
                date=parsed_date,
                sku=sku_int,
                quantity=qty_int,
                revenue=revenue_float,
                wb_commission=commission_float,
                logistics=logistics_float,
                storage=storage_float,
                penalties=penalties_float,
                deductions=deductions_float,
                tax=tax_float,
                cost_price=cost_float,
                source_field_mapping=field_mapping,
                api_source=api_source,
                original_row=row,
            )

        except Exception as e:
            self.parse_errors.append(f"Row parse error: {str(e)}")
            return None

    def get_diagnostics(self) -> Dict[str, Any]:
        """Export normalization diagnostics for FinancialLoadResult."""
        return {
            "parse_errors": self.parse_errors[:10],  # First 10 errors
            "unmapped_fields": self.unmapped_fields,
            "missing_required_fields": self.missing_required_fields,
        }
