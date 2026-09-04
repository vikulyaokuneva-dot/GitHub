"""Wildberries integration contracts and adapters."""

from .contracts import (
    DuplicateRawObjectError,
    EndpointDataClass,
    EndpointDomain,
    EndpointMetadata,
    FINANCE_DETAIL_ENDPOINT,
    InMemoryRawObjectRepository,
    OperationalDateSemantics,
    PaginationSemantics,
    PayloadKind,
    RawObject,
    RawObjectNotFoundError,
    RawObjectRepository,
    RawObjectType,
    SALES_FUNNEL_PRODUCTS_ENDPOINT,
    TenantAccountScope,
)
from .sqlite_repository import SQLiteRawObjectRepository

__all__ = [
    "DuplicateRawObjectError",
    "EndpointDataClass",
    "EndpointDomain",
    "EndpointMetadata",
    "FINANCE_DETAIL_ENDPOINT",
    "InMemoryRawObjectRepository",
    "OperationalDateSemantics",
    "PaginationSemantics",
    "PayloadKind",
    "RawObject",
    "RawObjectNotFoundError",
    "RawObjectRepository",
    "RawObjectType",
    "SALES_FUNNEL_PRODUCTS_ENDPOINT",
    "SQLiteRawObjectRepository",
    "TenantAccountScope",
]
