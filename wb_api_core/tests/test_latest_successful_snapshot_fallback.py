from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

from report_v2.builders.report_payload_builder import build_report_payload_v2
from wb_api_core.artifacts import latest_successful_snapshot_path
from wb_api_core.run_daily import run_daily


def _endpoint(rows: list[dict], *, success: bool = True, status_code: int = 200, error_text: str = "") -> dict:
    return {
        "rows_raw": rows,
        "debug": {
            "success": success,
            "status_code": status_code,
            "attempts": 1,
            "rows_loaded": len(rows),
            "error_text": error_text,
            "final_failure_reason": error_text,
        },
    }


def _successful_raw_bundle(day: str = "2026-04-21") -> dict:
    return {
        "cabinet_commerce": _endpoint([]),
        "finance_final": _endpoint([]),
        "orders": _endpoint(
            [
                {
                    "date": f"{day}T09:00:00",
                    "lastChangeDate": f"{day}T09:05:00",
                    "srid": "order-1",
                    "nmId": 1001,
                    "supplierArticle": "A-100",
                    "quantity": 1,
                    "priceWithDisc": 100.0,
                }
            ]
        ),
        "sales": _endpoint(
            [
                {
                    "date": f"{day}T12:00:00",
                    "saleID": "sale-1",
                    "nmId": 1001,
                    "supplierArticle": "A-100",
                    "quantity": 1,
                    "priceWithDisc": 90.0,
                }
            ]
        ),
        "stocks": _endpoint(
            [
                {
                    "lastChangeDate": f"{day}T08:00:00",
                    "nmId": 1001,
                    "supplierArticle": "A-100",
                    "quantityFull": 7,
                }
            ]
        ),
    }


def _rate_limited_raw_bundle() -> dict:
    bundle = _successful_raw_bundle()
    for key in ("orders", "sales", "stocks"):
        bundle[key] = _endpoint(
            [],
            success=False,
            status_code=429,
            error_text="429 Too Many Requests",
        )
    return bundle


def _run_with_bundle(tmp_path: Path, raw_bundle: dict, *, run_date: str = "2026-04-21") -> dict:
    with patch.dict(os.environ, {"WB_API_TOKEN": "token", "TZ": "Europe/Moscow"}, clear=False):
        with patch("wb_api_core.run_daily.load_bundle", return_value=raw_bundle):
            return run_daily(seller="seller_001", run_date=run_date, repo_root=str(tmp_path))


def test_successful_run_writes_latest_successful_snapshot(tmp_path: Path) -> None:
    result = _run_with_bundle(tmp_path, _successful_raw_bundle())

    cache_path = Path(latest_successful_snapshot_path(str(tmp_path), "seller_001"))
    assert cache_path.exists()

    cached = json.loads(cache_path.read_text(encoding="utf-8"))
    assert cached["operational_date"] == result["operational_date"]
    assert cached["live_operational"]["orders"]["count"] == 1.0
    assert cached["live_operational"]["sales"]["amount"] == 90.0
    assert cached["live_operational"]["stocks"]["total_units"] == 7.0


def test_rate_limited_run_does_not_use_live_cache_from_another_day(tmp_path: Path) -> None:
    _run_with_bundle(tmp_path, _successful_raw_bundle("2026-04-21"), run_date="2026-04-21")

    result = _run_with_bundle(tmp_path, _rate_limited_raw_bundle(), run_date="2026-04-22")
    snapshot = result["snapshot"]
    debug = result["debug"]

    orders = snapshot["live_operational"]["orders"]
    sales = snapshot["live_operational"]["sales"]
    stocks = snapshot["live_operational"]["stocks"]

    assert orders["available"] is False
    assert orders["count"] is None
    assert "stale" not in orders
    assert sales["available"] is False
    assert stocks["available"] is False

    assert debug["endpoints"]["orders"]["status_code"] == 429
    assert debug["endpoints"]["sales"]["status_code"] == 429
    assert debug["endpoints"]["stocks"]["status_code"] == 429
    assert debug["cache_fallback"] == {}
    assert not any(
        item.get("code") == "orders_latest_successful_cache_fallback"
        for item in debug["warnings"]
    )

    cache_path = Path(latest_successful_snapshot_path(str(tmp_path), "seller_001"))
    cached_after_fallback = json.loads(cache_path.read_text(encoding="utf-8"))
    assert cached_after_fallback["operational_date"] == "2026-04-21"
    assert "stale" not in cached_after_fallback["live_operational"]["orders"]


def test_rate_limited_run_may_use_cache_from_same_day(tmp_path: Path) -> None:
    _run_with_bundle(tmp_path, _successful_raw_bundle("2026-04-21"), run_date="2026-04-21")

    result = _run_with_bundle(tmp_path, _rate_limited_raw_bundle(), run_date="2026-04-21")

    orders = result["snapshot"]["live_operational"]["orders"]
    assert orders["available"] is True
    assert orders["count"] == 1.0
    assert orders["stale"] is True
    assert orders["source_actual_date"] == "2026-04-21"
    assert result["debug"]["cache_fallback"]["latest_successful_snapshot_used"] is True


def test_report_payload_keeps_other_day_cache_out_of_report(tmp_path: Path) -> None:
    _run_with_bundle(tmp_path, _successful_raw_bundle("2026-04-21"), run_date="2026-04-21")
    result = _run_with_bundle(tmp_path, _rate_limited_raw_bundle(), run_date="2026-04-22")

    payload = build_report_payload_v2(result["snapshot"], debug=result["debug"])

    assert payload["live_operational"]["orders"]["available"] is False
    assert payload["live_operational"]["orders"]["stale"] is False

    diagnostic_flags = {item["name"]: item for item in payload["diagnostics"]["source_flags"]}
    assert diagnostic_flags["live_operational.orders.stale"]["value"] == "false"


def test_rate_limited_run_without_cache_keeps_no_data(tmp_path: Path) -> None:
    result = _run_with_bundle(tmp_path, _rate_limited_raw_bundle(), run_date="2026-04-22")

    assert result["snapshot"]["live_operational"]["orders"]["available"] is False
    assert "stale" not in result["snapshot"]["live_operational"]["orders"]
    assert result["debug"]["endpoints"]["orders"]["status_code"] == 429
    assert result["debug"]["cache_fallback"] == {}
