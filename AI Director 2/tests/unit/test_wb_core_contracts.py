from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from packages.wb_core.contracts import RawApiEvent, TenantAccountScope


def _event_payload(*, requested_at: datetime, responded_at: datetime) -> dict[str, object]:
    return {
        "scope": TenantAccountScope(tenant_id=uuid4(), account_id=uuid4()),
        "source": "wildberries",
        "endpoint": "/api/analytics/v3/sales-funnel/products",
        "request_fingerprint": "f" * 64,
        "payload_object_uri": "https://objects.example.test/raw/event.json",
        "payload_hash": "a" * 64,
        "schema_version": "analytics-v3",
        "requested_at": requested_at,
        "responded_at": responded_at,
        "http_status": 200,
    }


def test_raw_api_event_accepts_utc_provenance() -> None:
    now = datetime.now(UTC)

    event = RawApiEvent.model_validate(_event_payload(requested_at=now, responded_at=now + timedelta(seconds=1)))

    assert event.scope.tenant_id != event.scope.account_id
    assert event.http_status == 200


def test_raw_api_event_rejects_non_utc_timestamp() -> None:
    naive = datetime(2026, 8, 23, 10, 0)

    with pytest.raises(ValidationError, match="UTC"):
        RawApiEvent.model_validate(_event_payload(requested_at=naive, responded_at=naive))
