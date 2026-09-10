"""Regression: WB statistics windows must be attributed by event date.

statistics-api /supplier/orders and /supplier/sales return rows filtered by
``lastChangeDate >= dateFrom``, so one daily RawObject legitimately contains
rows from adjacent days. Counting the whole window inflates the day; STAGE
20.22 pins the rule: an orders/sales row belongs to the day it happened
(its own ``date``), the raw window stays untouched, and unattributable rows
are not counted either.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from packages.data.normalization import NormalizationError, normalize_orders, normalize_sales
from packages.wb_core.contracts import (
    ORDERS_ENDPOINT,
    SALES_ENDPOINT,
    EndpointMetadata,
    RawObject,
    TenantAccountScope,
)

DAY = date(2026, 9, 2)
RETRIEVED_AT = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


def _scope() -> TenantAccountScope:
    return TenantAccountScope(tenant_id=uuid4(), account_id=uuid4())


def _raw(endpoint: EndpointMetadata, payload: dict[str, Any] | list[Any]) -> RawObject:
    import hashlib
    import json

    payload_bytes = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    scope = _scope()
    return RawObject(
        object_id=hashlib.sha256(payload_bytes).hexdigest(),
        scope=scope,
        endpoint=endpoint,
        object_type=endpoint.object_type,
        source=endpoint.source,
        retrieved_at=RETRIEVED_AT,
        operational_date=DAY,
        request_scope={"dateFrom": DAY.isoformat()},
        payload=payload,
        raw_payload_bytes=payload_bytes,
        schema_version=endpoint.schema_version,
    )


def _row(order_day: str) -> dict[str, object]:
    return {
        "srid": f"row-{order_day}",
        "nmId": 1001,
        "supplierArticle": "ART-1",
        "quantity": "2",
        "priceWithDisc": "100.00",
        "isCancel": False,
        "date": f"{order_day}T12:00:00",
    }


def test_orders_window_only_counts_rows_of_the_operational_day() -> None:
    raw = _raw(
        ORDERS_ENDPOINT,
        {
            "data": [
                _row("2026-08-22"),  # order created earlier, changed inside window
                _row("2026-09-02"),  # the operational day itself
                _row("2026-09-03"),  # next day inside the same window
            ]
        },
    )

    records = normalize_orders(raw)

    assert [record.source_event_id for record in records] == ["row-2026-09-02"]
    assert records[0].operational_date == DAY
    assert records[0].quantity == Decimal("2")


def test_sales_window_only_counts_rows_of_the_operational_day() -> None:
    raw = _raw(
        SALES_ENDPOINT,
        {"data": [_row("2026-09-01"), _row("2026-09-02"), _row("2026-09-05")]},
    )

    records = normalize_sales(raw)

    assert [record.source_event_id for record in records] == ["row-2026-09-02"]


def test_row_without_parseable_event_date_is_not_attributed_to_the_day() -> None:
    missing = {"srid": "no-date", "nmId": 1001, "quantity": "1", "priceWithDisc": "10.00"}
    malformed = {**_row("bad"), "date": "not-a-date"}
    raw = _raw(ORDERS_ENDPOINT, {"data": [missing, malformed, _row("2026-09-02")]})

    records = normalize_orders(raw)

    assert [record.source_event_id for record in records] == ["row-2026-09-02"]


def test_structurally_invalid_row_still_raises_from_the_builder() -> None:
    raw = _raw(ORDERS_ENDPOINT, {"data": ["scalar-row"]})

    with pytest.raises(NormalizationError):
        normalize_orders(raw)
