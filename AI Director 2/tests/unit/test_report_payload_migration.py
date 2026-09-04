from __future__ import annotations

from datetime import date
from decimal import Decimal

from packages.data.normalization import normalize_orders
from packages.operational.service import build_operational_daily_read_model
from packages.reports.service import build_report_payload
from packages.wb_core.contracts import ORDERS_ENDPOINT, RawObject
from packages.wb_core.synthetic_scenario import SYNTHETIC_RETRIEVED_AT, synthetic_scope


def _operational() -> object:
    raw = RawObject(
        object_id="9" * 64, scope=synthetic_scope(), endpoint=ORDERS_ENDPOINT, object_type=ORDERS_ENDPOINT.object_type,
        source="wildberries", retrieved_at=SYNTHETIC_RETRIEVED_AT, operational_date=date(2026, 8, 20),
        request_scope={"dateFrom": "2026-08-20"}, schema_version=ORDERS_ENDPOINT.schema_version,
        payload={"data": [{"srid": "order-1", "nmId": 1001, "quantity": "2", "priceWithDisc": "100.00", "isCancel": False, "date": "2026-08-20"}]},
    )
    return build_operational_daily_read_model(orders=normalize_orders(raw))


def test_report_payload_only_projects_domain_metrics_with_one_owner() -> None:
    payload = build_report_payload(operational=_operational(), diagnostics=("source freshness is operational",))
    metric_map = {metric.key: metric for metric in payload.metrics}

    assert metric_map["orders"].owner == "operational"
    assert metric_map["orders"].value == Decimal("2")
    assert metric_map["cohort_buyouts"].value is None
    assert metric_map["cohort_buyouts"].status == "missing"
    assert all(metric.owner != "reports" for metric in payload.metrics)
    assert payload.operational_date == date(2026, 8, 20)
