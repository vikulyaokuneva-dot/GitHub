"""Reproducible read-only WB Core scenario used to exercise the raw boundary."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Final, cast
from uuid import UUID

from .contracts import (
    InMemoryRawObjectRepository,
    RawObject,
    RawPayload,
    SALES_FUNNEL_PRODUCTS_ENDPOINT,
    TenantAccountScope,
)

SYNTHETIC_TENANT_ID: Final = UUID("00000000-0000-0000-0000-000000000101")
SYNTHETIC_ACCOUNT_ID: Final = UUID("00000000-0000-0000-0000-000000000201")
SYNTHETIC_OBJECT_ID: Final = "5bca8eec1d936abf6edbe3db5d3aa72d5462dc1bc6ebd55adf817ea4d8d3b7ef"
SYNTHETIC_OPERATIONAL_DATE: Final = date(2026, 8, 20)
SYNTHETIC_RETRIEVED_AT: Final = datetime(2026, 8, 24, 10, 30, tzinfo=UTC)


def synthetic_scope() -> TenantAccountScope:
    """Return the fixed scope for the synthetic, credential-free scenario."""

    return TenantAccountScope(tenant_id=SYNTHETIC_TENANT_ID, account_id=SYNTHETIC_ACCOUNT_ID)


def synthetic_request_scope() -> dict[str, Any]:
    """Return a raw request description without transport headers or credentials."""

    return {
        "selected_period": {
            "start": SYNTHETIC_OPERATIONAL_DATE.isoformat(),
            "end": SYNTHETIC_OPERATIONAL_DATE.isoformat(),
        },
        "limit": 1000,
        "offset": 0,
    }


def synthetic_sales_funnel_payload() -> RawPayload:
    """Return a minimal raw object payload; no normalization is performed here."""

    return {
        "data": {
            "products": [
                {
                    "product": {"nmId": 1001, "vendorCode": "SYNTH-ART-1001"},
                    "statistic": {
                        "selected": {
                            "period": {
                                "start": SYNTHETIC_OPERATIONAL_DATE.isoformat(),
                                "end": SYNTHETIC_OPERATIONAL_DATE.isoformat(),
                            },
                            "openCount": 42,
                            "cartCount": 7,
                            "orderCount": 2,
                            "orderSum": "1234.56",
                            "currency": "RUB",
                        }
                    },
                }
            ]
        }
    }


def synthetic_raw_object() -> RawObject:
    """Build the raw object for one deterministic operational endpoint scenario."""

    return RawObject(
        object_id=SYNTHETIC_OBJECT_ID,
        scope=synthetic_scope(),
        endpoint=SALES_FUNNEL_PRODUCTS_ENDPOINT,
        object_type=SALES_FUNNEL_PRODUCTS_ENDPOINT.object_type,
        source=SALES_FUNNEL_PRODUCTS_ENDPOINT.source,
        retrieved_at=SYNTHETIC_RETRIEVED_AT,
        operational_date=SYNTHETIC_OPERATIONAL_DATE,
        request_scope=synthetic_request_scope(),
        payload=synthetic_sales_funnel_payload(),
        schema_version=SALES_FUNNEL_PRODUCTS_ENDPOINT.schema_version,
    )


def synthetic_repository() -> InMemoryRawObjectRepository:
    """Populate a fresh in-memory repository for the complete Stage 2 path."""

    repository = InMemoryRawObjectRepository()
    repository.save(synthetic_raw_object())
    return repository
