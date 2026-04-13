from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping

# Field aliases are extracted from v2 src/metrics.py and grouped by financial semantics.
# The migration step will keep formulas unchanged, but map rows to these semantic slots.
FINANCIAL_ROW_FIELD_ALIASES: Dict[str, tuple[str, ...]] = {
    "operation_name": (
        "supplier_oper_name",
        "supplierOperName",
        "operationTypeName",
        "doc_type_name",
    ),
    "operation_type": (
        "supplier_oper_type_name",
        "supplierOperTypeName",
        "supplier_oper_type",
        "supplierOperType",
    ),
    "sku": (
        "nm_id",
        "nmId",
        "nmID",
        "nm",
    ),
    "seller_sku": (
        "_supplier_article",
        "supplierArticle",
        "vendorCode",
    ),
    "quantity": (
        "quantity",
        "qty",
        "count",
    ),
    "row_amount": (
        "retail_amount",
        "retailAmount",
        "sale_amount",
        "saleAmount",
    ),
    "retail_price": (
        "retail_price",
        "retailPrice",
    ),
    "unit_price_discounted": (
        "retail_price_withdisc_rub",
        "retailPriceWithDiscRub",
    ),
    "wb_commission": (
        "ppvz_sales_commission",
        "ppvzSalesCommission",
        "commission_amount",
        "commissionAmount",
        "wb_reward_before_agent",
    ),
    "pvz_compensation": ("pvz_compensation",),
    "payment_services_compensation": (
        "payment_services_compensation",
        "payment_services_compensation_amount",
    ),
    "logistics": (
        "delivery_rub",
        "deliveryRub",
        "logistics",
        "logistics_cost",
        "rebill_logistic_cost",
    ),
    "storage": (
        "storage_fee",
        "storageFee",
        "storage",
    ),
    "penalties": (
        "penalty",
        "penaltyAmount",
        "fine",
    ),
    "payout": (
        "ppvz_for_pay",
        "ppvzForPay",
        "to_pay",
        "toPay",
    ),
}


@dataclass
class FinancialKernelInput:
    """
    Input contract for the future v3 financial kernel (v2 parity target).

    realization_rows:
        Financial rows from WB realization/sales detail dataset.
    tax_rate:
        Tax rate used by v2 formula (default 0.06).
    cogs_rows:
        Optional normalized COGS rows. If missing, fallback/legacy COGS mode may be used later.
    cogs_file_found:
        Optional explicit file status flag for COGS diagnostics parity.
    source_meta:
        Optional source/debug metadata (dates, endpoints, seller, lag).
    """

    realization_rows: List[Dict[str, Any]]
    tax_rate: float = 0.06
    cogs_rows: List[Dict[str, Any]] | None = None
    cogs_file_found: bool | None = None
    source_meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CommissionBreakdown:
    base_commission: float = 0.0
    pvz_compensation: float = 0.0
    payment_services_compensation: float = 0.0
    payment_services_compensation_amount: float = 0.0
    total_commission: float = 0.0


@dataclass
class AccountFinancialTotals:
    rows_count: int = 0
    sales_qty: int = 0
    returns_qty: int = 0
    gross_revenue: float = 0.0
    turnover_wb: float | None = None
    turnover_wb_rows_count: int = 0
    commission: float = 0.0
    logistics: float = 0.0
    storage: float = 0.0
    penalties: float = 0.0
    payout: float = 0.0
    tax_rate: float = 0.06
    tax: float = 0.0
    cogs_total: float = 0.0
    profit: float = 0.0
    margin: float = 0.0


@dataclass
class SKUFinancialRow:
    sales_qty: int = 0
    returns_qty: int = 0
    sales_revenue: float = 0.0
    returns_revenue_est: float = 0.0
    net_revenue: float = 0.0
    commission: float = 0.0
    logistics: float = 0.0
    storage: float = 0.0
    penalties: float = 0.0
    payout: float = 0.0
    tax_alloc: float = 0.0
    cogs: float = 0.0
    profit: float = 0.0
    margin: float = 0.0


@dataclass
class FinancialKernelOutput:
    """
    Output contract for the future v3 financial kernel (v2 parity target).

    On the skeleton step this structure is returned with placeholders only.
    """

    account_financial_totals: AccountFinancialTotals
    sku_financials: Dict[int, SKUFinancialRow] = field(default_factory=dict)
    commission_breakdown: CommissionBreakdown = field(default_factory=CommissionBreakdown)
    cogs_diagnostics: Dict[str, Any] = field(default_factory=dict)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    source_meta: Dict[str, Any] = field(default_factory=dict)
    kernel_status: str = "skeleton"


def as_dict(payload: Mapping[str, Any] | Any) -> Dict[str, Any]:
    if isinstance(payload, dict):
        return dict(payload)
    return {}
