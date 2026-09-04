from __future__ import annotations

from datetime import date
from decimal import Decimal

from packages.data.normalization import normalize_orders
from packages.operational.service import build_operational_daily_read_model
from packages.reports.contracts import ReportMetric
from packages.reports.renderers import render_email_html, render_email_text, render_pdf
from packages.reports.service import build_report_payload
from packages.wb_core.contracts import ORDERS_ENDPOINT, RawObject
from packages.wb_core.synthetic_scenario import SYNTHETIC_RETRIEVED_AT, synthetic_scope


def _payload() -> object:
    raw = RawObject(
        object_id="8" * 64, scope=synthetic_scope(), endpoint=ORDERS_ENDPOINT, object_type=ORDERS_ENDPOINT.object_type,
        source="wildberries", retrieved_at=SYNTHETIC_RETRIEVED_AT, operational_date=date(2026, 8, 20),
        request_scope={"dateFrom": "2026-08-20"}, schema_version=ORDERS_ENDPOINT.schema_version,
        payload={"data": [{"srid": "order-1", "nmId": 1001, "quantity": "2", "priceWithDisc": "100.00", "isCancel": False, "date": "2026-08-20"}]},
    )
    return build_report_payload(operational=build_operational_daily_read_model(orders=normalize_orders(raw)))


def test_outputs_are_deterministic_and_read_only() -> None:
    payload = _payload()
    assert render_email_text(payload) == render_email_text(payload)
    assert render_email_html(payload) == render_email_html(payload)
    assert render_pdf(payload) == render_pdf(payload)


def test_outputs_contain_payload_values_without_calculating_metrics() -> None:
    payload = _payload()
    assert "orders: 2" in render_email_text(payload)
    assert "<td>orders</td><td>2</td><td>complete</td>" in render_email_html(payload)
    assert render_pdf(payload).startswith(b"%PDF")


def test_outputs_render_metric_states_without_missing_zero_conversion() -> None:
    payload = _payload().model_copy(
        update={
            "metrics": (
                ReportMetric(key="normal_value", owner="test", value=Decimal("12.30"), status="available"),
                ReportMetric(key="zero_value", owner="test", value=Decimal("0"), status="available"),
                ReportMetric(key="missing_value", owner="test", value=None, status="missing"),
                ReportMetric(key="unavailable_value", owner="test", value=None, status="unavailable"),
                ReportMetric(key="unresolved_value", owner="test", value=None, status="unresolved"),
                ReportMetric(key="conflict_value", owner="test", value=None, status="conflict"),
            )
        }
    )
    text = render_email_text(payload)
    html = render_email_html(payload)

    assert render_email_text(payload) == render_email_text(payload)
    assert "normal_value: 12.30" in text
    assert "zero_value: 0" in text
    assert "missing_value: Нет данных" in text
    assert "unavailable_value: Недоступно" in text
    assert "unresolved_value: Не определено" in text
    assert "conflict_value: Конфликт данных" in text
    assert "missing_value: Нет данных [missing]" not in text
    assert "<td>missing_value</td><td>Нет данных</td><td>missing</td>" in html
