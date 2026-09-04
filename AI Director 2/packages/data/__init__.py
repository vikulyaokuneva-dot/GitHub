"""Canonical data contracts and source normalizers."""

from .canonical import (
    CanonicalCurrency,
    CanonicalFinanceDetailRecord,
    CanonicalFieldInput,
    CanonicalInputState,
    CanonicalSalesFunnelProduct,
    CanonicalSourceMetadata,
    CanonicalSourceMoney,
    CanonicalValueKind,
    FinancialRecordClassification,
)
from .normalization import (
    NormalizationError,
    FinanceDetailNormalizer,
    RawObjectNormalizer,
    SalesFunnelProductsNormalizer,
    normalize_sales_funnel_products,
    normalize_finance_detail,
)

__all__ = [
    "CanonicalCurrency",
    "CanonicalFinanceDetailRecord",
    "CanonicalFieldInput",
    "CanonicalInputState",
    "CanonicalSalesFunnelProduct",
    "CanonicalSourceMetadata",
    "CanonicalSourceMoney",
    "CanonicalValueKind",
    "FinancialRecordClassification",
    "NormalizationError",
    "FinanceDetailNormalizer",
    "RawObjectNormalizer",
    "SalesFunnelProductsNormalizer",
    "normalize_sales_funnel_products",
    "normalize_finance_detail",
]
