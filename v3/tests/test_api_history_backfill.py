from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from v3.history import api_history_backfill
from v3.history.history_store import load_history_index


class _FakeClient:
    pass


def test_backfills_previous_operational_day_once(monkeypatch, tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_load(client, target_date: str, **kwargs):
        calls.append(target_date)
        return {
            "rows_raw": [
                {
                    "product": {"nmId": 739377515},
                    "statistic": {
                        "selected": {
                            "openCount": 10,
                            "cartCount": 4,
                            "orderCount": 2,
                            "orderSum": "1500.25",
                            "buyoutCount": 1,
                            "buyoutSum": "1000.00",
                        }
                    },
                },
                {
                    "product": {"nmId": 453526507},
                    "statistic": {
                        "selected": {
                            "openCount": 5,
                            "cartCount": 1,
                            "orderCount": 1,
                            "orderSum": "400.00",
                            "buyoutCount": 1,
                            "buyoutSum": "400.00",
                        }
                    },
                },
            ],
            "debug": {"success": True, "rows_loaded": 2},
        }

    monkeypatch.setattr(api_history_backfill, "load_cabinet_commerce", fake_load)
    now = datetime(2026, 7, 23, 8, 0, tzinfo=ZoneInfo("Europe/Moscow"))

    first = api_history_backfill.backfill_previous_operational_day(
        seller_id="seller_001",
        run_date="2026-07-23",
        repo_root=tmp_path,
        client=_FakeClient(),
        now=now,
    )
    second = api_history_backfill.backfill_previous_operational_day(
        seller_id="seller_001",
        run_date="2026-07-23",
        repo_root=tmp_path,
        client=_FakeClient(),
        now=now,
    )

    assert first["status"] == "backfilled"
    assert first["target_date"] == "2026-07-21"
    assert second["status"] == "skipped_existing"
    assert calls == ["2026-07-21"]

    history_dir = tmp_path / "cabinets" / "seller_001" / "history"
    index = load_history_index(history_dir)
    snapshot = index["snapshots"][0]
    assert snapshot["date"] == "2026-07-21"
    assert snapshot["kpi"]["revenue"] == "1400.00"
    assert snapshot["kpi"]["orders_amount"] == "1900.25"
    assert snapshot["kpi"]["profit"] is None
    assert snapshot["kpi"]["ads_spend"] is None
    assert snapshot["kpi"]["funnel"]["open_count"] == 15
    assert snapshot["kpi"]["funnel"]["buyouts_count"] == 2
    assert snapshot["source"]["api_version"] == "v3"

    raw_path = history_dir / "api_backfill" / "2026-07-21" / "sales_funnel_api_v3.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    assert raw["target_date"] == "2026-07-21"
    assert raw["fetched_at_utc"].endswith("+00:00")
    assert len(raw["rows"]) == 2


def test_source_failure_does_not_create_history(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        api_history_backfill,
        "load_cabinet_commerce",
        lambda *args, **kwargs: {
            "rows_raw": [],
            "debug": {"success": False, "error_text": "rate limited"},
        },
    )

    result = api_history_backfill.backfill_previous_operational_day(
        seller_id="seller_001",
        run_date="2026-07-22",
        repo_root=tmp_path,
        client=_FakeClient(),
        now=datetime(2026, 7, 23, 8, 0, tzinfo=ZoneInfo("Europe/Moscow")),
    )

    assert result["status"] == "source_unavailable"
    assert result["target_date"] == "2026-07-21"
    assert not (tmp_path / "cabinets" / "seller_001" / "history" / "history_index.json").exists()
