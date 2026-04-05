from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from audit.audit_facts_builder import _derive_audit_period


def _base_args() -> dict:
    return {
        "period_label": "",
        "report_date": dt.date(2026, 4, 5),
        "selected_files": {},
        "parse_diagnostics": {},
        "period_days": 7,
    }


def test_audit_period_prefers_funnel_dates() -> None:
    args = _base_args()
    period = _derive_audit_period(
        **args,
        funnel_rows=[{"date": "2026-04-01"}, {"date": "2026-04-07"}],
        orders_rows=[{"date": "2026-03-20"}, {"date": "2026-03-31"}],
        finance_rows=[{"date": "2026-01-01"}, {"date": "2026-01-31"}],
    )
    assert period["date_from"] == "2026-04-01"
    assert period["date_to"] == "2026-04-07"
    assert period["source"] == "funnel"
    assert int(period["days"]) == 7
    assert period["audit_kind"] == "Недельный аудит"


def test_audit_period_falls_back_to_orders_then_finance() -> None:
    args = _base_args()
    period_from_orders = _derive_audit_period(
        **args,
        funnel_rows=[],
        orders_rows=[{"date": "02.04.2026"}, {"date": "05.04.2026"}],
        finance_rows=[{"date": "2026-03-01"}, {"date": "2026-03-31"}],
    )
    assert period_from_orders["date_from"] == "2026-04-02"
    assert period_from_orders["date_to"] == "2026-04-05"
    assert period_from_orders["source"] == "orders"

    period_from_finance = _derive_audit_period(
        **args,
        funnel_rows=[],
        orders_rows=[],
        finance_rows=[{"date": "2026-04-03"}, {"date": "2026-04-05"}],
    )
    assert period_from_finance["date_from"] == "2026-04-03"
    assert period_from_finance["date_to"] == "2026-04-05"
    assert period_from_finance["source"] == "finance"


def test_conflicting_sources_use_narrowest_range() -> None:
    args = _base_args()
    period = _derive_audit_period(
        **args,
        funnel_rows=[{"date": "2026-03-01"}, {"date": "2026-03-31"}],
        orders_rows=[{"date": "2026-03-10"}, {"date": "2026-03-15"}],
        finance_rows=[{"date": "2026-02-01"}, {"date": "2026-04-01"}],
    )
    assert period["date_from"] == "2026-03-10"
    assert period["date_to"] == "2026-03-15"
    assert period["source"] == "orders"
    assert int(period["days"]) == 6
    assert period["audit_kind"] == "Недельный аудит"


def test_long_period_is_periodic_audit() -> None:
    args = _base_args()
    period = _derive_audit_period(
        **args,
        funnel_rows=[],
        orders_rows=[],
        finance_rows=[{"date": "2026-03-01"}, {"date": "2026-03-20"}],
    )
    assert int(period["days"]) == 20
    assert period["audit_kind"] == "Периодический аудит"

