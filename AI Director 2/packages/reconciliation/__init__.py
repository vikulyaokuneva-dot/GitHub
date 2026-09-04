"""Deterministic reconciliation contracts for canonical source facts."""

from .contracts import (
    CanonicalCohortMetricFact,
    CanonicalSalesConfirmationFact,
    ReconciliationDiagnostic,
    ReconciliationIdentity,
    ReconciliationLagState,
    ReconciliationResult,
    ReconciliationStatus,
)
from .service import reconcile_sales_funnel_products

__all__ = [
    "CanonicalCohortMetricFact",
    "CanonicalSalesConfirmationFact",
    "ReconciliationDiagnostic",
    "ReconciliationIdentity",
    "ReconciliationLagState",
    "ReconciliationResult",
    "ReconciliationStatus",
    "reconcile_sales_funnel_products",
]
