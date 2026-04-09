from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from audit.audit_facts_builder import _build_local_orders_insights
from audit.audit_loader import parse_orders_file_with_diagnostics


def test_parse_orders_feed_collects_buyout_diagnostics(tmp_path: Path) -> None:
    path = tmp_path / "orders_feed.xlsx"
    df = pd.DataFrame(
        [
            {"nmId": 101, "date": "2026-04-04", "region": "Москва", "city": "Москва", "buyout": True, "quantity": 1},
            {"nmId": 102, "date": "2026-04-04", "region": "", "city": "", "buyout": True, "quantity": 1},
            {"nmId": 103, "date": "2026-04-04", "region": "Казань", "city": "Казань", "buyout": False, "quantity": 1},
        ]
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="all orders", index=False)

    rows, diag = parse_orders_file_with_diagnostics(str(path))

    assert diag.get("status") == "ok"
    assert int(diag.get("buyouts_rows_total") or 0) == 2
    assert int(diag.get("buyouts_rows_without_geo") or 0) == 1
    assert int(diag.get("buyouts_units_total") or 0) == 2
    assert int(diag.get("buyouts_units_without_geo") or 0) == 1
    assert any(int((row or {}).get("buyoutCount") or 0) > 0 for row in rows)


def test_local_orders_insights_uses_only_buyouts_for_regions() -> None:
    payload = _build_local_orders_insights(
        orders_rows=[
            {"nmId": 111, "region": "Москва", "city": "Москва", "buyout": True},
            {"nmId": 111, "region": "", "city": "", "buyout": True},
            {"nmId": 222, "region": "Санкт-Петербург", "city": "Санкт-Петербург", "orders": 7, "buyout": False},
        ],
        funnel_rows=[],
        stocks_rows=[],
    )

    by_region = payload.get("by_region") or []
    diagnostics = payload.get("diagnostics") or {}

    assert payload.get("available") is True
    assert int(payload.get("total_buyouts") or 0) == 1
    assert len(by_region) == 1
    assert str((by_region[0] or {}).get("region") or "") == "Москва"
    assert int((by_region[0] or {}).get("buyouts") or 0) == 1
    assert all(str((item or {}).get("region") or "") != "Санкт-Петербург" for item in by_region)
    assert int(diagnostics.get("buyout_rows_scanned") or 0) == 2
    assert int(diagnostics.get("buyout_rows_without_geo") or 0) == 1
    assert int(diagnostics.get("region_buyouts_sum") or 0) == 1
    assert bool(diagnostics.get("region_buyouts_match_total")) is True
