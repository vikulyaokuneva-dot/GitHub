from __future__ import annotations

import json
from pathlib import Path

from v3.history.history_store import save_daily_history_snapshot


def test_history_store_writes_canonical_funnel_fields_with_legacy_aliases(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "cabinets" / "seller_001" / "artifacts"
    history_dir = tmp_path / "cabinets" / "seller_001" / "history"
    artifacts_dir.mkdir(parents=True)
    (artifacts_dir / "metrics.json").write_text(
        json.dumps(
            {
                "funnel_daily": {
                    "open_count": 280,
                    "cart_count": 28,
                    "orders_count": 4,
                    "buyouts_count": 0,
                    "orders_amount": 7400,
                    "buyouts_amount": 0,
                }
            }
        ),
        encoding="utf-8",
    )

    result = save_daily_history_snapshot(
        seller_id="seller_001",
        run_date="2026-07-21",
        artifacts_dir=artifacts_dir,
        history_dir=history_dir,
    )
    funnel = result["snapshot_meta"]["kpi"]["funnel"]

    assert funnel["open_count"] == 280
    assert funnel["cart_count"] == 28
    assert funnel["orders_count"] == 4
    assert funnel["buyouts_count"] == 0
    assert funnel["clicks"] == funnel["open_count"]
    assert funnel["cart"] == funnel["cart_count"]
    assert funnel["orders"] == funnel["orders_count"]
    assert funnel["buyouts"] == funnel["buyouts_count"]


def test_history_store_keeps_missing_funnel_values_distinct_from_zero(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "cabinets" / "seller_001" / "artifacts"
    history_dir = tmp_path / "cabinets" / "seller_001" / "history"
    artifacts_dir.mkdir(parents=True)
    (artifacts_dir / "metrics.json").write_text(
        json.dumps({"funnel_daily": {"buyouts_count": 0}}),
        encoding="utf-8",
    )

    result = save_daily_history_snapshot(
        seller_id="seller_001",
        run_date="2026-07-21",
        artifacts_dir=artifacts_dir,
        history_dir=history_dir,
    )
    funnel = result["snapshot_meta"]["kpi"]["funnel"]

    assert funnel["open_count"] is None
    assert funnel["cart_count"] is None
    assert funnel["orders_count"] is None
    assert funnel["buyouts_count"] == 0
