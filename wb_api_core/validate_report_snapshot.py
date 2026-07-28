from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _has_value(block: Dict[str, Any], fields: tuple[str, ...]) -> bool:
    return any(block.get(field) is not None for field in fields)


def validate_report_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    operational_date = str(snapshot.get("operational_date") or "").strip()
    cabinet = _safe_dict(snapshot.get("cabinet_commerce_daily"))
    funnel = _safe_dict(snapshot.get("funnel_daily"))
    live = _safe_dict(snapshot.get("live_operational"))
    live_orders = _safe_dict(live.get("orders"))
    live_sales = _safe_dict(live.get("sales"))

    cabinet_confirmed = (
        bool(cabinet.get("available", False))
        and str(cabinet.get("target_date") or "").strip() == operational_date
        and _has_value(
            cabinet,
            ("orders_count", "orders_amount", "buyouts_count", "buyouts_amount"),
        )
    )
    funnel_confirmed = (
        bool(funnel.get("available", False))
        and str(funnel.get("target_date") or "").strip() == operational_date
        and _has_value(
            funnel,
            ("orders_count", "orders_amount", "buyouts_count", "buyouts_amount"),
        )
    )
    live_orders_confirmed = (
        bool(live_orders.get("available", False))
        and str(live_orders.get("target_date") or "").strip() == operational_date
        and _has_value(live_orders, ("count", "amount"))
    )
    live_sales_confirmed = (
        bool(live_sales.get("available", False))
        and str(live_sales.get("target_date") or "").strip() == operational_date
        and _has_value(live_sales, ("count", "amount"))
    )
    sources = {
        "cabinet_commerce": cabinet_confirmed,
        "funnel_lower": funnel_confirmed,
        "live_orders": live_orders_confirmed,
        "live_sales": live_sales_confirmed,
    }
    reportable = any(sources.values())
    return {
        "reportable": reportable,
        "operational_date": operational_date,
        "confirmed_sources": sources,
        "reason": "" if reportable else "current_operational_commerce_unavailable",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate that a daily core snapshot contains current commerce data."
    )
    parser.add_argument("--snapshot", required=True)
    args = parser.parse_args()

    snapshot_path = Path(args.snapshot)
    with snapshot_path.open("r", encoding="utf-8-sig") as stream:
        snapshot = json.load(stream)
    if not isinstance(snapshot, dict):
        raise SystemExit("snapshot must contain a JSON object")

    result = validate_report_snapshot(snapshot)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if not result["reportable"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
