from __future__ import annotations

from wb_api_core.validate_report_snapshot import validate_report_snapshot


def _snapshot() -> dict:
    return {
        "operational_date": "2026-07-27",
        "cabinet_commerce_daily": {
            "available": False,
            "target_date": "2026-07-27",
            "orders_count": None,
            "orders_amount": None,
            "buyouts_count": None,
            "buyouts_amount": None,
        },
        "funnel_daily": {
            "available": False,
            "target_date": "2026-07-27",
        },
        "live_operational": {
            "orders": {
                "available": False,
                "target_date": "2026-07-27",
                "count": None,
                "amount": None,
            },
            "sales": {
                "available": False,
                "target_date": "2026-07-27",
                "count": None,
                "amount": None,
            },
        },
    }


def test_empty_current_day_is_not_reportable() -> None:
    result = validate_report_snapshot(_snapshot())

    assert result["reportable"] is False
    assert result["reason"] == "current_operational_commerce_unavailable"


def test_confirmed_zero_day_is_reportable() -> None:
    snapshot = _snapshot()
    snapshot["cabinet_commerce_daily"].update(
        {
            "available": True,
            "orders_count": 0,
            "orders_amount": 0,
            "buyouts_count": 0,
            "buyouts_amount": 0,
        }
    )

    result = validate_report_snapshot(snapshot)

    assert result["reportable"] is True
    assert result["confirmed_sources"]["cabinet_commerce"] is True


def test_other_day_data_is_not_reportable() -> None:
    snapshot = _snapshot()
    snapshot["live_operational"]["sales"].update(
        {
            "available": True,
            "target_date": "2026-07-26",
            "count": 2,
            "amount": 1899.97,
        }
    )

    assert validate_report_snapshot(snapshot)["reportable"] is False
